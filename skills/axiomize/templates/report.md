# Template: Final Model Report

The deliverable of every full modeling session. Copy this skeleton, fill every section, delete nothing (write "none" where a section is empty — empty sections are information).

---

# Model Report: <one-line name>

**Idea as stated:** <user's original words, quoted>
**Model in one sentence:** <"This idea reduces to a ___-type system with ___">

## 1. Decomposition

| Sub-problem | Nature | Archetype match |
|---|---|---|
| ... | flow / interaction / decision / uncertainty | canonical model or "novel" |

Couplings: <which sub-problems feed which>

## 2. Parameters

<full table from templates/parameters.md — symbol, unit, exo/endo, range, source, sensitivity, used-in-lens>

Excluded: <what you left out and why>

## 3. Assumptions

<table from templates/assumptions.md — with [E]/[R]/[S] class and violation consequence>

Load-bearing assumptions: <the ones that flip conclusions if wrong>

## 4. Perspective models

For each lens built:

```
### <Lens>
Model:      <formal equations, every symbol defined, units attached>
Fits because: <one sentence tied to decomposition>
Unique insight: <what ONLY this view reveals>
Blind spot: <what this view cannot see>
```

Rejected lenses (one line each): <lens> — <why not worth its cost here>.

## 5. Comparison

<scored table 1-5 per criterion; only built lenses as columns>

| Criterion | Lens A | Lens B | ... |
|-----------|--------|--------|-----|

**Recommendation:** <primary model> (+ <secondary, for validation>) — justified by the scores.

## 6. Implementation & validation

```python
# runnable reference code OR tool invocation
```

Sanity checks run: <conservation / bounds / theory-match / distributional — PASS status>
Sensitivity sweep: <top-2 sensitive parameters, what moved>

## 7. Predictions & falsifiability

Concrete predictions: <numbers/intervals this model commits to>
Killed by: <observations that would falsify it, mapped back to assumptions>

## 8. Confidence ledger

| Claim | Type | Basis |
|-------|------|-------|
| e.g., "R0 > 1 ⟹ outbreak" | established | standard SIR theory |
| e.g., "demand is i.i.d. weekly" | assumption | needs data check |
| e.g., "customers will accept 3 min waits" | speculation | unvalidated |

---
*Generated via Axiomize workflow · archetypes matched: <list>*
