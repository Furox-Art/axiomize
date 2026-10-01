# Benchmark Results

Two different things live under `benchmarks/`, and this page keeps them apart on purpose.

- **Reproducible now** — the automated layer of [benchmarks/rubric.md](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/rubric.md) applied to the ten stored blind-test reports in `benchmarks/reports/`. Reproduction inputs are recorded below, and CI reruns the same loop on every push.
- **Recorded history** — benchmark waves from 2026-08-24 and 2026-08-29, graded against an older skill version. **Not reproducible.** The generating agent, model, prompt revision and commit were never recorded, and both the skill content and the runner have changed since. Kept so the changelog history is not silently rewritten, not as current evidence.

## Reproducible run

Every number in the table below came from the command on this page, run against the stored reports
at the stated commit. Reproduce it and a different result is a real regression, not noise.

| Field | Value |
|---|---|
| Package line | 1.12.3 |
| Commit | `ffa357fc17869bef7c1ac6ce2aa99156f2cdfbeb` |
| Runner | `skills/axiomize/tools/benchmark_runner.py` · sha256 `c9bd859be3dc2d392437a377e1bec853ffae1351aa8138e5c97c906be95cb310` |
| Case set | `benchmarks/ideas.json` · sha256 `039f0e129fba83d9190de80a4e69df132d7f61a5932f941016ea3b0128620f55` · 10 cases |
| Rubric | `benchmarks/rubric.md` · sha256 `2b8e0012679c2156b640f16fbfe984d0bd6cb3eb560a918f7ee977ec00a953d6` |
| Environment | CPython 3.12.10, Windows 11 x64 |
| Run at | 2026-10-01T19:04:37Z |

```bash
python skills/axiomize/tools/benchmark_runner.py --case <id> --report benchmarks/reports/<id>.md
```

| Case | Checks | Score /10 | Report |
|------|--------|-----------|--------|
| epidemic-threshold | 11/11 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/epidemic-threshold.md) |
| barista-staffing | 10/10 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/barista-staffing.md) |
| app-adoption-ceiling | 8/8 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/app-adoption-ceiling.md) |
| duopoly-price-cut | 9/9 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/duopoly-price-cut.md) |
| reserve-ruin | 9/9 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/reserve-ruin.md) |
| greenhouse-setpoint | 8/8 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/greenhouse-setpoint.md) |
| school-rumor-reach | 8/8 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/school-rumor-reach.md) |
| ad-lift-causal | 9/9 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/ad-lift-causal.md) |
| physics-pendulum-drift | 10/10 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/physics-pendulum-drift.md) |
| chemistry-batch-yield | 10/10 | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/chemistry-batch-yield.md) |

**100 of 100 automated checks pass across 10 cases.**

### What a perfect automated score does and does not mean

The automated layer checks report *structure*: archetype vocabulary appears, required tokens are
present, a minimum number of lens blocks exists, at least one lens was rejected with a stated
reason, and the contract artifacts (parameter table with units, assumptions with consequences,
falsifiability section) are present. It does not evaluate whether the mathematics is correct.

Two things follow, and both matter:

- A uniform 10.0 means the stored reports satisfy every structural check the runner makes. It is
  not a quality ranking, and the ten cases are not comparable to one another on any axis beyond
  pass/fail.
- The `PASS` in the runner output is the **automated** verdict at a 7.5/10 threshold. The rubric's
  real gate is a combined automatic + human score of at least 15/20 per case with a suite average
  of at least 16/20. The human layer is a human judgement and is **not recorded anywhere in this
  repository**, so no combined score is published here. Treat the automated column as a structural
  smoke test and nothing more.

CI reruns exactly this loop, so the table cannot silently drift away from the stored reports.

### Stored reports that are not graded

`benchmarks/reports/` also holds two reports whose cases are absent from `ideas.json`. No case id
resolves for them, so CI neither grades nor checks them:

- [`novel-async-alignment.md`](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/novel-async-alignment.md)
- [`novel-telephone-fidelity.md`](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/novel-telephone-fidelity.md)

They are kept as sample reports. Do not read them as scored results.

## Recorded history (not reproducible)

These waves were produced by agents working from `ideas.json` prompts with fresh memory, forbidden
from reading `examples/`, `benchmarks/`, `docs/` and `packs/`. Nothing about the run environment
was recorded, and the skill has since moved from the v1.3.x line to 1.12.3. The scores below
cannot be rerun and are published only as a record.

### Wave 2026-08-24 · skill v1.3.0 content · automated layer only

| Case | Score /10 | Report |
|------|-----------|--------|
| school-rumor-reach | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/school-rumor-reach.md) |
| greenhouse-setpoint | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/greenhouse-setpoint.md) |
| barista-staffing | 10.0 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/barista-staffing.md) |
| duopoly-price-cut | 8.9 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/duopoly-price-cut.md) |
| reserve-ruin | 8.9 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/reserve-ruin.md) |
| ad-lift-causal | 8.9 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/ad-lift-causal.md) |
| app-adoption-ceiling | 8.8 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/app-adoption-ceiling.md) |
| epidemic-threshold | 8.2 | [report](https://github.com/Furox-Art/axiomize/blob/main/benchmarks/reports/epidemic-threshold.md) |

Suite average as recorded at the time: 73.7/80 = 9.21/10, automated layer only. An earlier 9.35
figure was a miscomputation, corrected at the time.

Qualitative notes recorded from the same wave. Unverified and not rerunnable:

- The rigor escalation rule fired unprompted in 3 of 8 sessions.
- Agents documented their own numerical artifacts (relay chatter, RK4 stiffness).
- Where the runtime exposed no subagent tool, the reports disclosed the sequential fallback.

### Wave 2026-08-29 · numeric oracle cases

`physics-pendulum-drift` and `chemistry-batch-yield` were the first cases carrying a numeric
oracle; both were reported at 10.0/10 on the automated layer. Reviewers noted at the time that a
deliberately nonsensical report would have passed the earlier structural-only wave and that the
oracle gate should catch it. The nonsensical report itself is not in this repository, so that note
cannot be re-verified here. The oracle gate itself is visible in `ideas.json`.

### Adversarial QA wave · 2026-08-24

Three read-only passes over the tools and docs reported roughly 20 tool probes, a consistency audit
and a math referee pass, with fixes landing in the v1.3.1 line. No probe transcripts or audit
reports are stored in this repository. This paragraph is an unverified historical note.

## What would make this benchmark stronger

Recorded as an open item rather than a claim. A numeric oracle on every case, a published human
layer, and per-wave records of generating agent, model, prompt hash and commit would turn the
structural smoke test above into evidence about modeling quality. Until then it is not that.
