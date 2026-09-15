# Benchmark protocol

This directory measures whether the skill improves results rather than merely producing more reasoning text.

## Who runs the benchmarks

Real model evaluations are intentionally **community-run**. The repository supplies the benchmark protocol, seed cases, JSON Schemas, evaluator and submission validator; users run experiments on the models/providers they have access to.

Maintainer-run access to every commercial or local model is not required. The project therefore separates **benchmark infrastructure** from **third-party empirical results**.

Submitted results are evidence from the contributor who produced them. They are not automatically endorsed by the project and should not be generalized beyond the tested model/version/configuration without replication.

## Principle

Run the **same model, model version, task set, tool access, temperature/sampling settings, and token budget policy** twice:

1. baseline: normal instructions without `SKILL.md`
2. skill: the same setup with `SKILL.md`

Do not compare different models and attribute the difference to the skill.

## Seed cases

`cases.jsonl` contains deterministic smoke-test cases. They are intentionally small and are **not sufficient evidence of reasoning improvement**. A serious evaluation should add difficult held-out tasks from the target domains and report their provenance/licensing.

Each case has:

```json
{"id":"...","domain":"...","prompt":"...","accepted_answers":["..."]}
```

## Machine-readable schemas

The contracts are versioned with the repository:

- [`schemas/case.schema.json`](./schemas/case.schema.json) — one benchmark case
- [`schemas/result.schema.json`](./schemas/result.schema.json) — one baseline/skill result row
- [`schemas/metadata.schema.json`](./schemas/metadata.schema.json) — experiment metadata
- [`schemas/comparison.schema.json`](./schemas/comparison.schema.json) — evaluator comparison output

A result row requires:

```json
{
  "case_id": "math-arithmetic-001",
  "answer": "323",
  "tokens": 120,
  "tool_calls": 0,
  "latency_ms": 950
}
```

Failed/refused runs should still be represented rather than silently removed. The optional `status` field may be `ok`, `refusal`, `timeout`, or `error`.

Skill-aware runners may additionally record observable aggregate telemetry such as `branches_total`, `branches_distinct`, `revived_branches`, `recovered_errors`, `contradictions_found`, and `contradictions_resolved`. Do not store private chain-of-thought.

## Evaluate one run

```bash
python benchmark/evaluate.py \
  --cases benchmark/cases.jsonl \
  --skill path/to/skill-results.jsonl
```

## Compare baseline vs skill

```bash
python benchmark/evaluate.py \
  --cases benchmark/cases.jsonl \
  --baseline path/to/baseline-results.jsonl \
  --skill path/to/skill-results.jsonl \
  --output comparison.json
```

The evaluator reports exact-answer accuracy, mean token use, tool calls, latency, branch diversity, revival/error recovery, contradiction resolution, and baseline-to-skill deltas.

## Required experimental controls

For a publishable comparison, record at minimum:

- provider and exact model/version
- date of the run
- decoding/sampling parameters
- context and output limits
- tool availability
- prompt wrapper/system instructions
- number of repetitions per case
- random seed when the provider supports one
- hardware/runtime details for local models
- failures, refusals and timeouts rather than silently dropping them

Use multiple repetitions for stochastic models and report confidence intervals. Keep benchmark cases separate from any prompts used while designing or tuning the skill.

## Submitting community results

Results can be submitted in either of two ways:

1. Open a **Benchmark result** issue and provide the required metadata plus links/attachments to the result artifacts.
2. Open a pull request containing a reproducible result bundle under:

```text
benchmark/results/community/<provider>-<model>-<YYYY-MM-DD>/
```

Every benchmark-result PR bundle must contain:

```text
metadata.json
cases.jsonl
baseline.jsonl
skill.jsonl
comparison.json
README.md
```

Including `cases.jsonl` inside the bundle makes the exact evaluated case set immutable and reviewable even when custom cases are used.

Generate `comparison.json` with `benchmark/evaluate.py`; do not hand-edit it. Before opening a PR, validate the bundle:

```bash
python benchmark/validate_submission.py --root benchmark/results/community
```

CI runs the same validator. It rejects missing artifacts, incomplete metadata, duplicate/missing case results, and a `comparison.json` that differs from a fresh evaluator recomputation.

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for the complete submission and integrity policy.

## Interpretation

A useful result is not simply "skill accuracy is higher". Report the trade-off between accuracy and compute. A skill that gains 1 percentage point while using 5x tokens may be undesirable for many workloads.

The reference thresholds in `reference/branch_controller.py` are defaults to test, not validated constants. Benchmark evidence should drive later calibration.

The project makes no universal performance claim from a single model, provider, benchmark or contributor submission. Independent replication is preferred.
