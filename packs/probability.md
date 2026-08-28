# Probability & Statistics Pack — Bayes, CLT, Markov Chains & Hypothesis Testing

Curated pointers for modeling sessions where **uncertainty is the load-bearing structure** — noisy measurement, partial knowledge, repeated random dynamics, or evidence thresholds. Covers regimes where equations are **literal** (Bayes, CLT, Markov, Neyman-Pearson).

## Scope — What belongs here

| Sub-domain | Phenomena | State variables | Typical goal |
|---|---|---|---|
| Bayesian updating | Screening tests, diagnosis, spam filtering | prior $\pi$, likelihood $P(E\|H)$, posterior $P(H\|E)$ [–] | posterior probability / PPV |
| Large-sample / estimation | Polling, measurement averaging, simulation | sample mean $\bar X_n$, variance $\sigma^2$, $n$ | CI for $\mu$, required $n$ |
| Markov dynamics | Disease-state progression, queue states, churn | distribution $\mathbf{p}(t)$, transition $P_{ij}$ | stationary $\boldsymbol\pi$, absorption prob. |
| Frequentist inference | Hypothesis testing, power analysis | test stat $T$, $p$-value, power $1-\beta$ | decide $H_0$, report interval |

Out of scope: measure-theoretic foundations, Bayesian nonparametrics, deep learning bounds, full EVT beyond CLT caveats.

Scale rule: When $N\lesssim100$ counts or $n\pi(1-\pi)<5$, normal approximation suspect — use exact Binomial/Beta.

## Archetypes

### A1 — Bayes Rule / Positive Predictive Value (PPV)

$$P(H\mid E)=\frac{P(E\mid H)P(H)}{P(E)},\quad P(E)=\sum_H P(E\mid H)P(H)$$

$$PPV\equiv P(D\mid+)=\frac{Se\cdot\pi}{Se\cdot\pi+(1-Sp)(1-\pi)},\quad LR_{+}=\frac{Se}{1-Sp}$$

$$O_{\text{post}}=\Lambda\cdot O_{\text{prior}},\quad \Lambda\equiv\frac{P(E\mid H_1)}{P(E\mid H_0)}$$

Sequential independent tests multiply $\Lambda$: $O(D\mid+,+)=LR_{+}^2 O_{\text{prior}}$.

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $\pi=P(D)$ | prevalence / prior | – | base rate, most sensitive for rare events |
| $Se=P(+\mid D)$ | sensitivity | – | true-positive rate |
| $Sp=P(-\mid\neg D)$ | specificity | – | true-negative rate |
| $PPV$ | positive predictive value | – | $P(D\mid+)$ |
| $LR_{+},LR_{-}$ | likelihood ratios | – | how much a result moves odds |
| $O$ | odds $p/(1-p)$ | – | $p=O/(1+O)$ |

Base-rate neglect: with $\pi=0.001$, $Se=Sp=0.99$ → $PPV\approx9\%$.

Sources: Gelman et al. *Bayesian Data Analysis* Ch.1–2; Casella & Berger Ch.4; Fagan NEJM 1975.

### A2 — Central Limit Theorem / Normal Approximation

$$Z_n\equiv\frac{\bar X_n-\mu}{\sigma/\sqrt{n}}\xrightarrow{d}N(0,1),\quad \bar X_n\dot\sim N(\mu,\sigma^2/n)$$

$$CI_{1-\alpha}\approx\bar X_n\pm z_{1-\alpha/2}\cdot SE,\quad SE=\sigma/\sqrt{n}$$

De Moivre–Laplace: $k\sim\text{Binom}(n,p)\approx N(np,np(1-p))$, $P(k\le k_0)\approx\Phi((k_0+0.5-np)/\sqrt{np(1-p)})$

Wilson score interval (preferred when $p$ near 0/1):

$$CI_{Wilson}=\frac{\hat p+z^2/2n \pm z\sqrt{\hat p(1-\hat p)/n+z^2/4n^2}}{1+z^2/n}$$

Sample-size for margin $m$: $n\approx z_{1-\alpha/2}^2\sigma^2/m^2$.

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $\mu$ | population mean | [X] | $E[X]$ |
| $\sigma^2$ | population variance | [X²] | needs finite for CLT |
| $n$ | sample size | – | effective $n$ after clustering |
| $SE$ | standard error | [X] | $\sigma/\sqrt{n}$ |
| $z_{1-\alpha/2}$ | normal quantile | – | 1.96 for 95% |

Groups: $CoV=\sigma/\mu$, $n\pi(1-\pi)$ (Binomial rule $\ge5$).

Sources: Feller Vol.I Ch.VIII; Casella & Berger Thm 5.5.14; Lehmann & Romano Ch.11.

### A3 — Markov Chain (Stationary, Absorption, CTMC)

$$P_{ij}=P(X_{t+1}=j\mid X_t=i),\quad \mathbf{p}_{t+1}=\mathbf{p}_t P$$

$$\boldsymbol\pi=\boldsymbol\pi P,\quad \sum_i\pi_i=1$$

$$q_{i\to j}\ge0,\quad \frac{d\mathbf{p}}{dt}=\mathbf{p}Q,\quad \boldsymbol\mu Q=\mathbf{0}$$

Gillespie exact simulation: draw $\tau\sim\text{Exp}(\sum_j q_{i\to j})$, jump to $j$ with prob. $q_{i\to j}/\sum_k q_{i\to k}$.

Absorption: $N=(I-Q)^{-1}$, $\mathbf{t}=N\mathbf{1}$, $B=N R$.

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $P_{ij}$ | transition prob. | – | row-stochastic |
| $q_{i\to j}$ | transition rate | 1/time | CTMC |
| $\boldsymbol\pi$ | stationary distribution | – | long-run fraction |
| $h_i$ | expected hitting time from $i$ | time | solves linear system |

Sources: Norris *Markov Chains* Ch.1–3; Grimmett & Stirzaker Ch.6; Gillespie 1977.

### A4 — Hypothesis Test & Interval (p-value, Power, CI)

$$H_0:\theta\in\Theta_0\ \text{vs}\ H_1:\theta\in\Theta_1,\quad p=P_{H_0}(T\ge t_{obs})$$

Decision: reject $H_0$ if $p\le\alpha$. $\alpha=P(\text{Type I})$, $\beta=P(\text{Type II})$, power $=1-\beta$.

$$CI_{1-\alpha}=\hat\theta\pm z_{1-\alpha/2}\cdot SE(\hat\theta)$$

Clopper–Pearson: $CI_{CP}=[\text{Beta}_{\alpha/2}(k,n-k+1),\ \text{Beta}_{1-\alpha/2}(k+1,n-k)]$

Power & sample-size:

$$n\approx\left(\frac{(z_{1-\alpha/2}+z_{1-\beta})\sigma}{\Delta}\right)^2$$

Multiple testing: Bonferroni $\alpha/m$, Holm, FDR $q$-value.

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $p$ | p-value | – | $P_{H_0}(T\ge t_{obs})$; NOT $P(H_0\mid data)$ |
| $\alpha$ | significance level | – | 0.05 is convention not law |
| $1-\beta$ | power | – | report before experiment |
| $\Delta$ | minimum detectable effect | [X] | the $\Delta$ you designed for |

Sources: Lehmann & Romano Ch.3,7; Wasserman Ch.10; Cohen 1988; Benjamini & Hochberg 1995.

## Lens-to-archetype mapping

| Archetype | Primary lens | Secondary |
|---|---|---|
| A1 Bayes / PPV | `stochastic.md` + `decision-theory.md` | `information-theory.md` ($I(D;T)$, EVPI) |
| A2 CLT / Normal approx | `stochastic.md` (CLT, MC SE) | `spc.md` (control limits) |
| A3 Markov | `stochastic.md` (CTMC/Gillespie) + `network.md` | `reliability.md` (absorption = failure) |
| A4 HT & CI | `causal-inference.md` guard | `decision-theory.md` (α,β as loss) |

Composition rule: build ≥2 lenses; **stochastic (what credence?) + decision (so what?)** is highest-value pair.

## Worked mini-example

**Idea:** "Rapid test is 99% Se and 99% Sp for disease with $\pi=1/1000$; patient tests positive — reassure or refer?"

- Bayes (A1): $PPV=0.99·0.001/(0.99·0.001+0.01·0.999)\approx0.09$ (9%). Two independent positives: $O_{++}=99^2·0.001\Rightarrow p_{++}=0.91$ (91%).
- CLT/interval (A2): Manufacturer $Sp$ on $n=500$, $k=495$ → Wilson $[0.977,0.996]$, SE for PPV ≈0.015.
- Markov (A3): Repeat-testing policy 3-state chain, expected time to absorption $h_{unknown}=1.09$ tests.
- HT & decision (A4): $p=0.01$ would reject at $\alpha=0.05$ yet $P(D\mid+)=0.09$: $p\neq P(D\mid+)$.

## Lens priorities

1. Stochastic — is answer a distribution/credence?
2. Decision-theory — who must act under that credence?
3. Causal-inference — does question claim $do(X)$?
4. Information-theory — what is next test worth in bits?

## Examples to imitate

- `examples/probability-bayes.md` (Bayes primary + CLT validation + decision)
- `examples/epidemic-sir.md` (deterministic+stochastic pair)
- `examples/sensor-placement.md` (information lens audit)

## Tools pattern

```bash
python -c "from scipy.stats import binom, beta, norm; import numpy as np
# PPV analytic + Wilson/Clopper-Pearson + MC N≥1e5 + sweep pi in [0.001,0.1]
# CLT: SE = sigma/np.sqrt(n); norm.ppf(0.975) -> 1.96
# Markov: pi @ P; np.linalg.solve(I-Q, np.ones(k))
# HT: power = 1 - norm.cdf(z_a - delta*np.sqrt(n)/sigma)
"
# Analytic first (A1c), exact interval if np(1-p)<5, else Wald/Wilson
# Monte Carlo N≥1e5; SE_MC ~ 1/sqrt(N)
```

Order: units check → analytic Bayes → exact CI before Wald → MC → sensitivity sweep → power audit.

## Domain gotchas

- Base-rate neglect: $Se=Sp=0.99$ feels certain; $PPV\approx9\%$ at $\pi=0.001$
- Wald interval delusion at $p\approx0/1$ and $n\lesssim30$; Wilson wins
- CLT without variance: heavy tails $\alpha\le2$ have no $\sigma$
- $p>0.05\neq$ no effect; $p\le0.05$ with huge $n$ ≠ important
- Power after the fact is noisy transform of $p$
- Memoryless fiction: Markov assumes history-free
- Independence fiction: multiplying $LR$s assumes conditionally independent tests
- Transporting $Se,Sp$ across spectrum bias shifts $PPV$ 3–5×

## Typical falsifiers

- Field $PPV$ outside analytic $CI_{Wilson}$ by $>2\times SE$ (kills A1 transport)
- Binomial CI misses nominal coverage (kills normal approx)
- Empirical sojourn not Exponential (kills Markov)
- Observed power curve disagrees >20% or $p$-curve not uniform under $H_0$
