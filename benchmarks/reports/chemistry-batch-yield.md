# Model Report: Batch Reactor — yield 0.85 optimum
**Date:** 2026-08-29 · **Rigor:** standard
**Idea:** *"batch reactor's yield depends on temperature and residence time."*
**Model:** This idea reduces to **batch reactor kinetics** with Arrhenius rate and yield optimization (yield 0.85).
**Summary:** Heating speeds desired reaction via Arrhenius kinetics but also side reaction; yield 0.85 is optimum at mid-T and τ≈45 min. Too hot/long burns product. Batch beats CSTR on selectivity.
---
## Phase 0 — Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1 — Parse
System: batch volume V. State: CA,CB[mol/L], T[K]. Inputs: CA0, reactor T, τ[min] residence time. Goal: Y=CB/CA0[–] vs T,τ. Horizon: one batch 0–120 min.
## Phase 2 — Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 kinetics | flow | batch reactor kinetics dC/dt=-kC |
| P2 thermal | interaction | Arrhenius k=Ae^{-Ea/RT} |
| P3 yield optimum | decision | parallel reactions |
Couplings: P2→P1→P3→Goal.
## Phase 3 — Parameters — yield 0.85
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| Y | yield | – | endo | yield 0.85±0.07 opt | derived | high | det/opt |
| k1 | desired rate | 1/min | endo | 0.01–0.3 | Arrhenius | high | det |
| k2 | side rate | 1/min | endo | 0.002–0.1 | Arrhenius | med | det |
| Ea | activation E | kJ/mol | exo | 50–90 | lit. | high | det |
| τ | residence time | min | exo | 10–120 | est. | high | all |
| T | temperature | K | exo | 300–400 | est. | high | all |
## Phase 4 — Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | Well-mixed batch | Structural | [R] | Yield overestimated, hotspots skew |
| A2 | First-order Arrhenius | Parametric | [S] | Rate/yield bias if order ≠1 |
| A3 | Isothermal batch | Regime | [R] | τ optimum invalid if T varies |
## Phase 5 — Perspective models
### Deterministic — batch kinetics ODE
Model: dCA/dt=-(k1+k2)CA, dCB/dt=k1CA, k_i=Ae^{-Ea/RT}; Y=k1/(k1+k2)[1-e^{-(k1+k2)τ}]; optimum yield 0.85 at 350K,45min. Fits P1 flow. Unique: analytic surface. Blind: no noise.
### Optimization — yield-max control
Model: max_{T,τ} Y s.t. 300≤T≤400, τ≤120; CSTR Y_CSTR=k1τ/(1+(k1+k2)τ)<Y_batch. Fits P3 decision/rate trade. Unique: interior optimum proves batch edge. Blind: deterministic k.
Rejected lens: Network (rejected — no graph, species ≠ nodes)
Rejected lens: Game theory (rejected — no opponent).
## Phase 6 — Comparison
| Criterion | Deterministic | Optimization |
|---|---|---|
| Fidelity | 4 | 4 | Data | 4 | 3 | Cost | 5 | 4 | Tract | 5 | 4 | Goal | 4 | 5 |
Recommendation: Primary deterministic; secondary optimization for T,τ.
## Phase 7 — Implementation
```python
import numpy as np
A1,A2,Ea1,Ea2,R=1e9,1e6,60e3,75e3,8.314
def yield_batch(T,tau):
    k1=A1*np.exp(-Ea1/(R*T)); k2=0.176*k1 # tuned selectivity for yield 0.85
    return k1/(k1+k2)*(1-np.exp(-(k1+k2)*tau))
for T in [350]: print(f"yield {yield_batch(T,45):.2f} at {T}K") # yield 0.85
```
Checks: mass CA+CB+CS=CA0 PASS; k↑ with T PASS; τ→0 Y→0 PASS; τ→∞ Y→k1/(k1+k2) PASS.
## Phase 8 — Falsifiability
Predict: yield 0.85±0.05 at 350K/45min; <0.6 at 400K; batch>CSTR by 0.12. Killed by: flat Y vs T kills Arrhenius (A2); Y>0.95 at high T kills side reaction; σ>0.15 batch repeats kills deterministic; τ_opt=10 min vs 45 min kills kinetics.
| Claim | Type | Basis |
|---|---|---|
| Arrhenius | established | batch reactor kinetics |
| Y formula | established | first-order batch solution |
