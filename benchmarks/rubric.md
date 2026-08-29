# Benchmark Scoring Rubric

How to grade an axiomize session against [ideas.json](ideas.json). Two graders: automated string checks + human judgment on quality bars.

## Automated layer (scriptable)

For each case, check the produced report for:

1. **Archetype match** — the `expected_archetype` concept appears with formal structure (not just name-dropped)
2. **`must_contain` tokens** — every regex hits somewhere in the report
3. **Lens count** — number of `### Perspective:` blocks ≥ `min_lenses_built`
4. **Rejection discipline** — if `must_reject_at_least_one`, at least one lens rejected WITH a reason line
5. **Contract artifacts** — parameter table present with Unit column non-empty; assumptions table has violation-consequence column filled; falsifiability section names observations, not vibes

Score = 10 * passed / total, where total is 8–12 depending on the case (must_contain length, whether rejection is required, and whether a numeric oracle is present). Previously stated as “/5” which did not match the runner’s variable denominator; scores were therefore incomparable across cases. Human total /10 is added to automated /10 → final /20 per case.

## Human layer (rubric, score each 0–2)

| Dimension | 0 | 1 | 2 |
|-----------|---|---|---|
| Symbol discipline | undefined symbols | minor gaps | every symbol defined inline |
| Units | missing | partial | all quantities carry units |
| Assumption honesty | no classes | classes but no consequences | `[E]/[R]/[S]` + consequence each |
| Comparison honesty | single lens pushed | table without justification | scores tied to goal question |
| Plain-language opener | absent | present, jargon leaks | ≤5 sentences, clean |

Human total /10, added to automated fraction ×10 → final /20 per case.

## Pass thresholds

- Individual case: ≥ 15/20
- Suite: ≥ 16/20 average AND zero cases below 12

A failing suite blocks any SKILL.md structural change from shipping (regression guard).
