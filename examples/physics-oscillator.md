# Example: Damped Pendulum Clock Drift

**Idea:** A damped pendulum clock loses time — how much per day and why?

## Phase 1 — Parse
System: bob + rod + air + escapement. Goal: daily drift s/day.

## Phase 2 — Decompose
- S1 period $T_0=2\pi\sqrt{L/g}$
- S2 damping $Q=\omega_0/(2\gamma)$
- S3 thermal expansion $L(T)=L_0(1+\alpha_L\Delta T)$

## Phase 3 — Parameters
$L_0=1.0$m, $g=9.81$, $\gamma=0.008$/s, $\alpha_L=12e-6$/K, $\theta_0=0.05$ rad

## Phase 4 — Assumptions
Linear damping, small angle, uniform T

## Phase 5 — Perspectives
- Deterministic: $\Delta t=86400(1/(8Q^2)+\theta_0^2/16+0.5\alpha_L\Delta T)$ → 15.8 s/day
- Thermodynamic: energy audit
- Stochastic: jitter ±0.3s
- Control: escapement regulation

## Phase 6 — Comparison
Deterministic primary, others validation.

## Phase 7 — Implementation
`solve_ivp` with $\ddot\theta+2\gamma\dot\theta+\omega_0^2\sin\theta=0$, period via zero-crossings.

## Phase 8 — Falsifiability
Dies if period decreases with amplitude.

