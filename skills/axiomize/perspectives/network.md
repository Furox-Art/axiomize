# Perspective: Network Science (Structure Changes Everything)

Use when **who-interacts-with-whom** matters as much as how much they interact: epidemics on contact graphs, cascading failures in power grids, information spread on social media, supply networks.

## When Applicable

- Phase 2 found `interaction` structure AND contacts are heterogeneous/clustered (homogeneous mixing assumption fails — see assumptions template)
- Questions like: which node matters most? where does it spread / break? effect of removing targeted nodes/edges?
- Populations too large or structured for ABM, but mixing is clearly non-uniform

## Model Forms

### Statics: graph as object
Represent as `G = (V, E)`; summarize by degree distribution P(k), clustering C, average path length L, community structure.
- Centrality for importance ranking: degree (local influence), betweenness (bottlenecks), eigenvector/PageRank (global influence), k-core (robust cores).
- Percolation: remove nodes/edges at fraction f — find critical f_c where giant component collapses (network resilience).

### Dynamics ON networks
Compartmental processes where transition rates depend on neighbors' states:
- SIS/SIR on networks: effective reproduction number becomes `R_eff = R₀ · ⟨k²⟩/⟨k⟩` — hubs inflate outbreak risk beyond the mean-field prediction.
- Threshold models (adoption): node activates when fraction of active neighbors > θ.
- Cascade/failure propagation: load redistribution after node removal.

Analysis methods ladder (cheap→expensive):
1. Mean-field: replace degrees by ⟨k⟩ (fast, wrong when variance high)
2. Heterogeneous mean-field: average over P(k)
3. Pair approximation / edge-based: tracks correlations
4. Direct simulation on the actual graph (ground truth)

## Standard Analysis Output

1. Structural summary: P(k) shape (heavy-tailed?), clustering, communities
2. Key-node ranking with the centrality matched to the question
3. Modified threshold condition (R_eff with degree heterogeneity correction)
4. Targeted vs random intervention comparison: removing top-1% hubs vs random 1% (usually orders-of-magnitude difference)
5. Resilience curve: largest connected component size vs fraction removed

## Strengths / Blind Spots

- (+) Captures heterogeneity & clustering cheaply; yields actionable targeting (whom to vaccinate/influence/inspect)
- (-) Needs real network data (often unavailable — then state this and fall back to synthetic graphs with stated P(k)); temporal network changes usually ignored; dynamics parameters still come from other lenses

---

**See also:** pairs naturally with [deterministic](deterministic.md) (your R₀ becomes R_eff = R₀·⟨k²⟩/⟨k⟩) and [agent-based](agent-based.md) (ABM on the actual graph). No worked example yet — see [CONTRIBUTING](../../../CONTRIBUTING.md) to add one.
