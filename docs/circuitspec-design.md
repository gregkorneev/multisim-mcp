# CircuitSpec: проект контракта image → Multisim

## Решение аудита

`CircuitSpec` должен быть входным контрактом **между Codex и MCP**, а не
форматом OCR/CV и не заменой `.ms14`. Codex по изображению извлекает
структурированную схему, MCP валидирует её, преобразует в поддерживаемый SPICE
netlist и передаёт существующему `create_schematic_from_netlist`. Последний уже
создаёт нативный Multisim XML из user-local template pack, кодирует `.ms14` и
при включённом `open_after_build` открывает и проверяет его через COM.

Это сохраняет upstream-архитектуру: распознавание изображения не входит в MCP,
а `.ms14` не создаётся через UI automation. Нынешний builder принимает только
SPICE; он **не принимает CircuitSpec, произвольные координаты, угол или
waypoints как публичный API**. Поэтому ниже — целевой v0.1 контракт и список
минимальных расширений адаптера, а не заявление о реализованной функции.

## Нормативный JSON-пример

```json
{
  "schema_version": "0.1",
  "title": "10 V resistor load",
  "units": { "length": "multisim-grid", "value": "SI" },
  "components": [
    {
      "id": "V1", "type": "dc_voltage_source", "value": "10 V",
      "terminals": { "positive": "2", "negative": "1" },
      "position": { "x": 36, "y": 216 }, "rotation": 0, "mirror": false,
      "polarity": { "positive_terminal": "positive" }
    },
    {
      "id": "R1", "type": "resistor", "value": "1 kOhm",
      "position": { "x": 306, "y": 189 }, "rotation": 0, "mirror": false
    },
    { "id": "GND", "type": "ground", "position": { "x": 486, "y": 324 }, "rotation": 0 }
  ],
  "nets": [
    { "id": "VIN", "terminals": ["V1.positive", "R1.1"] },
    { "id": "0", "terminals": ["R1.2", "V1.negative", "GND.0"] }
  ],
  "connections": [
    { "net": "VIN", "from": "V1.positive", "to": "R1.1" },
    { "net": "0", "from": "R1.2", "to": "GND.0" },
    { "net": "0", "from": "GND.0", "to": "V1.negative" }
  ],
  "junctions": [],
  "wire_waypoints": []
}
```

### Schema rules

* `id` is unique and must become a valid SPICE reference designator. `type` is
  a stable CircuitSpec name mapped by a versioned component registry (not a
  raw template filename). `value` stays a displayable engineering string and
  is parsed to the numeric value required by the existing builder.
* Coordinates are absolute **Multisim diagram coordinates**, not normalized
  percentages. Upstream currently emits positions such as `(36,216)` and
  `(306,189)` and stores them in XML transform fields. A future UI may offer a
  normalized view, but conversion must occur before validation.
* `rotation` is one of `0`, `90`, `180`, `270`; `mirror` is boolean. These are
  requested intent fields. They require a builder extension because upstream
  currently chooses transform matrices from fixed layout profiles/component
  kinds rather than public per-component input.
* A terminal has the canonical spelling `componentId.terminalName`; the
  registry resolves names such as `positive`/`negative` to native terminals
  (`V`: 2/1). `nets` state electrical connectivity. `connections` are optional
  rendering edges and must agree with `nets`; a validator rejects dangling
  terminals, duplicate conflicting net membership and ungrounded designs when
  the analysis requires ground.
* `junctions` are explicit named points only for a user-required visible tee.
  Two-terminal nets need none. `wire_waypoints` are ordered grid points and
  may be associated with a connection; they are validated to be orthogonal,
  start/end on real native pins and avoid bodies. If absent, existing
  `orthogonal_routing.route_pins` selects a route.

## Minimal API boundary

The first implementation should add a `CircuitSpecAdapter` and these thin MCP
tools, retaining existing names for compatibility:

| Target API | Implementation boundary | Result |
| --- | --- | --- |
| `validate_circuit(spec)` | pure schema + component registry + `layout_validation.py` | normalized spec, diagnostics, generated SPICE preview |
| `create_circuit(spec, output_ms14, ...)` | adapter → existing builder/codec/COM verification | `.ms14`, XML, geometry, topology evidence |
| `inspect_circuit()` | existing `circuit_info`, enumeration, netlist export; later structured snapshot | native evidence, not editable COM objects |
| `patch_circuit(patch)` | compile restricted changes to existing RLC/replace or regenerate from source spec | new revision plus explicit diff |
| `capture_schematic(path)` | stable alias of `get_circuit_image` | PNG/JPG/BMP path |
| `save_circuit(path)` | stable alias of `save_circuit` | saved `.ms14` path |
| `run_simulation(request)` | dispatch to existing DC/AC/transient tools | sampled result rows and readiness/evidence |

`create_circuit` must always write the input spec, resolved component mapping,
generated SPICE and geometry report beside the output. It must not silently
fall back from an unsupported `type`, terminal, rotation or waypoint to a
different topology.

## Phased implementation

1. `feature/circuit-spec`: JSON Schema/Pydantic model, registry for R/C/L,
   DC V/I and ground, pure validation and netlist compiler; COM-free tests.
2. `feature/native-builder`: feed deterministic placement, transform and
   waypoint intent into `schematic_builder.py`, preserving its default router.
3. `feature/instruments`: add only template-backed, native instruments with
   verified terminal mapping; do not treat data-derived `read_virtual_multimeter`
   as a placed Multisim multimeter.
4. `feature/visual-verification`: capture and compare schematic image,
   topology and layout report after open/save/reopen.

## Image workflow

```text
image → Codex vision → CircuitSpec JSON → validate_circuit
      → create_circuit → native editable .ms14 → open/inspect/capture
```

Codex must supply uncertainty explicitly (for example a missing value or
ambiguous junction) and request clarification before generation. No OCR,
OpenCV, neural model, GUI automation or image upload code belongs in MCP.
