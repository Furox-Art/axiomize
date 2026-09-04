---
name: axiomize
description: Transforms vague ideas, real-world problems and scientific hypotheses into rigorous mathematical models. Clarifies missing mechanisms in plain language, recommends weak/medium/strong depth, builds and compares multiple candidate models, fits and validates them with scientific tools, quantifies uncertainty and sensitivity, produces visualizations and testable hypotheses, and records reproducible runs while keeping extra agent/API consumption under explicit user control. Use when the user wants to formalize, model, simulate, fit, validate, compare, or scientifically test an idea, system, process, mechanism, or hypothesis.
---

# Axiomize: Idea → Rigorous Mathematical Model

Turn an idea into multiple testable mathematical models, compare them honestly, validate them with real tools, and state what could make them wrong.

Before starting, read and obey:

- [adaptive-workflow.md](adaptive-workflow.md) — authoritative interaction, honesty, data, hypothesis, visualization, reproducibility and consumption rules.
- [rigor.md](rigor.md) — weak / medium / strong depth ladder.
- [archetypes.md](archetypes.md) — canonical model matches.
- [first-principles.md](first-principles.md) — novel-mechanism path when no archetype fits.

If an older instruction conflicts with `adaptive-workflow.md`, the adaptive workflow wins.

## Phase 0 — Clarify the idea and choose depth

Recommend **weak**, **medium**, or **strong** and give one short reason. The user may override it.

Clarify the idea before model construction. Extract:

- **system boundary** — what is inside/outside the model;
- **state** — what changes over time, space or entities;
- **inputs/drivers** — what perturbs the system;
- **goal** — predict, explain, optimize or control;
- **measurable outcome** — what observation tells us whether the model works;
- **horizon** — relevant time/spatial scale;
- **mechanism** — what is believed to cause the effect.

Ask missing core questions in the style the user prefers: one-by-one or all-at-once. If no preference is known, ask one short question at a time.

If the **mechanism is unclear**, say that explicitly and resolve it before treating one mechanism as fact. Candidate mechanisms may be carried forward separately if the uncertainty itself is scientifically meaningful.

Optional missing information may be estimated when useful, but every estimate must be labeled as an assumption with uncertainty.

## Phase 1 — Decompose and identify data needs

Break the problem into 2-7 coupled sub-problems depending on depth. Classify each as one or more of:

- `flow` — accumulation/dynamics;
- `interaction` — networks/agents/entities affecting each other;
- `decision` — choices under constraints;
- `uncertainty` — stochastic variation dominates;
- `causal` — intervention/cause-effect claim;
- `spatial` — location/geometry matters.

Draw a Mermaid coupling graph when useful.

Before quantitative claims, state:

1. what data are required;
2. which missing data matter most;
3. what can be measured directly vs inferred.

When public data lookup is available and relevant, use it as part of the requested workflow. Check source reliability, reconcile conflicting sources, and flag stale data. Do not repeatedly search without a material reason.

## Phase 2 — Parameters, assumptions and provenance

Build the active parameter table using [templates/parameters.md](templates/parameters.md):

| Symbol | Name | Unit | Type | Range | Source | Sensitivity |
|--------|------|------|------|-------|--------|-------------|

Rules:

- define every symbol and unit;
- distinguish exogenous vs endogenous quantities;
- record measured / fitted / literature / assumed / speculative provenance;
- rank expected sensitivity;
- state which parameters were excluded and why;
- strong mode: identify dimensionless groups and practical identifiability.

Write assumptions using [templates/assumptions.md](templates/assumptions.md). Every assumption must include its **violation consequence**: what fails if reality violates it.

## Phase 3 — Build multiple candidate models

First scan [archetypes.md](archetypes.md). If a canonical model matches at least two core features, adapt it and state exactly what was inherited and changed.

If no archetype fits, use [first-principles.md](first-principles.md): mechanism → conservation/accounting structure → rate laws → dimensions → minimal model → falsifiers → validation.

Read the relevant files in `perspectives/` and build actual candidates, not name-drops. Available lenses include deterministic, stochastic, optimization, agent-based, network, control, game theory, causal inference, information theory, reliability, SPC, thermodynamic analogies, decision theory, demographic/actuarial and spatial statistics.

Default behavior:

- build **multiple defensible candidates** whenever possible;
- weak: usually ≥2 lightweight candidates;
- medium: ≥2 formal candidates;
- strong: ≥3 independent lenses when the problem justifies them.

### Subagent / parallel execution guard

Do **not** automatically spawn subagents merely because the runtime supports them.

Parallel subagents are allowed only when the user explicitly requested/allowed additional agents or subtasks. When allowed, freeze the shared Phase 0-2 context and give each lens an independent brief from [templates/subagent-brief.md](templates/subagent-brief.md).

Without permission, run the candidate analyses through the current agent and local scientific tools. Do not multiply provider/API calls silently.

## Phase 4 — Data quality, fitting and computation

If observed data exist:

1. inspect data quality before fitting;
2. preserve the original data;
3. clean invalid/malformed data only with an audit trail;
4. state every transformation;
5. compare original vs cleaned results when feasible;
6. prominently flag conclusions that materially depend on cleaning.

Fit each plausible candidate rather than fitting only the favorite model. Use appropriate established tools:

- NumPy / SciPy for numerical work;
- statsmodels for statistical models;
- scikit-learn when its model family is appropriate;
- SymPy for symbolic checks;
- cvxpy / CasADi for optimization;
- NetworkX for graph models;
- control for control systems;
- Z3 / Lean for logic or formal claims when applicable;
- PyMC/JAX when strong Bayesian/automatic-differentiation work is justified and available.

Never trust a solver's `success=True` by itself. Check conservation laws, residuals, dimensions, bounds, stability/convergence and domain constraints as applicable.

For statistical candidates, report fit quality and parameter uncertainty. Compare with evidence such as residual diagnostics, AIC/BIC or out-of-sample performance when valid for the candidate class.

## Phase 5 — Compare, rank and reject

Do not force a single universal winner.

Rank the strongest **2-3 candidates** and explain:

- why candidate 1 ranks above candidate 2/3;
- which assumptions drive the ranking;
- under which conditions each candidate becomes the better model;
- what important effect each model captures or misses;
- why rejected candidates were rejected.

Use explicit criteria: fidelity, data requirements, identifiability, computational cost, analytical tractability, validation evidence and ability to answer the user's actual goal.

If tools or models disagree, expose the conflict. Investigate whether the cause is assumptions, data, numerical method, stochasticity, approximation, identifiability or implementation error. Never average conflicts away merely to produce one answer.

## Phase 6 — Error search, uncertainty, sensitivity and falsification

Actively try to break the result before presenting it.

For important conclusions, use an appropriate confidence label:

- **certain**;
- **strong probability**;
- **medium confidence**;
- **low confidence**.

State:

- remaining uncertainties and why they remain;
- the model's validity domain;
- conditions that invalidate it;
- observable falsifiers;
- major risks/failure modes.

Rank the variables that most affect the result. For high-impact variables, show concrete sensitivity scenarios when computable.

Use Matplotlib for standard plots when available. Produce 3D visualizations when they materially improve understanding. Visualize model structure and variable interactions, not only the final number. Use directed dependency/coupling graphs when useful.

## Phase 7 — Hypotheses and empirical test plan

For empirical domains such as engineering, biology, physics and chemistry, translate the selected models into explicit testable hypotheses.

State:

- hypothesis;
- expected observation if it is true;
- observation that would refute it;
- data/measurement required;
- concrete experiment/test design.

If real testing is costly, dangerous or destructive, run simulation/virtual testing first when possible.

If a hypothesis fails, investigate why. Generate and rank the strongest 2-3 alternative hypotheses, state what evidence would distinguish them, and reject weak hypotheses with explicit reasons.

Repeating the **entire** analysis with independent alternative methods is user-controlled: do it only when the user asks or has already granted permission for that extra work.

## Phase 8 — Reproducibility and delivery

Record enough state to reproduce the work:

- problem definition;
- input data references and original/cleaned transformations;
- parameters and provenance;
- assumptions;
- candidate and selected models;
- equations;
- solver settings;
- random seeds;
- tools/library versions;
- validation/conflict results;
- uncertainty and sensitivity results;
- generated artifacts.

Use `RunState` when operating through the Python engine.

Deliver the result in two layers:

1. **plain-language summary** — short and direct;
2. **technical detail** — equations, evidence, validation, uncertainty and reproducibility.

The user controls how much technical detail is shown.

Offer a stronger rerun when more tools/checks would materially improve confidence. Do not end with a generic "now you should do X" that hands workflow management back to the user.

## Consumption and autonomy rules

Axiomize manages the requested analysis, but it is not allowed to silently expand the bill or workload.

Explicit permission is required before:

- spawning new agents/subtasks;
- repeating the whole analysis with alternative methods;
- adding extra paid/provider calls beyond the selected workflow.

Local deterministic computation, validation, plotting and report generation that are already part of the requested analysis may proceed without an extra permission prompt.

## Hard Rules

- NEVER present an equation without defining every symbol.
- ALWAYS state units where units exist.
- NEVER hide mechanism uncertainty.
- NEVER turn an assumption into a fake fact.
- ALWAYS compare multiple plausible models when possible.
- ALWAYS state why a model is preferred or rejected.
- ALWAYS disclose unresolved conflicts and uncertainty.
- ALWAYS state what could falsify or invalidate the model.
- NEVER discard original data during cleaning.
- NEVER silently multiply agent/API/model calls.
- If no measurable quantity exists, say so and propose the closest measurable proxy instead of inventing precision.
