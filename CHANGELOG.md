# Changelog

All notable changes to Axiomize are documented here. Versioning follows SemVer.

## [1.12.0] - 2026-09-05

### Added

- Bounded end-to-end scientific benchmark/stress matrix covering every current Model IR family plus adversarial, portability and numerical-verification contracts; installed as `axiomize-stress`.
- Causal Engine 2.0 with DAG cycle validation, verified back-door adjustment, bounded automatic adjustment-set search, randomized difference-in-means, heteroskedasticity-robust linear adjustment, IPW/AIPW, overlap diagnostics and counterfactual mean predictions.
- Native multi-chain Bayesian engine diagnostics: split-Rhat, bulk ESS, MCSE and per-chain acceptance rates.
- Normal-likelihood posterior predictive checks with predictive intervals, coverage, RMSE and Bayesian checks for mean/variance.
- Real bounded FEniCS/FEniCSx FEM execution for declarative 1D Poisson problems when `dolfinx` or legacy FEniCS/dolfin is installed; arbitrary weak-form/Python source is not executed.
- Family-complete explicit numerical-verification contracts: tolerance/mesh refinement, sampling convergence, MCMC convergence, optimization multi-start, output-grid stability, causal conditioning/overlap and deterministic repeatability as scientifically appropriate.
- Model exports for LaTeX, Content MathML, Graphviz DOT, Markdown model cards and Julia/DifferentialEquations.jl ODE scripts.
- Exact-installed-wheel scientific benchmark release smoke.

### Changed

- Package/runtime version advanced to 1.12.0.
- Capability discovery now reports Causal Engine 2.0, Bayesian diagnostics/PPC, family-complete verification, expanded export formats and real FEM availability.
- Bayesian hard-work preflight includes chain count, burn, draws, observation count and returned-sample allocation.
- README and ROADMAP now reflect the actual post-1.11.2 scientific engine rather than the early skill-only architecture.

### Compatibility / scientific semantics

- Existing successful simulations are not automatically failed by optional non-discretization verification. Family-complete verification is available explicitly through the numerical-verification action; historical automatic PDE/DAE attachment behavior remains.
- Unsupported export/backend combinations return `ADAPTER_REQUIRED` or `TOOL_UNAVAILABLE` rather than fabricating a result.

## [1.11.2] - 2026-09-05

### Security and correctness hardening

- Replaced permissive mathematical parsing paths with bounded AST-whitelisted parsing and removed runtime `eval`/`exec` surfaces.
- Hardened Model IR structure/schema validation, future-schema rejection and migration approval semantics.
- Added non-bypassable allocation/work ceilings across advanced model families and standalone scientific tools.
- Arbitrary local Python and Lean execution require explicit trust; subprocesses use reduced environments, time/output/resource controls where supported.
- REST: loopback-by-default, explicit remote opt-in/authentication, request/concurrency/I/O bounds, security headers and run-root path confinement.
- MCP: message bounds, path confinement and normalized error handling.
- OpenAI-compatible provider endpoints: URL validation, redirect/auth-header protection, timeout and response-size bounds.
- Run state: atomic writes, format/integrity metadata and SHA-256 verification on load.
- LaTeX conversion: mathematical macro allow-list, bounded input and `pdflatex -no-shell-escape -halt-on-error`.
- Z3: safe AST translation, solver timeout, bounded parser complexity and real-arithmetic denominator-domain guards.
- Fixed finite-horizon SIR validation versus asymptotic final-size theory.
- Fixed calibration/CSV/benchmark/playground, PyMC, CVXPY, CasADi, statsmodels, FTCS and router/backend edge cases found by the second runtime audit.
- Added adversarial security regressions and a permanent source/workflow security contract.

### CI / release

- Python 3.10/3.11/3.12/3.13 validation matrix.
- Immutable commit-SHA pinning for external GitHub Actions.
- Dependency vulnerability audit in CI and release preflight.
- Trusted Publishing-first release contract retained.
- PyPI verification made propagation-safe and retryable without weakening exact-artifact gates.

## [1.11.1] - 2026-09-05

### Added

- Permanent exact built-wheel + CLI smoke on Ubuntu/Linux, Windows and macOS.
- Release publication now depends on all three platform wheel/CLI jobs as well as the deep Linux preflight.

### Fixed

- macOS ARM dependency compatibility for Z3 by constraining Darwin to the compatible 4.x line.
- Cross-platform smoke horizon corrected so SIR portability tests do not compare a truncated 60-day simulation with the infinite-time final-size result.

## [1.11.0] - 2026-09-05

### Added

- Validated polynomial surrogate/reduced-order modeling with Latin-hypercube training design, untouched holdout evaluation, explicit acceptance thresholds and blocked extrapolation by default.
- CLI, REST and MCP surrogate paths plus exact-wheel release smoke.

## [1.10.0] - 2026-09-05

### Added

- Explicit numerical verification module for PDE mesh and ODE/DAE solver-tolerance refinement.
- Separate numerical/discretization error reporting from parameter/data/structural uncertainty.
- Approval gate for repeated numerical refinement.

## [1.9.0] - 2026-09-05

### Added

- Native advanced-family execution for PDE, index-1 DAE, optimization, control, network, Bayesian, agent-based, discrete-event, hybrid, multiphysics and causal Model IR.

## [1.8.0] - 2026-09-05

### Added

- Canonical versioned Model IR/DSL and approval-visible schema migration.
- Generic model planning, execution, fitting, validation, constraints, residual diagnostics, AIC/BIC, stability/validity, SINDy-style discovery, experiment design, provenance and export surfaces.
- Shared CLI/REST/MCP Model IR paths and exact-installed-wheel release smoke.

## [1.0.0–1.7.x] - 2026-08-24 to 2026-09-04

### Added

- Initial Agent Skill workflow, mathematical lenses, archetype catalog and first-principles protocol.
- SIR/Gillespie/Erlang-C validation, SIR/logistic calibration, CSV quality checks, sensitivity/uncertainty tools and report benchmark runner.
- LaTeX report conversion, Gradio playground, examples, domain packs and GitHub Pages.
- Scientific tool adapters and routing for SymPy, SciPy, statsmodels, NetworkX, Z3, control, CVXPY, CasADi, optional PyMC/JAX, Lean and FEniCS probing.
- Shared application services, CLI, REST v1, MCP, capability discovery, reproducible RunState and provider abstraction.

[1.12.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.12.0
[1.11.2]: https://github.com/Furox-Art/axiomize/releases/tag/v1.11.2
[1.11.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.11.1
[1.11.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.11.0
[1.10.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.10.0
[1.9.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.9.0
[1.8.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.8.0
