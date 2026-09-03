# Template: Assumptions Checklist

Copy this table into every modeling session. Every assumption MUST have a violation consequence. An assumption you can't state a consequence for is probably load-bearing but unexamined.

| # | Assumption | Type | Violation consequence |
|---|------------|------|----------------------|
| 1 | *(e.g., Population mixes homogeneously)* | Structural | *Model overestimates spread if contact network is clustered* |
| 2 | | | |
| 3 | | | |

## Assumption types

- **Structural**, about system architecture (who interacts with whom, what flows exist)
- **Parametric**, about parameter values/constancy (rates constant in time)
- **Boundary**, about what's excluded from the system (imports ignored)
- **Regime**, about operating range (linear response, no capacity limits hit)

## Quality bar

Each assumption should be classified:

- `[E]` Established, supported by evidence/literature
- `[R]` Reasonable, defensible simplification, standard in the field
- `[S]` Speculative, convenient fiction; flag for sensitivity testing

Rule: every `[S]` assumption must appear in the Phase 7 sensitivity sweep.

## Litmus tests

1. Would a domain expert object to this assumption? If yes → it needs `[E]` or explicit defense.
2. Does the conclusion depend on it? Flip it mentally; if conclusions flip, it's load-bearing → test it.
3. Is it stated because of data availability or because it's true? Be honest about which.
