# Example: Batch Reactor Scale-Up Diagnosis

**Idea:** Yield drops 92%→74% on scale-up 1L→100L. Kinetics or mixing?

## Phase 1 — Parse
System: vessel + catalyst + jacket. State: $c_A,c_B,c_C,T$.

## Phase 2 — Decompose
Intrinsic kinetics, equilibrium, diffusion $Da_{II}$, heat balance

## Phase 3 — Parameters
$k_1,k_2, E_a, D_{eff}, k_La, \phi=L\sqrt{k_1/D_{eff}}$

## Phase 4 — Assumptions
Well-mixed bulk, Arrhenius, $\gamma=1$

## Phase 5 — Perspectives
- Deterministic: $dc/dt=\nu·r$, Arrhenius
- Spatial: $ \eta=\tanh\phi/\phi$
- Thermodynamic: $Y_{eq}$
- Causal: DAG for confounders

## Phase 6 — Recommendation
Spatial primary + deterministic null.

## Phase 7 — Implementation
`solve_ivp` ODE + Thiele modulus sweep, stir-speed ladder.

## Phase 8 — Falsifiability
Dies if yield independent of stir speed.

