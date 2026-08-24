# Perspective: Reliability Engineering (Will It Break, and When)

Use when the question lives over **failure times**: MTBF targets, warranty reserves, maintenance scheduling, spare-parts stocking, system availability guarantees.

## When Applicable

- Phase 2 signature: `uncertainty` over **time-to-event** quantities
- Questions like: how often will it fail? how long until replacement beats repair? what reserve covers breakdowns?
- Distinct from [stochastic](stochastic.md) general machinery by its focus on hazard rates and lifetime distributions

## Model Forms

1. **Exponential baseline** (constant hazard h = λ): time-to-failure ~ Exp(λ); MTBF = 1/λ. Justified only when failures are truly memoryless (electronic components past burn-in).
2. **Weibull lifetime** with shape β and scale η: hazard h(t) = (β/η)(t/η)^(β−1).
   - β < 1 → infant mortality (hazard decreasing)
   - β = 1 → reduces to exponential
   - β > 1 → wear-out (hazard increasing) — preventive maintenance only makes sense here
3. **System reliability from component structure:**
   - Series: R_sys = Π R_i (every part must survive)
   - Parallel/redundant: R_sys = 1 − Π(1 − R_i)
   - k-of-n majority variants for graceful degradation
4. **Renewal–reward long-run cost rate:** replace preventively at age t_p:
   L(t_p) = [c_p + c_f·F(t_p)] / ∫₀^tp S(t)dt — minimize over t_p where c_f ≫ c_p is the corrective cost including downtime.

## Standard Analysis Output

1. Fitted lifetime distribution (β, η with standard errors) + goodness-of-fit note against observed failure ages
2. MTBF with confidence interval
3. System availability A = MTBF / (MTBF + MTTR) per configuration; redundancy effect table
4. Optimal preventive replacement interval t_p* with the cost curve plotted/described around it
5. Spare-parts implication: expected demand rate λ·N_units feeds an inventory model ([optimization](optimization.md) handoff)

## Strengths / Blind Spots

- (+) Quantifies failure risk and maintenance economics; turns "service regularly" into a specific number of days
- (-) Assumes stationarity and independent failures unless explicitly modeled; sparse failure data make tail behavior speculative (`[S]`); censored data (units not yet failed) need survival methods, not naive averages

---

**See also:** shares machinery with [stochastic](stochastic.md) (Poisson processes, Monte Carlo validation) · hands off to [optimization](optimization.md) for cost minimization layers · worked example: [fleet maintenance](../../../examples/fleet-maintenance.md)
