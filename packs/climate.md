# Climate Pack
Curated pointers for climate / energy / decarbonization modeling sessions.

## Scope: What belongs here
| Sub-domain | Phenomena | State variables | Typical goal |
|---|---|---|---|
| Energy balance | radiative forcing, EBM, feedbacks | T [K], F [W/m2] | warming, ECS |
| Carbon cycle | emissions, sinks, budget | CO2 [ppm], E [GtCO2/yr] | concentration path |
| Mitigation & energy | capacity, LCOE, storage | capacity [GW], cost [$] | optimal mix |
| Extremes & risk | heatwaves, tail events | return period [yr] | risk, adaptation |
Out of scope: full GCM CFD, NWP weather, IAM political negotiation.
Scale rule: 0-D EBM when global mean suffices; promote spatial.md for gradients.

## Archetypes
### A1: Zero-D Energy Balance Model
**When:** global-mean T response to forcing with feedback.
$$C dT/dt = F(t) - lambda T \tag{A1a}$$
$$F2x=3.7 W/m2,\ ECS=F2x/lambda \tag{A1b}$$
Symbols: C [J/m2/K] ~8, lambda [W/m2/K] 1.0-1.5, ECS [K] ~3.
Sources: North 1981; IPCC AR6 Ch.7.
### A2: Kaya + Carbon Budget
**When:** emissions drivers and warming from cumulative carbon.
$$E=P*g*e*f \tag{A2a}$$
$$dT~TCRE*sum E,\ TCRE~0.45K/1000GtCO2 \tag{A2b}$$
Symbols: P pop., g GDP/P, e energy/GDP, f CO2/energy; TCRE transient.
Sources: Raupach 2007; IPCC AR6.
## Lens-to-archetype mapping
| Archetype | Primary lens | Secondary |
|---|---|---|
| A1 EBM | deterministic.md | stochastic.md for variability |
| A2 Kaya/Budget | optimization.md | control.md for pathways |
## Lens priorities
1. Deterministic 2. Optimization 3. Stochastic 4. Control
## Examples to imitate
[climate-energy](../examples/climate-energy.md) · [control-greenhouse](../examples/control-greenhouse.md)
## Tools pattern
```bash
python skills/axiomize/tools/validate.py --model ebm --ecs 3.0
# sweep lambda 0.8-1.5, TCRE 0.35-0.55
```
## Domain gotchas
- ECS != TCR, transient lags ECS by decades (ocean inertia)
- Airborne fraction 0.4-0.6; constant-AF overstates after 2050
- Discount rate r=3% vs 7% flips mitigation sign
- Mean warming misses tail extremes, variance matters
## Typical falsifiers
GMST trend outside EBM envelope at fixed lambda; AF outside 0.3-0.7 decade.
Observed LCOE learning curve breaks Kaya cost assumption.
Carbon budget linearity fails above ~3000 Gt cumulative; curtailment > predicted.
Storage cost outside Wright law envelope at observed scale.
