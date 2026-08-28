# Example: Drone Hover in Wind

**Idea:** Drone hovers unstably — what control stabilizes it?

## Phase 1 — Parse
System: quadrotor + IMU + wind. State $z,v,T$, setpoint $z_{set}$.

## Phase 2 — Decompose
Open-loop double integrator, wind OU, PID/LQR, reliability

## Phase 3 — Parameters
$m=1.5$kg, $\tau_m=0.08$s, $K_p,K_i,K_d$, $\sigma_w=2$N

## Phase 4 — Assumptions
Linearized about hover, OU wind, no saturation

## Phase 5 — Perspectives
- Control: $\dot x=Ax+Bu+Ew$, PID/LQR, PM≥45°
- Stochastic: OU Monte Carlo $\Pr(|\tilde z|>\epsilon)$
- Optimization: $\min J=\int(x^TQx+u^TRu)$
- SPC: EWMA on residuals

## Phase 6 — Recommendation
PID/LQR primary + stochastic validation.

## Phase 7 — Implementation
`solve_ivp` closed-loop + wind OU, step response metrics.

## Phase 8 — Falsifiability
Dies if 30% overshoot despite PM≥45° (delay/saturation).

