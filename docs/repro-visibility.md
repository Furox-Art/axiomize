# Physical plausibility, reproducibility and interactive charts

Dimensional consistency is necessary but not sufficient, a run is only reproducible if its record
says what was assumed and what it was solved with, and a chart is only evidence if it can be traced
to the run that produced it. This page covers three committed, runnable examples that address those
three gaps, plus the CanvasXpress export module they exercise.

Every number below was captured from a real run on Linux, Python 3.12.3, Axiomize 1.12.5,
scipy 1.11.4 / DOP853. The `*_output.txt` file next to each script is that capture, and each script
exits non-zero if its own committed output stops describing current engine behaviour.

## Reproducing this page

From a clean checkout, with the repository root as the working directory:

```bash
python examples/physical_plausibility_validation.py
python examples/reproducibility_run_record.py
python examples/canvasxpress_export_example.py
python -m pytest tests/test_canvasxpress_export.py -q
```

Each script prints its report, rewrites its own `*_output.txt` and prints a `SELF-CHECK` line. A
clean run exits `0` for all four commands. No editable install is required: the examples put
`src/` on `sys.path` themselves, which is how a reader who has just cloned the repository runs them.

## 1. Dimensional analysis passes, the physics still fails

`examples/physical_plausibility_validation.py` runs three models that share one Model IR shape, one
unit table and one solver. They differ only in the sign and the magnitude of a drag force:

| Model | `dv/dt` | Verdict |
|---|---|---|
| `CORRECT` | `-(F/m)*v/v_ref` | passes everything |
| `WRONG_SIGN` | `+(F/m)*v/v_ref` | accelerates without external work |
| `WRONG_SCALE` | `-2*(F/m)*v/v_ref` | books less heat than the block loses |

A 1 kg block slides on a level surface at 20 m/s against linear drag, so no external work crosses
the boundary. Total energy must hold at `0.5*m*v^2 + W == 0.5*m*v0^2 = 200 J` for all `t`. Because
`F/m` is m/s² and `v/v_ref` is dimensionless, all three models pass the unit checks identically.
Measured, not asserted:

```
model           engine    falsification     energy_residual[J]   closed_form_err
CORRECT         PASS      PASS                    2.129127e-09      1.954190e-11
WRONG_SIGN      PASS      FAIL                    5.896526e+04      1.210041e+01
WRONG_SCALE     PASS      FAIL                    9.999546e+01      2.499883e-01
```

All three report `structural checks: 25 run, 25 PASS, 0 FAIL` and `unit checks: 7 run, all PASS`.
Conservation of energy and a closed-form reference separate them anyway.

`WRONG_SCALE` is the interesting case: its speed trace looks entirely plausible, it never exceeds
its initial speed, and its heat is monotone. It simply decays twice as fast as the drag law it
declares, so the energy ledger settles at 100 J instead of 200 J. Only the conservation ledger or the
closed form catches it.

### Numerical error is not model error

The energy ledger closes to `2.1e-09` J, not to machine precision, and it should not be expected to:
`solve_ivp` integrates a discretized system. The example tightens the tolerance four times and shows
the residual shrinking at every step:

```
      rtol     atol    nfev   energy_residual[J]    closed_form_err
     1e-07    1e-09     131         1.185912e-06       1.206840e-08
     1e-08    1e-10     143         1.543693e-07       1.494671e-09
     1e-10    1e-12     203         2.129127e-09       1.954190e-11
     1e-12    1e-14     320         2.469847e-11       2.086109e-13
```

The falsification threshold is set *above* the residual at the settings actually used, so a
discretization artefact is never reported as a scientific failure. The broken models miss by roughly
`1.0e+02` and `5.9e+04` J, which is not a tolerance question.

Each verdict is a named observable, a threshold and a direction evaluated against measured output
through `axiomize.falsification`, with the scientific law recorded on the falsifier itself
(`conservation_of_energy`, `passivity`, `second_law_of_thermodynamics`, `experimental_reference`).

## 2. What a reproducibility record has to contain

`examples/reproducibility_run_record.py` builds a run record for the same model and then re-executes
the stored computation to confirm the outputs still match. Captured metadata, measured rather than
asserted:

```
run_format_version : 1
axiomize_version   : 1.12.5
input_hash         : cdc76fecdc5b892d6c76cd730a17f73651e9355df86ec28793e215c964bed1c4
```

Assumptions, equations, solver settings and tolerances are recorded alongside the seed and the
version of every backend. Backends that are not installed say so rather than guessing:

```
python 3.12.3   axiomize 1.12.5   numpy 1.26.4   scipy 1.11.4   sympy 1.12
z3 not-installed   control not-installed   cvxpy not-installed   casadi not-installed
```

The run directory is integrity-hashed, and the hash is recomputed independently on load:

```
declared run_sha256 : 12df316892d86794701ad0dddfe78aa75f84fbc904dd0f431a9669d4b0ed1430
actual run_sha256   : 12df316892d86794701ad0dddfe78aa75f84fbc904dd0f431a9669d4b0ed1430
integrity match     : True
```

Re-executing the stored computation reproduces the trajectory bit-for-bit:

```
trajectory identical bit-for-bit: True
max |v_recorded - v_rerun|  : 0.000e+00 m/s
v_final recorded / rerun    : 1.641699972490 / 1.641699972490
rhs evaluations recorded / rerun: 203 / 203
```

Finally `compare_run_states` is run twice. Two identical runs report no difference; a record with one
loosened tolerance is explained rather than merely flagged:

```
a) two runs of the same computation
   same_input_hash : True
   same_results    : True
   likely_reasons  : ['no recorded reproducibility difference detected']

b) same model, one solver tolerance loosened (rtol 1e-10 -> 1e-7)
   same_input_hash : True
   differences     : ['solver_settings']
   likely_reasons  : ['solver/numerical settings changed']
   solver_settings delta:
     atol: 1e-12 -> 1e-09
     rtol: 1e-10 -> 1e-07
```

This is the property that makes cross-environment comparison discussable: `inputs differ`,
`tool_versions changed` and `solver settings changed` are named distinctly instead of collapsing into
`results do not match`.

## 3. CanvasXpress chart definitions with provenance

`src/axiomize/visualization/canvasxpress_export.py` builds CanvasXpress JSON definitions from the same
numeric results the rest of the engine produces, so an interactive chart can never be built from a
number that is not also recorded in the run. Two properties are deliberate.

**No silent invention.** Every value passes the same finite/shape checks the simulation path uses. A
NaN, a ragged matrix or a misaligned annotation raises instead of producing a chart that silently
drops rows. CanvasXpress would otherwise misalign every sample rather than discard the annotation.

**Charts carry their own provenance.** `attach_run_record` binds the input hash, recorded results,
validation outcome, assumptions, solver settings and tool versions into the definition under a
reserved `axiomize` key, which CanvasXpress ignores. A chart can therefore be audited without the
conversation that produced it.

The Matplotlib helpers in `axiomize.visualization.plots` are untouched and still produce PNGs. This
module is additive, emits JSON only, and needs no browser, JavaScript runtime or optional backend.

`examples/canvasxpress_export_example.py` drives it from a real run and writes five definitions:

| File | `graphType` | vars × smps | bytes |
|---|---|---|---|
| `01-state-trajectory.json` | `Line` | 2 × 41 | 12534 |
| `02-sensitivity.json` | `Bar` | 3 × 1 | 577 |
| `03-response-surface.json` | `Heatmap` | 5 × 6 | 1656 |
| `04-response-surface-3d.json` | `Scatter3D` | 3 × 30 | 2499 |
| `05-dependency-graph.json` | `Network` | 6 × 6 | 965 |

The trajectory chart carries the run's provenance:

```
run_input_sha256 : cdc76fecdc5b892d6c76cd730a17f73651e9355df86ec28793e215c964bed1c4
axiomize_version : 1.12.5
python           : 3.12.3   numpy 1.26.4   scipy 1.11.4
selected model   : sliding-block-linear-drag
assumptions      : 3 recorded
recorded results : v_final=1.641699972, energy_residual=2.034e-09
validation       : PASS
served_by_mcp_tool: model_visualize
```

A chart whose provenance hash does not match a recorded run can be rejected, not argued with.

Sensitivity indices come from the engine's own Monte Carlo screening (`n=400`, `seed=0`), and the
response surface is a real 6 × 5 scan of final speed over drag force and initial speed:

```
SENSITIVITY INDICES (measured, Monte Carlo, n=400, seed=0)
  m        0.421212
  F        0.357640
  v_ref    0.221149

RESPONSE SURFACE: v(5s) over F [N] by v0 [m/s]
  v0\F           2         4         6         8        10        12
     10    3.67879   1.35335   0.49787   0.18316   0.06738   0.02479
     15    5.51819   2.03003   0.74681   0.27473   0.10107   0.03718
     20    7.35759   2.70671   0.99574   0.36631   0.13476   0.04958
     25    9.19699   3.38338   1.24468   0.45789   0.16845   0.06197
     30   11.03638   4.06006   1.49361   0.54947   0.20214   0.07436
```

### Rendering

A definition is consumed by the CanvasXpress JavaScript library, which is not a dependency of this
package:

```html
<canvas id="cx" width="640" height="480"></canvas>
<script src="https://www.canvasxpress.org/releases/canvasXpress.min.js"></script>
<script>
  fetch('01-state-trajectory.json').then(r => r.json()).then(function (cx) {
    new CanvasXpress('cx', cx.y ? {y: cx.y, x: cx.x, z: cx.z} : cx.data,
                    Object.assign({}, cx.config || {}, {title: 'Axiomize run'}));
  });
</script>
```

No Python-side rendering is claimed or performed: the deliverable is the chart definition, and it is
valid JSON on disk.

## 4. Tests

`tests/test_canvasxpress_export.py` pins the shape of the emitted JSON, the refusal behaviour on data
that would silently lose rows, the provenance binding, and the ranking parity with the Matplotlib
helper so a chart and a PNG can never disagree. It needs no browser, JavaScript runtime or optional
visualization backend.

```bash
python -m pytest tests/test_canvasxpress_export.py -q
```

26 tests pass. The module is additionally mypy-clean and adds no ruff findings.

## MCP sensitivity chart from a recorded run

The chart exporter remains usable as Python functions for all five chart types. A lightweight
MCP wrapper adds the specific Reddit proof-of-concept mapping without guessing any results:

```python
from axiomize.runs.state import RunState
from axiomize.server.mcp_server import call_tool

run = RunState(sensitivity_results={"K_cat": 0.82, "K_m": -0.44, "E_tot": 0.21})
run.save("runs/experiment-001")
response = call_tool("axiomize.model_visualize", {"run_dir": "experiment-001"}, run_root="runs")
chart = response["chart"]           # CanvasXpress-compatible data/config only
metadata = response["metadata"]     # stored tool versions, input and chart SHA-256
```

The renderer can consume `chart["data"]` and `chart["config"]`. A separate
`metadata` object avoids relying on CanvasXpress accepting arbitrary application keys.
The only currently dispatched `chart_type` is `"sensitivity"`; trajectory, heatmap,
Scatter3D and network exporters are available as Python functions, not MCP chart types yet.
Non-finite scores, path traversal, missing manifests and modified run payloads are rejected.
The MCP integration is exercised by `tests/test_canvasxpress_mcp.py`; no external browser
test or CanvasXpress package is needed for its JSON/schema contracts.

## What this does not establish

- The three examples run one model family (linear ODE) on one machine. Cross-environment comparison
  is prepared for — `compare_run_states` names the changed setting — but this repository does not yet
  carry an executed cross-environment diff.
- Reproducibility is verified within a single environment. Trajectories match bit-for-bit here;
  numerical agreement across different BLAS, scipy or platform builds is not asserted.
- The charts are validated as JSON definitions and re-parsed after writing. They are not rendered
  here, because rendering needs the external CanvasXpress library and a browser.
- The `axiomize.model_visualize` MCP tool now reads an integrity-checked stored run beneath
  the configured run root and emits a CanvasXpress sensitivity bar definition plus separate
  provenance metadata. The tool is read-only, rejects missing sensitivity scores, and does not
  claim browser rendering. The `chart_spec_sha256` covers canonical UTF-8 JSON of the
  `chart` renderer payload only; its metadata retains the originally recorded `input_hash`,
  `run_sha256`, solver settings and tool versions. The saved manifest is integrity-checked
  against `run.json`, but without a digital signature its metadata is not an authenticity proof.
