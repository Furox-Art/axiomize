# Probability Pack

Foundations for every lens where uncertainty is load-bearing.

## Scope

Aleatoric (counts, waiting times), epistemic (Bayes), Markov dynamics, hypothesis testing.

## Archetypes

### 1. Bayes

$$P(H|E)=P(E|H)P(H)/P(E),\quad PPV=Se·π/(Se·π+α(1-π))$$

$\pi$ prevalence [–], $Se=P(+|D)$, $Sp=P(-|¬D)$, $PPV$ [–].

### 2. CLT

$$Z_n=(\bar X_n-μ)/(σ/√n)→N(0,1),\quad \bar X_n≈N(μ,σ²/n)$$

$n$ [–], $μ,σ$ [X], CI: $\bar X_n±1.96σ/√n$.

### 3. Markov Chain

$$P_{ij}=P(X_{t+1}=j|X_t=i),\quad π=πP,\quad h_i=1+∑_j P_{ij}h_j$$

$q_{i→j}$ [1/time] for CTMC, Gillespie exact.

### 4. Hypothesis Test

$$p=P_{H0}(T≥t_{obs}),\quad Power=1-β,\quad CI_{1-α}$$

$\alpha$ [–], $p$ [–].

## Gotchas

- Base-rate neglect
- CLT needs n large & finite variance
- p>0.05 ≠ no effect
