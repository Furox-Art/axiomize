# Changelog

All notable changes to Axiomize are documented here. Axiomize follows semantic versioning; release claims are tied to exact-wheel CI/release evidence.

## Unreleased

- `server.json` description fits the MCP registry's 100-character limit. `.github/workflows/mcp-registry.yml` publishes that file on `workflow_dispatch` with GitHub OIDC. npm is still not published.

## [1.12.4] - 2026-10-02

Documentation and repository visibility. No library code, CLI surface, or public API changed.

- The README now carries `mcp-name: io.github.Furox-Art/axiomize` and `server.json` describes the existing `axiomize mcp` server.
- The npm shim is no longer published. PyPI is the install path.
- This release exists so the PyPI long description includes the MCP name line.

### Fixed

- `docs/example-gallery.md` linked to a `README.md#the-fifteen-lenses` anchor that does not exist;
  the README no longer contains that section. The gallery now points at the perspective lens
  directory that actually backs the claim.
- the example gallery listed 11 of the 18 files in `examples/`; the 7 unlisted examples are now
  present, and the two 20-line phase skeletons are labelled as condensed skeletons rather than
  presented as full worked examples
- `docs/benchmark-results.md` presented historical wave scores in the same table as reproducible
  ones, with no commit or script identity. The page is now split into a reproducible run that
  records commit, runner sha256, case-set sha256, rubric sha256, interpreter and timestamp, and a
  clearly labelled history section that states its runs cannot be rerun
- `docs/benchmark-results.md` labelled automated-layer scores with a `PASS` verdict as if it were
  the rubric's gate. It now states that the rubric gate is a combined automatic plus human score
  of 15/20 per case, that the human layer is not recorded in this repository, and that no
  combined score is published
- the two stored reports whose cases are absent from `benchmarks/ideas.json`
  (`novel-async-alignment.md`, `novel-telephone-fidelity.md`) were unlabelled; they are now
  identified as stored samples that CI neither grades nor checks
- worked examples carried `lit.` / `data.` / `est.` source classes with no citation behind them.
  Every example now opens with a provenance note saying the values are illustrative and uncited
- the README advertised an npm version badge for a package whose entry point was broken, and its
  npm section did not say what the failure was. The badge is still absent, and the section now
  separates the two states accurately: the `index.js` fix landed on `main` via #32/#33, but the
  registry still serves the old 1.12.2 tarball, so the published package is still broken. The
  section tells readers how to check the registry version themselves. The npm badge returns when
  the registry version matches PyPI
- `docs/index.md` had no route to the domain packs, which were not linked from anywhere

### Added

- `docs/documentation.md`: what builds what, which pages are excluded from the site nav and why,
  what CI enforces, how to publish a benchmark number with provenance, and the **manual PyPI
  description sync step**. `README.md` is the PyPI long description as of build time, so README
  edits merged after a release do not reach the PyPI page until the next release; the page gives
  the command that shows the difference and states that a new release is the only correct fix
- `.github/ISSUE_TEMPLATE/feature_request.md` and `.github/ISSUE_TEMPLATE/question.md`
- `.github/ISSUE_TEMPLATE/config.yml` routing security reports away from public issues
- the bug report template now covers the Python API, CLI, MCP, REST and agent skill surfaces
  instead of assuming an agent runtime, and asks for version, Python version and
  `axiomize capabilities` output
- `README.md` links to `ROADMAP.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, the example directory
  and the domain packs

### Changed

- `mkdocs.yml`: maintainer-only pages (`publishing-checklist.md`, `security-ci-contract.md`,
  `security-maintenance.md`, `security-release-checklist.md`, `security-audit-1.11.2.md`) are
  removed from the user-facing nav and moved to `exclude_docs`. They still build and stay
  reachable by direct link. User-facing security pages are untouched.
- `CITATION.cff`: added `type`, `abstract`, `license`, `repository-code` and `keywords` so the
  file is usable by citation tooling rather than only parseable
- `SECURITY.md`: the claim that private reporting is enabled now names the API endpoint that
  proves it and gives a profile link as the fallback contact
- the pull request template covers documentation, provenance and release-lockstep checks

### Not changed here

- `pyproject.toml`, `package.json` and `index.js` were fixed on `main` by #33 (`be8d347`) and #32
  (`0854fe5`), both merged after this documentation branch was cut. This branch merges `main`
  rather than reimplementing them, so those fixes are present and were not re-derived here. What
  is still outstanding is publication: the npm shim and the Python distributions ship together
  from the next release commit, and until that release the registry keeps serving the broken
  1.12.2 tarball.
- the published PyPI long description still reflects the README at the 1.12.3 release. Only a new
  release can change it. See `docs/documentation.md`.

## [1.12.3] - 2026-09-29

### Added

- runnable `examples/quickstart_sir.py`, plus a README and `docs/quickstart.md` quickstart that quote its real output
- `docs/quickstart.md`, a five-minute path from install to a validated result with the actual expected output for each command
- `.github/scripts/readme_example_check.py`: CI gate asserting that README and docs links resolve, that the documented quickstart output still matches a real run, and that documented CLI entry points answer on real input
- `.github/scripts/stage_docs.py`: single implementation of the docs staging step, shared by the Pages workflow and the new CI docs job so a local build matches the deployed site
- mkdocs navigation now covers every page under `docs/`, including the tutorials, integrations, portable export, benchmark results, and the full security series
- `pyproject.toml`: added `Changelog`, `Security`, `Contributing`, and `Benchmarks` project URLs; regrouped and expanded keywords; added Bio-Informatics, Physics, Information Analysis, Education, MIT, and `Python :: 3 :: Only` classifiers
- CI now builds documentation in strict mode and runs the README/docs contract gate against the installed wheel

### Fixed

- README no longer advertises a nonexistent `Model.from_yaml` API, and no longer instructs the reader to add meters to seconds as if it were checked
- README and `docs/index.md` no longer duplicate a "Quick Start" section or leave the first screen without an install command, use cases, or documentation links
- README npm section now states that the published npm entry point is broken instead of advertising `npx axiomize` as a working install path
- docs build failed `mkdocs build --strict` on a clean checkout because four nav targets were generated only inside the Pages workflow; the staging step is now runnable locally
- `SECURITY.md` now gives a concrete supported-version table and the actual private-reporting URL, matching the now-enabled repository setting
- `CONTRIBUTING.md` states Python 3.10+ instead of 3.9+, and lists the local commands CI actually runs
- `.gitignore` covers `docs/adaptive-workflow.md` (a staged page that was previously left untracked), plus `.venv/`, `dist/`, and build artifacts

### Changed

- Package summary rewritten to describe the verifiable feature set: versioned Model IR, explicit units, dimensional and numerical validation, calibration, sensitivity and uncertainty analysis, causal/Bayesian inference, portable export via CLI/REST/MCP

- Metadata-only patch release: refreshed PyPI keywords, classifiers, and discovery metadata; no functional API changes.

## [1.12.2] - 2026-09-05

### Fixed / hardened

- synchronized the public README package line with the actual release version and made release CI enforce README/CHANGELOG/package/trigger version lockstep
- blocked the Release workflow from publishing when manually dispatched against any ref other than `refs/heads/main`
- rejected boolean values at shared finite numeric boundaries instead of silently coercing `True`/`False` to `1.0`/`0.0`
- bounded textual integer parsing before conversion so oversized integer strings fail before interpreter-dependent parsing limits are reached
- made run-manifest format-version validation exact, rejecting booleans and fractional values that previously could be accepted through `int(...)` coercion
- closed the superseded unmerged 1.12.0 scientific-maturity draft PR after the shipped 1.12.0/1.12.1 line replaced it

### Release gates

- full Python 3.10/3.11/3.12/3.13 validation
- security contract and dependency audit
- source and installed import-graph contracts
- exact built-wheel CLI/Model IR/export/surrogate/LaTeX/scientific stress checks
- Ubuntu/Linux, Windows and macOS exact-wheel CLI smoke
- Trusted Publishing-first PyPI publication and verification

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

[1.12.2]: https://github.com/Furox-Art/axiomize/releases/tag/v1.12.2
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