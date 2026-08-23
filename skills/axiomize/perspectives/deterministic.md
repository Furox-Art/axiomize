# Perspective: Deterministic (Continuous / Discrete Dynamics)

Use when the system is dominated by **accumulating flows**: populations, concentrations, capital, temperatures, queues with large counts.

## When Applicable

- Phase 2 classified the core as `flow`
- Individual randomness averages out (large numbers)
- The question is about trends, equilibria, thresholds — not fluctuations

## Model Forms

### Continuous time → Ordinary Differential Equations

State vector `x(t)`, rate law `dx/dt = f(x, p, t)`.

Checklist for building it:
1. Name each state variable and its unit.
2. Write one balance/flow equation per variable: `d(state)/dt = inflow − outflow + production − decay`.
3. Choose functional forms for rates: mass-action (`k·x·y`), linear decay (`−k·x`), saturating (`V·x/(K+x)`), logistic (`r·x(1−x/K)`).
4. Identify fixed points: solve `f(x*) = 0`.
5. Classify stability via Jacobian eigenvalues at fixed points.

### Discrete time → Difference Equations

`x[n+1] = F(x[n])` when events happen in steps (generations, billing cycles, seasons). Watch for: instability from too-large steps, period doubling, chaos when gains are high.

## Standard Analysis Output

1. Fixed points and their stability
2. Threshold conditions (the critical value of a parameter where behavior flips — e.g., R₀ = 1)
3. Long-run behavior (converge? oscillate? diverge?)
4. Phase portrait description if 2D

## Strengths / Blind Spots

- (+) Cheap, interpretable, exact threshold results
- (-) No noise, no individual variation, wrong when populations are small or events are rare

---

**See also:** worked example using this lens as primary — [epidemic SIR](../../../examples/epidemic-sir.md) · templates: [parameter table](../templates/parameters.md), [assumptions](../templates/assumptions.md)
