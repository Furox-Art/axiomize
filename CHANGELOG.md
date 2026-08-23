# Changelog

All notable changes to Axiomize are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/); versioning is SemVer.

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

[1.0.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.0.0
