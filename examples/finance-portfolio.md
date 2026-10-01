# Example: Finance-Portfolio -- Mean-Variance Allocation (Condensed Skeleton)

> **Status:** this is a 20-line phase outline, not a full worked example and not a validated
> model. It shows the shape of the 8-phase report. Read a full-length example first; see
> [docs/example-gallery.md](https://github.com/Furox-Art/axiomize/blob/main/docs/example-gallery.md).
>
> **Parameter provenance:** the values below are illustrative placeholders and cite no external
> source.

## Phase 1 -- Parse
Idea: "Allocate across 5 assets for max Sharpe at 12% vol." System: portfolio; State: weights; Goal: optimal w.
## Phase 2 -- Decompose
Return tails (stochastic) -> allocation (optimization) -> game vs market (game-theory).
## Phase 3 -- Parameters
| Symbol | Name | Unit | Notes |
| mu | expected return | %/yr | exo noisy |
## Phase 4 -- Assumptions
GBM iid; constant Sigma; no transaction costs [S]; fractional leverage allowed.
## Phase 5 -- Perspectives
Optimization Markowitz A1; Stochastic GBM A2; Kelly growth; Game vs benchmark.
## Phase 6 -- Comparison & Recommendation
Recommend A1 with shrinkage + A2 MC stress; Kelly fractional overlay for growth.
## Phase 7 -- Implementation
```bash
python skills/axiomize/tools/validate.py --model portfolio --risk 0.12
```
## Phase 8 -- Falsifiability
Out-of-sample Sharpe < predicted; realized vol > VaR 5% breach >>5%.
