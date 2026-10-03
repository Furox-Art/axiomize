# Axiomize

**Reproducible scientific modeling that survives contact with reality.** Axiomize turns a
vague idea into an explicit, versioned mathematical model, validates it dimensionally and
numerically, and exports an artifact someone else can re-run years from now.

This is not the numerical-methods library. That door is [scientific-computing-system](https://github.com/Furox-Art/scientific-computing-system). Axiomize is the modeling layer: mandatory units, a versioned Model IR, and export to SBML, CellML, and Modelica. The MCP server is `axiomize mcp`.

mcp-name: io.github.Furox-Art/axiomize

[![CI](https://github.com/Furox-Art/axiomize/actions/workflows/ci.yml/badge.svg)](https://github.com/Furox-Art/axiomize/actions/workflows/ci.yml)
[![Pages](https://github.com/Furox-Art/axiomize/actions/workflows/pages.yml/badge.svg)](https://furox-art.github.io/axiomize/)
[![PyPI](https://img.shields.io/pypi/v/axiomize)](https://pypi.org/project/axiomize/)
[![PyPI downloads](https://img.shields.io/pypi/dm/axiomize)](https://pypi.org/project/axiomize/)
[![npm](https://img.shields.io/npm/v/axiomize)](https://www.npmjs.com/package/axiomize)
[![Python](https://img.shields.io/pypi/pyversions/axiomize)](https://pypi.org/project/axiomize/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Current package line: **1.12.5** on PyPI and npm.

Documentation: **[furox-art.github.io/axiomize](https://furox-art.github.io/axiomize/)** ·
Changelog: **[CHANGELOG.md](CHANGELOG.md)** · Roadmap: **[ROADMAP.md](ROADMAP.md)** ·
Security: **[SECURITY.md](SECURITY.md)** · Contributing: **[CONTRIBUTING.md](CONTRIBUTING.md)** ·
Code of conduct: **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** ·
Cite: **[CITATION.cff](CITATION.cff)**

## Why

I got tired of scientific models that live in Jupyter notebooks and die there.

Someone writes a beautiful simulation, it works on their machine, they graduate or change
jobs, and six months later nobody can run it. The dependencies are broken, the data is
missing, and the "documentation" is a 47-cell notebook with no explanation.

Axiomize forces models to be explicit, versioned, testable code instead of exploratory
spaghetti. Every assumption is written down. Every parameter carries a unit. Every result
carries enough provenance that another person, on another machine, can reproduce it.

## Who it is for

| If you are… | Start here |
|---|---|
| A scientist whose result has to be defensible in review | [Why](#why) and the [example gallery](https://furox-art.github.io/axiomize/example-gallery/) |
| An engineer sizing capacity, reliability, or inventory | [CLI quickstart](#cli-in-five-minutes) and `axiomize solve` / `axiomize fit` |
| Building an agent that should reason with numbers, not vibes | `axiomize capabilities`, then [MCP or REST](docs/integrations.md) |
| Reproducing or auditing someone else's published model | `axiomize model --action numerical-verify` and [portable export](docs/portable-export.md) |

Not a fit: if you want a black-box predictor with no inspectable assumptions, or if you
need the engine to make scientific claims for you without a human in the loop.

## Install

```bash
pip install axiomize
```

Optional extras: `pip install "axiomize[full]"` for PyMC/JAX Bayesian sampling.

The `playground` extra installs `gradio` and `pandas` but ships no UI: `playground/app.py` is
not in the wheel or the sdist, so `pip install "axiomize[playground]"` alone leaves you with
dependencies and nothing to run. To use it, get the file from the repository:

```bash
git clone https://github.com/Furox-Art/axiomize
pip install "axiomize[playground]"
python axiomize/playground/app.py
```

## Python in five minutes

Declare the model, then let Axiomize check it. Units are mandatory, so dimensional
mistakes fail loudly instead of producing a meaningless number. This block is the model in
[`examples/quickstart_sir.py`](examples/quickstart_sir.py), field for field.

```python
from axiomize.general_engine import simulate_model
from axiomize.model_ir import ModelIR

model = ModelIR.from_dict({
    "schema_version": "1.0",
    "name": "sir-outbreak",
    "domain": "epidemiology",
    "family": "ode",
    "independent_variable": "t",
    "independent_unit": "day",
    "variables": [
        {"name": "S", "unit": "person", "initial": 990.0, "bounds": [0.0, None]},
        {"name": "I", "unit": "person", "initial": 10.0, "bounds": [0.0, None]},
    ],
    "parameters": [
        {"name": "beta", "unit": "1/day", "value": 0.3, "bounds": [0.0, None]},
        {"name": "gamma", "unit": "1/day", "value": 0.1, "bounds": [0.0, None]},
        {"name": "N", "unit": "persons", "value": 1000.0},
    ],
    "equations": [
        {"target": "S", "expression": "-beta*I*S/N", "kind": "derivative"},
        {"target": "I", "expression": "beta*I*S/N - gamma*I", "kind": "derivative"},
    ],
    "constraints": [
        {"name": "cases_nonnegative", "expression": "I", "relation": "ge",
         "threshold": 0.0, "scientific_basis": "case counts cannot be negative"},
    ],
    "assumptions": ["closed population of 1000", "homogeneous mixing"],
})

result = simulate_model(model, t_span=(0.0, 30.0), points=4)
print(f"status: {result['status']}")
print(f"solver: {result['solver']['backend']} / {result['solver']['method']}")
print(f"days:   {result['time']}")
print(f"infected: {[round(v, 3) for v in result['states']['I']]}")
print(f"checks: {result['validation']['status']} ({len(result['validation']['checks'])} of them)")
```

Real output, and byte-identical to `python examples/quickstart_sir.py`:

```text
status: PASS
solver: scipy / DOP853
days:   [0.0, 10.0, 20.0, 30.0]
infected: [10.0, 65.393, 239.869, 290.024]
checks: PASS (25 of them)
```

## CLI in five minutes

Every command prints JSON you can pipe.

```bash
# What is actually installed, and is it usable? Backends report honestly.
axiomize capabilities

# Clarify a vague idea before any numbers get committed.
axiomize intake "Reduce traffic congestion in a mid-size city"

# Check a model against closed-form theory, not just vibes.
axiomize-validate --model sir --beta 0.3 --gamma 0.1
```

`axiomize-validate` output on those inputs:

```text
=== SIR validation ===
horizon                = 180 days  (final-size theory is the t->infinity limit)
R0                     = 3.000  (outbreak)
Peak infected          = 300,465 at day 61.4
Final size (simulated) = 0.9404
Final size (theory)    = 0.9405
Theory match           = True

--- sanity checks ---
population_conserved                PASS
compartments_nonnegative            PASS
R_monotonic_increase                PASS
```

The two flags that matter once you leave the reference model are `--input-json` (the Model IR
request as a file) and `--approve-heavy` (authorizes repeated refinement runs):

```bash
# Without --approve-heavy the study is refused rather than run silently.
axiomize model --action numerical-verify --input-json request.json
# status: APPROVAL_REQUIRED, study: solver_tolerance_refinement

axiomize model --action numerical-verify --input-json request.json --approve-heavy
# status: PASS, uncertainty_separation.numerical: 6.6100987239990846e-11
```

Step-by-step versions of all of this, with the request files, are in
[docs/quickstart.md](docs/quickstart.md).

## Surface map

The engine is 68 public modules behind four interfaces. This README names the whole CLI and
the shape of the two servers; the per-module detail belongs in
[docs/integrations.md](docs/integrations.md).

### Console scripts (8)

| Command | Does |
|---|---|
| `axiomize` | The main CLI. 14 subcommands, below. |
| `axiomize-validate` | Closed-form theory checks for the three reference models: `sir`, `gillespie`, `queue` |
| `axiomize-fit` | Calibrate `sir` or `logistic` against a `time,value` CSV; `--selftest` runs the built-in checks |
| `axiomize-csv-check` | Data quality on an observation file: gaps, duplicates, outliers via modified z-score |
| `axiomize-benchmark` | Grades a produced report against a case in `benchmarks/ideas.json` |
| `axiomize-to-latex` | Converts a standardized report to LaTeX, optionally `--pdf`. **This is the only LaTeX path in the project**; it is not a model export format. |
| `axiomize-index-reports` | Rebuilds `reports/INDEX.md` from the reports in a directory |
| `axiomize-sweep` | Parallel parameter sweeps (`--job sweep`, `--job mc`) |

### `axiomize` subcommands (14)

`intake` · `policy` · `model` · `clean-data` · `compare-runs` · `solve` · `fit` ·
`validate` · `tools` · `capabilities` · `reproduce` · `benchmark` · `serve` · `mcp`

`tools` and `capabilities` report backend availability; `policy` reports what the agent is
allowed to spend; `reproduce` and `compare-runs` work on stored run directories.

### `axiomize model --action` (16)

| Family | Values |
|---|---|
| Model lifecycle | `plan` · `validate` · `simulate` · `fit` · `compare` · `repair` · `export` |
| Analysis | `stability` · `validity` · `discover` · `experiment-design` · `uncertainty` · `bifurcation` |
| Verification | `numerical-verify` · `stop-check` · `surrogate` |

### MCP and REST

The MCP server exposes **34 tools** named `axiomize.<verb>`. `axiomize.model_*` mirrors the
`model --action` values above; the unprefixed names (`solve`, `fit_model`, `cross_validate`,
`sensitivity_analysis`, `uncertainty_analysis`, `falsify`, `compare_models`, `intake`,
`workflow_policy`, `clean_data`, `compare_runs`, `experiment_design`, `inspect_run`,
`reproduce`, `get_capabilities`, `list_tools`, `select_tools`) cover the surrounding
workflow. Enumerate them rather than trusting a list:

```bash
axiomize mcp        # stdio transport; send tools/list over stdin
```

The REST server serves **30 route handlers** (26 POST, plus GET `/tools`, `/capabilities`,
`/workflow-policy` and `/runs/{id}`) under a `/v1` prefix, on loopback by default:

```bash
axiomize serve --port 8765
curl -s http://127.0.0.1:8765/v1/capabilities
```

Both surfaces are larger than any README can enumerate honestly, which is why the naming
convention matters more than the list. Both counts come from the installed handlers.

### Model export formats

`axiomize model --action export --input-json request.json` dispatches on the `"format"`
field. What actually returns `PASS` for a given model:

| Format | Status | Notes |
|---|---|---|
| `json` | yes | Canonical Model IR, sorted keys |
| `python` | yes | Rerunnable script that re-imports the IR |
| `yaml` | yes | Needs PyYAML; otherwise `TOOL_UNAVAILABLE` |
| `ipynb` | yes | nbformat 4 notebook |
| `sbml-l3v2` | yes | SBML Level 3 Version 2 Core |
| `modelica` | yes | Modelica 3.6 text |
| `portable-bundle` | yes | `axiomize.portable-bundle.v1` with a SHA-256 over canonical IR |
| `graphml` | conditional | Needs `family: network` IR with `metadata.network` |
| `causal-dot` | conditional | Needs `family: causal` IR with identification metadata |
| `cellml-2.0` | conditional | Passes for supported units; `ADAPTER_REQUIRED` naming the ones it will not reinterpret |
| `sbml`, `cellml` | no | Unversioned aliases deliberately return `ADAPTER_REQUIRED` |

LaTeX is **not** in this dispatch chain. `latex`, `tex` and `pdf` raise
`ValueError: format must be json, python, yaml, sbml, or cellml`. Use
`axiomize-to-latex` on a written report instead.

### Content in the repository

| What | Where | Count |
|---|---|---|
| Domain packs | [packs/](packs/domain-packs.md) | 12 |
| Perspective lenses | [skills/axiomize/perspectives/](skills/axiomize/perspectives/) | 15 |
| Report templates | [skills/axiomize/templates/](skills/axiomize/templates/) | 5 |
| Worked examples | [examples/](examples/) | 18 `.md` + `quickstart_sir.py` |
| MCP registry manifest | [server.json](server.json) | 1 |

`server.json` is what the MCP registry reads to publish `axiomize mcp`; its `mcp-name` line
is repeated at the top of this README for clients that scrape it.

## Adoption path

1. **Try it on something you already believe.** Recreate a model you trust with
   `axiomize-validate`. If the engine disagrees with a result you can defend, stop here and
   open an issue.
2. **Move one real question onto Model IR.** Declare units and constraints explicitly. The
   dimensional checks are where the value shows up first.
3. **Gate the expensive steps.** Discretized families return `APPROVAL_REQUIRED` until you
   pass `--approve-heavy`. Approval authorizes compute; it never disables a resource ceiling.
4. **Export something portable.** `axiomize model --action export` emits canonical IR JSON,
   and SBML, CellML or Modelica for supported models, so the artifact outlives this library.
5. **Wire it into review.** Ship the exported IR and the validation record alongside the
   result, not just a figure.

## What it actually does

- Validates dimensional consistency, so you cannot add meters to seconds
- Enforces scientific constraints as named, justified checks rather than prose
- Separates numerical error from stochastic variability before claiming convergence
- Compares candidate model families and records why one was chosen
- Exports to JSON, Python, YAML, notebooks, SBML Level 3, CellML 2.0, Modelica, GraphML,
  Graphviz DOT and a SHA-256 portable bundle; see the [format table](#model-export-formats)
  for which of those are conditional
- Converts written reports to LaTeX via `axiomize-to-latex`, which is a separate path
- Keeps an integrity-checked run ledger, so a stored result can be verified before use

## Honest limits

- It does not make a bad model good. It makes a bad model fail loudly.
- Bayesian sampling needs the `full` extra (PyMC/JAX); FEM needs FEniCS/DOLFINx. Both are
  reported as unavailable rather than silently substituted.
- [Benchmark results](docs/benchmark-results.md) grade report *structure* in blind runs, not
  modeling correctness. Only the table carrying script, case-set and commit hashes is
  reproducible; the older waves are kept as history and cannot be rerun.
- Worked examples use illustrative parameter ranges labelled `lit.` / `data` / `est.`. No
  example cites an external source, so treat the numbers as reading material rather than
  literature-backed results.
- Generated-code execution and theorem elaboration are not an OS sandbox. See
  [SECURITY.md](SECURITY.md).

## Documentation

- Quickstart and workflow: [furox-art.github.io/axiomize](https://furox-art.github.io/axiomize/)
- Worked examples: [example gallery](https://furox-art.github.io/axiomize/example-gallery/),
  or the [19 files in `examples/`](examples/)
- Domain packs (which lenses matter per field):
  [packs/domain-packs.md](packs/domain-packs.md)
- Agent integration (MCP, REST, CLI): [docs/integrations.md](docs/integrations.md)
- Portable export formats: [docs/portable-export.md](docs/portable-export.md)
- Trust boundaries and reporting: [SECURITY.md](SECURITY.md), [docs/security.md](docs/security.md)
- Agent skill pack: [skills/axiomize/SKILL.md](skills/axiomize/SKILL.md), plus the
  [15 perspective lenses](skills/axiomize/perspectives/)

## npm

`npx axiomize` works and forwards to `python -m axiomize.cli`, so it needs Python and
`pip install axiomize` underneath; it is not a standalone binary. npm `1.12.2` is published
and broken (`index.js` had a syntax error); `1.12.4` is the first working release. PyPI
`1.12.4` carries PEP 740 attestations, the npm tarball does not. Full detail, including
verification commands and how to tell registry metadata signatures from provenance:
[docs/documentation.md](docs/documentation.md#supply-chain-attestations-what-exists-and-what-does-not).

## License

MIT. Use it, break it, fix it.
