# Axiomize

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10--3.13-informational)
![CI](https://github.com/Furox-Art/axiomize/actions/workflows/ci.yml/badge.svg)

**Turn an idea into explicit, executable, testable mathematical models — then try to break them.**

Axiomize is an Agent Skill and Python scientific engine. It uses a versioned Model IR as the single source of truth for simulation, fitting, validation, numerical verification, causal/Bayesian analysis, experiment design, provenance and export.

Current package line: **1.12.0**. Version **1.11.2** was the root/runtime-hardening release; 1.12.0 builds the scientific-maturity layer on top of those security and release guarantees.

## Install

```bash
pip install -U axiomize
```

Optional PyMC/JAX integrations:

```bash
pip install 'axiomize[full]'
```

FEniCS/FEniCSx is intentionally external: install it using the distribution method appropriate to your platform, then `axiomize capabilities` will report whether the real FEM executor is available.

## Scientific Model IR

Axiomize has native execution contracts for all current Model IR families:

- algebraic
- ODE
- PDE
- DAE
- stochastic
- optimization
- control
- network
- Bayesian
- agent-based
- discrete-event
- hybrid
- multiphysics
- causal

Each Model IR can explicitly record equations, variables, parameters, units, initial/boundary conditions, assumptions, constraints, solver settings, validity information and provenance. Unknown/future schema versions are never silently rewritten; supported migrations require explicit approval.

## What the engine does

```text
idea / data
   ↓
clarify missing mechanism and scientific target
   ↓
rank multiple candidate model families
   ↓
construct explicit Model IR
   ↓
dimensional + structural + scientific checks
   ↓
solve / simulate / fit / infer
   ↓
numerical verification appropriate to the family
   ↓
residual / stability / uncertainty / causal diagnostics
   ↓
compare models and expose conflicts
   ↓
export + provenance + reproducible run
```

Axiomize does not turn correlation into causation, does not silently replace an unsupported model with a toy reference model, and does not silently launch expensive repeated computation.

## 1.12.0 scientific-maturity stack

### Full scientific benchmark / stress matrix

`axiomize-stress` runs a bounded, deterministic end-to-end matrix covering **all 14 Model IR families**, adversarial parser/schema cases, portability/export and numerical-verification contracts.

```bash
axiomize-stress
```

The same matrix is a permanent exact-installed-wheel CI/release gate. Every case has a wall-clock budget and fixed numerical tolerances; the suite makes no paid/provider calls.

### Causal Engine 2.0

The causal engine separates identification from estimation. It supports:

- DAG cycle validation;
- back-door identification using d-separation on the supplied DAG;
- bounded automatic minimal adjustment-set search;
- rejection of treatment descendants in an adjustment set;
- randomized difference-in-means;
- heteroskedasticity-robust linear adjustment;
- IPW and AIPW for binary treatment;
- propensity overlap and effective-sample-size diagnostics;
- confidence intervals and intervention/counterfactual mean predictions.

If identification is not established, the result is `INSUFFICIENT_CAUSAL_EVIDENCE`; a regression coefficient alone is never relabeled as causal.

### Bayesian diagnostics and posterior predictive checks

The native Bayesian engine now runs bounded multiple-chain random-walk Metropolis and reports:

- split-Rhat;
- bulk effective sample size (ESS);
- Monte Carlo standard error (MCSE) of the posterior mean;
- per-chain acceptance rates;
- posterior predictive means and 95% intervals;
- predictive interval coverage and RMSE;
- Bayesian predictive checks for the observed mean and variance.

Sampling remains approval-gated and subject to non-bypassable draw/data/work ceilings.

### Real FEniCS/FEniCSx FEM executor

The optional FEM adapter now executes a real, bounded declarative finite-element problem rather than advertising an unimplemented backend. The first safe contract is 1D Poisson:

```text
-u'' = f on [a,b], with left/right Dirichlet boundary values
```

It probes FEniCSx (`dolfinx`) first and legacy FEniCS/dolfin second, solves the weak form with the installed backend and reports DOFs plus error against the analytic constant-source solution. Arbitrary Python/weak-form source is deliberately not executed.

### Numerical verification for every family

`axiomize model --action numerical-verify` has a family-specific contract for every Model IR family:

| Families | Verification contract |
|---|---|
| ODE / DAE | solver-tolerance refinement |
| PDE | spatial mesh refinement |
| stochastic / agent-based / discrete-event | sampling convergence |
| Bayesian | Rhat / ESS convergence |
| optimization | multi-start consistency |
| control / network / hybrid | output-grid refinement |
| causal | estimator conditioning + overlap diagnostics |
| algebraic | deterministic repeatability/residual behavior |
| multiphysics | repeatability plus native coupling-convergence diagnostics |

The engine does **not** call every one of these “discretization error.” Sampling, conditioning, coupling and optimization stability are labeled separately. Repeated verification work requires explicit approval.

### Expanded export

Existing portable exports remain:

- JSON
- Python
- optional YAML
- Jupyter/nbformat 4
- SBML Level 3 Version 2 (supported conservative subset)
- CellML 2.0 (supported conservative subset)

1.12.0 additionally provides:

- LaTeX model fragments;
- Content MathML;
- Graphviz DOT dependency / causal / network graphs;
- Markdown model cards;
- Julia + DifferentialEquations.jl scripts for supported ODE Model IR.

Unsupported family/standard combinations return `ADAPTER_REQUIRED` rather than producing misleading pseudo-standard output.

## Scientific tools

Core runtime dependencies include NumPy, SciPy, SymPy, NetworkX, statsmodels, Matplotlib, Z3, python-control, CVXPY and CasADi. PyMC and JAX are optional. Lean and FEniCS/FEniCSx are probed live.

```bash
axiomize tools
axiomize capabilities
```

The router selects only backends that actually report runnable. Missing tools are surfaced as `TOOL_UNAVAILABLE` or explicit degraded fallbacks.

## Data, fitting and diagnostics

The data layer preserves original observations and records cleaning operations. It can reject or explicitly handle non-finite rows, ordering and duplicate times, while robust outliers are flagged rather than silently deleted.

Model fitting supports bounded nonlinear least squares, residual diagnostics, identifiability information where available, AIC/BIC comparison and uncertainty reporting. Validated surrogate models use untouched holdouts and are rejected outside their qualified domain by default.

## Consumption and safety contract

Axiomize distinguishes **permission** from **hard resource safety**.

Approval may authorize expensive scientific work, but it never disables hard ceilings on request size, arrays, graph dimensions, samples, optimizer iterations, solver events, generated output or expression complexity. Extra paid/provider calls, whole-analysis repeats, expensive Bayesian sampling, broad refinement and multiphysics co-simulation remain user-controlled.

Security-sensitive runtime surfaces added or hardened in 1.11.2 include:

- AST-whitelisted mathematical parsing and no runtime `eval`/`exec` path;
- explicit trust gate for arbitrary local Python / Lean execution;
- REST loopback-by-default, remote auth, request/concurrency/I/O bounds and run-root confinement;
- MCP message/path bounds;
- provider URL/redirect/response limits;
- atomic run-state persistence with integrity verification;
- LaTeX macro allow-list and `-no-shell-escape` compilation;
- Z3 timeout/domain guards;
- allocation/work ceilings across scientific tools;
- immutable GitHub Action SHAs, dependency audit and security-contract CI.

See [SECURITY.md](SECURITY.md) for the trust model.

## Interfaces

The shared service layer is available through:

- Python
- CLI
- REST API v1
- MCP over stdio

Examples:

```bash
axiomize capabilities
axiomize model --input-json request.json --action simulate
axiomize model --input-json request.json --action numerical-verify --approve-heavy
axiomize-stress
axiomize serve --port 8765
axiomize mcp
```

Remote REST binding requires explicit opt-in and authentication.

## Reproducibility and provenance

Run records can preserve Model IR schema/version, inputs and data hashes, assumptions, parameters, solver/algorithm settings, package/tool versions, random seeds, transformations, validation results and generated artifacts. Numerical error is reported separately from parameter/data/structural uncertainty where scientifically meaningful.

## CI and release guarantees

A package release cannot reach PyPI unless the permanent release gates pass, including:

- full tests and import contracts;
- dependency/security audit;
- exact built-wheel installation and CLI contracts;
- Model IR, advanced-family, export, surrogate and LaTeX smokes;
- the scientific benchmark/stress matrix;
- exact-wheel CLI smoke on Ubuntu/Linux, Windows and macOS;
- Trusted Publishing-first PyPI flow and publication verification.

## Mathematical perspectives

The Agent Skill still provides the fifteen modeling lenses: deterministic, stochastic, optimization, agent-based, network, control, game theory, causal inference, information theory, reliability, SPC, thermodynamic analogies, decision theory, demographic/actuarial and spatial statistics. See [`skills/axiomize/perspectives/`](skills/axiomize/perspectives/).

## Development

```bash
git clone https://github.com/Furox-Art/axiomize
cd axiomize
pip install -r requirements-test.txt
pytest tests/ -v
python .github/scripts/security_contract_smoke.py
python .github/scripts/scientific_benchmark_release_smoke.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [ROADMAP.md](ROADMAP.md) and [CHANGELOG.md](CHANGELOG.md).

## License

MIT
