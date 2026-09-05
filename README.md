# Axiomize

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-informational)
![CI](https://github.com/Furox-Art/axiomize/actions/workflows/ci.yml/badge.svg)

**A versioned scientific modeling engine and Agent Skill for turning an idea into explicit, testable, reproducible mathematical models.**

Axiomize combines a machine-readable Model IR with native scientific executors, validation, fitting, uncertainty analysis, causal/Bayesian inference, formal/numerical checks, portable export, and an adaptive modeling workflow. It is designed to make assumptions, solver choices, uncertainty and failure modes visible rather than burying them in generated prose.

Current package line: **1.12.2**. Version **1.11.2** was the repository-wide security/runtime hardening release; 1.12.0 added the full scientific stress matrix, Causal Engine 2.0, Bayesian convergence/PPC diagnostics, real optional FEniCS FEM execution, family-wide numerical verification and broader export. Version 1.12.1 fixed DOLFINx-aware PDE solver selection; 1.12.2 tightens release/documentation consistency and exact numeric/run-integrity boundaries after a follow-up repository audit.

## Install

```bash
pip install -U axiomize
```

Optional PyMC/JAX support:

```bash
pip install -U "axiomize[full]"
```

FEniCS/DOLFINx is intentionally an external optional backend because its installation is platform/HPC dependent. When present, Axiomize probes the real runtime before advertising it.

## Core contract

Axiomize uses a versioned **Model IR** as the single source of truth for solve/simulate/fit/validate/export. A model can describe:

- variables, parameters and units;
- equations and equation roles;
- initial and boundary conditions;
- scientific assumptions and validity domain;
- solver settings and fallbacks;
- causal-identification metadata;
- provenance and migration history.

Schema migration is never silent: unsupported/newer schemas are rejected and supported migrations require explicit approval with a visible preview.

## Native model families

The Model IR supports native execution contracts for:

| Family | Native path |
|---|---|
| algebraic | SymPy nonlinear solve |
| ODE | SciPy IVP with solver fallbacks |
| PDE | bounded method-of-lines reaction/diffusion |
| DAE | semi-explicit index-1 solve |
| stochastic | Euler-Maruyama / stochastic executors |
| optimization | bounded nonlinear optimization |
| control | state-space simulation/stability |
| network | graph-coupled dynamics |
| Bayesian | bounded multi-chain Metropolis inference |
| agent-based | per-agent trajectories |
| discrete-event | bounded event queue/Gillespie-style execution |
| hybrid | event-driven piecewise ODE |
| multiphysics | approval-gated partitioned co-simulation |
| causal | identified treatment-effect estimation |

No unsupported family is silently replaced with a toy reference model.

## Causal Engine 2.0

Causal conclusions require identification evidence. Fit/correlation alone is not treated as causality.

The 1.12 engine adds:

- acyclic DAG validation;
- explicit or DAG-derived backdoor adjustment sets;
- rejection of post-treatment adjustment variables;
- AIPW doubly-robust estimation for binary treatment;
- IPW and outcome-regression estimates alongside AIPW;
- robust linear backdoor adjustment for continuous treatment;
- propensity overlap/positivity diagnostics;
- effective sample size under weighting;
- standardized mean-difference balance before/after weighting;
- intervention/counterfactual mean predictions;
- explicit causal scope and assumptions in every result.

If identification is insufficient, the engine returns `INSUFFICIENT_CAUSAL_EVIDENCE` and states what evidence is missing.

## Bayesian diagnostics and posterior predictive checks

The package-native Bayesian engine now runs bounded multi-chain random-walk Metropolis sampling and reports:

- split R-hat;
- bulk effective sample size;
- Monte Carlo standard error of the mean;
- 95% posterior interval/HDI-style summary;
- per-chain acceptance rate;
- posterior predictive RMSE;
- 90%/95% predictive coverage;
- Bayesian p-values for replicated mean and standard deviation.

Sampling remains approval-gated when the compute estimate is material, and hard likelihood/allocation ceilings cannot be bypassed with an approval flag.

## Numerical verification for every family

Numerical/discretization uncertainty is reported separately from parameter, data, aleatoric and structural uncertainty.

Dedicated studies:

- ODE: tolerance refinement;
- DAE: tolerance refinement;
- PDE: mesh refinement with observed-order/Richardson-style estimates.

Other executable families receive an explicit bounded verification contract using either output-resolution refinement or deterministic same-seed replay, whichever is scientifically meaningful. For stochastic/Bayesian/agent/event models, same-seed replay checks implementation/numerical reproducibility; **between-seed variation is not mislabeled as numerical error**.

Repeated refinement multiplies solver work, so it requires explicit approval.

## Real optional FEniCS FEM executor

`FEniCSAdapter` no longer claims availability merely because an import exists. In 1.12 it contains a real, structured FEM path for scalar Poisson problems using:

- DOLFINx + UFL + PETSc when available; or
- legacy FEniCS when available.

The bounded contract currently supports P1 Lagrange elements on a unit interval or unit square with constant source and Dirichlet boundary data. It deliberately does **not** execute arbitrary user-supplied Python/UFL strings.

Check availability:

```bash
axiomize tools
axiomize capabilities
```

## Scientific benchmark and stress gates

Axiomize has two complementary regression layers:

1. package/reference benchmark cases for correctness and model-selection behavior;
2. an **all-family scientific stress matrix** that executes every Model IR family through the installed wheel, checks adversarial parser boundaries, verifies the numerical-verification approval contract, exercises extended exports, and enforces per-case/total runtime budgets.

The scientific stress matrix is a permanent exact-wheel CI and release prerequisite. A PyPI release cannot proceed unless it passes together with the ordinary tests, dependency/security audit, import graph checks, installed CLI checks and cross-platform wheel smoke tests.

## Export

Portable/native formats include:

- JSON Model IR;
- generated Python;
- Jupyter notebook (`ipynb` / nbformat 4);
- SBML Level 3 Version 2 for the conservative supported subset;
- CellML 2.0 for the conservative supported subset;
- Modelica 3.6 textual models for supported algebraic/ODE/DAE equations;
- GraphML for network models;
- Graphviz DOT for causal DAGs;
- `axiomize.portable-bundle.v1`, containing canonical Model IR, assumptions, provenance and SHA-256 integrity metadata;
- YAML when the optional YAML dependency is available.

Standards adapters fail honestly with `ADAPTER_REQUIRED` when a model cannot be represented without changing its meaning.

## Scientific tool stack

Core runtime dependencies include NumPy, SciPy, SymPy, statsmodels, NetworkX, Matplotlib, Z3, python-control, CVXPY and CasADi. Optional integrations include PyMC, JAX, Lean and FEniCS/DOLFINx.

The router only selects a backend whose availability probe actually passes. Optional-backend absence is surfaced explicitly instead of being disguised as a successful tool call.

## Data, fitting and model criticism

The engine supports:

- conservative data cleaning with original-data preservation and an audit trail;
- SIR/logistic reference fitting and generic ODE fitting;
- identifiability and residual diagnostics;
- AIC/BIC comparison and simplest-sufficient-model preference;
- sensitivity and validity scans;
- local stability analysis;
- sparse dynamics/SINDy-style discovery;
- experiment-time ranking by a Fisher-information proxy;
- validated polynomial surrogate/reduced-order models with untouched holdout data and extrapolation blocking.

Constraint violations are visible PASS/FAIL records. Rebuild/refit after a failed scientific constraint requires approval and preserves the failed model/result.

## Security and trust boundaries

The 1.11.2 hardening line remains part of the 1.12 contract:

- AST-whitelisted mathematical expressions translated without arbitrary Python evaluation;
- hard expression, array, graph, draw, event, process and solver ceilings;
- arbitrary Python/Lean execution disabled by default and explicitly marked as not being an OS sandbox;
- REST request/concurrency/read-time limits, loopback-by-default binding and auth for remote binding;
- run-root path confinement and run-state integrity hashes;
- provider URL/redirect/response limits;
- LaTeX macro allow-list and `-no-shell-escape` compilation;
- Z3 timeout/domain guards;
- immutable-SHA GitHub Actions dependencies;
- dependency vulnerability audit and security-contract CI.

See [SECURITY.md](SECURITY.md) and [docs/security.md](docs/security.md).

## Release integrity

Every package release must pass:

- Python 3.10 / 3.11 / 3.12 / 3.13 validation;
- security contract and dependency audit;
- source and installed import-graph checks;
- exact built-wheel install and full CLI contract;
- Model IR, advanced-family, export, surrogate and LaTeX release smokes;
- all-family scientific stress matrix;
- exact-wheel CLI smoke on **Ubuntu/Linux, Windows and macOS**;
- Trusted Publishing-first PyPI publication and post-publication verification.

## Adaptive workflow

The Agent Skill can clarify a vague idea, recommend weak/medium/strong depth, construct multiple defensible candidate models, compare the best candidates, expose conflicts, quantify uncertainty, and produce falsifiers/experiment plans.

Expensive work is not silently multiplied. Large Monte Carlo runs, broad sweeps, Bayesian sampling, multiphysics co-simulation, repeated numerical refinement, extra paid model calls and whole-analysis reruns are approval-gated.

## Interfaces

The same application-service layer is available through:

- Python;
- CLI;
- REST API v1;
- MCP over stdio.

```bash
axiomize capabilities
axiomize serve --port 8765
axiomize mcp
```

REST binds to loopback by default. Remote binding requires explicit opt-in plus authentication.

## Reference checks

```bash
# package-native benchmark
axiomize benchmark

# deterministic SIR reference validation
axiomize-validate --model sir --beta 0.3 --gamma 0.1

# stochastic validation
axiomize-validate --model gillespie --N 10000 --I0 1 --runs 300

# report conversion
axiomize-to-latex --input report.md --output report.tex
```

## Reproducibility

Axiomize records the information needed to explain and reproduce a run: Model IR/schema version, parameters, solver/method, tool/package versions, seeds, data hashes, preprocessing, assumptions, validation results and outputs. Run-state persistence uses atomic writes and integrity verification.

## Design rules

1. No undefined model symbols.
2. Units/dimensional consistency are checked where defined.
3. Mechanism uncertainty is explicit.
4. Multiple plausible models are compared when evidence permits.
5. Causal claims require identification, not correlation.
6. Numerical error is not conflated with scientific uncertainty.
7. Original data and failed models are preserved.
8. Tool/solver conflicts are shown, not hidden.
9. Expensive or paid work is approval-gated.
10. Release claims must be demonstrated on the exact wheel that is published.

See [skills/axiomize/adaptive-workflow.md](skills/axiomize/adaptive-workflow.md), [ROADMAP.md](ROADMAP.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT