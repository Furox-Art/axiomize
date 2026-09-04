# Axiomize

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-informational)
![CI](https://github.com/Furox-Art/axiomize/actions/workflows/ci.yml/badge.svg)

**Turn a vague idea into multiple rigorous, testable mathematical models.**

Axiomize is an Agent Skill plus a Python scientific engine for Claude Code, opencode, Cursor and other compatible agents. It clarifies missing mechanisms, recommends an analysis depth, builds competing models from multiple mathematical lenses, fits and validates them with real scientific tools, reports uncertainty honestly, and records enough state to reproduce the work.

Version **1.7** adds an adaptive, user-controlled workflow: Axiomize may manage the scientific analysis, but it does not silently spawn extra agents, repeat the whole analysis, or multiply paid/provider calls.

![SIR epidemic curve animation](docs/sir-demo.gif)

## What happens when you give it an idea

```text
idea
 │
 ├── clarify missing system / goal / measurement / horizon / mechanism
 ├── recommend weak / medium / strong depth
 ├── identify required data and assumptions
 ├── build several defensible candidate models
 ├── fit / simulate / optimize with real scientific tools
 ├── compare and rank the best 2–3 models
 ├── search for errors, conflicts and invalid assumptions
 ├── quantify uncertainty and sensitivity
 ├── visualize behavior and variable interactions
 ├── produce falsifiers + testable hypotheses / experiment plan
 └── record a reproducible run
```

If the core mechanism is unclear, Axiomize says so and asks for the missing information instead of hiding the uncertainty inside an equation.

## Adaptive depth

Axiomize recommends the level automatically and tells you why. You can override it.

| Level | Intended use | What changes |
|---|---|---|
| **weak** | quick exploration, low-stakes/simple problems | lightweight candidate models and core checks |
| **medium** | default scientific analysis | formal models, fitting/validation, uncertainty, sensitivity |
| **strong** | research, high stakes, unclear mechanisms, conflicting models, causal/experimental work | more independent tools, cross-checks, model criticism, stronger UQ and reproducibility |

Legacy names remain accepted by the Python API: `basic → weak`, `standard → medium`, `research → strong`.

Strong mode means **more evidence and verification**, not merely longer prose.

## Clarification is user-controlled

Axiomize can ask missing questions:

- one at a time; or
- all at once.

If no preference is known, it defaults to one short question at a time.

```bash
axiomize intake "A city wants to reduce traffic congestion"
```

Once the system boundary, goal, measurable outcome, horizon and mechanism are sufficiently clear, the intake returns a ready scientific workflow plan.

## Multiple models, not one plausible guess

Axiomize does not force the first reasonable equation it finds. Whenever possible it builds multiple candidates, then reports:

1. the strongest 2–3 models in rank order;
2. why each ranks where it does;
3. under which conditions each becomes the better choice;
4. why weaker candidates were rejected;
5. what observation would falsify each important claim.

If methods or tools disagree, the disagreement is exposed and investigated rather than averaged away.

## Fifteen mathematical lenses

| Lens | Typical questions | Core methods |
|---|---|---|
| [Deterministic](skills/axiomize/perspectives/deterministic.md) | trends, equilibria, thresholds | ODEs, difference equations, stability |
| [Stochastic](skills/axiomize/perspectives/stochastic.md) | risk, rare events, random dynamics | Markov chains, Monte Carlo |
| [Optimization](skills/axiomize/perspectives/optimization.md) | best decision under constraints | LP/NLP/ILP |
| [Agent-based](skills/axiomize/perspectives/agent-based.md) | emergence from local rules | agent simulations |
| [Network](skills/axiomize/perspectives/network.md) | interaction topology | graphs, centrality, network dynamics |
| [Control](skills/axiomize/perspectives/control.md) | steering a system | feedback, stability margins |
| [Game theory](skills/axiomize/perspectives/game-theory.md) | strategic interaction | equilibria, mechanisms |
| [Causal inference](skills/axiomize/perspectives/causal-inference.md) | intervention effects | DAGs, DiD, IV, adjustment |
| [Information theory](skills/axiomize/perspectives/information-theory.md) | information limits | entropy, mutual information |
| [Reliability](skills/axiomize/perspectives/reliability.md) | failure and maintenance | hazards, renewal models |
| [SPC](skills/axiomize/perspectives/spc.md) | signal vs noise | control charts, EWMA/CUSUM |
| [Thermodynamic analogies](skills/axiomize/perspectives/thermodynamic.md) | stock-flow constraints | conservation and resistance maps |
| [Decision theory](skills/axiomize/perspectives/decision-theory.md) | choices under deep uncertainty | payoff models, EVPI, maximin |
| [Demographic / actuarial](skills/axiomize/perspectives/demographic.md) | populations and liabilities | life tables, Leslie matrices |
| [Spatial statistics](skills/axiomize/perspectives/spatial.md) | geographic patterns | Moran's I, LISA, kriging |

The lenses can compose; Axiomize selects only the ones that materially help the problem.

## Scientific tool stack

The Python engine probes tools live and never claims an unavailable backend ran.

Core package:

- NumPy
- SciPy
- SymPy
- statsmodels
- NetworkX
- Matplotlib (2D + 3D visualization)
- Z3
- python-control
- CVXPY
- CasADi

Optional heavy backends:

```bash
pip install axiomize[full]
```

adds PyMC and JAX when available. Lean and FEniCS are probed as external/optional backends and report unavailable explicitly when absent.

Inspect the current environment:

```bash
axiomize tools
axiomize capabilities
```

The router maps explicit problem signals to the real installed stack: e.g. convex optimization → CVXPY, nonlinear optimization → CasADi, regression → statsmodels/SciPy, logical constraints → Z3, formal proofs → Lean when available.

## Data quality and fitting

Axiomize's adaptive data layer follows a conservative rule: **never silently destroy the original data**.

It can:

- remove structurally invalid/non-finite rows with a recorded audit trail;
- sort time coordinates when required;
- merge duplicate time points under an explicit policy;
- flag possible outliers without deleting them automatically;
- preserve original and cleaned arrays;
- warn when cleaning materially changes the dataset;
- compare candidate fits using diagnostics such as residuals and BIC when statistically appropriate.

Bundled reference fitting commands remain available:

```bash
python skills/axiomize/tools/fit.py --model sir --data mycases.csv --plot fit.png
python skills/axiomize/tools/fit.py --model logistic --data adoption.csv
```

## Visualization

Matplotlib is a core dependency in 1.7. The engine includes helpers for:

- ranked sensitivity plots;
- 3D response surfaces;
- directed variable/mechanism dependency graphs.

Visuals are intended to explain both the result and **how variables affect each other**, not merely decorate the report.

## Hypotheses and empirical testing

For engineering, biology, physics, chemistry and other empirical domains, Axiomize converts the model into a testable hypothesis and states:

- expected observation if the hypothesis is true;
- observation that would refute it;
- data/measurement needed;
- experiment/test design;
- validity domain and failure modes.

When a physical experiment is costly, dangerous or destructive, the workflow prefers simulation/virtual testing first when feasible. If a hypothesis fails, Axiomize can generate and rank replacement hypotheses and say what evidence would distinguish them.

## User-controlled consumption

Axiomize does **not** silently expand the number of agents or paid calls.

These actions require explicit permission unless the user already requested them:

- spawning extra agents/subtasks;
- repeating the whole analysis with independent alternative methods;
- making extra paid/provider calls beyond the selected workflow.

Local deterministic computation, validation and plotting that are already part of the requested analysis can proceed normally.

Inspect or configure the policy:

```bash
axiomize policy
axiomize policy --allow-subtasks --allow-repeat --allow-extra-paid-calls
```

## Interfaces

The same core services are exposed through:

- Python
- CLI
- REST API v1
- MCP over stdio

Start the servers:

```bash
axiomize serve --port 8765
axiomize mcp
```

Adaptive intake is also available over REST (`POST /v1/intake`) and MCP (`axiomize.intake`). MCP tools publish real JSON input schemas instead of empty placeholder schemas.

## Reproducibility

`RunState` can preserve:

- problem definition and inputs;
- original data references and transformations;
- parameters, assumptions and provenance;
- candidate model ranking;
- equations and solver settings;
- tools and library versions;
- validation conflicts;
- uncertainty and confidence labels;
- validity domain and sensitivity results;
- falsifiers and hypotheses;
- generated visualizations/artifacts.

This allows an older run to be inspected or repeated and gives Axiomize enough metadata to investigate why a rerun changed.

## Install from PyPI

```bash
pip install axiomize
```

Or install the Agent Skill directly from the repository:

```bash
git clone https://github.com/Furox-Art/axiomize

# Claude Code
cp -r axiomize/skills/axiomize ~/.claude/skills/

# opencode
cp -r axiomize/skills/axiomize ~/.config/opencode/skills/
```

Then ask your agent, for example:

> Model this idea mathematically: a coffee shop wants to decide how many baristas to schedule.

## Reference implementation checks

```bash
# deterministic SIR + theory checks
python skills/axiomize/tools/validate.py --model sir --beta 0.3 --gamma 0.1 --sweep --plot curve.png

# stochastic CTMC validation
python skills/axiomize/tools/validate.py --model gillespie --N 10000 --I0 1

# queueing example
python skills/axiomize/tools/validate.py --model queue --lam 60 --mu 20 --target-wait 3

# package-native benchmark
axiomize benchmark
```

## Worked examples

| Idea | Model family | File |
|---|---|---|
| Disease in a city | SIR + stochastic fade-out | [epidemic-sir.md](examples/epidemic-sir.md) |
| Uncertain retailer inventory | newsvendor + safety stock | [supply-chain-inventory.md](examples/supply-chain-inventory.md) |
| Coffee-shop staffing | Erlang-C + staffing optimization | [coffee-shop-staffing.md](examples/coffee-shop-staffing.md) |

## Design rules

1. **No undefined symbols.** Every equation defines its terms.
2. **Units are mandatory where they exist.**
3. **Mechanism uncertainty is explicit.**
4. **Multiple plausible models are compared whenever possible.**
5. **Assumptions state what breaks when violated.**
6. **Falsifiability is required.**
7. **Original data are preserved during cleaning.**
8. **Tool/model conflicts are shown, not hidden.**
9. **Extra agent/API consumption is user-controlled.**
10. **Runs should be reproducible.**

See [skills/axiomize/adaptive-workflow.md](skills/axiomize/adaptive-workflow.md) for the full behavioral contract and [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance.

## License

MIT
