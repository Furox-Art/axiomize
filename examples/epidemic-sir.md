# Example: Idea → Mathematical Model (Epidemic Spread)

Demonstration of the full workflow on a concrete idea.

## Phase 1 — Parse

**Idea (user)**: "A new contagious disease appears in a city of 1M people. What happens?"

- **System**: human population of the city, compartmentalized by disease status
- **State**: counts of Susceptible / Infectious / Recovered individuals over time
- **Inputs**: initial infections, contact patterns
- **Goal**: prediction — peak size and timing, total infected, does it die out?
- **Horizon**: months, daily resolution

## Phase 2 — Decompose

| Sub-problem | Nature |
|---|---|
| Transmission on contact | interaction → but mass-action aggregation valid for large city ⇒ treat as flow |
| Recovery process | flow |
| Population turnover (births/deaths) | flow (negligible on months horizon) |

Coupling: transmission consumes susceptibles, feeds infectious; recovery drains infectious.

## Phase 3 — Parameters

| Symbol | Name | Unit | Exo/Endo | Range | Source | Sensitivity |
|--------|------|------|----------|-------|--------|-------------|
| β | transmission rate | 1/day | exo | 0.2–0.5 | lit. | high |
| γ | recovery rate | 1/day | exo | 0.05–0.2 | lit. | high |
| I(0) | initial infected | persons | exo | 1–50 | est. | medium |
| S(t), I(t), R(t) | compartment counts | persons | endo | ≥0 | derived | — |

Excluded: seasonal forcing (horizon << 1 yr), spatial structure (first pass), demographics (months horizon). Derived quantity: **R₀ = β/γ** — threshold at R₀ = 1.

## Phase 4 — Assumptions

| # | Assumption | Type | Violation consequence |
|---|-----------|------|----------------------|
| 1 | Homogeneous mixing `[R]` | Structural | Overestimates early growth if network is clustered |
| 2 | Constant β, γ in time `[S]` | Parametric | Wrong peak timing if behavior/seasonality shifts rates |
| 3 | No imports/exports `[R]` | Boundary | Misses re-seeding waves |
| 4 | Permanent immunity after recovery `[S]` | Structural | Multi-wave dynamics lost if immunity wanes |

Assumptions 2 and 4 are `[S]` → included in sensitivity sweep.

## Phase 5 — Perspectives

### Deterministic (primary)
$$\frac{dS}{dt} = -\beta \frac{S I}{N}, \quad \frac{dI}{dt} = \beta \frac{S I}{N} - \gamma I, \quad \frac{dR}{dt} = \gamma I$$
Insight: sharp threshold — epidemic iff R₀ > 1; final size equation predicts total attack rate independent of details. Blind spot: no chance of early stochastic fade-out.

### Stochastic (validation)
Continuous-time Markov chain with same rates, Gillespie simulation. Insight: with a single index case I(0)=1, extinction before major outbreak has probability ≈ 1/R₀ even when R₀ > 1 (for larger seeds it falls roughly as (1/R₀)^I(0)) — invisible to ODEs. Blind spot: expensive, gives distributions not clean thresholds.

### Optimization (secondary)
Policy question layered on top: choose closure level c ∈ [0,1] reducing β → β(1−c), minimize economic cost k·c² + medical cost m·I_peak. Insight: reveals acceptable intervention intensity trade-off. Blind spot: assumes cost curves are known.

### Agent-based (rejected)
Rejected: heterogeneity and network structure deliberately excluded in first pass; ABM adds cost without answering THIS question better. Would become relevant if assumption 1 fails validation against data.

## Phase 6 — Comparison & Recommendation

| Criterion | Det | Stoch | Opt | ABM |
|-----------|-----|-------|-----|-----|
| Fidelity (this question) | 4 | 4 | 3 | 4 |
| Data needs | low | low | med | high |
| Compute cost | tiny | low | tiny | high |
| Answers goal question | ✓ peak/timing | ✓ fade-out prob | policy layer | ✗ overkill |

**Recommendation**: deterministic SIR primary + stochastic CTMC validation. Code below implements both.

## Phase 7 — Implementation

See `skills/axiomize/tools/validate.py` usage:

```python
python skills/axiomize/tools/validate.py --model sir --beta 0.3 --gamma 0.1 --I0 10 --N 1000000
```

Outputs: peak height/timing, final size vs theoretical prediction (consistency check), R₀, sensitivity sweep over β ∈ [0.2, 0.5].

## Phase 8 — Falsifiability

Model dies if observed data show: (a) multiple waves without behavior change (assumption 4 broken), (b) early exponential growth far from βSI/N prediction (mixing assumption broken), (c) sustained endemic plateau (waning immunity).

## Confidence Ledger

| Claim | Type | Basis |
|-------|------|-------|
| R₀ > 1 ⟹ epidemic; final-size equation | established | standard SIR theory |
| Stochastic fade-out ≈ 1/R₀ for single index case | established | branching-process result |
| β, γ ranges and constant rates | assumption | lit. ranges; `[S]` on constancy |
| Permanent immunity | assumption | `[S]`, sweep-covered |
| Announcement coverage p achievable | speculation | unvalidated policy claim |
