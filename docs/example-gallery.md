# Worked Example Gallery

These examples demonstrate the 8-phase workflow: each turns a plain-language idea into an explicit mathematical model, states which perspectives were rejected and why, and closes with falsification criteria. Rows are grouped by primary lens, following the [15 perspective lenses](https://github.com/Furox-Art/axiomize/tree/main/skills/axiomize/perspectives). Most examples also compose secondary lenses.

## How to read the numbers

Parameter values in these files are **illustrative**. Each range carries a source class (`lit.` /
`data` / `est.`) so you know how much weight it deserves, but the repository cites no external
source for any of them. Read these as material for learning the workflow, not as
literature-backed models. The one place where numbers are machine-checked is
[benchmark results](https://github.com/Furox-Art/axiomize/blob/main/docs/benchmark-results.md),
which carries its own reproduction command and its own limits.

## Full worked examples

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Epidemic Spread](https://github.com/Furox-Art/axiomize/blob/main/examples/epidemic-sir.md) | Deterministic (+ stochastic check) | Epidemiology | An SIR model exposes an R₀ threshold: whether an outbreak explodes or dies out is decided before any stochastic detail matters. |
| [App Adoption Growth](https://github.com/Furox-Art/axiomize/blob/main/examples/startup-growth.md) | Deterministic (Bass diffusion archetype-first) | Product growth | A single well-chosen archetype, calibrated and gated by BIC, answers ceiling and stall-timing questions. |
| [Lake Algae Bloom Tipping Point](https://github.com/Furox-Art/axiomize/blob/main/examples/biology-population.md) | Deterministic (+ stochastic validation) | Limnology / ecology | A Monod-coupled algae–zooplankton system has two stable states, so a modest cut in nutrient loading does not clear the bloom. |
| [Batch Reactor Scale-Up](https://github.com/Furox-Art/axiomize/blob/main/examples/chemistry-reaction.md) | Deterministic (+ spatial/transport, thermodynamic, control) | Chemical reaction engineering | Intrinsic selectivity falls with temperature, but internal pellet diffusion can mask the true rate behind the observed one. |
| [Damped Pendulum Clock](https://github.com/Furox-Art/axiomize/blob/main/examples/physics-oscillator.md) | Deterministic (+ stochastic, thermodynamic, control) | Mechanics | Amplitude, thermal expansion and drag each cost a fraction of a second per day, and the dominant term is the one you can fix. |
| [Medical Test Bayes](https://github.com/Furox-Art/axiomize/blob/main/examples/probability-bayes.md) | Bayesian inference (+ CLT validation, decision theory, information) | Diagnostics | A 99%-accurate test on a rare disease produces mostly false positives; only an independent second positive moves the posterior. |
| [Drone Hover in Wind](https://github.com/Furox-Art/axiomize/blob/main/examples/engineering-control.md) | Control (+ stochastic, optimization, SPC) | Control engineering | Feasibility, via thrust margin, decides whether altitude is holdable at all; PID and LQR tuning only matters afterwards. |
| [Retail Inventory Under Uncertain Demand](https://github.com/Furox-Art/axiomize/blob/main/examples/supply-chain-inventory.md) | Stochastic (+ optimization, control) | Retail operations | Demand randomness turns a restocking question into an (s,Q) policy built from newsvendor logic plus safety stock. |
| [Insurance Ruin Risk](https://github.com/Furox-Art/axiomize/blob/main/examples/insurance-ruin.md) | Stochastic | Insurance / risk | For rare-event solvency questions, deterministic averages are useless; ruin probability is a tail property only a stochastic model can price. |

## Other lenses

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Coffee Shop Staffing](https://github.com/Furox-Art/axiomize/blob/main/examples/coffee-shop-staffing.md) | Optimization (+ queueing) | Service operations | An Erlang-C wait cliff embedded in an ILP shows lenses composing: queueing computes the wait, optimization schedules the staff. |
| [Two Cafés Pricing War](https://github.com/Furox-Art/axiomize/blob/main/examples/cafe-pricing-war.md) | Game theory | Economics / competition | A price cut looks profitable while rivals are frozen; game theory reveals the rival-response term single-actor optimization cannot see. |
| [Rumor Spread in a School](https://github.com/Furox-Art/axiomize/blob/main/examples/network-rumor.md) | Network | Social dynamics | Contact structure, not just counts, decides how far a rumor travels and whether a public announcement stops it. |
| [Greenhouse Night Temperature](https://github.com/Furox-Art/axiomize/blob/main/examples/control-greenhouse.md) | Control | Agriculture / building systems | Holding temperature above a setpoint against disturbances is a feedback problem, not a prediction problem. |
| [Marketing Attribution](https://github.com/Furox-Art/axiomize/blob/main/examples/marketing-attribution.md) | Causal inference | Digital marketing | Users who see retargeting ads buying 3x more is selection, not effect; backdoor adjustment comes before spending decisions. |
| [Sensor Placement](https://github.com/Furox-Art/axiomize/blob/main/examples/sensor-placement.md) | Information theory | Data center monitoring | When you cannot measure everything, mutual information tells you which few sensor locations carry the most signal. |
| [Delivery Fleet Preventive Maintenance](https://github.com/Furox-Art/axiomize/blob/main/examples/fleet-maintenance.md) | Reliability | Logistics | Fixed-schedule versus run-to-failure becomes decidable once failure timing is a hazard distribution and costs are renewal-reward. |

## Condensed skeletons

Two files are 20-line phase outlines rather than full worked examples. They show the report
structure, not a validated model; read them after a full-length example.

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Climate-Energy Decarbonization Mix](https://github.com/Furox-Art/axiomize/blob/main/examples/climate-energy.md) | Optimization (+ deterministic, stochastic) | Energy systems | Condensed skeleton: capacity choice is an optimization problem checked against an energy-balance model, with Monte Carlo wind for reliability. |
| [Finance Portfolio Allocation](https://github.com/Furox-Art/axiomize/blob/main/examples/finance-portfolio.md) | Optimization (+ stochastic, game theory) | Finance | Condensed skeleton: mean-variance allocation with shrinkage, stress-tested by Monte Carlo and compared against a benchmark. |

---

All 18 files live in [/examples](https://github.com/Furox-Art/axiomize/tree/main/examples/).
Domain bundles that say which lenses matter per field are in
[packs/domain-packs.md](https://github.com/Furox-Art/axiomize/blob/main/packs/domain-packs.md).
