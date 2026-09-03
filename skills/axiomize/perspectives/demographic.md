# Perspective: Demographic & Actuarial Modeling (Populations That Age)

Use when the question lives over **age structure**: pension and insurance liabilities, workforce planning, customer-base aging, subscription cohorts growing old together.

## When Applicable

- Phase 2 signature: `uncertainty` over time-to-event quantities **aggregated across an age-structured population**, the population itself has state (age mix), not just individuals
- Questions like: what reserve covers pensions 30 years out? which subscription cohorts will still be paying in 2035? how does the workforce age pyramid shift hiring needs?
- Distinct from [reliability](reliability.md): there each unit fails independently against one lifetime distribution; here the *composition* of the population by age drives future cash flows and needs, and exits compete (death, retirement, churn, migration)
- What this lens answers that others cannot: timing and amount of future obligations as a function of who is currently how old

## Model Forms

1. **Life table** (the atom). Columns indexed by age x (in years):
   - `l_x` = number alive at exact age x out of the radix `l_0` (conventionally 100,000 lives, dimensionless)
   - `q_x` = probability of dying within the next year, dimensionless; `p_x = 1 − q_x`
   - `d_x = l_x − l_{x+1}` = deaths between ages x and x+1 (lives)
   - `e_x = Σ_{k≥0} l_{x+k} / l_x` = complete life expectancy at age x (years)
   - Multi-year survival: `_k p_x = l_{x+k} / l_x` = probability someone aged x is alive after k years (k in years)
   - Checklist: fix the radix, state the table's source year and population, decide closed (ages capped) vs open intervals.
2. **Cohort vs period, never conflate.**
   - Period table: all ages observed in one calendar year; fast but mixes generations.
   - Cohort table: follows one birth/exposure group through time; honest about trend but needs long data.
   - Mortality improvement means period tables understate cohort survival, apply improvement factors `q_{x,t+s} ≈ q_{x,t}·(1−r_x)^s`, with r_x the annual relative improvement rate at age x (dimensionless per year).
3. **Leslie matrix projection** (age-structured dynamics). With age-class vector n_t (counts of lives per class, width w years):
   - `n_{t+1} = L·n_t`; first row holds fecundities F_i (offspring per individual of class i per step), subdiagonal holds interval survival probabilities `_w p_iw` = l_{x+w}/l_x (probability of surviving from class i into i+1, dimensionless per step)
   - Dominant eigenvalue λ₁ = asymptotic growth rate per step (per year if steps are years); λ₁ > 1 growing, < 1 shrinking
   - Right eigenvector of λ₁ = stable age distribution; convergence time set by |λ₂/λ₁| (steps)
   - Migration enters as an additive vector m_t (lives per step) or extra survival terms, state which.
4. **Actuarial present value** (cash flows weighted by survival). Discount factor `v = 1/(1+i)` per year, i the annual discount rate (fraction per year):
   - Life annuity-due: `ä_x = Σ_{k≥0} v^k · _k p_x` = present value of 1 unit of currency paid at the start of each surviving year; multiply by annual payment to get a liability in currency
   - Term variant caps the sum at k < n years; deferred annuities start the sum at k = m
5. **Multiple-decrement model** (competing exits). Each cause j has force μ_j(x) (probability per year); total hazard μ(x) = Σ_j μ_j(x); cause-specific exit probabilities `q_x^{(j)} = ∫₀¹ p·μ_j(x+t)dt`. Deaths, retirements, lapses, disability all live here, removing one cause changes every other column (competing risks are not independent rates).

Analysis ladder: (a) headcount × life expectancy, minutes; (b) life-table roll-forward of cohorts with fixed rates, hours; (c) full Leslie/Lee, Carter-style projection with multiple-decrement exits and discounted liability under scenario sets, days.

## Standard Analysis Output

1. Life-table extract actually used: source, radix, year, improvement assumption applied
2. Projection of the age structure under base, migration, and named scenario variants (e.g., mortality improving 1%/yr vs flat), with population counts (lives) and dependency ratios (dimensionless) by year
3. Present-value liability in currency with a **discount-rate sensitivity table**, report PV at ±100, ±200 basis points of i; state explicitly whether rate or mortality assumptions moved the answer more (usually rate)
4. Cohort heat-map description: calendar year on one axis, age/birth-cohort band on the other, color = size or cost; diagonal bands reveal cohort waves that single-year snapshots hide

## Strengths / Blind Spots

- (+) Converts aging into explicit cash-flow timing, obligations become dated amounts, not vague "future costs"; the discount-rate sensitivity exposes which assumption actually drives the liability
- (-) Assumes fitted mortality/migration persist for decades while regimes change (medical breakthroughs, wars, product pivots) (`[S]`); small cohorts make granular projections noisy, smooth or aggregate before trusting cell-level numbers

---

**See also:** [reliability](reliability.md) (same survival mathematics, human vocabulary) · [stochastic](stochastic.md)
