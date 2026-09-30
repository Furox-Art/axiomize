# Tutorials

Real workflows against the real API. Every code block here runs against the installed
package; the quickstart commands are additionally re-executed by CI via
[`.github/scripts/readme_example_check.py`](https://github.com/Furox-Art/axiomize/blob/main/.github/scripts/readme_example_check.py).

If you want the shortest verified path, start at [quickstart.md](quickstart.md).

## 1. Your first model in five minutes

Build a model, run it, and read the validation record. The full annotated version with
real output is [quickstart.md](quickstart.md) and
[`examples/quickstart_sir.py`](https://github.com/Furox-Art/axiomize/blob/main/examples/quickstart_sir.py).

The shape is always the same:

```python
from axiomize.general_engine import simulate_model
from axiomize.model_ir import ModelIR

model = ModelIR.from_dict({
    "schema_version": "1.0",
    "name": "sir-outbreak",
    "family": "ode",
    "independent_variable": "t",
    "independent_unit": "day",
    "variables": [{"name": "S", "unit": "person", "initial": 990.0}],
    "parameters": [{"name": "gamma", "unit": "1/day", "value": 0.1}],
    "equations": [{"target": "S", "expression": "-gamma*S", "kind": "derivative"}],
    "assumptions": ["closed population"],
})

result = simulate_model(model, t_span=(0.0, 10.0), points=3)
print(result["status"], result["states"]["S"])
```

Declare units on every variable, parameter, and equation target. The dimensional checks
reject a model that is missing them, which is the point: an undeclared unit is an
assumption you have not admitted to making.

## 2. Fit parameters to your own data

Write a CSV with `time,value` columns, then calibrate:

```bash
axiomize fit --data observations.csv
```

The output contains the fitted parameters and fit-quality diagnostics. For scientific
engines backed by real solvers rather than closed forms, use the Model IR path:

```bash
axiomize model --action fit --input-json fit-request.json
```

Start from [clean-data](https://github.com/Furox-Art/axiomize/blob/main/docs/integrations.md)
when your observations have gaps or duplicates; the returned `audit` field records what
changed.

## 3. Compare model families before committing

```bash
axiomize model --action plan --input-json idea.json
```

You get ranked candidate families with a reason for each rank, and an explicit
`next_contract` describing what a real model must supply. Ranking is a proposal, not a
decision: the reasons are there so you can overrule it.

## 4. Check the numerics, not just the output

```bash
axiomize model --action numerical-verify --input-json request.json --approve-heavy
```

Discretized families return `APPROVAL_REQUIRED` until you pass `--approve-heavy`. The
result separates numerical error from stochastic variability, because reporting one as
the other is the most common way a converging result is still wrong.

For a quick check against closed-form theory with no model of your own:

```bash
axiomize-validate --model sir --beta 0.3 --gamma 0.1
```

## 5. Export for review or for another tool

```bash
axiomize model --action export --input-json request.json
```

The request JSON selects the format (`"format": "sbml-l3v2"`, `"cellml-2.0"`,
`"modelica"`, `"graphml"`, `"json"`, `"python"`, `"yaml"`, `"ipynb"`). The response echoes
the format, the standard it targets, and a `validation` record stating what was and was not
verified: for the XML formats, that is well-formedness only, since full schema validation
needs `python-libsbml`.

Supported formats and their honest limitations are in
[portable-export.md](portable-export.md). Export the IR alongside the number you publish,
so a reviewer can re-run the check instead of trusting the figure.

## 6. Wire it into an agent

MCP over stdio, a loopback REST API, and the CLI all call the same core services, so
validation behavior does not depend on the caller. Setup and the tool list are in
[integrations.md](integrations.md).

```bash
axiomize capabilities   # what is installed and usable right now
axiomize policy         # what the agent is and is not permitted to spend
```

## Where to go deeper

- [Example gallery](example-gallery.md) for full worked problems per domain
- [Beginner walkthrough](tutorial.md) for the agent-skill path with no Python
- [Benchmark results](benchmark-results.md) for what the scoring does and does not prove