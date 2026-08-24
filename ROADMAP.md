# Roadmap

Public plan. Checked items ship; everything here is open for contribution — see CONTRIBUTING.md.

## Shipped

- [x] v1.0.0 — 6 lenses, archetype catalog, rigor ladder, parallel dispatch, bundled tools, CI

## Shipped in v1.1

- [x] Mermaid coupling diagrams in reports
- [x] Glossary for basic-tier readers
- [x] Archetype catalog 16 → 30
- [x] New lenses: game theory, causal inference, information theory (+ reliability, SPC, thermodynamic analogies in v1.2)
- [x] Five new worked examples (network, control, growth-calibration, ruin risk, pricing game) + fleet maintenance in v1.2
- [x] fit.py: residual diagnostics + AIC/BIC model comparison + --compare mode
- [x] reports/INDEX.md auto-generation and cross-session referencing
- [x] Animated demo GIF
- [x] GitHub Pages documentation site
- [x] CI Python version matrix
- [x] Issue/PR templates

## Shipped in v1.3

- [x] Lenses 12 → 15: decision theory, demographic/actuarial, spatial statistics
- [x] Benchmark runner (benchmark_runner.py) grading reports against ideas.json
- [x] fit.py --json machine-readable output
- [x] Gradio playground (playground/app.py)
- [x] Example gallery page + beginner tutorial
- [x] Project-management domain pack

## Shipped in v1.2

- [x] Lenses 9 → 12: reliability engineering, statistical process control, thermodynamic analogies
- [x] Worked examples for reliability, causal inference, information theory lenses
- [x] Benchmark suite: benchmarks/ideas.json + scoring rubric (8 standard test cases)
- [x] Domain packs: economics, ecology (+ epidemiology, operations earlier)
- [x] Beginner tutorial (docs/tutorial.md)
- [x] CSV data quality pre-check tool (csv_check.py)

## Later / candidates

- [ ] Benchmark suite: 10 standard test ideas + scoring rubric for skill quality regression
- [ ] Web playground (Gradio/Streamlit) demo deployment
- [ ] Submission to agent-skill registries and awesome lists
- [ ] JSON export of parameter tables for downstream tooling

## Non-goals

- Becoming a solver engine (we generate and validate models; heavy numerics belong to established solvers)
- Fine-tuning models on modeling corpora (prompt-discipline first; revisit only if evidence shows ceiling)
