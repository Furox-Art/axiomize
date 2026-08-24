# Project Management Pack

Curated pointers for project/schedule modeling sessions.

## Archetypes that dominate here
PERT/CPM networks with critical path · Little's Law applied to WIP limits · Erlang-C support teams · renewal-reward for release cycles · EVT for tail-risk schedule slips

## Lens priorities
1. Optimization (scheduling/resources)
2. Network (dependency graph = critical path)
3. Stochastic (estimate uncertainty, Monte Carlo finish dates)
4. Control (burn-down tracking as regulation)

## Examples to imitate
[coffee-shop-staffing](../examples/coffee-shop-staffing.md) (team capacity) · [fleet-maintenance](../examples/fleet-maintenance.md) (incident load)

## Domain gotchas (feed into Phase 4 as candidate assumptions)
- Student syndrome/Parkinson's law invalidate naive task independence
- Estimates are `[S]` speculation until calibrated on team's own history
- Critical path moves when you staff it (reflexivity)
- Multi-tasking multiplies lead times (queueing effect)

## Typical falsifiers
Monte Carlo finish dates repeatedly beaten by reality in same direction; velocity stable while model assumes drift.
