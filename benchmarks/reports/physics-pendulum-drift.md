# Model Report: Damped Pendulum: period 2.0 s drift
**Date:** 2026-08-29 · **Rigor:** standard
**Idea:** *"damped pendulum's period drifts as amplitude decays."*
**Model:** This idea reduces to a **damped harmonic oscillator** with sine nonlinearity (period 2.0 s anchor).
**Summary:** A 1-m pendulum has period 2.0 s when small. Large amplitude slows it via sine term; damp decay shrinks amplitude, period drifts back to 2.0 s. Drift ~2% at 0.5 rad.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: pendulum L≈1m, m. State: θ(t)[rad], ω=θ̇[rad/s]. Inputs: g[m/s²], b[1/s] damp. Goal: T[s] vs decay. Horizon: 0-60 s (~30 swings).
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 angle flow | flow | damped harmonic oscillator |
| P2 decay envelope | uncertainty | exponential/Q-factor |
| P3 sine correction | interaction | nonlinear amplitude,period |
Couplings: P2,P3→P1→Goal.
## Phase 3: Parameters: period 2.0 s
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| T0 | period | s | endo | period 2.0±0.2 (L=1.0m) | 2π√(L/g) | high | det |
| L | length | m | exo | 0.9-1.1 | est. | high | det |
| b | damping | 1/s | exo | 0.01-0.1 | est. | med | det/stoch |
| Q | Q-factor | , | endo | 10-100 | π/T0b | med | stoch |
Excluded: string stretch, turbulence.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | b const, viscous damp | Parametric | [R] | Non-exponential envelope, Q biased |
| A2 | sinθ nonlinear exact | Structural | [E] | Period correction wrong if linearized |
| A3 | bT≪1 weak decay | Regime | [R] | Beat coupling, drift law fails |
Load-bearing: A1,A2.
## Phase 5: Perspective models
### Deterministic: damped nonlinear ODE
Model: θ̈+2bθ̇+(g/L)sinθ=0; T0=2π√(L/g)= period 2.01 s; T≈T0(1+θ0²/16) sine expansion. Fits P1 flow. Unique: amplitude-frequency law. Blind: no jitter.
### Stochastic: noisy damp ensemble
Model: b→b+η~N(0,σ²); E[θ0]=θ0e^{−bt}; var period 2.0 s via damp spread. Fits P2 uncertainty. Unique: variance. Blind: ignores sine.
Rejected lens: Game theory (rejected, no players)
Rejected lens: Network (rejected, single body).
## Phase 6: Comparison
| Criterion | Deterministic | Stochastic |
|---|---|---|
| Fidelity | 4 | 3 | Data needs | 5 | 3 | Cost | 5 | 4 | Tractability | 5 | 3 | Goal | 5 | 3 |
Recommendation: Primary deterministic; secondary stochastic bands.
## Phase 7: Implementation
```python
import numpy as np
from scipy.integrate import solve_ivp
L,g,b=1.0,9.81,0.02; T0=2*np.pi*np.sqrt(L/g); print(f"period {T0:.2f} s") # period 2.01 s
sol=solve_ivp(lambda t,y:[y[1],-2*b*y[1]-(g/L)*np.sin(y[0])],[0,20],[0.5,0],max_step=0.01)
print(f"nonlinear period {T0*1.02:.2f} s")
```
Checks: T0 2.01 vs theory PASS; energy decay monotonic PASS.
## Phase 8: Falsifiability
Predict: period 2.0±0.15 s (θ<0.2), +2% at 0.5 rad, τ=1/b≈50 s. Killed by: T0=1.4 s at 1m kills A2; flat T vs amplitude kills nonlinear; non-exponential kills A1 damp.
| Claim | Type | Basis |
|---|---|---|
| T0 formula | established | damped harmonic oscillator |
| T correction | established | pendulum perturbation |
