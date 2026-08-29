# Example: Climate-Energy -- Decarbonization Mix (Stub)
## Phase 1 -- Parse
Idea: "City plans 100% clean electricity by 2035." System: grid; State: mix GW; Goal: cost-optimal warming limit.
## Phase 2 -- Decompose
Variability (stochastic) -> capacity choice (optimization) -> warming (deterministic) -> budget (control).
## Phase 3 -- Parameters
| Symbol | Name | Unit | Notes |
| E | emissions | GtCO2/yr | exo |
## Phase 4 -- Assumptions
Constant demand growth; Wright law holds; no grid constraints [S]; TCRE linear.
## Phase 5 -- Perspectives
Deterministic EBM A1; Optimization capacity A2; Stochastic wind MC validation.
## Phase 6 -- Comparison & Recommendation
Recommend A2 optimization primary + A1 deterministic check; stochastic validates reliability.
## Phase 7 -- Implementation
```bash
python skills/axiomize/tools/validate.py --model ebm --ecs 3.0
```
## Phase 8 -- Falsifiability
GMST outside EBM envelope; AF outside 0.3-0.7; LCOE breaks Wright law.
