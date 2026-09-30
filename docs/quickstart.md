# Quickstart

A five-minute path from install to a validated result. Every command below is
executed by [`.github/scripts/readme_example_check.py`](https://github.com/Furox-Art/axiomize/blob/main/.github/scripts/readme_example_check.py)
on every CI run, so this page cannot drift from real behavior without failing the build.

## 1. Install

```bash
pip install axiomize
```

Verify the install, including which optional scientific backends are actually
usable in your environment. Backends report honestly rather than silently
substituting a weaker method:

```bash
axiomize capabilities
```

Requires Python 3.10 or newer. Optional extras: `axiomize[full]` for PyMC/JAX
Bayesian sampling, `axiomize[playground]` for the Gradio playground.

## 2. Clarify the idea before committing to numbers

```bash
axiomize intake "Reduce traffic congestion in a mid-size city"
```

The response is JSON with a `status`, a clarifying `questions` array, and a
`rigor_recommendation`. A vague idea yields `NEEDS_INPUT`; a specific one yields
`READY`. This is the same intake the agent skill uses, exposed on the CLI and
over REST and MCP.

## 3. Run a model

The runnable version of this example is
[`examples/quickstart_sir.py`](https://github.com/Furox-Art/axiomize/blob/main/examples/quickstart_sir.py).

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

```text
status: PASS
solver: scipy / DOP853
days:   [0.0, 10.0, 20.0, 30.0]
infected: [10.0, 65.393, 239.869, 290.024]
checks: PASS (25 of them)
```

Note what the engine did and did not do. It refused the model until every
variable, parameter, and equation carried a unit, then ran 25 structural and
dimensional checks before integrating. It did not verify that a closed
1000-person population is the right model for your city.

## 4. Check against theory, not just plausibility

The strongest cheap check is agreement with a closed-form result:

```bash
axiomize-validate --model sir --beta 0.3 --gamma 0.1
```

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

Simulation final size (0.9404) matches final-size theory (0.9405). Conservation
holds to machine precision. A model that disagrees with theory here is broken;
one that agrees has at least earned the right to be debated on its assumptions.

## 5. Gate the expensive steps

Discretized families return `APPROVAL_REQUIRED` until you opt in:

```bash
axiomize model --action numerical-verify --input-json request.json --approve-heavy
```

Approval authorizes compute. It never disables a resource ceiling. The engine
separates numerical error from stochastic variability before reporting
convergence, because those two are routinely conflated.

## 6. Export something portable

```bash
axiomize model --action export --input-json request.json
```

Canonical Model IR JSON, plus SBML Level 3, CellML 2.0, Modelica, GraphML, a
rerunnable Python script, or a notebook. Supported formats and their limits are
listed in [portable-export.md](portable-export.md).

## Where to go next

| Goal | Page |
|---|---|
| See a full worked example per domain | [Example gallery](example-gallery.md) |
| Understand the agent workflow and rigor ladder | [Rigor ladder](rigor.md), [Archetypes](archetypes.md) |
| Wire it into an agent | [Integrations](integrations.md) |
| Know what is and is not a security boundary | [Security](security.md), [SECURITY.md](https://github.com/Furox-Art/axiomize/blob/main/SECURITY.md) |
| Understand what the benchmarks do and do not prove | [Benchmark results](benchmark-results.md) |