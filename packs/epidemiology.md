# Epidemiology Pack

Curated pointers for epidemic / public-health modeling sessions.

## Archetypes that dominate here
SIR/SIS/SEIR compartmental · metapopulation patches · percolation (vaccination coverage) · rumor/threshold models for behavior · EVT for outlier outbreak days

## Lens priorities
1. Deterministic (thresholds, R₀, final size)
2. Stochastic (fade-out risk, small-population extinction)
3. Network (super-spreading, ⟨k²⟩/⟨k⟩ correction)
4. Causal inference (intervention effect claims from observational data)

## Examples to imitate
[epidemic SIR](../examples/epidemic-sir.md) · [network rumor](../examples/network-rumor.md), same mathematics, behavioral variant

## Tools pattern
`validate.py --model gillespie` for fade-out checks · `fit.py --model sir` on case series (mind reporting delays)

## Domain gotchas
- Reporting delays and case ascertainment corrupt time series before any model sees them
- Behavior changes are endogenous to awareness, β is rarely constant
- R₀ is regime- and population-dependent; quoting it without context is meaningless
- Homogeneous-mixing conclusions overestimate reach in clustered contact networks

## Typical falsifiers
Reach or growth rates far from model prediction at matched parameters; multiple waves without behavior/immunity change.
