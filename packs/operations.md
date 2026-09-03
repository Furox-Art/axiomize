# Operations Pack

Curated pointers for operations / logistics / service-operations modeling sessions.

## Archetypes that dominate here
newsvendor/(s,Q) inventory · M/M/c queueing + Little's Law · LP/ILP scheduling · renewal, reward maintenance · Erlang loss

## Lens priorities
1. Optimization (staffing, ordering, routing decisions)
2. Stochastic (demand/wait risk, service levels)
3. Control (reorder triggers, capacity feedback)
4. Reliability (equipment fleets, maintenance windows)

## Examples to imitate
[supply-chain inventory](../examples/supply-chain-inventory.md) · [coffee-shop staffing](../examples/coffee-shop-staffing.md) · [fleet maintenance](../examples/fleet-maintenance.md)

## Tools pattern
Erlang-C staffing cliffs (`validate.py --model queue`) · Monte Carlo service levels · `csv_check.py` then `fit.py --model logistic` on demand series

## Domain gotchas
- Utilization near 1 breaks every average, queues explode nonlinearly
- Lead-time VARIANCE hurts more than lead-time mean
- Cost curves are guessed `[S]` assumptions, sweep them, never trust point estimates
- Integer constraints matter at small scale; LP relaxations lie for 3 servers

## Typical falsifiers
Realized service levels outside Monte Carlo intervals; staffing plans that feel stable but miss SLA exactly at demand peaks.
