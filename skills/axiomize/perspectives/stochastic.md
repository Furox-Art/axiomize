# Perspective: Stochastic (Randomness Is Structural)

Use when **variability or rare events dominate**: small populations, noisy signals, one-off shocks, arrival processes, gambling/insurance-like risk.

## When Applicable

- Phase 2 classified the core as `uncertainty`
- Counts are small (deterministic averages are meaningless for N ≈ few)
- The question is about risk: "probability of X", "worst case", "how likely is extinction/failure"
- Timing of events is irregular (arrivals, mutations, defaults)

## Model Forms

### Random variables & distributions
1. Identify the random quantity and whether it's a count (→ Binomial/Poisson), waiting time (→ Exponential/Weibull), sum (→ tends Normal via CLT), extreme (→ Gumbel/Pareto).
2. State mean AND variance — models that only track means miss risk entirely.

### Markov chains
- Discrete states, memoryless transitions: define state space S and transition matrix P.
- Analysis: stationary distribution π = πP; absorption probabilities; expected time to absorption.
- Use when system jumps between qualitatively distinct regimes.

### Continuous-time Markov chains / Gillespie
For reaction-style dynamics (infection, adoption, queueing): rates q_i→j, simulate exactly via Gillespie algorithm instead of discretizing time.

### Monte Carlo estimation
When no closed form exists:
1. Sample inputs from their distributions (Phase 3 ranges!)
2. Propagate through ANY model (even an ODE or optimizer)
3. Report output as distribution: median, 5–95% interval, P(catastrophe)
4. N runs: use ≥ 10⁴ unless cost forbids; report standard error ∝ 1/√N

## Standard Analysis Output

1. Distribution choice per random input + justification
2. Probability of the critical event (extinction, ruin, overload)
3. Expected time to the critical event
4. Variance/scale of fluctuations around the deterministic prediction — when does the deterministic lens lie? (usually: near thresholds, small N)
5. Stochastic resonance/noise-induced effects if present

## Strengths / Blind Spots

- (+) Quantifies risk and uncertainty honestly; captures rare-event and threshold phenomena invisible deterministically
- (-) Needs more data to fit distributions; results are intervals not points (some users hate this); computationally heavier

---

**See also:** worked examples — [epidemic SIR](../../../examples/epidemic-sir.md) (fade-out check), [retail inventory](../../../examples/supply-chain-inventory.md) (safety stock), [coffee shop](../../../examples/coffee-shop-staffing.md) (Erlang-C waits) · runnable demo: `tools/validate.py --model gillespie`
