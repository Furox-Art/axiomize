# Perspective: Control Theory (Steering a System)

Use when the question is not just "what will happen?" but **"how do we keep it on target?"**: regulating inventories, cruising speed under disturbances, drug dosing, thermostat-like problems, stabilizing an unstable equilibrium.

## When Applicable

- The system has actuators: inputs you can choose continuously/periodically
- There is a target trajectory or setpoint, plus disturbances pushing away from it
- Phase 2 found `flow` dynamics AND the user's goal contains regulate / maintain / stabilize / track
- Feedback is possible: you can observe (part of) the state and react

## Model Forms

### State-space form
```
x' = f(x, u, w)      state x, control input u, disturbance w
y  = g(x)            measurement y (what you can actually observe)
```

### Analysis & design checklist
1. **Open loop**: with u fixed, where does x drift? (usually: nowhere good)
2. **Equilibrium & linearization**: find (x*, u*) with f(x*, u*) = 0; Jacobians A = ∂f/∂x, B = ∂f/∂u at that point.
3. **Controllability**: rank([B AB A²B …]) = n? If not, some states are unreachable — say which.
4. **Feedback law**:
   - Pole placement / LQR: `u = −K·(x − x_setpoint)`; LQR cost `∫ (xᵀQx + uᵀRu) dt` trades tracking vs effort.
   - PID for SISO industrial practice: `u = Kp·e + Ki·∫e + Kd·ė` — tune until response is fast without oscillation.
5. **Closed-loop properties to report**: stability margin, step-response overshoot/settling time, disturbance rejection (does a shock die out and how fast), control effort saturation (`|u| ≤ u_max` respected?).
6. **Observability** (if partial sensing): can y reveal x? Kalman filter if noise.

## Standard Analysis Output

1. Setpoint + linearized model (A, B with units)
2. Chosen controller structure + gains (or Q/R matrices) with justification
3. Simulated response: target tracking curve + disturbance-kick recovery time
4. Robustness note: how much can parameters drift before instability
5. Actuator limits check: required control effort within physical bounds?

## Strengths / Blind Spots

- (+) Turns "what happens" into "how to act"; quantifies trade-off between error and effort; explicit robustness margins
- (-) Local (linearized) validity only — big excursions leave the regime; assumes sensor+actuator availability; optimal ≠ implementable if gains require unrealistic reaction speeds

---

**See also:** worked example — [retail inventory](../../examples/supply-chain-inventory.md) (reorder rule as feedback controller, lead time as dead-time). Builds directly on [deterministic](deterministic.md) state-space form; extends to [optimization](optimization.md) via LQR cost.
