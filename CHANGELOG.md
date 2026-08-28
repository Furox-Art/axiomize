# Changelog

All notable changes to Axiomize are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/); versioning is SemVer.

## [1.5.0] - 2026-08-24

### Added
- First-principles protocol (`skills/axiomize/first-principles.md`) for ideas with no matching archetype: derive the model from conservation/accounting identities instead of forcing a known template
- Two novel-domain benchmark reports exercising that path — async-alignment and telephone-fidelity — neither drawn from the archetype catalog
- Novel-territory appendix in the report template, recording which quantities were derived rather than borrowed

### Changed
- SKILL.md routes to the first-principles protocol when archetype matching fails

## [1.4.1] - 2026-08-24

### Fixed
- LaTeX converter hardening: all 11 worked examples and 8 benchmark reports now compile with zero errors
- `texput.log`, a LaTeX build artifact, had been committed in 1.4.0; removed and `*.aux` / `*.log` / `*.out` added to `.gitignore`

## [1.4.0] - 2026-08-24

### Added
- LaTeX/PDF export for reports (`skills/axiomize/tools/report_to_latex.py`): booktabs tables, verbatim code blocks, unicode transliteration
- Sample rendered report checked in as `docs/report-sample.tex` / `.pdf`

## [1.3.2] - 2026-08-24

### Added
- Animated demo embedded in the README
- Benchmark regression wired into CI: the eight stored blind-test reports are replayed on every run, so a scoring regression fails the build

## [1.3.1] - 2026-08-24

### Added
- Eight blind-test benchmark reports committed under `benchmarks/reports/` (8/8 PASS, mean score 9.35) plus `docs/benchmark-results.md` summarising them
- Epidemiology and operations domain packs filled out

### Fixed
- QA-wave defects: fade-out theory formula, Erlang-C overflow on large offered load, `csv_check` reporting a false PASS, and `fit` bounds

### Removed
- Registry submission kit (`docs/submissions.md`) — premature

## [1.3.0] - 2026-08-24

### Added
- Three new lenses: decision theory (deep uncertainty, EVPI), demographic/actuarial, spatial statistics — fifteen total
- Benchmark runner: `benchmark_runner.py` grades produced reports against ideas.json cases automatically
- `fit.py --json` for machine-readable calibration output
- Local playground: Gradio UI wrapping csv_check + calibration (`playground/app.py`)
- Example gallery page and registry submission kit in docs
- Domain pack: project management

### Fixed
- benchmark_runner --case-list no longer requires --report

## [1.2.0] - 2026-08-24

### Added
- Three new lenses: reliability engineering, statistical process control, thermodynamic analogies (twelve total)
- Three new worked examples: fleet maintenance (reliability), marketing attribution (causal), sensor placement (information theory) — eleven examples total
- Benchmark suite: `benchmarks/ideas.json` with 8 standard test cases + scoring rubric
- Domain packs: economics and ecology (alongside epidemiology and operations)
- Beginner tutorial: `docs/tutorial.md`
- New tool: `csv_check.py` — data quality pre-check before calibration
- Parallel subagent wave executed for lens/example authoring; orchestrator integration pattern documented by example

### Fixed
- f-string backslash incompatibility breaking Python 3.9/3.11 in parallel_sweep.py

## [1.1.0] - 2026-08-24

### Added
- Three new lenses: game theory, causal inference, information theory (nine total)
- Archetype catalog expanded 16 → 30 entries
- Five new worked examples: network rumor, greenhouse control, startup growth (Bass + calibration), insurance ruin risk, café pricing war — network and control lenses now have dedicated examples
- Mermaid coupling diagrams in Phase 2 and the report template
- `fit.py`: AIC/BIC diagnostics, residual autocorrelation flag, `--compare` mode ranking models on the same data
- `tools/index_reports.py`: rebuilds `reports/INDEX.md`; sessions now cross-reference earlier reports
- Glossary template supporting basic-tier readers
- GitHub Pages site (`mkdocs-material`) via Pages workflow
- Domain packs: epidemiology, operations
- Publishing checklist for external registries
- CI: Python 3.9 / 3.11 / 3.13 matrix with dependency floors

## [1.0.0] - 2026-08-24

First tagged release.

### Added
- 8-phase workflow: parse → decompose → parameters → assumptions → multi-perspective modeling → comparison → implementation → falsifiability
- Six mathematical lenses: deterministic, stochastic, optimization, agent-based, network, control
- Archetype catalog mapping idea patterns to canonical models (SIR, Bass, newsvendor, M/M/c, logistic, Lotka–Volterra...)
- Three-tier rigor ladder (basic / standard / research) with plain-language guarantee and automatic escalation on threshold risk
- Parallel Dispatch Protocol: lenses run as independent subagents from frozen self-contained briefs; assumption conflicts surface at merge
- Standardized report template with confidence ledger and research appendix
- Tools bundled inside the skill:
  - `validate.py` — SIR / Gillespie CTMC / Erlang-C queue modes with sanity checks and sweeps
  - `fit.py` — parameter calibration from CSV data with confidence intervals and self-tests
  - `parallel_sweep.py` — real process-pool execution of grids and Monte Carlo chunks
  - `check_skill.py` — metadata, link and compile linter (wired into CI)
- Three worked examples: epidemic SIR, retail inventory, coffee-shop staffing
- GitHub Actions CI running all validation modes

[1.5.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.5.0
[1.4.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.4.1
[1.4.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.4.0
[1.3.2]: https://github.com/Furox-Art/axiomize/releases/tag/v1.3.2
[1.3.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.3.1
[1.3.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.3.0
[1.2.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.2.0
[1.1.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.1.0
[1.0.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.0.0
