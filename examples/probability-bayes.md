# Example: Medical Test Bayes

**Idea:** Test 99% accurate, disease 1/1000 — worry if positive?

## Phase 1 — Parse
State $D\in{0,1}, T\in{+,-}$, prior $\pi=0.001$, $Se=0.99, Sp=0.99$

## Phase 2 — Decompose
Bayes update, CLT for Se/Sp uncertainty, decision, information

## Phase 3 — Parameters
$\pi=0.001$, $Se=0.99$, $Sp=0.99$, payoff $u_{ij}$

## Phase 4 — Assumptions
Se/Sp apply here, $\pi$ known, independent retest

## Phase 5 — Perspectives
- Bayes: $PPV=Se\pi/(Se\pi+\alpha(1-\pi))\approx9\%$
- Decision: $EU(a_i)=\sum p_j u(x_{ij})$, EVPI
- Information: $I(D;T)\approx0.06$ bits
- HT: Binomial CI for $Se,Sp$

## Phase 6 — Recommendation
Bayes primary (PPV 9%) + decision table.

## Phase 7 — Implementation
Analytic + Monte Carlo $N=200k$, sweep $\pi\in[0.001,0.1]$.

## Phase 8 — Falsifiability
Dies if field PPV far from 9% at same π,Se,Sp.

