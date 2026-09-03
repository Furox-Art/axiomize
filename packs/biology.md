# Biology Pack: Population, Community, Ecology & Molecular Kinetics

Curated pointers for biology modeling sessions where quantities obey conservation of individuals / biomass / molecules, saturating functional responses, and compartmental flows. Covers regimes where equations are **literal** mass-balance ODEs, distinct from the *analogy* lens `skills/axiomize/perspectives/thermodynamic.md:1`.

## Scope: What belongs here

| Sub-domain | Phenomena | State variables | Typical goal |
|---|---|---|---|
| Population growth | Logistic, Allee, harvesting, invasions | abundance $N(t)$, biomass $B$ [individuals or kg] | MSY, extinction threshold, time to $K$ |
| Community interactions | Competition, predation, mutualism with Type I/II/III | $N_i(t)$ by species, resource $R$ | coexistence, cycle period |
| Infection / collective spread | SIR/SEIR, SIS, waning immunity | $S,E,I,R$ [counts] | $R_0$, peak time/size |
| Molecular kinetics | Enzyme catalysis, transport, cooperativity | $[S],[E],[ES],[P]$ [mM], rate $v$ | $K_m$, saturation, switch |

Out of scope: ab initio quantum biochemistry, whole-body PBPK, adaptive evolution >10 generations.

Scale rule: mean-field ODE holds when $N\gtrsim100$; when $N\lesssim100$ or $[E]_0/[S]\gtrsim0.1$, promote `stochastic.md`.

## Archetypes

### A1: Logistic Growth (with Harvest & Allee)

$$ \frac{dN}{dt} = rN\left(1-\frac{N}{K}\right) $$
$$ N(t)=\frac{K}{1+Ce^{-rt}},\quad C=\frac{K-N_0}{N_0} $$
$$ \frac{dN}{dt}=rN\left(1-\frac{N}{K}\right)-hN $$
$$ \frac{dN}{dt}=rN\left(\frac{N}{A}-1\right)\left(1-\frac{N}{K}\right) $$

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $N(t)$ | abundance | individuals | endo state |
| $r$ | intrinsic growth | 1/time | $t_{double}=\ln2/r$ |
| $K$ | carrying capacity | same as $N$ | seasonally moving |
| $h$ | harvest mortality | 1/time | $h_{crit}=r$ |
| $A$ | Allee threshold | same as $N$ | unstable interior |

Fixed points: $N^*=0,K$ (logistic); $K(1-h/r)$ (harvest); $0,A,K$ (Allee). MSY $h_{MSY}=r/2$, $Y_{max}=rK/4$.

Sources: Verhulst 1838; Murray Ch.1-2; Kot Ch.2; Schaefer 1954.

### A2: Lotka, Volterra Competition & Predation

$$ \frac{dN_i}{dt}=r_iN_i\left(1-\frac{N_i+\sum_{j\neq i}\alpha_{ij}N_j}{K_i}\right) $$

$$ \frac{dN}{dt}=rN\left(1-\frac{N}{K}\right)-f(N)P,\quad \frac{dP}{dt}=e\,f(N)P-mP $$

$$ f_I(N)=aN,\quad f_{II}(N)=\frac{aN}{1+ahN},\quad f_{III}(N)=\frac{aN^2}{1+ahN^2} $$

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $a$ | attack rate | area/predator/time | $a=1/h_{search}$ |
| $h$ | handling time | time/prey | saturation scale |
| $e$ | conversion efficiency | , | $0<e\ll1$ |
| $m$ | predator mortality | 1/time | |

Coexistence iff $\alpha_{12}\alpha_{21}<1$ and $K_2/\alpha_{21}>K_1>K_2\alpha_{12}$.

Sources: Lotka 1925; Volterra 1926; Holling 1959; Rosenzweig & MacArthur 1963.

### A3: SIR / SEIR

$$ \frac{dS}{dt}=-\beta\frac{SI}{N},\quad \frac{dI}{dt}=\beta\frac{SI}{N}-\gamma I,\quad \frac{dR}{dt}=\gamma I $$

$$ R_0\equiv\frac{\beta}{\gamma},\quad p_c=1-\frac1{R_0},\quad R_\infty =1-e^{-R_0R_\infty} $$

Early exponential $I(t)\approx I_0 e^{\gamma(R_0-1)t}$; peak when $S=N/R_0$.

Sources: Kermack & McKendrick 1927; Anderson & May Ch.2,6.

### A4: Michaelis, Menten / Hill

$$ v=\frac{V_{max}[S]}{K_m+[S]},\quad V_{max}=k_{cat}[E]_0 $$

$$ v=\frac{V_{max}[S]^n}{K_{half}^n+[S]^n},\quad r(S)=r_{max}\frac{[S]}{K_s+[S]} $$

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $[S]$ | substrate conc. | mM | |
| $V_{max}$ | maximal velocity | conc/time | $=k_{cat}[E]_0$ |
| $K_m$ | Michaelis constant | same as [S] | $[S]$ at $v=V_{max}/2$ |
| $n_H$ | Hill coefficient | , | cooperativity |

QSSA validity: $[S]_0\gg[E]_0$ and $t\gg(k_1[S]_0+k_{-1}+k_{cat})^{-1}$.

Sources: Michaelis & Menten 1913; Briggs & Haldane 1925; Monod 1949.

## Lens-to-archetype mapping

| Archetype | Primary lens | Secondary |
|---|---|---|
| A1 Logistic | `deterministic.md` | `stochastic.md` if $N\lesssim100$ |
| A2 LV / Holling | `deterministic.md` | `spatial.md` for patch dispersal |
| A3 SIR/SEIR | `deterministic.md` | `network.md` if $\langle k^2\rangle$ matters |
| A4 MM/Hill | `deterministic.md` | `optimization.md` for $V_{max}$ |

Composition rule: build ≥2 lenses; deterministic + stochastic is highest-value pair.

## Worked mini-example

**Idea:** "Invasive carp 200 fish in 50 ha lake with $K\approx5000$, $r=0.6$/yr, removal $h=0.15$/yr, will they establish?"

- Deterministic A1c: $N^*=K(1-h/r)=3750$ stable → establishes.
- Allee audit A1e: if $A=300$, $N_0<A$ → deterministic predicts extinction.
- Stochastic: Gillespie $P(establish)\approx0.62$ when near $A$.
- Control: critical effort $qE>r(1-A/K)$.

## Lens priorities

1. Deterministic 2. Stochastic (when $N<100$) 3. Spatial/Network 4. Control

## Examples to imitate

- `examples/biology-population.md` (lake bloom tipping)
- `examples/epidemic-sir.md`

## Tools pattern

```bash
python -c "from scipy.integrate import solve_ivp; ..."
# fit: tools/fit.py --model logistic --data counts.csv
```

Order: dimension check → steady/phase-line → linear stability → MC → sensitivity sweep.

## Domain gotchas

- $K$ moves with season/nutrients
- Type I overestimates at high prey
- QSSA needs $[S]\gg[E]_0$
- $R_0$ regime-dependent

## Typical falsifiers

- Sustained growth above fitted $K$
- Recovery below $A$ (kills Allee)
- $v$ not saturating at $\gg K_m$ (kills MM)
