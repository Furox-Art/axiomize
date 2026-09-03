# Rigor Ladder: basic · standard · research

One skill, three depths. A student asking "how many baristas?" and a PhD student building a thesis chapter both get served, without the student drowning or the researcher getting toy output.

## Selecting the level (Phase 0)

| User signals | Level |
|---|---|
| "quickly", "roughly", "just tell me", casual chat, small everyday decision | **basic** |
| nothing specified (DEFAULT) | **standard** |
| "rigorous", "research-grade", "for my thesis/paper", "publishable", "PhD-level", mentions of reviewers/grants | **research** |

Announce the chosen level in your first line: *"Rigor level: standard"*, and offer the ladder once: *"say 'deeper' or 'quicker' anytime."*

## Per-phase expectations

| Phase | basic | standard | research |
|-------|-------|----------|----------|
| 1 Parse | restate idea + goal question | full system/state/goal/horizon | + classify the formal problem type; state whether it is even well-posed as asked |
| 2 Decompose | 2-3 sub-problems | 3-7 with coupling map | + test sub-problem independence; critique where boundaries were drawn |
| 3 Parameters | top-5 parameters only | full table with units/sensitivity | + reduce to dimensionless groups (Buckingham π); flag which parameters are identifiable from realistic data |
| 4 Assumptions | 3 load-bearing ones | full checklist, [E]/[R]/[S] | + tie each to the field's convention (cite the standard practice by name) |
| 5 Perspectives | 2 lenses, informal math acceptable | ≥ 2 lenses, formal notation | ≥ 3 lenses + **model criticism**: for each lens name the strongest rival hypothesis it silently excludes |
| 6 Compare | 3 criteria, prose verdict | 5 criteria, scored table | + justify criterion weights from the goal question; if data exist, mention information criteria (AIC/BIC) for statistical candidates |
| 7 Implement | sketch or reference code | runnable code + sanity checks | + uncertainty quantification (intervals, not points), fixed seeds, convergence/stability notes |
| 8 Deliverable | plain summary + recommendation | full report template | full report + explicit limitations, reproducibility statement (seeds/versions/data needs), named canonical results |

## Language rules

- **All tiers:** the final deliverable OPENS with *Plain-language summary*, ≤ 5 sentences a smart 15-year-old could follow. Professor-level content, entrance-level door.
- **basic:** define every symbol inline the moment it appears; prefer analogy over abstraction; no undefined jargon, ever.
- **research:** name the canonical results you inherit (Engset insensitivity, final-size equation, Bellman optimality...) instead of re-deriving them; precision beats pedagogy.

## Escalation rule

If a basic- or standard-tier run reveals a red flag, a parameter marked high-sensitivity sits exactly at a threshold (R₀ ≈ 1, ρ ≈ 1), two lenses disagree on the recommendation, or the falsifiers look cheap to trigger, escalate THAT sub-problem one tier up, announce it, and continue. Depth is earned by risk, not requested by vanity.

## Anti-patterns

- Research-tier theater: LaTeX everywhere but no model criticism or UQ, decoration is not depth.
- Basic-tier condescension: simplifying by omitting units or assumptions rather than by omitting ceremony.
- Mixed tiers inside one phase without announcement.
