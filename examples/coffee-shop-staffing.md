# Example: Idea → Mathematical Model (Coffee Shop Staffing)

Third worked example — demonstrates queueing + optimization on an operations question, including a rejected-lens rationale.

## Phase 1 — Parse

**Idea (user)**: "A coffee shop wants to decide how many baristas to schedule per hour of the day."

- **System**: service process — customers arrive, wait, get served
- **State**: number in queue / busy baristas per hour h
- **Inputs**: arrival pattern λ(h) (varies by hour), service speed
- **Goal**: decision — staffing level per hour meeting a wait-time promise at minimum wage cost
- **Horizon**: one day, hourly buckets

## Phase 2 — Decompose

| Sub-problem | Nature |
|---|---|
| Random arrivals & service times | uncertainty → stochastic lens (queueing) |
| How many staff per hour | decision → optimization lens |
| Queue builds when arrivals exceed capacity | flow → deterministic fluid baseline |

Coupling: staffing sets capacity; stochastic arrivals determine realized waits.

## Phase 3 — Parameters

| Symbol | Name | Unit | Exo/Endo | Range | Source | Sensitivity |
|--------|------|------|----------|-------|--------|-------------|
| λ(h) | arrival rate by hour | cust/h | exo | 10–90 | data | high |
| μ | service rate per barista | cust/h | exo | 15–25 | data | high |
| c(h) | baristas scheduled | persons | endo | ≥1 | derived | — |
| w* | promised max avg wait | min | exo | 2–5 | policy | high |
| κ | wage cost | $/barista-h | exo | 15–25 | data | medium |

Excluded: no-shows/sick leave (staffing buffer handled as fixed %), customer balking behavior. Derived: utilization `ρ = λ/(c·μ)`.

## Phase 4 — Assumptions

| # | Assumption | Type | Violation consequence |
|---|-----------|------|----------------------|
| 1 | Arrivals ~ Poisson(λ(h)) `[R]` | Parametric | Underestimates waits if arrivals bursty (rush after bus) |
| 2 | Service ~ Exponential(μ) `[S]` | Parametric | Real service less variable → M/M/c pessimistic (safe direction) |
| 3 | No balking/reneging `[R]` | Boundary | Overestimates congestion slightly |
| 4 | Staff only at integer hours, shift length ≥ 2h `[R]` | Structural | True optimum with flexible shifts is lower |

`[S]` item 2 enters the sensitivity sweep.

## Phase 5 — Perspectives

### Stochastic: M/M/c queue (primary)
Per hour bucket with c servers: Erlang-C formula gives P(wait > 0) and expected wait
`E[W] = C(c, ρ) / (cμ − λ)`.
Insight: **nonlinear cliff** — at ρ → 1 waits explode; one extra barista near rush hour buys a 10× wait reduction, the same person at noon buys nothing.
Blind spot: says nothing about cost or shifts.

### Optimization (primary)
Integer program over the day:
```
minimize    Σ_h κ · c(h)
subject to  E[W](λ(h), μ, c(h)) ≤ w*   ∀h
            c(h+1) − c(h) ≤ Δmax       (ramp constraint)
            c(h) ∈ ℤ₊
```
Insight: shadow structure shows which hours are "free" (wait constraint slack) vs "binding" (every minute of break costs real money).
Blind spot: needs E[W] from queueing lens as input — lenses compose.

### Deterministic fluid (quick sanity check)
Staff so that `c(h) ≥ ⌈λ(h)/μ⌉ + 1`. Insight-free but instant; use as lower bound and sanity floor for the ILP solution.
Blind spot: ignores randomness entirely — understaffs precisely at rush hour.

### Agent-based (rejected)
Heterogeneity (regulars, group orders) would matter for loyalty studies, not aggregate staffing; M/M/c answers THIS question cheaper. One-line rejection recorded per skill rules.

### Network / Control (rejected)
No interaction topology between customers; no continuous setpoint regulation problem (staffing is re-decided daily, not steered).

## Phase 6 — Comparison & Recommendation

| Criterion | Stoch(M/M/c) | Opt(ILP) | Fluid | ABM |
|-----------|--------------|----------|-------|-----|
| Fidelity | 4 | 4 | 2 | 4 |
| Data needs | low | low | tiny | high |
| Answers goal question | ✓ waits | ✓ schedule | ✗ floor | ✗ overkill |
| Compute cost | tiny | tiny | tiny | high |

**Recommendation**: M/M/c wait model inside an ILP staffing optimizer; fluid bound as sanity check. Composed lenses, each doing what it's best at.

## Phase 7 — Implementation

```bash
python skills/axiomize/tools/validate.py --model queue --lam 60 --mu 20 --target-wait 3
```

Prints minimal staffing c meeting the wait target across utilization range, plus the cliff table showing E[W] vs c. Sensitivity sweep over μ ∈ {15..25}.

## Phase 8 — Falsifiability

Model dies if observed data show: (a) measured waits >> Erlang-C prediction at same ρ (bursty arrivals — assumption 1), (b) waits << prediction (service faster than assumed — assumption 2), (c) heavy reneging visible in data (assumption 3).
