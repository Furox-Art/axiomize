# Perspective: Thermodynamic Analogies (Flows, Stocks, and Limits)

> **Status: ANALOGY LENS.** This perspective imports structure from thermodynamics — conservation, potential-driven flow, gradient decay — as a source of hypotheses about social and economic systems. Physics laws do not transfer automatically: verify every borrowed law against the target system before trusting any conclusion reached with it. The analogy suggests; it never proves.

## When Applicable

- Phase 2 classified the core as `flow`, and the system decomposes into **stocks** held in reservoirs and exchanged across channels
- Canonical stock types: money (budgets, capital), attention (users, pageviews), talent (headcount, skills), traffic (vehicles, packets, patients)
- The question concerns **equilibrium distribution** ("where does money pool?"), **dissipation** ("where does value leak?"), or **bottlenecks** ("which channel caps total throughput?")
- You want conservation imposed **by construction**: every unit leaving one reservoir must arrive somewhere, so leaks become explicit line items instead of silent errors

What this lens sees that others miss: which single channel's resistance bounds system-wide throughput, what stock distribution follows from channel conductances alone, and how fast gradients decay once the input sustaining them stops.

## Model Forms

### 1. Stock-flow balance as a thermal circuit

Reservoirs indexed `i = 1..n` hold stock `S_i(t)` in stock units `[S]` (e.g., USD, persons, vehicles). Each reservoir has an intensive variable, the **potential** `V_i(t)`:

| Thermodynamic | Social analog | Example potential units |
|---|---|---|
| Temperature | price level | USD/item |
| Pressure | queue pressure | jobs/server |
| Concentration | density of stock | persons/region |

Flux on channel `i -> j` is `J_ij` `[S/time]`, proportional to the potential difference:

`J_ij = G_ij * (V_i - V_j)` with `G_ij >= 0` the channel conductance `[S/(time*potential)]`

Balance at reservoir `i`:

`dS_i/dt = sum_j J_ji - sum_j J_ij + In_i(t) - Out_i(t)`

where `In_i`, `Out_i` are external source/sink rates `[S/time]`. Conservation audit: summing over all `i`, internal fluxes cancel identically, leaving `sum_i dS_i/dt = sum In_i - sum Out_i`.

Mapping table:

| Thermal concept | Symbol | Social analog | Units |
|---|---|---|---|
| Resistance | `R_ij = 1/G_ij` | friction: transaction cost, approval delay | time*potential/S |
| Capacitance | `C_i = dS_i/dV_i` | inventory buffering per unit potential rise | S/potential |
| Dissipation | `Phi = sum J_ij*(V_i-V_j)` | value burned crossing a channel | S*potential/time |

With capacitance, substitute `dS_i/dt = C_i * dV_i/dt` to get an ODE system in potentials.

### 2. Entropy-style dispersion argument

Claim shape: without maintained gradients, stocks disperse — market shares equalize, attention spreads, talent diffuses toward lower-pressure regions. This is why incentives decay: a differential advantage drives flow, the flow erodes the very difference driving it, and the advantage self-extinguishes unless continuously paid for.

Formalize for one maintained gradient `Delta_V = V_a - V_b > 0` between high side `a` and low side `b`, with channel conductance `G_ab` and effective capacitance `C_eff = d(Delta_V)/d(S_a - S_b)`:

`C_eff * d(Delta_V)/dt = m(t) - G_ab * Delta_V`

where `m(t)` `[S/time]` is the maintenance flow propping up side `a` (ad spend, wage premium, subsidy). Steady state `Delta_V* = m/G_ab`, relaxation time `tau = C_eff/G_ab`. Read backwards: set `m = 0` and the gradient decays exponentially with time constant `tau` — the analog of heat flow ending at temperature equality. Dispersion is free; gradients are rented.

### 3. Near-equilibrium linear response caveat

`J = G*Delta_V` is the near-equilibrium (Ohmic) regime, valid only while `|Delta_V| << V_scale`, the characteristic potential magnitude of the system. Far from equilibrium, flows saturate at hard caps (road capacity, max click-through rate, max hiring speed). Replace linear channels with a saturating form such as:

`J_ij = J_max * tanh(G_ij * (V_i - V_j) / J_max)` where `J_max` `[S/time]` is the channel's capacity cap

State which regime the model operates in before trusting any steady state.

Analysis ladder: (cheap) steady-state network solve with fixed conductances; (medium) linear ODE dynamics with capacitances, closed-form modes and eigenvalues; (expensive) saturating nonlinear channels calibrated to data, simulated to steady state.

## Standard Analysis Output

1. Conserved (or leaking) quantity named explicitly, with unit and the audit identity `sum_i dS_i/dt = sum In_i - sum Out_i` checked term-by-term
2. Reservoir-resistance diagram in text form, edges labeled with conductances and units:

```
[ A: S_A, V_A ] --G_AB--> [ B: S_B, V_B ] --G_BC--> [ sink ]
      ^                                              |
      +------------------ G_CA <---------------------+

external inflow In_A enters A; leak rate Out_B leaves B
all G_xy in [S/(time*potential)]
```

3. Steady-state solution: all fluxes `J_ij*` and potentials `V_i*`; total dissipation `Phi*`; bottleneck identified as the channel carrying the largest `Phi` share or the smallest conductance on the critical path
4. Dominant relaxation time `tau = R_eq * C_eq`, where `R_eq`, `C_eq` are the equivalent resistance and capacitance seen from the perturbed reservoir — the answer to "how long until prices, arrears, or backlogs settle"
5. **Breakdown statement** (mandatory): list explicitly where the analogy breaks — agents optimize and anticipate, rerouting before gradients form, unlike molecules; potentials may fail to be state functions (price depends on expectations, not local stock alone); flows can create their own gradients (network effects reverse dispersion). Any conclusion resting on an unverified borrowed law is recorded as hypothesis, not result.

## Strengths / Blind Spots

- (+) Imposes conservation discipline — sinks and leaks become explicit terms, catching accounting errors other lenses tolerate
- (+) Reveals bottlenecks as resistances: total throughput is bounded by the minimal-conductance channel regardless of everything else
- (+) Fast equilibrium intuition: relaxation times fall out of `R*C`, giving back-of-envelope settling times
- (-) Social systems violate equipartition — stocks do not spread evenly over accessible states (power-law wealth distributions persist indefinitely) — and violate the intensive/extensive split (doubling a team does not double its "pressure")
- (-) Observed flows can run against current potential differences (speculation buys high expecting higher), which heat never does
- (-) The analogy is a hypothesis generator, not proof: conclusions must be re-verified in another lens before entering a report; mark every borrowed law `[S]` in the assumptions checklist until verified

---

**See also:** [deterministic](deterministic.md) · [network](network.md) · templates: [assumptions](../templates/assumptions.md) (analogy validity is `[S]` class)
