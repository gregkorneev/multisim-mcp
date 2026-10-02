from __future__ import annotations

import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from multisim_mcp.circuit_spec import (
    CIRCUIT_SPEC_VERSION,
    approve_circuit_spec,
    validate_circuit_spec,
    validate_circuit_spec_approval,
)
from multisim_mcp.schematic_builder import _compose_symbol_orientation


EXAMPLES = Path(__file__).parents[2] / "examples" / "circuitspec"


def _fixture() -> dict:
    return json.loads((EXAMPLES / "rc-low-pass.json").read_text(encoding="utf-8"))


class CircuitSpecTest(unittest.TestCase):
    def test_rc_example_compiles_deterministically(self) -> None:
        spec = _fixture()
        first = validate_circuit_spec(spec)
        second = validate_circuit_spec(spec)
        self.assertTrue(first["ready_to_build"])
        self.assertEqual(first["spice_netlist"], second["spice_netlist"])
        self.assertEqual(first["spec_sha256"], second["spec_sha256"])
        self.assertEqual(first["spice_netlist"], "V1 vin 0 DC 5\nR1 vin vout 1000\nC1 vout 0 0.0000001\n.end\n")

    def test_missing_value_is_rejected(self) -> None:
        spec = _fixture()
        del spec["components"][1]["value"]
        with self.assertRaisesRegex(ValueError, "value is required"):
            validate_circuit_spec(spec)

    def test_unknown_component_type_is_rejected(self) -> None:
        spec = _fixture()
        spec["components"][1]["type"] = "integrated_circuit"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            validate_circuit_spec(spec)

    def test_duplicate_component_id_is_rejected(self) -> None:
        spec = _fixture()
        spec["components"][2]["id"] = "R1"
        with self.assertRaisesRegex(ValueError, "duplicate component id"):
            validate_circuit_spec(spec)

    def test_unconnected_pin_is_rejected(self) -> None:
        spec = _fixture()
        spec["nets"][1]["terminals"].remove("C1.1")
        with self.assertRaisesRegex(ValueError, "at least two endpoints"):
            validate_circuit_spec(spec)

    def test_conflicting_net_membership_is_rejected(self) -> None:
        spec = _fixture()
        spec["nets"].append({"id": "other", "terminals": ["R1.1", "C1.2"]})
        with self.assertRaisesRegex(ValueError, "more than one net"):
            validate_circuit_spec(spec)

    def test_connection_disagreement_is_rejected(self) -> None:
        spec = _fixture()
        spec["connections"][0]["net"] = "vout"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            validate_circuit_spec(spec)

    def test_unresolved_visual_ambiguity_blocks_build(self) -> None:
        spec = _fixture()
        spec["uncertainties"] = [{"path": "crossing", "reason": "Dot unclear", "confidence": 0.4}]
        result = validate_circuit_spec(spec)
        self.assertTrue(result["valid"])
        self.assertFalse(result["ready_to_build"])
        self.assertEqual(len(result["unresolved_uncertainties"]), 1)

    def test_native_source_pin_mapping_is_checked(self) -> None:
        spec = _fixture()
        spec["components"][0]["terminals"] = {"positive": "1", "negative": "2"}
        with self.assertRaisesRegex(ValueError, "must map to native pin"):
            validate_circuit_spec(spec)

    def test_approval_is_digest_bound_to_the_exact_spec(self) -> None:
        spec = _fixture()
        digest = validate_circuit_spec(spec)["spec_sha256"]
        artifact = approve_circuit_spec(
            spec,
            {
                "approved": True,
                "spec_sha256": digest,
                "confirm_components": True,
                "confirm_topology": True,
                "confirm_values": True,
            },
        )
        self.assertEqual(validate_circuit_spec_approval(spec, artifact), artifact)
        spec["components"][1]["value"] = "2 kOhm"
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_circuit_spec_approval(spec, artifact)

    def test_geometry_hints_are_returned_for_the_builder(self) -> None:
        spec = _fixture()
        spec["components"][1].update(position={"x": 240, "y": 100}, rotation=90)
        spec["wire_waypoints"] = [{"net": "vin", "points": [{"x": 120, "y": 72}]}]
        result = validate_circuit_spec(spec)
        self.assertEqual(result["component_placements"]["R1"], {"x": 240.0, "y": 100.0, "rotation": 90, "mirror": False})
        self.assertEqual(result["wire_waypoints"]["vin"], [(120.0, 72.0)])

    def test_waypoints_are_rejected_for_multi_terminal_net(self) -> None:
        spec = _fixture()
        spec["wire_waypoints"] = [{"net": "0", "points": [{"x": 10, "y": 20}]}]
        with self.assertRaisesRegex(ValueError, "two-terminal net"):
            validate_circuit_spec(spec)

    def test_ambiguous_fixture_is_valid_but_not_buildable(self) -> None:
        spec = json.loads((EXAMPLES / "ambiguous-crossing.json").read_text(encoding="utf-8"))
        result = validate_circuit_spec(spec)
        self.assertTrue(result["valid"])
        self.assertFalse(result["ready_to_build"])
        self.assertTrue((EXAMPLES / "ambiguous-crossing.svg").is_file())

    def test_every_regression_spec_has_a_synthetic_image(self) -> None:
        files = list(EXAMPLES.glob("*.json"))
        self.assertEqual(len(files), 2)
        for path in files:
            with self.subTest(path=path.name):
                result = validate_circuit_spec(json.loads(path.read_text(encoding="utf-8")))
                self.assertTrue(result["valid"])
                self.assertTrue(path.with_suffix(".svg").is_file())

    def test_symbol_orientation_composes_rotation_and_mirror(self) -> None:
        symbol = ET.Element("CIITSymbolComp")
        _compose_symbol_orientation(symbol, 90, True)
        self.assertEqual(
            tuple(symbol.get("Transformer-" + key) for key in ("M00", "M01", "M10", "M11")),
            ("0", "-1", "-1", "0"),
        )

    def test_schema_version_is_required(self) -> None:
        spec = _fixture()
        spec["schema_version"] = "0.2"
        with self.assertRaisesRegex(ValueError, CIRCUIT_SPEC_VERSION):
            validate_circuit_spec(spec)


if __name__ == "__main__":
    unittest.main()
