# Upstream technical audit — 2026-09-17

## Scope and evidence

Audit target: `yxy050208/multisim-mcp`, commit `33ec7f4` (99 commits imported
unchanged to this repository). Evidence is source, unit tests and local runtime
inspection; labels below deliberately distinguish them from a real MCP run.

The VM contains `C:\Program Files (x86)\National Instruments\Circuit Design
Suite 14.0\multisim.exe` and registered `MultisimInterface.MultisimApp` COM
ProgID. It has **no discoverable 32-bit Python interpreter with pywin32** (only
the WindowsApps Python alias). The project correctly rejects 64-bit/no-pywin32
automation. Consequently the **MCP** variants of connect, open/save, native
builder verification, simulation and image-export were not run in this VM.
This is a blocked MCP E2E precondition, not a failed feature or an inferred
success.

Direct 32-bit PowerShell COM smoke evidence was obtained separately on
2026-09-17: `MultisimInterface.MultisimApp` connected successfully, reported
`Multisim 14.0`, created blank `Design1`, saved a 14,491-byte temporary `.ms14`,
reopened it and saved it again. Its actual `IMultisimCircuit` surface includes
`EnumComponents`, `ReplaceComponent`, DC/AC/transient methods,
`GetCircuitImage`, `Save` and `SaveAs`; it exposes no Add/Create/Place component
or wire method. The temporary test design was deleted after verification. No
components could honestly be created because that public COM surface lacks a
creation primitive. Install an x86 Python 3.10+ with package dependencies, set
`MULTISIM_MCP_WORKER_PYTHON`, then run
`tools/probe_multisim_native_api.py --blank` and the minimal regression listed
below.

## Architecture and constraints

| Area | Finding |
| --- | --- |
| Language/runtime | Python ≥3.10; MCP Python SDK 2 stdio. COM requires Windows, 32-bit Python and pywin32. |
| Tool registration | `server.py` uses `@mcp.tool()` and a profile wrapper; `MULTISIM_MCP_TOOL_PROFILE` selects core/experiment/optimization/full. Full is default. |
| COM ownership | 64/32-bit frontend sends allowlisted JSON RPC to long-lived `com_worker.py`; only that 32-bit worker owns the COM apartment/current circuit. Timeout/cancel kills/restarts worker. |
| `.ms14` | `Ms14Codec` runs pinned `electronics-workbench-decoder@0.2.0`; source builder writes XML then encodes `.ms14`. Local component templates are deliberately not distributed and must be bootstrapped from licensed Multisim. |
| Native creation | COM type-library audit finds open/new/enumerate/replace/analysis/export/save, but no public add-component/place/wire/connect/pin-geometry API. `EnumComponents` returns names only. |
| Builder | `schematic_builder.py` converts a constrained SPICE netlist to template-derived XML, creates native nodes/ports/wires, then routes with `orthogonal_routing.py`. It is the creation path, COM is verification/simulation/export. |
| Position/rotation | Builder stores absolute XML transforms and has deterministic profiles plus kind-specific rotations. It has no public input for arbitrary per-component x/y/0/90/180/270 or mirror. |
| Wires | Existing router creates true XML wires and junctions with automatically selected orthogonal intermediate points; public API cannot supply waypoints. |
| Instruments | Template-backed `XFG3` function generator and `OSC6` 4-channel scope are built/registered. `read_virtual_multimeter`, Bode and logic tools derive readings from raw data; they do not place native meter/multimeter symbols. |
| Simulation | COM supports DC, AC sweep/single frequency, transient, input/output request and sampled data. Safe command-engine SPICE limits commands to `op`, `dc`, `ac`, `tran` by default. |
| Export | Native `GetCircuitImage` exports PNG=0/JPG=1/BMP=2. Netlist, BOM and Markdown report also available. No `capture_schematic` alias yet. |
| Tests/packaging | Extensive unittest/pytest-style COM-free suite under `mcp_server/tests`; E2E script exists but needs local fixture and x86 Python. `pyproject.toml` produces PyPI package; GitHub Actions already exist upstream. |
| Codex setup | `tools/generate_agent_config.py` emits a Codex config using `python -m multisim_mcp.cli serve`; worker path can be separately configured. |

## Available MCP tools

`COM` means the request reaches the isolated worker; `XML` means local
builder/codec; `local` is pure service/filesystem/raw-data work. “Verified” is
test/source coverage only unless marked `E2E blocked`.

| Tool | Purpose; arguments | Returns | Backend | Actual state / need / extension |
| --- | --- | --- | --- | --- |
| `connect` | connect; — | connected/version/path | COM | E2E blocked; needed |
| `disconnect` | release circuit; — | connected false | COM | E2E blocked; needed |
| `runtime_status` | diagnose; — | worker/template/backend status | local | source-tested; needed |
| `open_circuit` | open; `path` | circuit info | COM | E2E blocked; needed |
| `new_circuit` | blank design; — | circuit info | COM | E2E blocked; needed |
| `circuit_info` | inspect open circuit; — | name/file/state/error | COM | E2E blocked; needs structured inspect later |
| `enum_components` | list references; `component_type=0` | names | COM | E2E blocked; insufficient geometry/details |
| `enum_inputs` | inputs; `input_type=0` | names | COM | E2E blocked; needed |
| `enum_outputs` | outputs; `output_type=0` | names | COM | E2E blocked; needed |
| `save_circuit` | save/SaveAs; `path?` | path | COM | E2E blocked; needed |
| `get_circuit_image` | image export; `path,image_format=0` | path | COM | E2E blocked; alias `capture_schematic` |
| `report_netlist` | export netlist; `path,probes_flag=false,fmt=0` | path | COM | E2E blocked; needed |
| `report_bom` | export BOM; `path,real_flag=false,fmt=0` | path | COM | E2E blocked; needed |
| `generate_report` | Markdown report; `output_path,title,analyses,include_*` | path/size | COM+local | E2E blocked for exports; useful |
| `decode_ms14` | decode; `path,output_xml?` | codec result | XML | source-tested; needed |
| `encode_ms14` | encode; `source_xml,output_ms14?` | codec result | XML | source-tested; needed |
| `schematic_component_catalog` | supported builder types; — | definitions/adapters | local | source-tested; needed |
| `create_schematic_from_netlist` | build editable design; `netlist,output_ms14,probe_nets?,include_experimental_probes?,open_after_build?,image_path?,overwrite?,approval?` | `.ms14`, XML, geometry, topology | XML+COM | builder tests; E2E blocked; adapt from CircuitSpec |
| `snapshot_open_circuit` | export validated snapshot; `output_dir,probes_flag,fmt,allow_unsupported` | design/artifact snapshot | COM+local | E2E blocked; useful inspect base |
| `get_rlc_value` | read R/L/C; `component_name` | value | COM | E2E blocked; needed patch base |
| `set_rlc_value` | mutate R/L/C; `component_name,value` | value | COM | E2E blocked; needed patch base |
| `set_output_request` | configure output; `output_name,method,sample_rate,num_samples,repeat_flag` | request | COM | E2E blocked; needed |
| `get_output_data` | read analysis; `output_name,max_points` | rows/shape | COM | E2E blocked; needed |
| `run_transient` | transient; `output_name,sample_rate,num_samples,duration,repeat_flag,timeout,max_points` | rows/readiness | COM | E2E blocked; needed |
| `run_dc_operating_point` | DC; `output_names,timeout,max_points` | rows/readiness | COM | E2E blocked; needed |
| `run_ac_sweep` | AC; `output_names,sweep_type,num_points,start_frequency,stop_frequency,timeout,max_points` | rows/readiness | COM | E2E blocked; needed |
| `run_ac_single_frequency` | AC point; `output_names,frequency,timeout,max_points` | rows/readiness | COM | E2E blocked; needed |
| `set_input_data_sampled` | waveform; `input_name,sample_rate,values,repeat_flag` | sample count | COM | E2E blocked; optional |
| `set_input_data_raw` | waveform; `input_name,times,values,repeat_flag` | sample count | COM | E2E blocked; optional |
| `clear_input_data` | clear waveform; `input_name` | cleared/warning | COM | E2E blocked; optional |
| `stop_simulation` | stop; — | stopped/state | COM | E2E blocked; needed |
| `do_command_line` | command file; `command_file,log_file` | path | COM | unsafe-gated; not core |
| `run_spice_netlist` | safe SPICE; `netlist,commands,output_dir,...` | raw/CSV/SVG | COM+local | tests; E2E blocked |
| `run_circuit_experiment` | build+simulate+report; `netlist,commands,output_dir,title,timeout,max_points,overwrite` | experiment artifacts | XML+COM | E2E blocked; use after CircuitSpec |
| `run_verified_circuit_experiment` | experiment requirements; `spec,output_dir,...approvals` | evidence verdicts | XML+COM | E2E blocked; optional |
| `submit_circuit_experiment` | durable job; netlist/commands/output and limits | job | XML+COM | tests; E2E blocked |
| `get_experiment_job` | job state; `job_id` | job | local | tests; useful |
| `list_experiment_jobs` | job list; `state,limit` | jobs | local | tests; useful |
| `cancel_experiment_job` | cancel; `job_id` | job | local | tests; useful |
| `retry_experiment_job` | retry; `job_id` | submission | local | tests; useful |
| `register_experiment_artifacts` | register output; `output_dir` | resource index | local | tests; useful |
| `list_experiment_artifacts` | list; `experiment_id` | metadata | local | tests; useful |
| `read_experiment_artifact` | read page; `experiment_id,name,offset,max_chars` | text | local | tests; useful |
| `export_experiment_artifact` | copy artifact; `experiment_id,name,destination_subdir,overwrite` | path | local | tests; useful |
| `get_experiment_summary` | summary; `experiment_id` | summary | local | tests; useful |
| `register_sweep_artifacts` | register sweep; `output_dir` | resources | local | tests; optional |
| `measure_experiment` | measurements; `experiment_id,measurements` | metrics | local | tests; optional |
| `read_virtual_multimeter` | data meter; `experiment_id,signal,reference_signal?` | DC/RMS | local | tests; not native instrument |
| `analyze_bode_response` | Bode; ids/signals | gain/phase | local | tests; not native instrument |
| `analyze_logic_signals` | logic traces; ids/signals/threshold | edges | local | tests; optional |
| `export_formal_experiment_report` | formal report; `experiment_id` | artifact | local | tests; optional |
| `audit_spice_compatibility` | static audit; netlist/backend/models/dialect | risks | local | tests; useful |
| `compare_experiment_backends` | compare runs; ids/signals/tolerances | comparison | local | tests; optional |
| `compare_native_sweep_baseline` | compare sweep; `ranking` | comparison | local | tests; optional |
| `component_adapter_catalog` | adapters; — | catalog | local | tests; useful |
| `build_behavioral_reference` | reference; `netlist` | reference | local | tests; optional |
| `run_behavioral_reference` | evaluate reference; netlist/commands/output | result | local | tests; optional |
| `verify_experiment_requirements` | verdicts; ids/requirements | PASS/FAIL | local | tests; optional |
| `plan_experiment_sweep` | plan sweep; `spec` | plan | local | tests; optional |
| `run_experiment_sweep` | execute sweep; spec/output | results | COM+local | E2E blocked; optional |
| `submit_experiment_sweep` | queued sweep; spec/output | job | local | tests; optional |
| `run_native_parameter_sweep` | native sweep; spec/output | runs | COM | E2E blocked; optional |
| `rank_native_sweep_results` | rank; `sweep` | ranking | local | tests; optional |
| `prepare_native_sweep_patch` | patch prep; ranking | patch | local | tests; optional |
| `apply_native_sweep_patch_to_copy` | patch copy; patch/path | result | COM | E2E blocked; optional |
| `export_native_sweep_report` | report; sweep/output | report | local | tests; optional |
| `plan_design_options` | plan; request | options | local | tests; optional |
| `review_design_requirements` | review; request | review | local | tests; optional |
| `bind_requirement_review_to_design` | bind; review/design | bound review | local | tests; optional |
| `select_design_option` | choose; plan/selection | selection | local | tests; optional |
| `prepare_design_specification` | prepare; option | spec | local | tests; optional |
| `prepare_netlist_draft` | draft; spec | netlist | local | tests; useful precursor |
| `resolve_component_requirements` | resolve; spec/catalog | mapping | local | tests; useful precursor |
| `approve_component_resolution` | approve; resolution | approval | local | tests; optional |
| `compile_executable_netlist` | compile; inputs | immutable netlist | local | tests; useful |
| `approve_executable_netlist` | approve; compiled | approval | local | tests; optional |
| `approve_simulation_plan` | approve; plan | approval | local | tests; optional |
| `build_course_waveform_demo` | demo; request | artifacts | local | tests; optional |
| `plan_model_engineering_request` | plan; text | plan | local | tests; optional |
| `run_model_engineering_request` | run; text/output/execute | result | local/COM | E2E blocked if execute |
| `submit_model_engineering_request` | queue; text/output | job | local | tests; optional |
| `submit_natural_engineering_job` | queue NL request; text/output | job | local | tests; optional |
| `run_natural_engineering_request` | NL flow; text/output/execute | result | local/COM | E2E blocked if execute |
| `plan_natural_engineering_request` | NL plan; text | plan | local | tests; optional |
| `plan_natural_rlc_engineering_request` | RLC plan; text | plan | local | tests; optional |
| `run_natural_rlc_engineering_request` | RLC flow; text/output/execute | result | local/COM | E2E blocked if execute |
| `plan_natural_opamp_engineering_request` | opamp plan; text | plan | local | tests; optional |
| `run_natural_opamp_engineering_request` | opamp flow; text/output/execute | result | local/COM | E2E blocked if execute |
| `run_generated_analog_project` | proposal; proposal/output/execute | result | local/COM | E2E blocked if execute |
| `plan_natural_analog_frontend` | plan; text | plan | local | tests; optional |
| `run_natural_analog_frontend` | flow; text/output/execute | result | local/COM | E2E blocked if execute |
| `plan_natural_dc_network` | plan; text | plan | local | tests; optional |
| `run_natural_dc_network` | flow; text/output/execute | result | local/COM | E2E blocked if execute |
| `plan_natural_common_emitter` | plan; text | plan | local | tests; optional |
| `run_natural_common_emitter` | flow; text/output/execute | result | local/COM | E2E blocked if execute |
| `plan_natural_rectifier` | plan; text | plan | local | tests; optional |
| `run_natural_rectifier` | flow; text/output/execute | result | local/COM | E2E blocked if execute |
| `optimize_natural_rectifier` | optimize; text/output/execute | result | local/COM | E2E blocked if execute |
| `diagnose_design` | diagnose; design/experiment_dir | diagnosis | local | tests; optional |
| `evaluate_design_patch` | evaluate; design/patch | result | local | tests; future patch base |
| `optimize_design` | optimize; design/objective | result | local | tests; optional |
| `global_optimize_design` | optimize; request | result | local | tests; optional |
| `submit_global_optimization` | queue; request | job | local | tests; optional |
| `autonomous_correct_design` | correct; request | result | local | tests; optional |
| `submit_autonomous_correction` | queue; request | job | local | tests; optional |
| `submit_design_optimization` | queue; request | job | local | tests; optional |
| `compare_design_variants` | compare; variants | comparison | local | tests; optional |

## Component and instrument matrix

“Builder” is evidence that XML/template creation is implemented; “Native test”
remains pending until the x86 runtime is installed.

| Component | Create | Position | Rotate | Set value | Connect | Simulation | Tested |
| --- | --- | --- | --- | --- | --- | --- |
| Resistor | Builder | fixed profile | internal only | `set_rlc_value` | XML/router | yes | unit; native pending |
| Capacitor | Builder | fixed profile | internal only | `set_rlc_value` | XML/router | yes | unit; native pending |
| Inductor | Builder | fixed profile | internal only | `set_rlc_value` | XML/router | yes | unit; native pending |
| DC voltage source | Builder | fixed profile | internal only | source netlist | XML/router | yes | unit; native pending |
| DC current source | Builder | fixed profile | internal only | source netlist | XML/router | yes | unit; native pending |
| Ground | Builder | derived layout | n/a | n/a | XML node `0` | required | unit; native pending |
| Switch (`S`/`W`) | generic carrier | fixed profile | internal only | model/netlist | XML/router | model-dependent | unit; native pending |
| Ammeter / Voltmeter | absent as native placement | — | — | — | — | derived only | no |
| Multimeter | no native placement | — | — | — | — | `read_virtual_multimeter` raw-data adapter | unit only |
| Oscilloscope | `OSC6` template | fixed profile | internal only | state params | XML/router | native state + data | unit; native pending |
| Function generator | `XFG3` template | fixed profile | internal only | waveform params | XML/router | native state + data | unit; native pending |

## Required real-Multisim regression

After installing x86 Python, use a **user-local component pack** and a temporary
directory outside the repository. Run `runtime_status`, `connect`, and native
API probe, then build this netlist through `create_schematic_from_netlist`:

```spice
V1 vin 0 DC 10
R1 vin 0 1k
.end
```

Verify open → `enum_components` → `get_rlc_value(R1)` → `set_rlc_value(R1,1000)`
→ `save_circuit(path)` → reopen, `report_netlist`, `get_circuit_image`, and
open the saved `.ms14` in Multisim. Manually verify R1/V1/ground can move,
change value and delete; wires must remain native after ordinary Multisim save.
Add an x86-only integration test that asserts the output file, R1 enumeration,
value round-trip and reopen. It must be excluded from ordinary CI and run on a
self-hosted Windows runner with licensed Multisim.

## Gap analysis

### Already available / reusable unchanged

Constrained netlist parsing, template-derived native XML, `.ms14` codec, router
and geometry validation, COM open/save/export/simulation, RLC mutation,
component catalog, topology/netlist evidence, native image export and durable
experiment/artifact plumbing are directly reusable.

### Must extend

Add versioned CircuitSpec validation/compiler; public per-component placement,
rotation/mirror and explicit wire waypoint input; native ammeter/voltmeter/
multimeter registry only after template + terminal verification; a stable
`capture_schematic` alias; and a structured `inspect_circuit`/restricted
`patch_circuit` facade. Add x86 real-Multisim regression coverage.

### Not present

No image recognition in MCP; no public COM component placement/wiring/pin
geometry; no documented native meter placement; no arbitrary CircuitSpec API;
no guaranteed arbitrary rotation/mirror/waypoint contract; and no actual E2E
evidence from this VM.

### Recommended next branch

Create `feature/circuit-spec` from `develop` after this audit is merged. Limit
it to pure schema/adapter/compiler and COM-free tests; defer builder geometry to
`feature/native-builder` and native instruments to `feature/instruments`.
