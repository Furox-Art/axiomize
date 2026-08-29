# Benchmark Results

Automated layer of [benchmarks/rubric.md](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/rubric.md) applied to blind-test reports produced by independent agents (fresh memory; forbidden from reading examples/, benchmarks/, docs/, packs/).

## Wave: 2026-08-24 · skill version at test time: v1.3.0 content

| Case | Score /10 | Verdict | Report |
|------|-----------|---------|--------|
| school-rumor-reach | 10.0 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/school-rumor-reach.md) |
| greenhouse-setpoint | 10.0 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/greenhouse-setpoint.md) |
| barista-staffing | 10.0 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/barista-staffing.md) |
| duopoly-price-cut | 8.9 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/duopoly-price-cut.md) |
| reserve-ruin | 8.9 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/reserve-ruin.md) |
| ad-lift-causal | 8.9 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/ad-lift-causal.md) |
| app-adoption-ceiling | 8.8 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/app-adoption-ceiling.md) |
| epidemic-threshold | 8.2 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/epidemic-threshold.md) |

**Suite average: 9.21/10 — threshold is 16/20 combined (automated layer shown here; 73.7/8 = 9.21, previously miscomputed as 9.35).**

> **Limitation:** the automated layer checks template compliance (sections, tables, code blocks), not correctness. A deliberately nonsensical report (`R0 = beta+gamma`, beta in kg, negative population, extinction prob. 7) scores **10/10** while the genuine `epidemic-threshold` report scores 8.2. The “9.21” is therefore evidence of formatting discipline, not modeling quality; the human rubric layer is required.

Qualitative notes from the same wave:

- Rigor escalation rule fired unprompted in 3 of 8 sessions (threshold risk / lens disagreement)
- Agents caught and documented their own numerical artifacts (relay chatter, RK4 stiffness)
- Parallel-dispatch fallback to sequential was correctly disclosed in every report lacking a subagent tool

## Adversarial QA wave (same day)

Three read-only auditors attacked tools and docs:

- **Tool stress testing** (20 probes): found Erlang-C overflow crash on realistic call-center loads, csv_check false-PASS on extreme outliers, fit.py bound/parse crashes, benchmark_runner silent-wrong exit code — all fixed in v1.3.1 and re-verified (overflow probe now completes with all checks PASS).
- **Consistency audit**: 10 HIGH findings (stale lens counts across README/mkdocs/docs after rapid expansion; phantom pack files) — all resolved; standalone epidemiology/operations packs created.
- **Math referee**: 3 ERRORs (stochastic fade-out formula — replaced with exact jump-chain result and numerically verified 0.0500 sim vs 0.0481 theory; garbled inventory Q* formula; Leslie matrix survival wording), 5 IMPRECISE — all fixed. ~30 other formulas verified correct as written.

## Pending cases (added 2026-08-28, awaiting benchmark wave)

Two new cases with numeric oracle were added to `benchmarks/ideas.json` after the 2026-08-24 wave:

| Case | Prompt | Oracle |
|------|--------|--------|
| physics-pendulum-drift | damped pendulum's period drifts as amplitude decays | `period ~ 2.0 ±0.3` |
| chemistry-batch-yield | batch reactor's yield depends on temperature and residence time | `yield ~ 0.85 ±0.1` |

Run the next wave to populate scores: `python skills/axiomize/tools/benchmark_runner.py --case physics-pendulum-drift --report <file>`

Reproduce any grade: `python skills/axiomize/tools/benchmark_runner.py --case <id> --report <file>`
