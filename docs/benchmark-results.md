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

**Suite average: 9.21/10 , threshold is 16/20 combined (automated layer shown here; 73.7/8 = 9.21, previously miscomputed as 9.35).**

> **Limitation:** the automated layer checks template compliance (sections, tables, code blocks), not correctness. A deliberately nonsensical report (`R0 = beta+gamma`, beta in kg, negative population, extinction prob. 7) scores **10/10** while the genuine `epidemic-threshold` report scores 8.2. The “9.21” is therefore evidence of formatting discipline, not modeling quality; the human rubric layer is required.

Qualitative notes from the same wave:

- Rigor escalation rule fired unprompted in 3 of 8 sessions (threshold risk / lens disagreement)
- Agents caught and documented their own numerical artifacts (relay chatter, RK4 stiffness)
- Parallel-dispatch fallback to sequential was correctly disclosed in every report lacking a subagent tool

## Adversarial QA wave (same day)

Three read-only auditors attacked tools and docs:

- **Tool stress testing** (20 probes): found Erlang-C overflow crash on realistic call-center loads, csv_check false-PASS on extreme outliers, fit.py bound/parse crashes, benchmark_runner silent-wrong exit code , all fixed in v1.3.1 and re-verified (overflow probe now completes with all checks PASS).
- **Consistency audit**: 10 HIGH findings (stale lens counts across README/mkdocs/docs after rapid expansion; phantom pack files) , all resolved; standalone epidemiology/operations packs created.
- **Math referee**: 3 ERRORs (stochastic fade-out formula , replaced with exact jump-chain result and numerically verified 0.0500 sim vs 0.0481 theory; garbled inventory Q* formula; Leslie matrix survival wording), 5 IMPRECISE , all fixed. ~30 other formulas verified correct as written.

## Wave: 2026-08-29 · numeric oracle cases (2 new ideas, first oracle-gated wave)

| Case | Score /10 | Verdict | Report |
|------|-----------|---------|--------|
| physics-pendulum-drift | 10.0 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/physics-pendulum-drift.md) |
| chemistry-batch-yield | 10.0 | PASS | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/chemistry-batch-yield.md) |

**New cases average: 10.0/10 · Full suite (10 cases): 93.7/10 = 9.37/10** , both contain the oracle keyword with a number inside tolerance (`period 2.01`, `yield 0.85`), so the deliberate nonsense report that previously scored 10/10 would now **FAIL** the oracle check.

Reproduce any grade: `python skills/axiomize/tools/benchmark_runner.py --case <id> --report <file>`
