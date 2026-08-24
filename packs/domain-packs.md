# Domain Packs

Curated bundles: which archetypes, lenses, and examples matter most in a given domain. Load the relevant pack's pointers into context instead of the whole catalog.

## Epidemiology & public health (`packs/epidemiology.md`)

- **Archetypes**: SIR/SIS/SEIR · metapopulation · percolation (vaccination coverage) · EVT (outlier outbreak days)
- **Lenses**: deterministic (thresholds) + stochastic (fade-out) + network (super-spreading)
- **Examples**: [epidemic-sir](../examples/epidemic-sir.md), [network-rumor](../examples/network-rumor.md) — same mathematics, rumor variant
- **Tools pattern**: `validate.py --model gillespie` for fade-out; `fit.py --model sir` on case series
- **Domain gotchas**: reporting delays corrupt time series; behavior changes endogenous to awareness; R₀ is regime-dependent

## Operations & logistics (`packs/operations.md`)

- **Archetypes**: newsvendor/(s,Q) · M/M/c + Little's Law · LP/ILP scheduling · renewal–reward maintenance
- **Lenses**: optimization (decisions) + stochastic (demand/wait risk) + control (reorder feedback)
- **Examples**: [supply-chain-inventory](../examples/supply-chain-inventory.md), [coffee-shop-staffing](../examples/coffee-shop-staffing.md)
- **Tools pattern**: Erlang-C staffing cliffs; Monte Carlo service levels; fit demand distributions first
- **Domain gotchas**: utilization near 1 breaks all averages; lead-time variance hurts more than lead-time mean; cost curves are guessed `[S]` assumptions — sweep them

Usage rule for agents: when an idea clearly belongs to a domain above, read that pack FIRST and adopt its gotchas as candidate Phase 4 assumptions.
