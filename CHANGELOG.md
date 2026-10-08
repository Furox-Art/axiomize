# Changelog

All notable changes to Axiomize are documented here. Axiomize follows semantic versioning; release claims are tied to exact-wheel CI/release evidence.

## Unreleased

Documentation only, against the live `1.12.5` release. No version bump, no publish, no tag. The
provenance statements below were verified against the registries on 2026-10-04 rather than assumed.

### Fixed

- the provenance documentation was pinned to `1.12.4` while `1.12.5` is the live release on both
  PyPI and npm. `README.md`, `SECURITY.md` and `docs/documentation.md` now state `1.12.5`
- **`docs/documentation.md` stated npm `1.12.4` provenance state without stating the PyPI state for
  the current release.** It now states the asymmetry explicitly: PyPI `1.12.5` **is** attested
  (PEP 740 bundles for both the wheel and the sdist, attested digest equal to the downloaded file,
  one transparency-log entry each), npm `1.12.5` **is not**, because it was published in token mode
  and a long-lived `NPM_TOKEN` cannot mint a Sigstore attestation
- npm `dist.signatures` was described as "not provenance" without saying what it *does* prove. It
  is now contrasted in a three-way table against PEP 740 attestations and `dist.integrity`, with
  the claim stated for each: attestation means a build workflow signed this digest;
  `dist.signatures` means only that the registry has not altered its own metadata and is present on
  every version including the broken `1.12.2`; digests mean the bytes match what was published but
  not who built them
- the per-file shape of the PyPI provenance endpoint was undocumented, and a directory-style URL
  like `pypi.org/integrity/axiomize/1.12.5/` 404s whether or not the release is attested. That
  makes a real attestation look absent. The correct form, and the fact that the directory form
  proves nothing either way, are now written down
- there was no consumer-facing verification guidance. `README.md`, `SECURITY.md` and
  `docs/documentation.md` now carry the exact commands for checking a PyPI attestation against a
  downloaded file, pinning a PyPI digest, pinning an npm `dist.integrity`, and the recommendation
  to pin by digest where no attestation exists
- trusted-publisher coordinates were never written down. Both are now, with PyPI marked
  **satisfied** (evidenced by the `1.12.5` bundles naming `Furox-Art/axiomize` and `release.yml`)
  and npm marked **pending**, together with what to change once it is registered

### Added

- `.github/scripts/check_provenance_claims.py`: parses a machine-checkable claim block in
  `docs/documentation.md` and fails when a documented `attested` value disagrees with the live
  registry. A claim of `true` that 404s fails; a claim of `false` that returns a real bundle fails;
  a 200 that is not a parseable bundle fails; a registry that cannot be reached fails rather than
  skips; the npm endpoint is negative-controlled against `left-pad@1.3.0` on every run so a 200
  cannot become meaningless; and deleting the claim block fails
- wired into the existing required `security-contract` job as one additive step. No permission,
  trigger or job-name change, so the required check context is unchanged. A provenance claim can no
  longer be introduced without registry evidence

No security claim was weakened. The PyPI attestation claim is stronger than before: it was
unqualified for a version that is no longer live, and it is now explicit, digest-matched and
continuously re-verified.

## [1.13.0] - 2026-10-09

Three additions that make physical correctness and reproducibility checkable
rather than asserted. No existing surface, console script or entry point
changes; `axiomize.visualization.canvasxpress_export` is the one new importable
module.

### Added

**Physical-plausibility validation** (`examples/physical_plausibility_validation.py`).
Dimensional analysis is necessary but not sufficient. Three models that share one
Model IR shape, one unit table and one solver differ only in the sign and the
magnitude of a drag force, so all 25 structural and all 7 unit checks pass
identically for every one of them. Conservation of energy, passivity and an
independent closed-form reference separate them: on the committed run `CORRECT`
closes its energy ledger to 2.1e-09 J, `WRONG_SIGN` misses by 5.9e+04 J and
`WRONG_SCALE` by 1.0e+02 J.

`WRONG_SCALE` is the catch the check exists for. Its speed trace never exceeds its
initial speed and its heat is monotone, so it looks plausible; it simply decays
twice as fast as the drag law it declares, and only the conservation ledger or the
closed form falsifies it. Numerical error is kept separate from model error: a
four-step tolerance ladder shows the residual falling monotonically
(1.2e-06 -> 2.5e-11 J), and the falsification threshold sits above the residual at
the settings used. The example rewrites its own captured output and exits non-zero
if that output stops describing current engine behaviour.

**Reproducibility run record** (`examples/reproducibility_run_record.py`). A run is
only reproducible if the record states what was assumed, what it was solved with,
and what came out. The record captures the mathematical assumptions, the equations,
the solver defaults and tolerances, the seed, and the versions of Python, Axiomize
and every optional backend, with a backend that is not installed reported as
not-installed rather than guessed at. It persists an integrity-hashed run
directory, recomputes the hash independently on load, and re-executes the stored
computation: the regenerated trajectory matches the recorded one bit-for-bit
(`max |dv| = 0.0`, `nfev` 203/203).

`compare_run_states` explains a divergence rather than merely flagging it. Given a
record with one loosened solver tolerance it names the changed setting
(`rtol` 1e-10 -> 1e-07, `atol` 1e-12 -> 1e-09) and its likely reason, which is what
makes a divergence explainable instead of mysterious. The run directory is written
to a temporary location, so a clean checkout is left with nothing behind.

**CanvasXpress export** (`src/axiomize/visualization/canvasxpress_export.py`).
Builds CanvasXpress JSON chart definitions from the same numeric results the rest
of the engine produces, so an interactive chart can never be built from a number
that is not also recorded in the run. Five chart kinds are covered: trajectory,
sensitivity, response surface, 3D response surface and dependency graph.

Two properties are deliberate. No silent invention: every value passes the same
finite/shape checks the simulation path uses, so a NaN, a ragged matrix or a
misaligned annotation raises instead of producing a chart that silently drops rows,
which is how CanvasXpress would otherwise misalign every sample. And charts carry
their own provenance: `attach_run_record` binds the input hash, recorded results,
validation outcome, assumptions, solver settings and tool versions under a reserved
`axiomize` key that CanvasXpress ignores, so a chart can be audited without the
conversation that produced it. The module emits JSON only and needs no browser,
JavaScript runtime or optional visualization backend. Sensitivity ranking is shared
with the existing Matplotlib helper, so a chart and a PNG can never disagree. The
Matplotlib helpers in `axiomize.visualization.plots` are untouched.

`docs/repro-visibility.md` ties the three examples together with exact reproduction
commands and the real captured outputs, and states plainly what they do not
establish: one model family on one machine, reproducibility verified within a
single environment only, charts validated as JSON definitions but not rendered, and
the `model_visualize` MCP tool recorded as the intended consumer without being
dispatched by the server yet.

### Quality

Measured on this branch rather than carried forward: coverage improved from 69.4%
to 70.2% and mypy errors fell from 35 to 28. Ruff holds at 81 findings, so the
ratchet budget is unchanged.

### Not changed here

- cross-environment reproducibility is not demonstrated. Only the interpreter that
  has the optional backends installed ran the comparison, so "reproduces the
  trajectory bit-for-bit" is a claim about one environment, not a portability claim
- the CanvasXpress charts are validated as JSON definitions and re-parsed, never
  rendered. No external CanvasXpress JavaScript was loaded, so the check is that the
  definitions are well-formed and internally consistent, not that they draw
- `model_visualize` is documented as the intended MCP consumer of the export module
  but is not yet dispatched by `mcp_server.py`

## [1.12.5] - 2026-10-04

Documentation only. No library code, CLI surface, or public API change; the importable surface,
console scripts and entry points are identical to `1.12.4`. This release exists so PyPI's project
page picks up the corrected README: `pyproject.toml` uses `README.md` as the `long_description`,
and the PyPI `1.12.4` page still shows the README as it stood at that release.

### Fixed

Four README claims the installed package did not support, each verified by running the installed
wheel rather than reading source:

- "Exports to JSON, Python, YAML, notebooks, SBML, CellML, Modelica, GraphML, and LaTeX" listed
  LaTeX as an export format. It is not in the dispatch chain: `latex`, `tex` and `pdf` all raise
  `ValueError`. LaTeX is a separate report-conversion path via `axiomize-to-latex`. The export list
  now names `SBML Level 3` and `CellML 2.0` precisely, and adds the two formats the claim had
  omitted: `causal-dot` and `portable-bundle`
- `pip install axiomize[playground]` left the reader with dependencies and nothing to run.
  `playground/app.py` is in neither the wheel nor the sdist. The instruction now says to fetch the
  file from the repository
- "the 18 example files" was wrong; `examples/` holds 19 (18 `.md` plus `quickstart_sir.py`)
- the Python quickstart block had drifted from `examples/quickstart_sir.py`, missing
  `"domain": "epidemiology"` and the `bounds` field on beta and gamma. The two are now identical
  field for field and print the same output
- the console-script table listed `ebm` and `portfolio` as `axiomize-validate` models. The tool
  accepts exactly `sir`, `gillespie`, `queue`

npm status, which `1.12.4` could not yet state correctly:

- the README and `docs/documentation.md` described npm as unpublished. npm `1.12.4` is published and
  is `dist-tags.latest`, matching PyPI, so the npm version badge is restored and the "not published"
  and "registry serves the broken 1.12.2" claims are removed
- the README npm section now records which release is which: `1.12.2` was published broken, because
  its `index.js` had a syntax error, and `1.12.4` is the first working npm release
- supply-chain provenance was implied rather than stated. PyPI `1.12.4` publishes PEP 740
  attestations for both the wheel and the sdist naming `Furox-Art/axiomize` via `release.yml`,
  recorded in the Sigstore transparency log. The npm `1.12.4` tarball was published in token mode
  and carries **no** attestation: the npm attestations endpoint returns 404 for `axiomize@1.12.4`
  while returning 200 for packages published with trusted publishing. The README and
  `docs/documentation.md` now say so explicitly and point readers at `dist.integrity` for npm
  verification instead of implying provenance exists
- `docs/documentation.md` warns that npm `dist.signatures` are registry metadata signatures, not
  provenance, and that a 404 must be distinguished from a wrong URL by testing the endpoint against
  a package known to publish attestations
- `docs/documentation.md` gained a post-release verification step: confirm `dist-tags.latest`
  actually advanced, and `node --check` the published files rather than only the repository copy

### Added

Public-surface coverage in the README, so a reader can tell what the package actually offers
without reading the source. Counts come from the installed handlers rather than source comments:
34 MCP tools from a real `tools/list` over stdio, 30 REST handlers under `/v1`, 8 console scripts
from the wheel's entry points, and repo counts from the tree.

- all 8 console scripts, described
- all 14 `axiomize` subcommands
- all 16 `model --action` values, grouped
- the MCP tool inventory by naming convention, with the live enumeration method, plus the honest
  note that both server surfaces are larger than any README can list
- the 30 REST route handlers, with a curl probe
- 12 domain packs, 15 perspective lenses, 5 report templates, and `server.json`
- a measured export-format table separating unconditional formats from those needing a specific
  model family

`docs/integrations.md` and `docs/portable-export.md` were rewritten to carry the per-module detail
the README no longer duplicates.

### Not changed here

- npm provenance cannot be added to the existing `1.12.4`: attestations are bound to a publish
  event. A future release using trusted publishing can carry them, and that is the only fix.
- no gate yet asserts the README's export-format list or its tool counts, so this class of drift
  can recur. Such a gate needs the installed wheel to be meaningful and belongs in a change that
  owns `.github/scripts/`.

## [1.12.4] - 2026-10-02

Documentation and repository visibility. No library code, CLI surface, or public API changed.

- The README now carries `mcp-name: io.github.Furox-Art/axiomize` and `server.json` describes the existing `axiomize mcp` server.
- The npm shim is no longer published. PyPI is the install path. **Superseded:** npm publishing was
  re-enabled in #41/#42 and `1.12.4` reached the registry on 2026-10-03. See the `Unreleased`
  section above for the current npm state.
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
  npm section did not say what the failure was. The badge was removed and the section was rewritten
  to separate the repository fix from the published package, which was still broken at the time.
  **Superseded:** the badge is back in the `Unreleased` section above, because npm `1.12.4` is now
  published and matches PyPI.
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
  rather than reimplementing them, so those fixes are present and were not re-derived here.
  **Superseded:** npm `1.12.4` has since been published from that fixed tree.
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