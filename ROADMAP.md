# Roadmap

Public engineering plan. Checked items are implemented; release claims still require the final release CI/PyPI verification for that version.

## Shipped through 1.5

- [x] Multi-perspective Agent Skill workflow and fifteen mathematical lenses
- [x] Archetype catalog, first-principles protocol and worked examples
- [x] SIR/Gillespie/Erlang-C validators, calibration tools, data-quality checks and report benchmark runner
- [x] LaTeX report conversion, Gradio playground, GitHub Pages and Python-version CI matrix

## Shipped through 1.10

- [x] Versioned canonical Model IR/DSL
- [x] Native execution contracts for algebraic, ODE, PDE, DAE, stochastic, optimization, control, network, Bayesian, agent-based, discrete-event, hybrid, multiphysics and causal families
- [x] Solver selection/fallbacks, constraints, repair approval gates, fitting, identifiability, residual diagnostics, AIC/BIC, stability and validity scans
- [x] SINDy-style model discovery and bounded experiment design
- [x] Numerical verification for PDE/DAE plus explicit ODE refinement service
- [x] Portable JSON/Python/YAML, SBML L3V2, CellML 2.0 and Jupyter notebook export
- [x] Validated polynomial surrogate models with untouched holdouts and blocked extrapolation
- [x] CLI + REST v1 + MCP shared service paths

## Shipped in 1.11.1

- [x] Exact built-wheel CLI smoke on Ubuntu/Linux, Windows and macOS
- [x] Cross-platform wheel gates are permanent prerequisites for PyPI publication
- [x] macOS Z3 dependency compatibility hardening

## Shipped in 1.11.2

- [x] Root/runtime security audit and adversarial regression suite
- [x] AST-restricted mathematical expressions and direct-core parser hardening
- [x] Hard, non-bypassable resource ceilings across runtime/scientific tools
- [x] REST/MCP path, message, request, concurrency and timeout hardening
- [x] Run-state integrity + atomic persistence
- [x] Provider URL/redirect/response hardening
- [x] Explicit trust boundary for local Python and Lean execution
- [x] LaTeX macro allow-list and `-no-shell-escape`
- [x] Z3 timeout/domain/parser hardening
- [x] Immutable GitHub Actions SHA pins, dependency audit and permanent security CI contract
- [x] Release/PyPI verification made propagation-safe without weakening Trusted Publishing-first

## 1.12.0 scientific maturity

- [x] **Full scientific benchmark/stress matrix**: every Model IR family plus adversarial, portability and verification cases with fixed seeds, tolerances and runtime budgets
- [x] **Causal Engine 2.0**: DAG validation, verified back-door adjustment, bounded auto-adjustment, robust OLS, IPW/AIPW, overlap and counterfactual diagnostics
- [x] **Bayesian diagnostics/PPC**: multiple chains, split-Rhat, ESS, MCSE and normal-likelihood posterior predictive checks
- [x] **Real FEniCS/FEniCSx FEM executor**: bounded declarative 1D Poisson weak-form execution when a supported backend is installed
- [x] **Numerical verification for every Model IR family** with family-appropriate semantics and approval-gated repeated work
- [x] **Expanded export**: LaTeX, MathML, Graphviz DOT, Markdown and Julia ODE scripts in addition to existing portable/standard formats
- [x] **README / ROADMAP / CHANGELOG synchronization** including the complete 1.11.2 hardening line
- [ ] Final 1.12.0 PR CI green
- [ ] Merge to `main`, main CI green
- [ ] 1.12.0 release workflow / PyPI / GitHub release verified

## Next candidates after 1.12.0

- [ ] Broader FEniCSx safe FEM problem catalog (2D Poisson, diffusion, linear elasticity) without arbitrary-code execution
- [ ] More causal estimands/treatment types (continuous treatment, longitudinal treatment, mediation) with explicit identification contracts
- [ ] HMC/NUTS adapter with the same diagnostics/PPC contract when a suitable backend is installed
- [ ] Broader symbolic-regression methods beyond the current SINDy-style sparse dynamics
- [ ] Independent external benchmark datasets and third-party reproducibility reports
- [ ] Web playground deployment and external agent-skill registry submissions
- [ ] JSON export of canonical report parameter tables (legacy feature PR remains separate from Model IR export)

## Permanent non-negotiable release gates

- Trusted Publishing-first PyPI flow
- exact-installed-wheel dependency/import/CLI checks
- Ubuntu/Linux + Windows + macOS exact-wheel CLI smoke
- security contract + dependency audit
- bounded scientific benchmark/stress matrix
- no silent schema migration, costly rerun, arbitrary-code execution or false standards/backend claim
