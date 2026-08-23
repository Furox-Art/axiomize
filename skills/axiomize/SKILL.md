---
name: axiomize
description: Transforms any idea, problem, or real-world phenomenon into a rigorous mathematical model. Decomposes the idea into sub-problems, extracts active parameters into structured tables, models the system from multiple mathematical perspectives (deterministic, stochastic, optimization, agent-based), compares the resulting models, and recommends the best one with runnable Python code. Use when the user wants to formalize, model, simulate, or mathematically analyze a concept, process, system, or hypothesis.
---

# Axiomize: Idea → Rigorous Mathematical Model

Turn vague ideas into formal mathematical models through disciplined decomposition and multi-perspective analysis.

## Core Workflow

Follow ALL phases in order. Never skip a phase. Show intermediate outputs to the user.

### Phase 1 — Parse the Idea

Restate the idea in one sentence. Then extract:

- **System**: What is the thing being modeled? What are its boundaries?
- **State**: What quantities change over time / space / across entities?
- **Inputs**: What drives or perturbs the system?
- **Goal**: What question must the model answer? (prediction? explanation? optimization? control?)
- **Horizon**: Time scale and spatial scale that matter.

If any of these is unclear, ask the user BEFORE proceeding.

### Phase 2 — Decompose

Break the idea into independent sub-problems:

1. List 3–7 sub-problems (e.g., "spread of influence" → population dynamics + interaction rules + external shocks).
2. For each sub-problem classify its nature:
   - `flow` — quantity accumulating over time (→ differential/difference equations)
   - `interaction` — entities affecting each other (→ networks / agent-based)
   - `decision` — choices under constraints (→ optimization / game theory)
   - `uncertainty` — randomness dominates (→ probability / stochastic processes)
3. State which sub-problems couple to which.

### Phase 3 — Parameter Table

Extract every active parameter using the template in [templates/parameters.md](templates/parameters.md):

| Symbol | Name | Unit | Type | Range | Source | Sensitivity |
|--------|------|------|------|-------|--------|-------------|

Rules:

- Mark each parameter as **exogenous** (given) or **endogenous** (model output).
- Estimate sensitivity qualitatively (low/med/high): "if this doubles, does the answer change wildly?"
- Explicitly list parameters you deliberately EXCLUDE and why (dimension reduction).

### Phase 4 — Assumptions

Write assumptions using [templates/assumptions.md](templates/assumptions.md). Every assumption must have a **violation consequence** — what breaks in the model if reality violates it.

### Phase 5 — Multi-Perspective Modeling

Read EVERY perspective file in `perspectives/`. For each applicable perspective, build an actual model — not just "this could apply":

1. [perspectives/deterministic.md](perspectives/deterministic.md) — ODEs, difference equations, compartmental models
2. [perspectives/stochastic.md](perspectives/stochastic.md) — random variables, Markov chains, Monte Carlo
3. [perspectives/optimization.md](perspectives/optimization.md) — objective functions, constraints, equilibria
4. [perspectives/agent-based.md](perspectives/agent-based.md) — local rules → global behavior

Applicability rule: model from at least **two** perspectives whenever possible. A single-perspective analysis is acceptable only if the user explicitly asks for speed.

For each perspective output:

```
### Perspective: <name>
Model: <equations / rules, written formally in LaTeX>
Why it fits: <one sentence tied to Phase 2 classification>
Key insight this lens reveals: <what ONLY this view shows>
Blind spots: <what this view cannot see>
```

### Phase 6 — Compare & Recommend

Build a comparison table:

| Criterion | Deterministic | Stochastic | Optimization | Agent-Based |
|-----------|---------------|------------|--------------|-------------|

Criteria (score 1–5): fidelity to reality, data requirements, computational cost, analytical tractability, answerability of the user's goal question.

Recommend ONE primary model (+ optionally one secondary for validation). Justify with the table, not vibes.

### Phase 7 — Implement & Validate

Generate runnable Python for the recommended model:

- Use `numpy`/`scipy.integrate.solve_ivp` for ODEs, `numpy` RNG for stochastic, `scipy.optimize` for optimization, plain loops/dataclasses for agent-based.
- Parameter values: use literature-typical defaults, clearly marked as placeholders.
- Then validate with `tools/validate.py` (dimensional checks, sanity bounds, conservation laws).
- Run a sensitivity sweep on the 2 highest-sensitivity parameters from Phase 3.
- Present results as: predicted behavior summary + plot description + limitations.

### Phase 8 — Deliverable Format

Final answer structure:

1. **One-line model statement** ("The idea reduces to a SIR-type system with reinfection")
2. Assumptions & parameter tables
3. All perspective models (formal notation)
4. Comparison table + recommendation
5. Code + validation results
6. **What would falsify this model** — observable predictions that, if wrong, kill the model

## Hard Rules

- NEVER present an equation without defining every symbol.
- NEVER skip Phase 5 multi-perspective analysis silently — if reducing scope, say so explicitly.
- ALWAYS state units for parameters.
- If the idea is purely qualitative (no measurable quantity exists), say so and propose the closest measurable proxy instead of inventing fake precision.
- Distinguish clearly between: established science, reasonable assumption, pure speculation.
