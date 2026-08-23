# Archetype Library: Idea Patterns → Canonical Models

Before inventing a new model (Phase 5), check whether the idea matches a known archetype. Recognizing an archetype gives you 80 years of accumulated theory for free: known thresholds, closed forms, failure modes, and validation targets.

Rule: if two or more core features match an archetype below, START from its canonical form, then adapt. Always state which archetype you used and what you changed.

## The catalog

| Idea smells like... | Core signature | Canonical model | Known results you inherit |
|---|---|---|---|
| Spread of disease / behavior / rumor | infection by contact + recovery/forgetting | SIR / SIS / SEIR compartmental | R₀ threshold, final-size equation, herd immunity |
| New product / technology adoption | innovators + imitation via word-of-mouth | Bass diffusion | adoption curve shape, peak timing formula |
| Population or market growth with limits | growth slows as it approaches capacity | Logistic growth | carrying capacity K, saturation time |
| Predator-prey / competing actors | two populations coupling each other's rates | Lotka–Volterra | cycles, coexistence equilibria |
| Stocking something with random demand | holding cost vs stockout cost | Newsvendor / (s,Q) policy | critical ratio, safety stock formulas |
| Customers arriving for service | random arrivals, limited servers | M/M/c queueing (Erlang A/B/C) | utilization cliff, Erlang-C wait formula |
| Something wearing out | survival probability decaying with age/stress | Weibull / exponential reliability | hazard rate, MTBF |
| Accumulating with interest / compound effects | rate proportional to current amount | Exponential growth/decay | doubling time ln2/r |
| Choosing under scarcity | maximize/minimize subject to constraints | LP / ILP / NLP | shadow prices, duality |
| Many self-interested actors | my payoff depends on your choice | Game theory (Nash equilibrium) | best-response analysis, price of anarchy |
| Keeping a value near target despite noise | sensor + actuator + setpoint | Feedback control (PID/LQR) | stability margins, settling time |
| Influence depends on who knows whom | heterogeneous contact structure | Network dynamics on graphs | R_eff = R₀·⟨k²⟩/⟨k⟩, super-spreaders |
| Rare events dominating risk | heavy tails, low probability high impact | Extreme value theory / Poisson processes | tail exponents, return periods |
| Learning from data to predict | function fitting with uncertainty | Regression / Bayesian inference | posterior intervals, bias-variance |
| Particles/agents moving under simple rules | local rules, emergent global pattern | Agent-based model / cellular automata | phase transitions, emergence criteria |
| Quantity conserved across transformations | inflow = outflow + accumulation | Compartmental flow / Kirchhoff-style balance | conservation constraints |

## How to use it in a session

1. After Phase 2 decomposition, scan the table against each sub-problem (not just the whole idea).
2. Declare matches explicitly: *"Sub-problem 'demand randomness' matches the Newsvendor archetype — starting from critical-ratio logic."*
3. Adapt, don't adopt blindly: list which canonical assumptions you keep, relax, or replace (feeds back into Phase 4 assumption table).
4. Inherit the validation target: canonical models come with closed-form checks (final size, Erlang-C, EOQ) — use them in Phase 7 sanity checks via `tools/validate.py` patterns.
5. If NOTHING matches: say so explicitly and build from first principles — flagging "this is novel territory" raises the burden of validation, it doesn't lower it.

## Anti-patterns

- Don't force-fit an archetype because it's famous (not everything is a network problem).
- Don't stack three archetypes when one covers the goal question — parsimony wins at recommendation time.
- Don't cite inherited results (R₀ thresholds etc.) without checking the archetype's assumptions still hold after your adaptation.
