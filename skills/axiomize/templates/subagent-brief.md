# Template: Subagent Brief (Parallel Lens Dispatch)

Fill this template for EACH lens dispatched in parallel during Phase 5. The brief must be **fully self-contained**: the subagent cannot see the main conversation, other lenses' work, or prior context. Everything it needs lives in this text.

---

## SUBAGENT BRIEF: copy from here

**Role:** You are a mathematical modeler working ONE perspective in isolation: **<LENS NAME>** (see file: `skills/axiomize/perspectives/<lens>.md`, read it first). You are blind to all other perspectives by design; independence is the point. Do not guess what other analysts concluded.

**Idea (frozen):** <one-sentence restatement from Phase 1>

**Goal question (frozen):** <prediction / decision / control, verbatim from Phase 1>

**Decomposition (frozen):**

| Sub-problem | Nature | Archetype match |
|---|---|---|
| <from Phase 2> | | |

**Parameter table (frozen, use these symbols and units EXACTLY):**

<paste the full Phase 3 table>

**Assumptions (frozen, you may neither add nor remove any; flag violations instead):**

<paste the full Phase 4 table>

**Your task:**

1. Build YOUR lens's model for this system, formally (LaTeX or precise pseudocode). Start from the archetype match if declared above; state what you keep/relax.
2. Follow your perspective file's "Standard Analysis Output" checklist completely.
3. Score YOUR lens only, 1-5, on: fidelity, data needs, compute cost, tractability, answerability of the goal question.
4. List 1-3 falsification candidates: observations that would kill YOUR model specifically.
5. If a frozen assumption blocks your lens, do NOT change it, output `ASSUMPTION CONFLICT: <which>` and model the best case consistent with the freeze.

**Output contract (exact structure):**

```
### Perspective: <name>
Archetype used: <canonical model or "novel territory">
Model: <formal equations, every symbol defined, units attached>
Fits because: <one sentence>
Unique insight: <what ONLY this view reveals>
Blind spot: <what this view cannot see>
Scores: fidelity _/5, data _/5, cost _/5, tractability _/5, answerability _/5
Falsifiers: <1-3 items>
ASSUMPTION CONFLICT: <or "none">
```

**Hard rules:** every symbol defined · units mandatory · no references to other lenses · no scope creep into their questions · established vs assumed vs speculative must be distinguishable.

## END BRIEF

---

Notes for the orchestrator (not part of the brief):

- Dispatch ALL lens briefs in a single message so they run concurrently.
- Sub-problems marked *coupled* in Phase 2 belong to the SAME brief; never split coupled dynamics across agents.
- On merge: collect output blocks verbatim → list every non-"none" ASSUMPTION CONFLICT → resolve conflicts yourself before Phase 6 (document resolutions in the report) → deduplicate overlapping insights, crediting the lens that found them first.
