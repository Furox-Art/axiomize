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
[![Python](https://img.shields.io/pypi/pyversions/axiomize)](https://pypi.org/project/axiomize/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Current package line: **1.12.4** (PyPI is the supported install path; see [npm](#npm))

Documentation: **[furox-art.github.io/axiomize](https://furox-art.github.io/axiomize/)** ·
Changelog: **[CHANGELOG.md](CHANGELOG.md)** · Roadmap: **[ROADMAP.md](ROADMAP.md)** ·
Security: **[SECURITY.md](SECURITY.md)** · Contributing: **[CONTRIBUTING.md](CONTRIBUTING.md)** ·
Code of conduct: **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** ·
Cite: **[CITATION.cff](CITATION.cff)**

There is deliberately still no npm version badge: the fix for the npm entry point has landed in
this repository but has not been published yet, so the registry and this README disagree on the
version (see [npm](#npm)).

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

Optional extras: `pip install "axiomize[full]"` (PyMC/JAX Bayesian sampling),
`pip install "axiomize[playground]"` (the Gradio playground).

## Python in five minutes

Declare the model, then let Axiomize check it. Units are mandatory, so dimensional
mistakes fail loudly instead of producing a meaningless number.

```python
from axiomize.general_engine import simulate_model
from axiomize.model_ir import ModelIR

model = ModelIR.from_dict({
    "schema_version": "1.0",
    "name": "sir-outbreak",
    "family": "ode",
    "independent_variable": "t",
    "independent_unit": "day",
    "variables": [
        {"name": "S", "unit": "person", "initial": 990.0, "bounds": [0.0, None]},
        {"name": "I", "unit": "person", "initial": 10.0, "bounds": [0.0, None]},
    ],
    "parameters": [
        {"name": "beta", "unit": "1/day", "value": 0.3},
        {"name": "gamma", "unit": "1/day", "value": 0.1},
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
print(result["status"])
print([round(v, 3) for v in result["states"]["I"]])
```

Real output, reproducible by running `python examples/quickstart_sir.py`:

```text
status: PASS
solver: scipy / DOP853
days:   [0.0, 10.0, 20.0, 30.0]
infected: [10.0, 65.393, 239.869, 290.024]
checks: PASS (25 of them)
```

## CLI in five minutes

No Python required. Every command prints JSON you can pipe.

```bash
pip install axiomize

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

Other surfaces: `axiomize solve` (reference SIR), `axiomize fit` (calibrate from CSV),
`axiomize model --action {plan,validate,simulate,fit,export,numerical-verify}`,
`axiomize serve` (REST, loopback by default), `axiomize mcp` (MCP over stdio).
See [docs/integrations.md](docs/integrations.md).

## Adoption path

1. **Try it on something you already believe.** Recreate a model you trust with
   `axiomize-validate` or one `axiomize model` run. If the engine disagrees with a result
   you can defend, stop here and open an issue.
2. **Move one real question onto Model IR.** Declare units and constraints explicitly. The
   dimensional checks are where the value shows up first.
3. **Gate the expensive steps.** Numerical refinement, mesh refinement, and heavy fitting
   return `APPROVAL_REQUIRED` until you pass `--approve-heavy`. Approval authorizes compute;
   it never disables a resource ceiling.
4. **Export something portable.** `axiomize model --action export` emits canonical Model IR
   JSON plus SBML, CellML, and Modelica for supported models, so the artifact outlives this
   library.
5. **Wire it into review.** Ship the exported IR and the validation record alongside the
   result, not just a figure.

## What it actually does

- Validates dimensional consistency, so you cannot add meters to seconds
- Enforces scientific constraints as named, justified checks rather than prose
- Separates numerical error from stochastic variability before claiming convergence
- Compares candidate model families and records why one was chosen
- Exports to JSON, Python, YAML, notebooks, SBML, CellML, Modelica, GraphML, and LaTeX
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
  or the [18 example files](examples/)
- Domain packs (which lenses matter per field):
  [packs/domain-packs.md](packs/domain-packs.md)
- Agent integration (MCP, REST, CLI): [docs/integrations.md](docs/integrations.md)
- Portable export formats: [docs/portable-export.md](docs/portable-export.md)
- Trust boundaries and reporting: [SECURITY.md](SECURITY.md), [docs/security.md](docs/security.md)
- Agent skill pack: [skills/axiomize/SKILL.md](skills/axiomize/SKILL.md), plus the
  [15 perspective lenses](skills/axiomize/perspectives/)

## npm

`pip install axiomize` is the supported install path. Use npm only if you already depend on it.

The npm `index.js` syntax error is fixed on `main`, and `package.json` is at 1.12.3 in lockstep
with the Python package. **That fix is not published yet.** The npm registry still serves 1.12.2,
whose tarball carries the broken entry point, so `npx axiomize` still fails to load today.

The fix ships with the next release, which publishes the npm shim from the same commit as the
Python distributions. Until that release lands, check
[registry.npmjs.org/axiomize](https://registry.npmjs.org/axiomize) before using npm: if the
reported version is lower than the PyPI version, the registry copy is still the old one. Tracked
in [CHANGELOG.md](CHANGELOG.md).

## License

MIT. Use it, break it, fix it.