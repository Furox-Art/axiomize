---
name: quantum-reasoning
description: Maintain multiple genuinely different candidate hypotheses or solution paths, test them against evidence and tools, suppress weak or contradictory paths, revive useful alternatives when new evidence appears, and collapse to the best-supported answer only at the end.
---

# Quantum Reasoning Skill

A model-facing reasoning protocol inspired by the idea of keeping multiple possibilities alive before selection. It runs on classical models and classical hardware; it is not quantum computation.

## When to use

Use this skill when a problem is difficult, ambiguous, high-stakes, multi-step, or vulnerable to early commitment: mathematics, scientific reasoning, debugging, planning, architecture, model selection, hypothesis testing, and technical diagnosis.

Do not add branching overhead to trivial questions.

## Core protocol

### 1. Frame the state

Identify the objective, constraints, verified facts, assumptions, unknowns, and available tools. Keep facts separate from hypotheses.

### 2. Open a diverse possibility set

Create several materially different candidate paths. Diversity is mandatory: do not count paraphrases, cosmetic variants, or branches that depend on the same hidden assumption as independent possibilities.

Prefer orthogonal strategy classes when applicable, such as:

- direct derivation
- counterexample / falsification
- decomposition
- alternative model or mechanism
- numerical or executable test
- independent reconstruction
- adversarial critique

### 3. Maintain branch states

Treat each candidate as one of:

- **active** — worth more compute now
- **dormant** — currently weak but potentially recoverable
- **rejected** — contradicted or decisively invalidated

Never permanently reject a branch merely because another branch initially looks more plausible.

### 4. Evaluate each branch independently

Judge branches using evidence, not eloquence. Consider:

- empirical or logical support
- external verification
- independence from other branches
- information gain
- contradiction count and severity
- unresolved assumptions
- expected value of another reasoning step
- compute / tool cost

Self-reported model confidence alone is weak evidence.

### 5. Use tools to falsify, not merely confirm

When available, route claims through the strongest suitable verifier: executable code, numerical tests, formal solvers, source lookup, direct file inspection, unit tests, symbolic algebra, or an independent model pass.

Actively search for evidence that would disprove leading branches.

### 6. Apply interference-like comparison

Compare branches against each other without pretending to perform quantum interference.

- Reinforce conclusions independently reached by different verified paths.
- Penalize branches that conflict with verified facts.
- Detect shared assumptions so correlated branches are not double-counted.
- Transfer newly verified facts to every branch they constrain.
- Preserve meaningful disagreement instead of averaging incompatible claims.

### 7. Allocate compute dynamically

Use uncertainty to control width and depth.

- **Low uncertainty:** narrow quickly and deepen the strongest path.
- **High uncertainty:** widen the possibility set.
- **High-value unresolved branch:** spend additional tool or reasoning budget.
- **Redundant or contradicted branch:** move to dormant or rejected.

Branch count is adaptive, not fixed.

### 8. Permit branch revival

If new evidence invalidates a leading assumption or materially improves a dormant branch, restore that branch to active status and re-evaluate the ranking.

### 9. Stop when more search has low value

Collapse the possibility set when one result is sufficiently verified, remaining branches are redundant or falsified, or additional search is unlikely to change the decision enough to justify its cost.

If multiple branches remain genuinely unresolved, report the alternatives and what evidence would distinguish them.

### 10. Produce the answer

Synthesize only from the strongest supported surviving branches. Run a final contradiction and requirement check before answering.

Do not expose hidden chain-of-thought. Return the conclusion, concise supporting evidence, important uncertainty, and materially different surviving alternatives when necessary.

## Adaptive intensity

Use a rough internal intensity level:

- **light:** 2–3 distinct candidates, one comparison pass
- **standard:** 4–8 candidates, verification + pruning + one revival check
- **deep:** 8+ candidates only when the problem and compute budget justify it; use repeated verification and adaptive expansion

Do not mechanically maximize branch count. The goal is better search of the possibility space, not more text.

## Operational reference policy

When the host system can track aggregate branch metadata, use explicit normalized values in `[0, 1]` for evidence, verification, independence, information gain, contradiction severity, unresolved assumptions, compute cost, shared-assumption overlap, and semantic redundancy.

A provider-agnostic reference controller is available in [`reference/branch_controller.py`](./reference/branch_controller.py). Its defaults make the qualitative protocol testable:

- independence is reduced when branches share critical assumptions or are near-duplicates
- strong contradiction can reject a branch
- weak branches become dormant instead of disappearing
- dormant branches can revive after a material evidence, verification, or contradiction change
- uncertainty controls a recommended search width
- collapse requires a verified leader, low contradiction, and a meaningful margin over surviving alternatives

The exact scoring weights and thresholds are **reference defaults, not validated constants**. They must be calibrated against benchmark evidence rather than treated as universal truths. See [`docs/MEASUREMENT.md`](./docs/MEASUREMENT.md) for the auditable formulas and thresholds.

Hosts that cannot expose these aggregate measurements should still follow the qualitative protocol above and must not invent numeric telemetry.

## Benchmark requirement

Do not claim that this skill improves reasoning merely because the protocol sounds plausible. Compare the same model and task configuration with and without the skill and measure at least accuracy, compute/token cost, latency, error recovery, contradiction resolution, and branch diversity when observable.

The reproducible benchmark schema and evaluator live under [`benchmark/`](./benchmark/README.md).

## Non-negotiable rules

1. Do not call this real quantum computation.
2. Do not treat repeated wording as independent evidence.
3. Do not let one branch evaluate itself without challenge when verification is possible.
4. Prefer falsification and executable checks over intuition.
5. Preserve a recoverable record of high-information dormant branches.
6. Collapse only after cross-branch comparison.
7. Never fabricate evidence, tool results, sources, certainty, or branch telemetry.
8. Do not present reference thresholds as empirically validated until benchmark evidence exists.
