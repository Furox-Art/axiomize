# Example: Idea → Mathematical Model (App Adoption Growth)

Demonstrates **archetype-first workflow** (Bass diffusion) and Phase 7 calibration with real data.

## Phase 1: Parse

**Idea**: "We launched an app; signups are growing. How big can this get and when does growth stall?"

- System: adopter population. State: cumulative installs A(t). Goal: prediction, ceiling and inflection timing. Horizon: 12 months, weekly.

## Phase 2: Decompose

| Sub-problem | Nature | Archetype |
|---|---|---|
| Word-of-mouth imitation | interaction (aggregated) | **Bass diffusion** |
| Ads / external discovery | input | innovation coefficient |
| Market saturation ceiling | boundary | carrying capacity K |

Single dominant flow; archetype match declared: Bass.

## Phase 3: Parameters

| Symbol | Name | Unit | Exo/Endo | Range | Source | Sensitivity |
|--------|------|------|----------|-------|--------|-------------|
| p | innovation (ad-driven) coef | 1/wk | exo | 0.005-0.05 | lit. | medium |
| q | imitation coef | 1/wk | exo | 0.2-0.6 | lit. | high |
| M | market ceiling | users | exo | ? | est. | high |
| A(t) | cumulative adoptions | users | endo | ≥0 | derived | , |

Excluded: churn/uninstalls (first-year focus), multi-market spillover.

## Phase 4: Assumptions

| # | Assumption | Type | Violation consequence |
|---|-----------|------|----------------------|
| 1 | Population homogeneous in susceptibility `[R]` | Structural | Two-segment markets show double hump |
| 2 | Imitation rate ∝ current adopters `[E]` | Structural | Core Bass premise; fails if virality saturates |
| 3 | Ceiling M static over horizon `[S]` | Parametric | Competitor entry shrinks M mid-flight |

## Phase 5: Perspectives

### Deterministic via Bass archetype (primary)
dA/dt = (p + q·A/M)(M − A). Closed form available; peak adoption at t* = ln(q/p)/(p+q). Insight: **q vs p ratio classifies the business**, q ≫ p means viral product where delaying launch costs compounding growth; p ≫ q means marketing-driven where spend timing matters more than network effects.

### Stochastic (validation)
Weekly signup counts as Poisson with mean = model increment; check dispersion of residuals, overdispersion flags unmodeled segments. Blind spot: parameter inference only.

### Information theory (secondary)
Model comparison MDL-style: does adding a second segment (5 params) buy enough likelihood to justify description cost? AIC/BIC verdict on segment split. Blind spot: no dynamics insight.

### Agent-based / Network / Control / Game theory / Causal (rejected)
Aggregate count question; no steering problem; no strategic actors; causal claims not requested, correlation-level fit suffices for prediction-only goal.

## Phase 6: Comparison & Recommendation

**Recommendation:** Bass ODE calibrated by `fit.py` (primary) + Poisson residual validation + BIC gate before allowing a second segment. Classic single-archetype session, most ideas need fewer lenses than they think.

## Phase 7: Implementation & Calibration

```bash
python skills/axiomize/tools/fit.py --model logistic --data weekly_signups.csv --plot fit.png
python skills/axiomize/tools/fit.py --model logistic --data weekly_signups.csv --selftest
```

Logistic is Bass's special case (p≈0); fit recovers K=M and an effective local rate r_eff(A) = q + p·M/A (rate rises as A shrinks, the innovation term dominates early). Checks: RMSE < 10% of range; M confidence interval finite; sweep q ∈ [0.2,0.6] → peak-week sensitivity table.

## Phase 8: Falsifiability & Ledger

Dies if: signups re-accelerate after apparent saturation (second segment/ceiling shift), or imitation coefficient collapses in cohorts without referral loop.
Ledger: Bass closed forms = established · M estimate from fit = assumption · "market static 12 months" = speculation.
