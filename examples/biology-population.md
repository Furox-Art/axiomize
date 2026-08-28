# Example: Lake Algae Bloom Tipping Point

**Idea:** Fertilizer runoff triggers bloom — critical loading?

## Phase 1 — Parse
System: lake epilimnion + P + algae. Goal: $I_{crit}$.

## Phase 2 — Decompose
Logistic $K(P)$ via MM uptake, LV grazing, bistable switch

## Phase 3 — Parameters
$\mu_{max}, K_p, r, I, s, g, h, Z$

## Phase 4 — Assumptions
Well-mixed, QSSA, static K

## Phase 5 — Perspectives
- Deterministic: $dP/dt=I-sP-u\mu(P)A$, $dA/dt=r(P)A(1-A/K(P))-...$
- Stochastic: Gillespie for $P(tip)$
- Spatial: Moran's I, patch model
- Control: $u$ fractional runoff reduction

## Phase 6 — Recommendation
Deterministic primary, stochastic mandatory near threshold.

## Phase 7 — Implementation
`solve_ivp` bifurcation sweep $I\in[1,8]$, Gillespie pulse ensemble.

## Phase 8 — Falsifiability
Dies if bloom clears immediately after small I cut (no hysteresis).

