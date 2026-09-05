# Roadmap

Axiomize has moved from a prompt/skill-only project into a versioned scientific engine. This roadmap records shipped engine milestones and the remaining evidence/maturity work; it is not a list of promises that unimplemented features already exist.

## Shipped foundation — 1.0–1.7

- [x] adaptive weak / medium / strong modeling workflow
- [x] 15+ mathematical perspectives and archetype/first-principles routing
- [x] report templates, LaTeX conversion, worked examples and GitHub Pages
- [x] deterministic/stochastic/queue reference validators
- [x] CSV quality checks and SIR/logistic calibration
- [x] report benchmark runner and package-native scientific benchmark
- [x] CLI, REST and MCP interfaces
- [x] user-controlled extra-agent/provider consumption

## Shipped general scientific engine — 1.8–1.10

- [x] versioned Model IR as solve/simulate/fit/validate/export source of truth
- [x] explicit migration preview + approval requirement
- [x] native algebraic, ODE and stochastic execution
- [x] PDE, index-1 DAE, optimization, control, network, Bayesian, agent-based, discrete-event, hybrid, multiphysics and causal execution contracts
- [x] dimensional/scientific constraints with PASS/FAIL evidence
- [x] generic ODE fitting, residual diagnostics, identifiability and AIC/BIC ranking
- [x] sensitivity, stability, validity scans, SINDy-style discovery and experiment ranking
- [x] numerical verification for ODE/DAE/PDE with numerical uncertainty separated from model/data/parameter uncertainty

## Shipped portability and release rigor — 1.11.0–1.11.1

- [x] versioned SBML L3V2, CellML 2.0 and rerunnable notebook export
- [x] validated polynomial surrogate/reduced-order models with untouched holdout and extrapolation blocking
- [x] package-wide source and exact-wheel import contracts
- [x] exact installed-wheel CLI/Model IR/export/surrogate/LaTeX release smokes
- [x] exact-wheel CLI smoke on Ubuntu/Linux, Windows and macOS
- [x] PyPI Trusted Publishing-first release chain

## Shipped root/runtime hardening — 1.11.2

- [x] AST-restricted mathematical-expression boundary and removal of arbitrary `eval` paths
- [x] Model IR namespace/schema/migration validation hardening
- [x] hard non-bypassable compute/allocation ceilings
- [x] arbitrary Python/Lean explicit-trust boundary and reduced environment exposure
- [x] REST/MCP request, concurrency, path and error hardening
- [x] run-state integrity hashes and atomic persistence
- [x] provider redirect/size/timeout hardening
- [x] Z3 timeout and real-arithmetic domain guards
- [x] LaTeX macro allow-list and `-no-shell-escape`
- [x] immutable GitHub Action SHAs, security contract and dependency audit
- [x] direct runtime/tool adversarial regression suite

## Axiomize 1.12.0 scientific upgrade

- [x] **full scientific benchmark/stress matrix** covering every Model IR family with bounded runtime budgets
- [x] permanent exact-wheel scientific stress CI/release gate
- [x] **Causal Engine 2.0**: DAG cycle validation, backdoor adjustment, AIPW/IPW/outcome regression, positivity/ESS/balance diagnostics and interventions
- [x] **Bayesian diagnostics/PPC**: bounded multi-chain MH, split R-hat, ESS, MCSE, posterior intervals and posterior predictive checks
- [x] **real optional FEniCS FEM executor** for structured bounded Poisson P1 problems through DOLFINx or legacy FEniCS when installed
- [x] **numerical verification contract for every Model IR family**, without mislabeling stochastic variation as numerical error
- [x] **extended export**: Modelica 3.6, GraphML, causal DOT and integrity-hashed portable bundle, alongside existing JSON/Python/notebook/SBML/CellML
- [x] README / ROADMAP / CHANGELOG synchronized with the hardened scientific engine

## Next evidence/maturity work

- [ ] broaden independent end-to-end benchmark corpora across physics, biology, chemistry, operations and causal datasets
- [ ] compare selected numerical results against external reference implementations, not only internal regression oracles
- [ ] add optional full schema/tool validation for CellML/Modelica where ecosystem validators are available
- [ ] broaden FEM problem classes beyond bounded scalar Poisson while preserving structured/non-executable input contracts
- [ ] broaden causal identification beyond backdoor/randomized studies (front-door, IV and longitudinal designs only when identification can be made explicit)
- [ ] add richer Bayesian likelihood families and gradient-based optional samplers while retaining package-native fallback and diagnostics
- [ ] collect independent-user reliability/performance evidence before declaring production/stable status

## Non-goals

- silently inventing scientific mechanisms when the evidence does not identify them
- claiming causality from fit/correlation alone
- treating temporary directories/subprocess timeouts as hostile-code OS sandboxes
- silently multiplying paid model/API calls or expensive scientific computation
- claiming an optional scientific backend ran when its real availability probe failed
