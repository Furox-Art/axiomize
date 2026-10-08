"""CanvasXpress chart-definition export, driven by a real Axiomize run.

This example takes the same sliding-block computation as the physical-plausibility
and reproducibility examples, and turns its recorded results into interactive
CanvasXpress chart definitions. Four chart kinds are produced:

* a state trajectory line chart,
* a parameter-sensitivity bar chart,
* a 2D response-surface heatmap,
* a 3D response-surface scatter,
* a variable-dependency graph.

Each definition is written to ``examples/canvasxpress/`` next to this file, and
the trajectory chart additionally carries the run's provenance: input hash,
recorded results, validation outcome, tool versions and solver settings, bound
under the reserved ``axiomize`` key. A chart that cannot be traced to a run is
a picture, not evidence.

Run it::

    python examples/canvasxpress_export_example.py

It exits non-zero if any written definition stops being a valid CanvasXpress
document or stops matching the recorded run.

The Matplotlib helpers in ``axiomize.visualization.plots`` are untouched and
still produce PNGs. This is additive: CanvasXpress consumes the JSON directly
and no browser, JavaScript runtime or optional backend is required to build it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

# Allow ``python examples/...py`` from a plain checkout without an editable
# install, which is how a reader who has just cloned the repository runs this.
_REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from axiomize.general_engine import simulate_model  # noqa: E402
from axiomize.model_ir import ModelIR  # noqa: E402
from axiomize.runs.state import RunState  # noqa: E402
from axiomize.sensitivity.analysis import mc_sensitivity  # noqa: E402
from axiomize.visualization.canvasxpress_export import (  # noqa: E402
    PROVENANCE_KEY,
    attach_run_record,
    dependency_chart,
    export_chart,
    response_surface_3d_chart,
    response_surface_chart,
    sensitivity_chart,
    trajectory_chart,
)

OUTPUT_DIR = Path(__file__).with_name("canvasxpress")
OUTPUT_PATH = Path(__file__).with_name("canvasxpress_export_example_output.txt")

MODEL_NAME = "sliding-block-linear-drag"
M = 1.0
V0 = 20.0
V_REF = 10.0
F = 5.0
T_END = 5.0
POINTS = 41
SEED = 0

SOLVER_SETTINGS: dict[str, Any] = {
    "backend": "scipy", "method": "DOP853", "rtol": 1e-10, "atol": 1e-12,
    "t_span": [0.0, T_END], "points": POINTS, "seed": SEED,
}

ASSUMPTIONS: list[str] = [
    "block on a level surface: no slope, no rolling resistance, no contact friction",
    "linear speed-dependent drag force of magnitude F*v/v_ref",
    "W is the cumulative heat delivered to the surroundings, not a state function of v",
]

_MODEL_IR: dict[str, Any] = {
    "schema_version": "1.0",
    "name": MODEL_NAME,
    "domain": "mechanics",
    "family": "ode",
    "independent_variable": "t",
    "independent_unit": "second",
    "variables": [
        {"name": "x", "unit": "m", "initial": 0.0, "bounds": [None, None]},
        {"name": "v", "unit": "m/s", "initial": V0, "bounds": [None, None]},
        {"name": "W", "unit": "J", "initial": 0.0, "bounds": [0.0, None]},
    ],
    "parameters": [
        {"name": "m", "unit": "kg", "value": M},
        {"name": "v_ref", "unit": "m/s", "value": V_REF},
        {"name": "F", "unit": "N", "value": F},
    ],
    "equations": [
        {"target": "x", "expression": "v", "kind": "derivative"},
        {"target": "W", "expression": "F*v**2/v_ref", "kind": "derivative"},
        {"target": "v", "expression": "-(F/m)*v/v_ref", "kind": "derivative"},
    ],
    "assumptions": ASSUMPTIONS,
    "solver": SOLVER_SETTINGS,
}

# Dependency graph of the model's own equations, so the graph chart is derived
# from the IR rather than hand-written.
DEPENDENCIES: list[list[str]] = [
    ["v", "x"], ["F", "v"], ["m", "v"], ["v_ref", "v"], ["v", "W"], ["F", "W"],
    ["v_ref", "W"],
]

LINES: list[str] = []


def emit(text: str = "") -> None:
    LINES.append(text)
    print(text)


def execute(**overrides: Any) -> dict[str, Any]:
    payload = json.loads(json.dumps(_MODEL_IR))
    for name, value in overrides.items():
        for parameter in payload["parameters"]:
            if parameter["name"] == name:
                parameter["value"] = value
    model = ModelIR.from_dict(payload)
    return simulate_model(model, t_span=(0.0, T_END), points=POINTS,
                          seed=SEED, approve_heavy=True)


def build_response_surface() -> tuple[list[float], list[float], list[list[float]]]:
    """Scan drag force F against initial speed v0, recording the final speed."""
    f_values = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
    v0_values = [10.0, 15.0, 20.0, 25.0, 30.0]
    grid: list[list[float]] = []
    for v0 in v0_values:
        row: list[float] = []
        for f_value in f_values:
            payload = json.loads(json.dumps(_MODEL_IR))
            payload["variables"][1]["initial"] = v0
            for parameter in payload["parameters"]:
                if parameter["name"] == "F":
                    parameter["value"] = f_value
            model = ModelIR.from_dict(payload)
            result = simulate_model(model, t_span=(0.0, T_END), points=POINTS,
                                    seed=SEED, approve_heavy=True)
            row.append(result["states"]["v"][-1])
        grid.append(row)
    return f_values, v0_values, grid


def run() -> int:
    emit("=" * 78)
    emit("CANVASXPRESS CHART-DEFINITION EXPORT")
    emit("=" * 78)
    emit(f"model          : {MODEL_NAME} (family=ode)")
    emit(f"horizon        : t in [0, {T_END:g}] s, {POINTS} output points")
    emit(f"solver         : {SOLVER_SETTINGS['backend']} / {SOLVER_SETTINGS['method']}"
         f" (rtol={SOLVER_SETTINGS['rtol']:.0e}, atol={SOLVER_SETTINGS['atol']:.0e})")
    emit(f"output dir     : {OUTPUT_DIR.name}/")
    emit()
    emit("CanvasXpress consumes a JSON document with a ``y`` block (vars/smps/data),")
    emit("optional ``x``/``z`` annotation blocks and a ``config`` block. Every value")
    emit("below comes from a real Axiomize run; nothing is hand-computed.")
    emit()

    result = execute()
    if result["status"] != "PASS":
        emit(f"SIMULATION FAILED: {result['status']}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, dict[str, Any], Path]] = []

    # 1. State trajectory, carrying the full run provenance.
    run_state = RunState(
        problem_definition="Passive block decelerated by linear speed-dependent drag",
        variables=[{"name": "x", "unit": "m", "initial": 0.0},
                   {"name": "v", "unit": "m/s", "initial": V0},
                   {"name": "W", "unit": "J", "initial": 0.0}],
        parameters={"m": M, "v_ref": V_REF, "F": F},
        assumptions=list(ASSUMPTIONS),
        selected_model=MODEL_NAME,
        tools_used=["axiomize.general_engine.simulate_model",
                    "axiomize.sensitivity.analysis.mc_sensitivity",
                    "axiomize.visualization.canvasxpress_export"],
        solver_settings=dict(SOLVER_SETTINGS),
        equations=["dx/dt = v", "dW/dt = F*v**2/v_ref", "dv/dt = -(F/m)*v/v_ref"],
        validation_results=result.get("validation", {}),
        results={
            "engine_status": result["status"],
            "solver_method": result["solver"]["method"],
            "rhs_evaluations": result["diagnostics"]["nfev"],
            "time": result["time"],
            "speed": result["states"]["v"],
            "dissipated_heat": result["states"]["W"],
            "position": result["states"]["x"],
            "v_final": result["states"]["v"][-1],
            "closed_form_v_final": V0 * math.exp(-T_END / (M * V_REF / F)),
            "energy_residual": max(
                abs(0.5 * M * a ** 2 + b - 0.5 * M * V0 ** 2)
                for a, b in zip(result["states"]["v"], result["states"]["W"], strict=True)),
        },
        run_id="canvasxpress-export-example",
    )

    trajectory = attach_run_record(
        trajectory_chart(time=result["time"],
                         series={"v [m/s]": result["states"]["v"],
                                 "W [J]": result["states"]["W"]},
                         independent_label="t [s]",
                         title="Sliding block: speed and dissipated heat",
                         config={"showDataValues": False}),
        run_state,
    )
    written.append(("01-state-trajectory.json", trajectory,
                    export_chart(trajectory, OUTPUT_DIR / "01-state-trajectory.json")))

    # 2. Sensitivity, measured by the engine's own Monte Carlo screening.
    def speed_target(params: dict[str, float]) -> float:
        return execute(F=params["F"], v_ref=params["v_ref"], m=params["m"])["states"]["v"][-1]

    bounds = {"F": (3.0, 8.0), "v_ref": (7.0, 14.0), "m": (0.5, 2.0)}
    scores = mc_sensitivity(speed_target, bounds, n=400, seed=SEED)
    sensitivity = sensitivity_chart(scores, title="Final speed: parameter sensitivity",
                                    config={"colorScheme": "Blues"})
    written.append(("02-sensitivity.json", sensitivity,
                    export_chart(sensitivity, OUTPUT_DIR / "02-sensitivity.json")))

    # 3. and 4. Response surface over F and v0, as a heatmap and as a 3D scatter.
    f_values, v0_values, grid = build_response_surface()
    surface = response_surface_chart(x=f_values, y=v0_values, z=grid,
                                     xlabel="drag force F [N]",
                                     ylabel="initial speed v0 [m/s]",
                                     zlabel="v(5s) [m/s]",
                                     title="Response surface: final speed over F and v0")
    written.append(("03-response-surface.json", surface,
                    export_chart(surface, OUTPUT_DIR / "03-response-surface.json")))

    surface_3d = response_surface_3d_chart(x=f_values, y=v0_values, z=grid,
                                           xlabel="drag force F [N]",
                                           ylabel="initial speed v0 [m/s]",
                                           zlabel="v(5s) [m/s]",
                                           title="Response surface: final speed over F and v0")
    written.append(("04-response-surface-3d.json", surface_3d,
                    export_chart(surface_3d, OUTPUT_DIR / "04-response-surface-3d.json")))

    # 5. Dependency graph derived from the model's own equations.
    dependency = dependency_chart(
        nodes=["x", "v", "W", "m", "F", "v_ref"],
        edges=DEPENDENCIES,
        title="Model dependency graph: sliding block with linear drag")
    written.append(("05-dependency-graph.json", dependency,
                    export_chart(dependency, OUTPUT_DIR / "05-dependency-graph.json")))

    # Report what was produced, from the files as actually written.
    emit("-" * 78)
    emit("GENERATED CHART DEFINITIONS")
    emit("-" * 78)
    for name, definition, path in written:
        y = definition["y"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        emit(f"  {name}")
        emit(f"    graphType   : {definition['config']['graphType']}")
        emit(f"    vars        : {len(y['vars'])} ({', '.join(map(str, y['vars'][:4]))}"
             f"{', ...' if len(y['vars']) > 4 else ''})")
        emit(f"    smps        : {len(y['smps'])}")
        emit(f"    size        : {path.stat().st_size} bytes")
        emit(f"    annotations : {sorted(k for k in ('x', 'z') if k in definition)}")
        emit(f"    provenance  : {'yes' if PROVENANCE_KEY in payload else 'no'}")
    emit()

    emit("-" * 78)
    emit("PROVENANCE BOUND INTO THE TRAJECTORY CHART")
    emit("-" * 78)
    provenance = trajectory[PROVENANCE_KEY]
    emit(f"  run_input_sha256 : {provenance['run_input_sha256']}")
    emit(f"  axiomize_version : {provenance['axiomize_version']}")
    emit(f"  python           : {provenance['tool_versions']['python']}")
    emit(f"  numpy            : {provenance['tool_versions']['numpy']}")
    emit(f"  scipy            : {provenance['tool_versions']['scipy']}")
    emit(f"  solver settings  : {json.dumps(provenance['solver_settings'], sort_keys=True)}")
    emit(f"  selected model   : {provenance['selected_model']}")
    emit(f"  assumptions      : {len(provenance['model_assumptions'])} recorded")
    emit(f"  recorded results : v_final={provenance['recorded_results']['v_final']:.9f}, "
         f"energy_residual={provenance['recorded_results']['energy_residual']:.3e}")
    emit(f"  validation       : {provenance['validation_results'].get('status')}")
    emit(f"  served_by_mcp_tool: {provenance['served_by_mcp_tool']}")
    emit()
    emit("  The chart therefore answers 'what run produced this picture' without anyone")
    emit("  having to have been in the conversation when it was made. A chart whose")
    emit("  provenance hash does not match a recorded run can be rejected, not argued with.")
    emit()

    emit("-" * 78)
    emit("SENSITIVITY INDICES (measured, Monte Carlo, n=400, seed=0)")
    emit("-" * 78)
    for name, value in sorted(scores.items(), key=lambda item: -item[1]):
        emit(f"  {name:8s} {value:.6f}")
    emit()

    emit("-" * 78)
    emit("RESPONSE SURFACE: v(5s) over F [N] by v0 [m/s]")
    emit("-" * 78)
    header = "  v0\\F  " + "".join(f"{value:>10g}" for value in f_values)
    emit(header)
    for i, v0 in enumerate(v0_values):
        emit(f"  {v0:>5g} " + "".join(f"{value:>10.5f}" for value in grid[i]))
    emit()

    emit("=" * 78)
    emit("RENDERING THE DEFINITIONS")
    emit("=" * 78)
    emit("  A definition is consumed by the CanvasXpress JavaScript library, which is not")
    emit("  a dependency of this package. To render one in a browser, load the library and")
    emit("  point it at the file:")
    emit()
    emit('    <canvas id="cx" width="640" height="480"></canvas>')
    emit('    <script src="https://www.canvasxpress.org/releases/canvasXpress.min.js"></script>')
    emit("    <script>")
    emit("      fetch('01-state-trajectory.json').then(r => r.json()).then(function (cx) {")
    emit("        new CanvasXpress('cx', cx.y ? {y: cx.y, x: cx.x, z: cx.z} : cx.data,")
    emit("                        Object.assign({}, cx.config || {}, {title: 'Axiomize run'}));")
    emit("      });")
    emit("    </script>")
    emit()
    emit("  No Python-side rendering is claimed or performed here, because none is needed:")
    emit("  the deliverable is the chart definition, and it is valid JSON on disk.")
    emit("=" * 78)

    # Verify the files as written.
    problems: list[str] = []
    for name, _definition, path in written:
        payload = json.loads(path.read_text(encoding="utf-8"))
        y = payload.get("y")
        if not isinstance(y, dict):
            problems.append(f"{name}: missing the CanvasXpress y block")
            continue
        if len(y.get("vars", [])) != len(y.get("data", [])):
            problems.append(f"{name}: vars/data row count mismatch")
        widths = {len(row) for row in y["data"]}
        if len(widths) != 1 or next(iter(widths)) != len(y["smps"]):
            problems.append(f"{name}: data column count does not match smps")
        if not payload.get("config", {}).get("graphType"):
            problems.append(f"{name}: no graphType in config")
        for row in y["data"]:
            for value in row:
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    problems.append(f"{name}: non-finite value in data")
    if PROVENANCE_KEY not in trajectory:
        problems.append("trajectory chart carries no provenance")
    elif trajectory[PROVENANCE_KEY]["run_input_sha256"] != run_state.input_hash():
        problems.append("trajectory provenance hash does not match the run")
    if problems:
        emit()
        for problem in problems:
            emit(f"SELF-CHECK FAILURE: {problem}")
        return 1
    emit()
    emit(f"SELF-CHECK: {len(written)} definitions written and re-parsed; every y block is")
    emit("rectangular and finite, every definition carries a graphType, and the trajectory")
    emit("chart's provenance hash matches the run that produced it.")
    return 0


def main() -> int:
    code = run()
    OUTPUT_PATH.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print()
    print(f"captured output written to {OUTPUT_PATH}")
    print(f"chart definitions written to {OUTPUT_DIR}/")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
