# Biology Pack

Curated pointers for population, community, and molecular biology.

## Scope

In: logistic growth, competition/predation, infection, enzyme kinetics. Out: pure physics without biology, clinical trials without transmission.

## Archetypes

### 1. Logistic Growth

$$dN/dt = rN(1-N/K),\quad N(t)=K/(1+Ce^{-rt})$$

$N$ [individuals], $r$ [1/time], $K$ [same as N]. Harvest: $dN/dt=rN(1-N/K)-hN$, Allee: $rN(N/A-1)(1-N/K)$.

### 2. Lotka–Volterra

$$dN/dt=rN-aNP,\quad dP/dt=eaNP-mP$$

$a$ [area/predator/time], $e$ [–], $m$ [1/time]. Type II: $aN/(1+ahN)·P$.

### 3. SIR

$$dS/dt=-\beta SI/N,\ dI/dt=\beta SI/N-\gamma I,\ R_0=\beta/\gamma$$

$\beta,\gamma$ [1/time], $R_0$ [–]. Final size, herd threshold $1-1/R_0$.

### 4. Michaelis–Menten

$$v=V_{max}[S]/(K_m+[S]),\quad V_{max}=k_{cat}[E]_0$$

$[S]$ [mM], $V_{max}$ [conc/time], $K_m$ [same as S].

## Lens priorities

1. Deterministic 2. Stochastic (when N<100) 3. Spatial/Network 4. Control 5. Causal

## Gotchas

- K moves with season/nutrients
- Type I overestimates at high prey
- QSSA needs [S]≫[E]₀
