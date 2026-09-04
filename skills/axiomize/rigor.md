# Rigor Ladder: weak · medium · strong

One skill, three depths. Axiomize recommends the level automatically, briefly explains why, and lets the user override it. Older names remain compatible: **basic → weak**, **standard → medium**, **research → strong**.

## Selecting the level (Phase 0)

| Signals | Level |
|---|---|
| quick exploration, small everyday problem, low stakes, few interacting mechanisms | **weak** |
| no special signal; balanced analysis | **medium** |
| research/publication, high stakes, multiple domains, unclear mechanism, model conflict, high sensitivity, causal claim, real-world experiment | **strong** |

Do not choose strong merely to produce more text. Strong means **more independent tools, validation, uncertainty analysis and cross-checks**.

Announce the recommendation briefly, e.g. *"Recommended depth: medium — balanced problem with no major escalation signal."* If the user explicitly chooses another level, honor it.

## Per-phase expectations

| Phase | weak | medium | strong |
|-------|------|--------|--------|
| 1 Parse | restate idea + goal question; clarify core gaps | full system/state/goal/horizon/mechanism | + classify formal problem; test whether the question is well-posed; resolve mechanism uncertainty |
| 2 Decompose | 2-3 sub-problems | 3-7 with coupling map | + test sub-problem independence and boundary choices |
| 3 Parameters | top-5 parameters | full table with units/sensitivity | + dimensionless groups; identifiability and data-priority analysis |
| 4 Assumptions | 3 load-bearing assumptions | full checklist with violation consequences | + tie assumptions to field conventions and rival mechanisms |
| 5 Perspectives | ≥2 lightweight candidates when feasible | ≥2 formal candidate models | ≥3 independent lenses when justified + model criticism and stronger tool verification |
| 6 Compare | rank top 2-3 with short reasons | scored comparison + conditions where each wins | + weighted criteria, statistical evidence when data exist, explicit conflict investigation |
| 7 Implement | runnable minimal implementation + sanity check | fit/validate + uncertainty + sensitivity + plots | + independent verification, convergence/stability checks, stronger UQ, reproducibility record |
| 8 Deliverable | short summary + ranked options | summary + technical detail + risks + validity domain | full report + falsifiers + reproducibility + hypothesis/experiment plan when applicable |

## Escalation rule

Escalate the affected sub-problem when risk earns more depth: mechanism uncertainty, high sensitivity near a threshold, disagreement between candidate models/tools, weak identifiability, a causal claim, or a real-world test with meaningful cost/safety consequences.

Escalation does **not** grant permission to spawn extra agents, repeat the entire analysis, or make extra paid/model calls. Those remain subject to the user-consent rules in [adaptive-workflow.md](adaptive-workflow.md).

## Language rules

- Every level starts with a short plain-language summary.
- Define symbols and units; simplification must not remove scientific honesty.
- Strong mode names canonical results and states uncertainty/limitations precisely.

## Anti-patterns

- Strong-mode theater: longer prose or more LaTeX without additional evidence or checks.
- Weak-mode overconfidence: fewer checks does not justify stronger claims.
- Hiding a mechanism gap by inventing a parameter value.
- Silently multiplying API/model calls in the name of "more rigor".
