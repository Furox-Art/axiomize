# Axiomize

**Reproducible scientific modeling that survives contact with reality.**

Axiomize turns a vague idea into an explicit, versioned mathematical model, validates it
dimensionally and numerically, and exports an artifact someone else can re-run years from
now. Units are mandatory, constraints are named and justified, and expensive steps ask
before they run.

## Start here

- New to the project: [Quickstart](quickstart.md) — install to validated result in five minutes.
- Want to see it done well: [Example gallery](example-gallery.md).
- Wiring it into an agent: [Integrations](integrations.md) (MCP, REST, CLI).
- Deciding whether to trust it with a real model: [Security](security.md) and
  [SECURITY.md](https://github.com/Furox-Art/axiomize/blob/main/SECURITY.md) first.

## The two ways to use it

**As a Python library and CLI.** `pip install axiomize` gives you the `axiomize` console
entry point, the Model IR engine, and REST/MCP servers.

```bash
pip install axiomize
axiomize capabilities        # which backends are actually usable here
axiomize intake "your idea"  # clarify before committing to numbers
```

**As an agent skill.** Copy `skills/axiomize/` into your agent's skills directory
(`~/.config/opencode/skills/` for opencode, `~/.claude/skills/` for Claude Code) and ask
in plain language: *"Model this idea mathematically: my gym keeps losing members after
three months; how do I stop the churn?"*

Both paths use the same engine and the same validation contract, so results do not depend
on which surface you call.

## What you get

- Dimensional validation, so you cannot add meters to seconds
- Scientific constraints as named, justified checks with a scientific basis
- Numerical verification that separates discretization error from stochastic variability
- Model-family comparison with recorded reasoning for the choice
- Portable export: Model IR JSON, Python, YAML, notebooks, SBML, CellML, Modelica, GraphML
- An integrity-checked run ledger for stored results

## What it does not do

It does not make a weak model strong. It makes a weak model fail early and visibly.
Bayesian sampling requires the `full` extra and FEM requires FEniCS/DOLFINx; both are
reported as unavailable rather than silently replaced by something weaker.

![SIR demo](sir-demo.gif)

## Project links

- Repository: [github.com/Furox-Art/axiomize](https://github.com/Furox-Art/axiomize)
- Changelog: [CHANGELOG.md](https://github.com/Furox-Art/axiomize/blob/main/CHANGELOG.md)
- Contributing: [CONTRIBUTING.md](https://github.com/Furox-Art/axiomize/blob/main/CONTRIBUTING.md)
- License: [MIT](https://github.com/Furox-Art/axiomize/blob/main/LICENSE)