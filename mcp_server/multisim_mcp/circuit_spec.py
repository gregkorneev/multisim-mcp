"""Codex-to-MCP contract for reconstructing supported circuits from images."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from .eda_core import CircuitComponent, CircuitDesign
from .spice_adapter import circuit_design_to_spice


CIRCUIT_SPEC_VERSION: Final = "0.1"
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_NODE = re.compile(r"^(?:0|[A-Za-z][A-Za-z0-9_-]{0,31})$")
_NUMBER = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-zµμΩ]*)$")
_SCALES = {
    "": Decimal(1), "t": Decimal("1e12"), "g": Decimal("1e9"),
    "meg": Decimal("1e6"), "k": Decimal("1e3"), "m": Decimal("1e-3"),
    "u": Decimal("1e-6"), "µ": Decimal("1e-6"), "μ": Decimal("1e-6"),
    "n": Decimal("1e-9"), "p": Decimal("1e-12"), "f": Decimal("1e-15"),
}

# Terminal order is also the SPICE node order. Source positive is node 1.
COMPONENT_REGISTRY: Final[dict[str, dict[str, Any]]] = {
    "resistor": {"kind": "R", "terminals": ("1", "2"), "unit": "ohm", "required_value": True},
    "capacitor": {"kind": "C", "terminals": ("1", "2"), "unit": "F", "required_value": True},
    "inductor": {"kind": "L", "terminals": ("1", "2"), "unit": "H", "required_value": True},
    "dc_voltage_source": {"kind": "V", "terminals": ("positive", "negative"), "native_terminals": {"positive": "2", "negative": "1"}, "unit": "V", "required_value": True},
    "dc_current_source": {"kind": "I", "terminals": ("positive", "negative"), "native_terminals": {"positive": "2", "negative": "1"}, "unit": "A", "required_value": True},
    "diode": {"kind": "D", "ref_prefix": "D", "terminals": ("anode", "cathode"), "native_terminals": {"anode": "1", "cathode": "2"}, "model_required": True, "models": ("1N4001", "1N4001GP", "D1N4001GP")},
    "npn_bjt": {"kind": "QNPN", "ref_prefix": "Q", "terminals": ("collector", "base", "emitter"), "native_terminals": {"collector": "2", "base": "1", "emitter": "3"}, "model_required": True, "models": ("2N3904",)},
    "pnp_bjt": {"kind": "QPNP", "ref_prefix": "Q", "terminals": ("collector", "base", "emitter"), "native_terminals": {"collector": "2", "base": "1", "emitter": "3"}, "model_required": True, "models": ("2N3906",)},
    "ideal_opamp": {"kind": "OPAMP5", "ref_prefix": "X", "terminals": ("input_positive", "input_negative", "positive_supply", "negative_supply", "output"), "native_terminals": {"input_positive": "1", "input_negative": "2", "positive_supply": "4", "negative_supply": "5", "output": "3"}, "model_required": False, "default_model": "OPAMP5", "models": ("OPAMP5", "IDEALOPAMP")},
    "ground": {"kind": "GND", "terminals": ("0",), "unit": "", "required_value": False},
}

_TOP_FIELDS = frozenset({"schema_version", "title", "units", "components", "nets", "connections", "junctions", "wire_waypoints", "uncertainties"})
_COMPONENT_FIELDS = frozenset({"id", "type", "value", "model", "terminals", "position", "rotation", "mirror", "polarity"})


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scalar(value: object, unit: str, path: str) -> tuple[str, Decimal]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be an engineering value string")
    match = _NUMBER.fullmatch(value.strip().replace(" ", ""))
    if not match:
        raise ValueError(f"{path} must be a numeric value with an optional engineering suffix and {unit}")
    try:
        number = Decimal(match.group(1))
        suffix = match.group(2)
        suffix_lower = suffix.casefold()
        unit_lower = unit.casefold()
        scale_suffix = suffix_lower
        unit_aliases = {unit_lower}
        if unit_lower == "ohm":
            unit_aliases.add("ω")
        matched_unit = next((candidate for candidate in sorted(unit_aliases, key=len, reverse=True) if suffix_lower.endswith(candidate)), None)
        if matched_unit:
            scale_suffix = suffix_lower[: -len(matched_unit)]
        elif unit_lower and suffix and not suffix_lower[-1:].isdigit() and suffix_lower not in _SCALES:
            raise ValueError(f"{path} unit must be {unit}")
        if scale_suffix not in _SCALES:
            raise ValueError(f"{path} has an unsupported engineering suffix")
        number *= _SCALES[scale_suffix]
    except (InvalidOperation, ArithmeticError) as exc:
        raise ValueError(f"{path} must be finite") from exc
    if not number.is_finite():
        raise ValueError(f"{path} must be finite")
    if unit in {"ohm", "F", "H"} and number <= 0:
        raise ValueError(f"{path} must be greater than zero")
    # Keep a deterministic, plain SPICE numeric token; source signs are retained.
    return format(number.normalize(), "f"), number


def _object(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return value


def _point(value: object, path: str) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"x", "y"}:
        raise ValueError(f"{path} must contain x and y")
    coords: list[float] = []
    for key in ("x", "y"):
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise ValueError(f"{path}.{key} must be a finite number")
        coords.append(float(item))
    return coords


def validate_circuit_spec(spec: object) -> dict[str, Any]:
    """Validate and compile a CircuitSpec without COM, file access, or image handling."""
    data = _object(spec, "spec")
    unknown = set(data) - _TOP_FIELDS
    if unknown:
        raise ValueError(f"spec contains unknown fields: {sorted(unknown)}")
    if data.get("schema_version") != CIRCUIT_SPEC_VERSION:
        raise ValueError(f"spec.schema_version must be {CIRCUIT_SPEC_VERSION!r}")
    title = data.get("title", "Image-derived circuit")
    if not isinstance(title, str) or not title.strip() or len(title) > 200 or "\x00" in title:
        raise ValueError("spec.title must be non-empty text of at most 200 characters")
    units = data.get("units", {"length": "multisim-grid", "value": "SI"})
    if units != {"length": "multisim-grid", "value": "SI"}:
        raise ValueError("spec.units must be {'length': 'multisim-grid', 'value': 'SI'}")
    raw_components = data.get("components")
    raw_nets = data.get("nets")
    if not isinstance(raw_components, list) or not raw_components:
        raise ValueError("spec.components must be a non-empty array")
    if len(raw_components) > 512:
        raise ValueError("spec.components exceeds 512 entries")
    if not isinstance(raw_nets, list) or not raw_nets:
        raise ValueError("spec.nets must be a non-empty array")

    components: dict[str, dict[str, Any]] = {}
    expected_terminals: set[str] = set()
    native_terminals: dict[str, dict[str, str]] = {}
    circuit_components: list[CircuitComponent] = []
    for index, raw in enumerate(raw_components):
        path = f"spec.components[{index}]"
        item = _object(raw, path)
        extra = set(item) - _COMPONENT_FIELDS
        if extra:
            raise ValueError(f"{path} contains unknown fields: {sorted(extra)}")
        ref = item.get("id")
        kind_name = item.get("type")
        if not isinstance(ref, str) or not _ID.fullmatch(ref):
            raise ValueError(f"{path}.id must be a SPICE-compatible identifier")
        if ref.lower() in {key.lower() for key in components}:
            raise ValueError(f"duplicate component id: {ref}")
        if not isinstance(kind_name, str) or kind_name not in COMPONENT_REGISTRY:
            raise ValueError(f"{path}.type is unsupported: {kind_name!r}")
        definition = COMPONENT_REGISTRY[kind_name]
        prefix = definition["kind"]
        id_prefix = definition.get("ref_prefix", prefix)
        if kind_name != "ground" and ref[:1].upper() != id_prefix:
            raise ValueError(f"{path}.id must start with {id_prefix} for {kind_name}")
        if kind_name == "ground" and ref[:1].upper() not in {"G", "0"}:
            raise ValueError(f"{path}.id for ground must start with G")
        terminals = item.get("terminals", {})
        if not isinstance(terminals, Mapping):
            raise ValueError(f"{path}.terminals must be an object")
        allowed_names = set(definition["terminals"])
        if set(terminals) - allowed_names:
            raise ValueError(f"{path}.terminals has unknown names: {sorted(set(terminals) - allowed_names)}")
        expected_native = definition.get(
            "native_terminals", {name: name for name in definition["terminals"]}
        )
        for name, native in expected_native.items():
            if name in terminals and str(terminals[name]) != native:
                raise ValueError(f"{path}.terminals.{name} must map to native pin {native}")
        polarity = item.get("polarity")
        if polarity is not None and (
            kind_name not in {"dc_voltage_source", "dc_current_source"}
            or polarity != {"positive_terminal": "positive"}
        ):
            raise ValueError(f"{path}.polarity is unsupported")
        position = _point(item.get("position"), f"{path}.position")
        rotation = item.get("rotation", 0)
        if isinstance(rotation, bool) or rotation not in {0, 90, 180, 270}:
            raise ValueError(f"{path}.rotation must be 0, 90, 180, or 270")
        mirror = item.get("mirror", False)
        if not isinstance(mirror, bool):
            raise ValueError(f"{path}.mirror must be boolean")
        value = None
        if definition["required_value"]:
            if item.get("value") is None:
                raise ValueError(f"{path}.value is required")
            value, _ = _scalar(item["value"], definition["unit"], f"{path}.value")
        elif "value" in item:
            raise ValueError(f"{path}.value is not used by {kind_name}")
        model = item.get("model", definition.get("default_model"))
        allowed_models = definition.get("models")
        if definition.get("model_required") and model is None:
            raise ValueError(f"{path}.model is required")
        if allowed_models and model is not None and model.upper() not in {name.upper() for name in allowed_models}:
            raise ValueError(f"{path}.model must be one of {', '.join(allowed_models)}")
        if not allowed_models and "model" in item:
            raise ValueError(f"{path}.model is not used by {kind_name}")
        compset = {"id": ref, "type": kind_name, "kind": prefix, "value": value, "model": model, "position": position, "rotation": rotation, "mirror": mirror, "polarity": polarity}
        components[ref] = compset
        pin_map = {name: str(terminals.get(name, native)) for name, native in expected_native.items()}
        native_terminals[ref] = pin_map
        expected_terminals.update(f"{ref}.{pin}" for pin in definition["terminals"])

    membership: dict[str, str] = {}
    net_ids: set[str] = set()
    net_nodes: dict[str, list[str]] = {}
    grounded_nets: set[str] = set()
    for index, raw in enumerate(raw_nets):
        path = f"spec.nets[{index}]"
        item = _object(raw, path)
        if set(item) != {"id", "terminals"}:
            raise ValueError(f"{path} must contain only id and terminals")
        net = item.get("id")
        terminals = item.get("terminals")
        if not isinstance(net, str) or not _NODE.fullmatch(net):
            raise ValueError(f"{path}.id must be a SPICE-compatible node name")
        key = net.casefold()
        if key in net_ids:
            raise ValueError(f"duplicate net id: {net}")
        net_ids.add(key)
        if net == "0":
            grounded_nets.add(net)
        if not isinstance(terminals, list) or len(terminals) < 2:
            raise ValueError(f"{path}.terminals must contain at least two endpoints")
        mapped: list[str] = []
        for endpoint in terminals:
            if not isinstance(endpoint, str) or endpoint not in expected_terminals:
                raise ValueError(f"{path} references unknown terminal: {endpoint!r}")
            if endpoint in membership:
                raise ValueError(f"terminal {endpoint} belongs to more than one net")
            membership[endpoint] = net
            ref, pin = endpoint.split(".", 1)
            if components[ref]["kind"] == "GND":
                if net != "0":
                    raise ValueError(f"ground terminal {endpoint} must belong to net 0")
                grounded_nets.add(net)
                mapped.append("0")
            else:
                mapped.append(net)
        net_nodes[net] = mapped

    missing = sorted(expected_terminals - set(membership))
    if missing:
        raise ValueError(f"unconnected terminals: {missing}")
    if len(grounded_nets) > 1:
        raise ValueError("all ground symbols must belong to the same net 0")
    # A ground symbol makes its whole declared net node 0.
    for raw in raw_nets:
        net = raw["id"]
        if net == "0" or any(components[endpoint.split(".", 1)[0]]["kind"] == "GND" for endpoint in raw["terminals"]):
            for endpoint in raw["terminals"]:
                membership[endpoint] = "0"
            if net != "0":
                net_nodes["0"] = net_nodes.pop(net)

    # Optional visual connection records must agree with electrical membership.
    raw_connections = data.get("connections", [])
    if not isinstance(raw_connections, list):
        raise ValueError("spec.connections must be an array")
    for index, raw in enumerate(raw_connections):
        path = f"spec.connections[{index}]"
        item = _object(raw, path)
        if set(item) != {"net", "from", "to"}:
            raise ValueError(f"{path} must contain net, from, and to")
        if not all(isinstance(item.get(key), str) for key in ("net", "from", "to")):
            raise ValueError(f"{path} net and terminal fields must be strings")
        if item["from"] not in membership or item["to"] not in membership:
            raise ValueError(f"{path} references an unknown terminal")
        if membership[item["from"]] != membership[item["to"]] or membership[item["from"]] != item["net"]:
            raise ValueError(f"{path} disagrees with net membership")
    for field_name in ("junctions", "wire_waypoints"):
        records = data.get(field_name, [])
        if not isinstance(records, list):
            raise ValueError(f"spec.{field_name} must be an array")
        if records and field_name == "junctions":
            raise ValueError("spec.junctions are not supported by this builder yet")

    waypoint_map: dict[str, list[tuple[float, float]]] = {}
    for index, raw in enumerate(data.get("wire_waypoints", [])):
        path = f"spec.wire_waypoints[{index}]"
        item = _object(raw, path)
        if set(item) != {"net", "points"}:
            raise ValueError(f"{path} must contain net and points")
        net, points = item.get("net"), item.get("points")
        if not isinstance(net, str) or net not in net_nodes:
            raise ValueError(f"{path}.net references an unknown net")
        if net in waypoint_map:
            raise ValueError(f"{path}.net has duplicate waypoint records")
        if len(net_nodes[net]) != 2:
            raise ValueError(f"{path}.net waypoints require a two-terminal net")
        if not isinstance(points, list) or not points:
            raise ValueError(f"{path}.points must be a non-empty array")
        normalized_points = []
        for point_index, point in enumerate(points):
            coords = _point(point, f"{path}.points[{point_index}]")
            assert coords is not None
            normalized_points.append((coords[0], coords[1]))
        waypoint_map[net] = normalized_points

    uncertainties = data.get("uncertainties", [])
    if not isinstance(uncertainties, list):
        raise ValueError("spec.uncertainties must be an array")
    for index, raw in enumerate(uncertainties):
        item = _object(raw, f"spec.uncertainties[{index}]")
        if set(item) - {"path", "reason", "confidence", "resolved"}:
            raise ValueError(f"spec.uncertainties[{index}] has unknown fields")
        if not isinstance(item.get("path"), str) or not item["path"].strip() or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError(f"spec.uncertainties[{index}] requires path and reason")
        if "resolved" in item and not isinstance(item["resolved"], bool):
            raise ValueError(f"spec.uncertainties[{index}].resolved must be boolean")
        confidence = item.get("confidence")
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
            raise ValueError(f"spec.uncertainties[{index}].confidence must be between 0 and 1")

    normalized_components: list[dict[str, Any]] = []
    for ref, item in components.items():
        definition = COMPONENT_REGISTRY[item["type"]]
        ordered_nodes = []
        for terminal in definition["terminals"]:
            net = membership[f"{ref}.{terminal}"]
            ordered_nodes.append("0" if net == "0" else net)
        if item["kind"] != "GND":
            if item["kind"] in {"V", "I"}:
                circuit_components.append(CircuitComponent(refdes=ref, kind=item["kind"], nodes=tuple(ordered_nodes), model=f"DC {item['value']}"))
            else:
                circuit_components.append(CircuitComponent(refdes=ref, kind=item["kind"], nodes=tuple(ordered_nodes), value=item["value"], model=item["model"]))
        normalized_component: dict[str, Any] = {"id": ref, "type": item["type"]}
        if item["value"] is not None:
            normalized_component["value"] = item["value"]
        if item["model"] is not None:
            normalized_component["model"] = item["model"]
        if native_terminals[ref]:
            normalized_component["terminals"] = native_terminals[ref]
        if item["polarity"] is not None:
            normalized_component["polarity"] = item["polarity"]
        if item["position"] is not None:
            normalized_component["position"] = {"x": item["position"][0], "y": item["position"][1]}
        if item["rotation"]:
            normalized_component["rotation"] = item["rotation"]
        if item["mirror"]:
            normalized_component["mirror"] = True
        normalized_components.append(normalized_component)

    nodes = list(dict.fromkeys(node for comp in circuit_components for node in comp.nodes))
    if "0" not in nodes and any(item["kind"] == "GND" for item in components.values()):
        nodes.append("0")
    design = CircuitDesign(
        design_id=f"circuitspec:{_digest(data)[:24]}",
        title=title.strip(),
        components=tuple(circuit_components),
        nets=tuple(nodes),
        annotations={"source": "codex-circuit-spec", "circuit_spec_version": CIRCUIT_SPEC_VERSION},
    )
    netlist = circuit_design_to_spice(design, prefer_source=False)
    normalized = {
        "schema_version": CIRCUIT_SPEC_VERSION,
        "title": title.strip(),
        "units": {"length": "multisim-grid", "value": "SI"},
        "components": normalized_components,
        "nets": [{"id": str(record["id"]), "terminals": list(record["terminals"])} for record in raw_nets],
        "connections": [dict(item) for item in raw_connections],
        "junctions": [dict(item) for item in data.get("junctions", [])],
        "wire_waypoints": [
            {"net": net, "points": [{"x": x, "y": y} for x, y in points]}
            for net, points in waypoint_map.items()
        ],
        "uncertainties": [dict(item) for item in uncertainties],
    }
    digest = _digest(normalized)
    unresolved = [item for item in uncertainties if item.get("resolved") is not True]
    return {
        "valid": True,
        "ready_to_build": not unresolved,
        "normalized_spec": normalized,
        "spec_sha256": digest,
        "circuit_design": design.to_dict(),
        "spice_netlist": netlist,
        "unresolved_uncertainties": unresolved,
        "component_registry_version": CIRCUIT_SPEC_VERSION,
        "component_placements": {
            ref: {
                **({"x": item["position"][0], "y": item["position"][1]} if item["position"] is not None else {}),
                "rotation": item["rotation"],
                "mirror": item["mirror"],
            }
            for ref, item in components.items()
            if item["kind"] != "GND" and (item["position"] is not None or item["rotation"] or item["mirror"])
        },
        "wire_waypoints": waypoint_map,
    }


def approve_circuit_spec(spec: object, approval: object) -> dict[str, Any]:
    """Bind explicit component, topology, and value review to one exact spec."""
    preview = validate_circuit_spec(spec)
    if not preview["ready_to_build"]:
        raise ValueError("unresolved visual uncertainties must be clarified before approval")
    if not isinstance(approval, Mapping):
        raise ValueError("approval must be an object")
    allowed = {"approved", "spec_sha256", "confirm_components", "confirm_topology", "confirm_values", "review_note"}
    unknown = set(approval) - allowed
    if unknown:
        raise ValueError(f"approval contains unknown fields: {sorted(unknown)}")
    for field in ("approved", "confirm_components", "confirm_topology", "confirm_values"):
        if approval.get(field) is not True:
            raise ValueError(f"approval.{field} must be true after explicit review")
    if approval.get("spec_sha256") != preview["spec_sha256"]:
        raise ValueError("approval.spec_sha256 does not match the validated CircuitSpec")
    note = approval.get("review_note", "")
    if not isinstance(note, str) or "\x00" in note or len(note) > 2048:
        raise ValueError("approval.review_note is invalid")
    reviewed = {
        "approved": True,
        "spec_sha256": preview["spec_sha256"],
        "confirm_components": True,
        "confirm_topology": True,
        "confirm_values": True,
        "review_note": note.strip(),
    }
    digest = _digest(reviewed)
    return {
        "schema_version": 1,
        "kind": "multisim-mcp-circuit-spec-approval",
        "spec_sha256": preview["spec_sha256"],
        "approval": {**reviewed, "approval_digest": digest},
        "ready_for_schematic": True,
        "ready_for_simulation": False,
        "execution_boundary": {
            "files_written": False,
            "schematic_generated": False,
            "simulation_started": False,
        },
    }


def validate_circuit_spec_approval(spec: object, artifact: object) -> dict[str, Any]:
    """Rebuild an approval artifact before a file-producing schematic call."""
    preview = validate_circuit_spec(spec)
    if not isinstance(artifact, Mapping) or artifact.get("kind") != "multisim-mcp-circuit-spec-approval":
        raise ValueError("approval.kind is invalid")
    if artifact.get("schema_version") != 1 or artifact.get("spec_sha256") != preview["spec_sha256"]:
        raise ValueError("approval does not match the validated CircuitSpec")
    reviewed = artifact.get("approval")
    if not isinstance(reviewed, Mapping):
        raise ValueError("approval.approval is required")
    raw = {key: value for key, value in reviewed.items() if key != "approval_digest"}
    expected = approve_circuit_spec(spec, raw)
    if dict(artifact) != expected:
        raise ValueError("approval digest or reviewed fields are invalid")
    return expected


__all__ = [
    "CIRCUIT_SPEC_VERSION",
    "COMPONENT_REGISTRY",
    "approve_circuit_spec",
    "validate_circuit_spec",
    "validate_circuit_spec_approval",
]
