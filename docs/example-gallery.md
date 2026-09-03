# Worked Example Gallery

These examples are end-to-end demonstrations of the 8-phase workflow: each turns a plain-language idea into a calibrated mathematical model, includes rejected-lens rationales for why other perspectives were set aside, and closes with explicit falsification criteria. Rows are grouped by the primary lens demonstrated, following [the fifteen lenses](https://github.com/Furox-Art/axiomize/blob/main/README.md#the-fifteen-lenses); most examples also compose secondary lenses.

## Deterministic

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Epidemic Spread](https://github.com/Furox-Art/axiomize/blob/main/examples/epidemic-sir.md) | Deterministic (+ stochastic check) | Epidemiology | An SIR model exposes an R₀ threshold: whether an outbreak explodes or dies out is decided before any stochastic detail matters. |
| [App Adoption Growth](https://github.com/Furox-Art/axiomize/blob/main/examples/startup-growth.md) | Deterministic (Bass diffusion archetype-first) | Product growth | A single well-chosen archetype (Bass ODE), calibrated on real signups and gated by BIC, answers ceiling and stall-timing questions. |

## Stochastic

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Insurance Ruin Risk](https://github.com/Furox-Art/axiomize/blob/main/examples/insurance-ruin.md) | Stochastic | Insurance / risk | For rare-event solvency questions, deterministic averages are useless , ruin probability is a tail property that only a stochastic model can price. |
| [Retail Inventory Under Uncertain Demand](https://github.com/Furox-Art/axiomize/blob/main/examples/supply-chain-inventory.md) | Stochastic (+ optimization, control) | Retail operations | Demand randomness converts a restocking question into an (s,Q) policy built from newsvendor logic plus safety stock. |

## Optimization

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Coffee Shop Staffing](https://github.com/Furox-Art/axiomize/blob/main/examples/coffee-shop-staffing.md) | Optimization (+ queueing) | Service operations | An Erlang-C wait cliff embedded in an ILP shows lenses composing: queueing computes the wait, optimization schedules the staff. |

## Network

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Rumor Spread in a School](https://github.com/Furox-Art/axiomize/blob/main/examples/network-rumor.md) | Network | Social dynamics | Who-connects-to-whom changes the answer: contact structure, not just counts, decides how far a rumor travels and whether a public announcement stops it. |

## Control

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Greenhouse Night Temperature](https://github.com/Furox-Art/axiomize/blob/main/examples/control-greenhouse.md) | Control | Agriculture / building systems | Keeping temperature above a setpoint against disturbances is a feedback problem , heater policy follows from the control view, not from prediction alone. |

## Game theory

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Two Cafés Pricing War](https://github.com/Furox-Art/axiomize/blob/main/examples/cafe-pricing-war.md) | Game theory | Economics / competition | A 20% price cut looks profitable when rivals are frozen , game theory reveals the rival's response term that single-actor optimization cannot see. |

## Causal inference

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Marketing Attribution](https://github.com/Furox-Art/axiomize/blob/main/examples/marketing-attribution.md) | Causal inference | Digital marketing | Users who see retargeting ads buying 3x more is selection, not effect , backdoor confounding must be adjusted before spending follows. |

## Information theory

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Sensor Placement](https://github.com/Furox-Art/axiomize/blob/main/examples/sensor-placement.md) | Information theory | Data center monitoring | When you cannot measure everything, mutual information tells you which 3 sensor locations carry the most signal about overheating. |

## Reliability

| Example | Primary lens(es) | Domain | One-line takeaway |
|---|---|---|---|
| [Delivery Fleet Preventive Maintenance](https://github.com/Furox-Art/axiomize/blob/main/examples/fleet-maintenance.md) | Reliability | Logistics | Fixed-schedule versus run-to-failure becomes decidable once breakdown timing gets a Weibull hazard and costs go through renewal-reward analysis. |

---

Full texts live in [/examples](https://github.com/Furox-Art/axiomize/blob/main/examples/); each follows the standardized 8-phase report structure.
