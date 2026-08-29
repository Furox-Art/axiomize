# Finance Pack
Curated pointers for finance / portfolio / risk modeling sessions.

## Scope — What belongs here
| Sub-domain | Phenomena | State variables | Typical goal |
|---|---|---|---|
| Asset pricing | returns, CAPM, factor premia | price P, return R | expected return, alpha |
| Portfolio choice | allocation, diversification | weights w, cov Sigma | optimal w*, Sharpe |
| Derivatives & risk | options, hedging, VaR | S [\$], vol sigma | price, hedge, VaR |
| Corporate & rates | discounting, credit | cash flow CF, r | NPV, spread, ruin |
Out of scope: full order-book microstructure, high-frequency limit order, tax micro.
Scale rule: mean-variance when N assets < 1000; promote stochastic.md for tails.

## Archetypes

### A1 — Markowitz Mean-Variance Portfolio
**When:** allocation across risky assets with return-risk tradeoff.
$$\min_w w^T Sigma w \quad s.t.\ w^T mu >= mu*,\ sum w=1 \tag{A1a}$$
$$w* ~ Sigma^{-1} mu,\ Sharpe = (mu_p - r_f)/sigma_p \tag{A1b}$$
Symbols: w weights, mu expected returns, Sigma covariance, r_f risk-free.
Sources: Markowitz 1952; Sharpe 1964; Bodie Kane Marcus Ch.7.
### A2 — GBM + Black-Scholes + Kelly
**When:** price dynamics, option pricing, growth-optimal sizing.
$$dS = mu S dt + sigma S dW,\ S(t)=S0 exp((mu-0.5 sigma^2)t+sigma W) \tag{A2a}$$
$$C=S N(d1)-K e^{-rT} N(d2),\ f*=(bp-q)/b \tag{A2b}$$
Symbols: mu drift, sigma vol, W Wiener, d1,d2 Black-Scholes, f* Kelly frac.
Sources: Black-Scholes 1973; Merton 1969; Kelly 1956.
## Lens-to-archetype mapping
| Archetype | Primary lens | Secondary |
|---|---|---|
| A1 Markowitz | optimization.md | stochastic.md for return tails |
| A2 GBM/BS/Kelly | stochastic.md | optimization.md + game-theory.md |

## Lens priorities
1. Optimization 2. Stochastic 3. Game theory 4. Decision theory
## Examples to imitate
[finance-portfolio](../examples/finance-portfolio.md) · [insurance-ruin](../examples/insurance-ruin.md)
## Tools pattern
```bash
python skills/axiomize/tools/validate.py --model portfolio --risk 0.15
# sweep mu +/-20%, sigma 0.15-0.40, r_f 0-0.05
```
## Domain gotchas
- Mu is noisy — estimation error dominates optimization (Michaud critique)
- Volatility clustering breaks GBM iid; fat tails kill normal VaR
- Correlation spikes in crises — diversification vanishes when needed
- Leverage + Kelly without fraction caps guarantees ruin
## Typical falsifiers
Realized Sharpe persistently below predicted after costs; out-of-sample w* underperforms equal weight.
Option implied vol surface violates Black-Scholes flatness; Kelly full fraction drawdown >80%.
