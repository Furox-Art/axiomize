# Perspective: Agent-Based (Emergence from Local Rules)

Use when **heterogeneous individuals interact** and global patterns emerge that no single agent intends: markets, crowds, epidemics on networks, ecosystems, opinion dynamics.

## When Applicable

- Phase 2 classified the core as `interaction`
- Agents differ from each other (heterogeneity matters)
- Spatial/network structure matters (who meets whom changes everything)
- Emergent phenomena exist that are invisible at the aggregate level (bubbles, stampedes, segregation)

## Model Specification Protocol

An ABM is only rigorous when fully specified:

1. **Agents**: type, count N, internal state variables (with units), heterogeneity (drawn from which distributions?)
2. **Environment**: grid? network (degree distribution)? continuous space?
3. **Local rules**: for each agent, pseudocode of one update step, perception → decision → action. Rules must be implementable, not narrative ("agents act sensibly" is NOT a rule).
4. **Update scheme**: synchronous vs random-asynchronous (results can differ, state your choice).
5. **Time step**: what real-world duration does one tick represent?

## Standard Analysis Output

1. Parameter sweep over the 2-3 most sensitive parameters (Phase 3 table)
2. Emergent macro statistics: time series of aggregate quantities + their distribution across runs
3. Emergence claim: "local rule X produces global pattern Y", verified across ≥30 independent runs
4. Critical slowing down / tipping points near phase transitions, if any
5. Comparison with mean-field (deterministic) prediction: does aggregation hide something?

## Implementation Notes

- Plain Python loops or `mesa` framework; dataclass per agent.
- Seed the RNG; report seeds so runs are reproducible.
- For N large and rules simple → prefer deterministic/stochastic compartment models instead; ABM earns its cost only when heterogeneity/structure genuinely matters.

## Strengths / Blind Spots

- (+) Captures heterogeneity, local interaction, emergence; intuitive to stakeholders
- (-) Many parameters → overfitting risk; slow; results are distributions needing careful statistics, not clean equations

---

**See also:** rejected in all current worked examples with recorded one-line reasons ([epidemic SIR](../../../examples/epidemic-sir.md), [retail inventory](../../../examples/supply-chain-inventory.md), [coffee shop](../../../examples/coffee-shop-staffing.md)), reading those rejections is the fastest way to learn when ABM earns its cost. Pairs with [network](network.md) for structure-aware ABMs.
