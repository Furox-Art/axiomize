# Ecology Pack

Curated pointers for ecology / environment / resources modeling sessions.

## Archetypes that dominate here
Lotka, Volterra and functional-response predation · logistic growth with harvesting · metapopulation patches · compartmental flow (nutrients, water) · percolation (habitat fragmentation)

## Lens priorities
1. Deterministic (population balances, equilibria, thresholds)
2. Stochastic (small populations: demographic noise → extinction risk)
3. Network (patch connectivity, dispersal corridors)
4. Agent-based when individual behavior heterogeneity drives outcomes (foraging)

## Examples to imitate
[epidemic SIR](../examples/epidemic-sir.md) (same mathematics, different vocabulary) · [network rumor](../examples/network-rumor.md) (dispersal on graphs)

## Domain gotchas
- Census data are counts with detection error, observation model needed before fitting
- Carrying capacity K moves with season; static-K conclusions break across years
- Allee effects: below critical density growth turns negative, logistic is wrong near extinction
- Management interventions are causal questions, correlation-based evaluation misleads ([causal-inference](../skills/axiomize/perspectives/causal-inference.md))

## Typical falsifiers
Recovery observed below modeled minimum viable population; harvest levels sustainable in data but predicted collapsing by fit.
