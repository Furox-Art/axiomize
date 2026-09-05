# Changelog

All notable changes to Axiomize are documented here. Axiomize follows semantic versioning; release claims are tied to exact-wheel CI/release evidence.

## [1.12.1] - 2026-09-05

### Fixed

- PDE automatic solver planning now uses the same real `FEniCSAdapter.availability()` probe as the executable FEM path.
- DOLFINx-only installations are correctly routed to the bounded FEM executor instead of being misclassified as SciPy/method-of-lines only.
- a merely importable but unrunnable legacy FEniCS installation no longer causes the planner to advertise FEM execution incorrectly.
- public `general_engine.select_solver()` and direct `general_engine_core.select_solver()` now share the same PDE backend decision contract while preserving explicit user solver configuration.

## [1.12.0] - 2026-09-05

### Added

- all-family scientific benchmark/stress matrix with explicit per-case and total runtime budgets
- permanent exact-installed-wheel scientific stress gate in CI and release preflight
- Causal Engine 2.0:
  - DAG cycle validation
  - explicit/DAG-derived backdoor adjustment
  - post-treatment-adjustment rejection
  - AIPW doubly-robust, IPW and outcome-regression estimates for binary treatment
  - robust continuous-treatment backdoor regression
  - positivity/overlap, effective-sample-size and covariate-balance diagnostics
  - bounded intervention/counterfactual predictions
- package-native Bayesian Engine 2.0:
  - bounded multi-chain random-walk Metropolis
  - split R-hat, bulk ESS and MCSE
  - posterior interval summaries
  - posterior predictive RMSE, predictive coverage and Bayesian p-values
- real optional structured FEniCS/DOLFINx FEM executor for bounded scalar Poisson P1 problems on unit intervals/squares
- numerical-verification contracts for every Model IR family; stochastic between-seed variability remains explicitly separate from numerical error
- Modelica 3.6 textual export for supported ODE/DAE/algebraic models
- GraphML network export
- Graphviz DOT causal-DAG export
- `axiomize.portable-bundle.v1` export with canonical Model IR SHA-256 integrity metadata

### Changed

- runtime capability discovery now advertises Causal Engine 2.0, Bayesian diagnostics/PPC, all-family numerical verification and extended exports
- FEniCS availability is based on a real executable backend probe rather than module-name presence
- README, ROADMAP and CHANGELOG now describe the actual hardened scientific engine rather than the older prompt/skill-only architecture

### Release gates

- Python 3.10/3.11/3.12/3.13 validation
- security contract and dependency vulnerability audit
- source and installed import-graph contracts
- exact built wheel installation and full CLI/Model IR/export/surrogate/LaTeX checks
- all-family scientific stress matrix
- Ubuntu/Linux, Windows and macOS exact-wheel CLI smoke
- Trusted Publishing-first PyPI publication and verification

## [1.11.2] - 2026-09-05

### Security / correctness

- replaced permissive mathematical parsing paths with a bounded AST-whitelist boundary and explicit AST→SymPy construction
- removed arbitrary `eval()` use from Z3 constraint handling; added solver timeout and denominator-domain guards
- hardened Model IR namespaces, targets, bounds, finite values, solver settings and schema migrations
- prevented silent future-schema migration and schema-version relabeling
- made arbitrary Python and Lean execution explicit-trust operations with reduced environment inheritance and resource/time limits
- confined REST/MCP run-file access to configured run roots; added request/message/concurrency/read-time limits and safer errors
- added provider URL/redirect/request/response/timeout hardening
- added run-state content integrity verification and atomic persistence
- added hard non-bypassable limits for arrays, draws, networks, optimization, event queues, PDE work, causal matrices and other native executors
- hardened LaTeX conversion with a mathematical macro allow-list and `-no-shell-escape`
- corrected finite-horizon SIR validation versus asymptotic final-size theory
- hardened direct SciPy/CVXPy/CasADi/statsmodels/PyMC/benchmark/playground/CSV/parallel-sweep surfaces
- preserved first-occurrence order when duplicate data are merged with `sort_time=False`

### CI / supply chain

- immutable commit-SHA pinning for external GitHub Actions
- permanent security-contract scanner
- dependency vulnerability audit
- direct adversarial runtime regressions
- release verification hardened against PyPI propagation delay without weakening Trusted Publishing or exact-artifact gates

## [1.11.1] - 2026-09-05

### Added

- permanent exact-wheel/CLI matrix on Ubuntu/Linux, Windows and macOS in normal CI and release preflight
- platform-independent wheel smoke harness

### Fixed

- macOS ARM dependency compatibility by constraining the Darwin Z3 line to compatible 4.x releases
- release smoke SIR horizon corrected so it tests CLI portability rather than an intentionally truncated asymptotic final-size comparison

## [1.11.0] - 2026-09-05

### Added

- validated polynomial response-surface surrogate/reduced-order models
- deterministic Latin-hypercube training design through full Model IR execution
- explicit approval before multiplying full-model simulations
- untouched holdout validation with RMSE/NRMSE/MAE/max-error/R² thresholds
- default blocking of out-of-domain surrogate extrapolation
- exact source-model provenance and dataset hashes
- CLI/REST/MCP surrogate paths and installed-wheel release smoke

## [1.10.0]

### Added

- numerical/discretization verification separated from parameter/data/structural uncertainty
- PDE mesh-refinement studies with observed-order/Richardson-style estimates
- ODE/DAE tolerance refinement
- approval gating before repeated numerical solves
- CLI and REST numerical-verification services

## [1.9.0]

### Added

- native advanced-family execution for PDE, index-1 DAE, optimization, control, network, Bayesian, agent-based, discrete-event, hybrid, multiphysics and causal Model IR
- method-of-lines finite-difference PDE support with Dirichlet/Neumann boundary conditions
- solver fallback diagnostics and advanced family execution through the stable general-engine facade

## [1.8.0]

### Added

- canonical versioned Model IR / DSL as the single source of truth for deterministic scientific execution
- migration preview/approval contract and reproducible migration history
- model-family/domain recommendation and solver selection
- native algebraic, ODE and stochastic execution
- generic ODE fitting, scientific constraints/repair, residual diagnostics, AIC/BIC, stability/validity and nondimensionalization planning
- SINDy-style sparse dynamics discovery, experiment ranking, provenance and portable exports
- CLI `axiomize model` path and shared REST/MCP application services

## [1.7.0]

### Added

- adaptive weak/medium/strong workflow and user-controlled clarification
- explicit consumption policy: no silent extra agents, whole-analysis reruns or extra paid calls
- stronger reproducibility, uncertainty, hypothesis/falsifier and visualization workflow contracts

## [1.6.0]

### Added

- standardized `ScientificTool` interface and live backend availability probes
- SciPy, SymPy, statsmodels, Z3, CVXPY, CasADi, network/control and Bayesian scientific adapters
- dimensional validation and explicit validation statuses
- application services, CLI, REST, MCP, provider abstraction and portable run-state foundations

## [1.5.0] - 2026-08-24

### Added

- first-principles protocol for ideas with no matching archetype
- novel-domain benchmark reports and novel-territory report appendix

## [1.4.1] - 2026-08-24

### Fixed

- LaTeX converter hardening across worked examples/benchmark reports
- removed committed TeX build artifacts and expanded `.gitignore`

## [1.4.0] - 2026-08-24

### Added

- LaTeX/PDF export for reports
- sample rendered report

## [1.3.2] - 2026-08-24

### Added

- animated demo
- benchmark-report regression wired into CI

## [1.3.1] - 2026-08-24

### Added

- stored blind-test benchmark reports and benchmark results documentation
- epidemiology and operations domain packs

### Fixed

- stochastic fade-out theory, Erlang-C overflow, CSV check and fit-bound defects

## [1.3.0] - 2026-08-24

### Added

- decision-theory, demographic/actuarial and spatial-statistics lenses
- report benchmark runner
- machine-readable fitting output
- local Gradio playground
- project-management domain pack

## [1.2.0] - 2026-08-24

### Added

- reliability, statistical-process-control and thermodynamic lenses
- additional worked examples and domain packs
- benchmark dataset/scoring rubric
- CSV quality pre-check

## [1.1.0] - 2026-08-24

### Added

- game-theory, causal-inference and information-theory lenses
- expanded archetype catalog and worked examples
- model-comparison diagnostics, report indexing and GitHub Pages

## [1.0.0] - 2026-08-24

First tagged release: multi-perspective modeling workflow, rigor ladder, standardized report, bundled validation/fitting/sweep tools, worked examples and GitHub Actions CI.

[1.12.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.12.1
[1.12.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.12.0
[1.11.2]: https://github.com/Furox-Art/axiomize/releases/tag/v1.11.2
[1.11.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.11.1
[1.11.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.11.0
[1.10.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.10.0
[1.9.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.9.0
[1.8.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.8.0
[1.7.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.7.0
[1.6.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.6.0
[1.5.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.5.0
[1.4.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.4.1
[1.4.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.4.0
[1.3.2]: https://github.com/Furox-Art/axiomize/releases/tag/v1.3.2
[1.3.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.3.1
[1.3.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.3.0
[1.2.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.2.0
[1.1.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.1.0
[1.0.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.0.0
