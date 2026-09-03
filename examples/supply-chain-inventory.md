# Example: Idea → Mathematical Model (Retail Inventory Under Uncertain Demand)

Second worked example, demonstrates stochastic + optimization + control lenses on a business problem.

## Phase 1: Parse

**Idea (user)**: "A retailer sells a product with unpredictable weekly demand. How much should they keep in stock and when should they reorder?"

- **System**: single product, single warehouse; inventory level over time
- **State**: on-hand inventory I(t); pipeline order if any
- **Inputs**: customer demand (random), replenishment orders
- **Goal**: decision policy, minimize total cost while keeping stockouts rare
- **Horizon**: months, weekly resolution

## Phase 2: Decompose

| Sub-problem | Nature |
|---|---|
| Demand randomness | uncertainty → stochastic lens |
| Order timing & size | decision → optimization lens |
| Inventory drains as demand arrives, refills on delivery | flow (+ delay) → deterministic baseline / control lens |

Coupling: the ordering decision shapes the flow; demand randomness shapes both.

## Phase 3: Parameters

| Symbol | Name | Unit | Exo/Endo | Range | Source | Sensitivity |
|--------|------|------|----------|-------|--------|-------------|
| μ_D, σ_D | weekly demand mean/std | units/wk | exo | 100 ± 30 | data | high |
| L | replenishment lead time | wk | exo | 1-4 | lit. | medium |
| h | holding cost | $/unit/wk | exo | 0.5-2 | data | medium |
| K | fixed ordering cost | $/order | exo | 20-100 | data | low |
| p | stockout penalty | $/unit | exo | 5-25 | est. | high |
| s, Q | reorder point, order qty | units | endo | ≥0 | derived | , |

Excluded: perishability (shelf-stable product), multiple products competing for space. Derived quantity: **service level** = P(no stockout during lead time).

## Phase 4: Assumptions

| # | Assumption | Type | Violation consequence |
|---|-----------|------|----------------------|
| 1 | Demand i.i.d. Normal per week `[R]` | Parametric | Misses seasonality/promotions; wrong safety stock |
| 2 | Lead time constant `[S]` | Parametric | Stockouts spike when suppliers are late |
| 3 | Unmet demand is lost, not backordered `[S]` | Structural | Wrong penalty accounting if customers wait |
| 4 | Infinite shelf capacity `[R]` | Boundary | Overorders if warehouse fills up |

`[S]` items 2-3 enter the sensitivity sweep.

## Phase 5: Perspectives

### Stochastic (primary)
Demand during lead time ~ Normal(μ_L = L·μ_D, σ_L² = L·σ_D²). Reorder point from service level α:
`s = μ_L + z_α·σ_L`, safety stock `SS = z_α·σ_L`.
Insight: stockout risk is exponential-ish in safety stock, last units of protection are brutally expensive.
Blind spot: doesn't say how MUCH to order.

### Optimization (primary)
Cycle stock from EOQ: `Q = sqrt(2*K*mu_D/h)` (correctly balances ordering vs holding). Safety stock / reorder point via newsvendor critical ratio `CR = p/(p+h)` ⇒ service-level quantile z on lead-time demand: `s = mu_L + z_alpha * sigma_L`. Full policy is the classical (s,Q): order Q whenever position hits s.
Insight: shadow price of the stockout constraint tells exactly what one avoided stockout is worth.
Blind spot: static policy, assumes demand distribution stays put.

### Control (validation)
Reorder rule as feedback controller: error e = s − I(t); order when e > 0. Insight: lead time L acts like dead-time and destabilizes naive proportional reordering (over-order oscillation); dampening via moving-average demand forecast stabilizes it.
Blind spot: tuning needs simulation anyway.

### Deterministic EOQ (baseline sanity check)
`EOQ = √(2Kμ_D/h)` with zero variance, quick lower-bound intuition; underestimates true cost.
Rejected as primary: ignores the very uncertainty that defines the problem.

### Network / Agent-based (rejected)
Single node, no interaction structure, structure adds nothing to THIS question. Relevant if extended to multi-warehouse networks (→ network.md).

## Phase 6: Comparison & Recommendation

| Criterion | Stoch | Opt | Ctrl | Det |
|-----------|-------|-----|------|-----|
| Fidelity | 5 | 4 | 4 | 2 |
| Data needs | med | med | low | low |
| Answers goal question | ✓ risk | ✓ policy | ✓ adaptation | ✗ |
| Compute cost | low | tiny | low | tiny |

**Recommendation**: (s,Q) policy from stochastic safety stock + newsvendor sizing; Monte Carlo simulation validates service level & cost; control view explains why naive rules oscillate.

## Phase 7: Implementation

```bash
python skills/axiomize/tools/validate.py --model gillespie   # stochastic epidemic demo
# inventory Monte Carlo follows the same pattern: sample demands ~ N(μ_D, σ_D),
# apply (s,Q) rule, report fill rate & avg cost across ≥10⁴ runs
```

Validation checks: simulated fill rate ≥ target α; cost curve convex near Q*; sensitivity sweep over L ∈ {1..4} weeks.

## Phase 8: Falsifiability

Model dies if observed data show: (a) demand autocorrelation/seasonality large vs σ_D (assumption 1), (b) supplier lateness correlated with order size (assumption 2), (c) systematic post-stockout demand drop (assumption 3).
