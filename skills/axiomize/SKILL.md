---
name: axiomize
description: Transforms any idea, problem, or real-world phenomenon into a rigorous mathematical model. Decomposes the idea into sub-problems, matches known modeling archetypes, extracts active parameters into structured tables, models the system from multiple mathematical perspectives (deterministic, stochastic, optimization, agent-based, network, control, game theory, causal inference, information theory, reliability, SPC, thermodynamic analogies), compares the resulting models, and delivers a standardized report with runnable Python code and falsifiability criteria. Use when the user wants to formalize, model, simulate, or mathematically analyze a concept, process, system, or hypothesis.
---

# Axiomize: Idea → Rigorous Mathematical Model

Turn vague ideas into formal mathematical models through disciplined decomposition and multi-perspective analysis.

## Core Workflow

Follow ALL phases in order. Never skip a phase. Show intermediate outputs to the user.

### Phase 0 — Set Rigor Level

Pick **basic**, **standard** (default), or **research** using the signals table in [rigor.md](rigor.md), announce it in your first line, and offer: *"say 'deeper' or 'quicker' anytime."* The ladder defines what each phase requires at each level — basic stays light but honest, research adds model criticism, dimensionless reduction, uncertainty quantification and reproducibility. Whatever the tier, the final answer opens with a plain-language summary (≤ 5 sentences).

### Phase 1 — Parse the Idea

Restate the idea in one sentence. Then extract:

- **System**: What is the thing being modeled? What are its boundaries?
- **State**: What quantities change over time / space / across entities?
- **Inputs**: What drives or perturbs the system?
- **Goal**: What question must the model answer? (prediction? explanation? optimization? control?)
- **Horizon**: Time scale and spatial scale that matter.

If any of these is unclear, ask the user BEFORE proceeding — but ask like a modeler, not generically:

- Vague goal → "Do you want to PREDICT what happens, DECIDE what to do, or CONTROL it to a target?" (this single question routes the whole session)
- No quantities named → "What would you MEASURE to know this is working?"
- No scale given → "Over what time period? At what size?"

Never proceed on an idea where neither system boundary nor goal question can be stated.

### Phase 2 — Decompose

Break the idea into independent sub-problems:

1. List 3–7 sub-problems (e.g., "spread of influence" → population dynamics + interaction rules + external shocks).
2. For each sub-problem classify its nature:
   - `flow` — quantity accumulating over time (→ differential/difference equations)
   - `interaction` — entities affecting each other (→ networks / agent-based)
   - `decision` — choices under constraints (→ optimization / game theory)
   - `uncertainty` — randomness dominates (→ probability / stochastic processes)
3. State which sub-problems couple to which.
4. Draw the coupling map as a Mermaid graph (renders on GitHub):

   ````
   ```mermaid
   graph LR
       Demand[uncertainty] --> Stock[flow]
       Reorder[decision] --> Stock
       Stock --> Answer[goal question]
   ```
   ````

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

**First, check [archetypes.md](archetypes.md):** scan the catalog against each sub-problem from Phase 2. If two or more core features match an archetype (SIR, Bass diffusion, newsvendor, M/M/c, logistic, Lotka–Volterra...), START from that canonical model and adapt — declare the match and what you changed. Inherited closed forms become Phase 7 validation targets. If nothing matches, say "novel territory" explicitly.

Then read EVERY perspective file in `perspectives/`. For each applicable perspective, build an actual model — not just "this could apply":

1. [perspectives/deterministic.md](perspectives/deterministic.md) — ODEs, difference equations, compartmental models
2. [perspectives/stochastic.md](perspectives/stochastic.md) — random variables, Markov chains, Monte Carlo
3. [perspectives/optimization.md](perspectives/optimization.md) — objective functions, constraints, equilibria
4. [perspectives/agent-based.md](perspectives/agent-based.md) — local rules → global behavior
5. [perspectives/network.md](perspectives/network.md) — graph structure, centrality, dynamics on networks
6. [perspectives/control.md](perspectives/control.md) — feedback, regulation, steering to setpoint
7. [perspectives/game-theory.md](perspectives/game-theory.md) — strategic interaction, equilibria, mechanisms
8. [perspectives/causal-inference.md](perspectives/causal-inference.md) — intervention claims from observational data
9. [perspectives/information-theory.md](perspectives/information-theory.md) — what can be known, transmitted, compressed
10. [perspectives/reliability.md](perspectives/reliability.md) — failure times, maintenance economics, availability
11. [perspectives/spc.md](perspectives/spc.md) — detecting process change vs common-cause noise
12. [perspectives/thermodynamic.md](perspectives/thermodynamic.md) — stock-flow analogies with explicit break points

Applicability rule: model from at least **two** perspectives whenever possible. A single-perspective analysis is acceptable only if the user explicitly asks for speed.

### Parallel Dispatch Protocol

If the runtime supports subagents (Claude Code `Task` tool, opencode `task` tool, equivalent), Phase 5 MUST run in parallel:

1. **Freeze first.** Phases 1–4 are completed and FROZEN before any dispatch: idea statement, goal question, decomposition, parameter table, assumptions. Frozen inputs go into every brief verbatim.
2. **Select lenses** (≥ 2 applicable). Sub-problems marked *coupled* in Phase 2 stay inside one brief — never split coupled dynamics across agents.
3. **Dispatch simultaneously**: fill [templates/subagent-brief.md](templates/subagent-brief.md) once per lens and send ALL briefs in a single message so they execute concurrently. Each brief is self-contained; subagents see no other lens's output (independence prevents anchoring bias between lenses).
4. **Merge**: collect blocks verbatim → resolve every `ASSUMPTION CONFLICT` yourself and document resolutions → deduplicate overlapping insights → proceed to Phase 6 with the collected scores.

Fallback (no subagent support): run the same briefs sequentially through your own context, in the order listed above, and note in the report that independence was sequential rather than parallel.

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

| Criterion | Det | Stoch | Opt | ABM | Net | Ctrl |
|-----------|-----|-------|-----|-----|-----|------|

Criteria (score 1–5): fidelity to reality, data requirements, computational cost, analytical tractability, answerability of the user's goal question. Only include columns for perspectives you actually built; mark rejected ones with a one-line rejection reason under the table.

Recommend ONE primary model (+ optionally one secondary for validation). Justify with the table, not vibes.

### Phase 7 — Implement & Validate

Generate runnable Python for the recommended model:

- Use `numpy`/`scipy.integrate.solve_ivp` for ODEs, `numpy` RNG for stochastic, `scipy.optimize` for optimization, plain loops/dataclasses for agent-based.
- Parameter values: use literature-typical defaults, clearly marked as placeholders.
- **If the user has real data** (CSV of observations), calibrate instead of guessing: `tools/fit.py --model <sir|logistic> --data <file>` returns fitted parameters with confidence intervals and derived quantities (R₀, K...). Report both fit quality (RMSE) and parameter uncertainty.
- Then validate with `tools/validate.py` (dimensional checks, sanity bounds, conservation laws).
- Run a sensitivity sweep on the 2 highest-sensitivity parameters from Phase 3.
- When matplotlib is available, produce a plot of the model behavior (`--plot`) and reference it in the report.
- Present results as: predicted behavior summary + plot description + limitations.

### Phase 8 — Deliverable Format

Assemble the final answer using [templates/report.md](templates/report.md). Its non-negotiable elements:

1. **One-line model statement** ("The idea reduces to a SIR-type system with reinfection")
2. Assumptions & parameter tables
3. All perspective models (formal notation)
4. Comparison table + recommendation
5. Code + validation results
6. **What would falsify this model** — observable predictions that, if wrong, kill the model
7. **Confidence ledger** — every major claim tagged as established / assumption / speculation

**Archive rule:** after delivering the report, save it to `reports/YYYY-MM-DD-<short-slug>.md` in the working directory (create the folder if needed) using the template header verbatim (Date / Rigor level / Model in one sentence), then run `tools/index_reports.py` to rebuild `reports/INDEX.md`, and tell the user the path. Reference earlier indexed sessions when relevant ("this extends your 2026-08-24 barista model") — modeling sessions should accumulate into a searchable personal archive, not evaporate into chat scrollback.

## Hard Rules

- NEVER present an equation without defining every symbol.
- NEVER skip Phase 5 multi-perspective analysis silently — if reducing scope, say so explicitly.
- ALWAYS state units for parameters.
- ALWAYS open the final deliverable with a plain-language summary, regardless of tier.
- If the idea is purely qualitative (no measurable quantity exists), say so and propose the closest measurable proxy instead of inventing fake precision.
- Distinguish clearly between: established science, reasonable assumption, pure speculation.
