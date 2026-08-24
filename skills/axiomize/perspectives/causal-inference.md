# Perspective: Causal Inference (Why, Not Just What)

Use when the goal is an **intervention claim** ("X causes Y", "this policy will change that") rather than prediction. Correlations from observational data answer prediction questions only.

## When Applicable

- The user's question is counterfactual: "what happens IF we change X?"
- Data are observational (no experiment) — or experiments are partial/expensive
- Warning sign this lens matters: someone is about to fit a regression and call the coefficient an "effect"

## Model Forms

1. **Causal graph (DAG):** draw variables as nodes, direct causal claims as arrows. Every missing arrow is also a claim.
2. **Identification step:** for effect X→Y, list backdoor paths and which to block; choose adjustment set Z such that P(Y | do(X)) = Σ_Z P(Y|X,Z). Rules of thumb: control common causes, do NOT control mediators or colliders.
3. **Estimator matched to identification:** regression adjustment, matching, difference-in-differences (parallel trends!), instrumental variable (relevance + exclusion), regression discontinuity.
4. **Sensitivity analysis:** how strong must an unmeasured confounder be to erase the effect? (E-value style reporting.)

## Standard Analysis Output

1. The DAG itself — every arrow defended in one sentence
2. Identification statement: estimand → adjustment set → estimator
3. Effect estimate WITH uncertainty interval and unit interpretation ("+12 min sleep per 1h less screen [95% CI 4–20]")
4. Assumption stress test: parallel trends plot / instrument first-stage strength / confounder robustness bound
5. Scope statement: population and regime where the effect transfers

## Strengths / Blind Spots

- (+) Converts "associated" into actionable intervention logic; exposes exactly which assumption carries the causal weight
- (-) Observational identification is fragile — conclusions are only as strong as untestable assumptions; no method rescues a wrong DAG

---

**See also:** guards every other lens — [deterministic](deterministic.md) rate constants fitted on observational data inherit these caveats · pairs with templates [assumptions](../templates/assumptions.md) (causal claims are `[S]` until identified)
