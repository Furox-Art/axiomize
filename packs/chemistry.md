# Chemistry Pack

Curated pointers for reaction kinetics, equilibrium, and transport.

## Scope

In: homogeneous/heterogeneous kinetics, catalysis, equilibria, diffusion, heat-coupled chemistry. Out: ab initio DFT, full turbulent CFD.

## Archetypes

### 1. Mass-Action Kinetics

$$r_j = k_j \prod_i [X_i]^{\nu_{ij}^f},\quad d[X_i]/dt = \sum_j \nu_{ij} r_j$$

| Symbol | Unit | Notes |
|---|---|---|
| $[X_i]$ | mol·L⁻¹ | concentration |
| $k_j$ | (mol·L⁻¹)^{1-n}·s⁻¹ | rate constant, n=overall order |
| $\nu_{ij}$ | – | net stoichiometric coeff. |

Network: $dc/dt = \nu \cdot r(c,T)$.

### 2. Arrhenius

$$k_j(T)=A_j\exp(-E_{a,j}/RT),\quad \ln k = \ln A - E_a/(RT)$$

$E_a$ [J/mol], $R=8.314$ J/mol/K, $T$ [K]. Group $Arr=E_a/(RT_0)$.

### 3. Equilibrium

$$\Delta_r G = \Delta_r G°+RT\ln Q,\quad K_{eq}= \exp(-\Delta_r G°/RT)$$

$Q=\prod a_i^{\nu_i}$, $a_i=\gamma_i c_i/c°$.

### 4. Diffusion & Transport

$$J_i=-D_i\nabla c_i,\quad \partial c_i/\partial t = \nabla·(D_i\nabla c_i)-v·\nabla c_i+\sum_j\nu_{ij}r_j$$

Film: $J_i=k_L a(c_i^*-c_i)$, $\eta=\tanh\phi/\phi$, $\phi=L\sqrt{k_1/D_{eff}}$.

Groups: $Da_I=k c_0^{n-1}\tau$, $Da_{II}=kL^2/D$, $Pe=vL/D$.

## Lens priorities

1. Deterministic (balances, ODE/PDE) 2. Spatial/Transport 3. Thermodynamic 4. Stochastic (Gillespie when counts low) 5. Optimization 6. Control

## Gotchas

- $k_{obs}=\eta·k$ — particle size changes $\eta$, not chemistry
- $E_a$ from narrow T window → wild extrapolation
- $\gamma_i=1$ fails above 0.1M
