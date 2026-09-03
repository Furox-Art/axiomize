# Template: Active Parameter Table

Extract EVERY quantity that influences the modeled behavior. This table is the contract between the idea and the mathematics.

| Symbol | Name | Unit | Exo/Endo | Range (typical) | Source | Sensitivity | In model(s) |
|--------|------|------|----------|------------------|--------|-------------|-------------|
| β | transmission rate | 1/day | exo | 0.1-0.5 | lit. | high | det, stoch |
| γ | recovery rate | 1/day | exo | 0.05-0.2 | lit. | medium | det, stoch |
| I(t) | infected count | persons | endo | ≥ 0 | derived | , | det, stoch |

## Column rules

- **Symbol**: single letter, used consistently in ALL equations afterward.
- **Unit**: mandatory. Dimensionless must be marked `(-)` deliberately, not forgotten.
- **Exo/Endo**: exogenous = input/given; endogenous = computed by the model. A parameter that is endogenous somewhere and exogenous elsewhere signals a coupling worth examining.
- **Range**: realistic values, not arbitrary ones. Cite source class: `lit.` (literature), `data` (user-provided), `est.` (your estimate, flag these).
- **Sensitivity**: qualitative first pass, "if this doubles, does the answer change wildly?" Top-2 high-sensitivity params go into the Phase 7 numerical sweep.
- **In model(s)**: which perspectives use it, reveals shared structure between lenses.

## Excluded parameters

List what you deliberately LEFT OUT:

| Excluded | Why it's safe to exclude |
|----------|--------------------------|
| *(e.g., seasonal forcing of β)* | *Horizon << 1 year* |

Exclusion with justification = dimension reduction. Exclusion without justification = hidden failure mode.

## Derived quantities

Record combinations that earn names (they usually carry the insight):

- R₀ = β/γ, basic reproduction number, threshold at R₀ = 1
- *(define analogous compound quantities for your model)*
