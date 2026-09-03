# Chemistry Pack: Kinetics, Equilibrium & Reaction Engineering Transport

Curated pointers for chemistry modeling sessions where mole balances, rate laws, equilibrium constraints, and diffusion set outcomes. Covers regimes where equations are **literal** (mass-action, Arrhenius/Eyring, $\Delta_r G$, Fick/ADR), distinct from the *analogy* lens `skills/axiomize/perspectives/thermodynamic.md:1` which borrows thermodynamic structure for social systems.

## Scope: What belongs here

| Sub-domain | Phenomena | State variables | Typical goal |
|---|---|---|---|
| Homogeneous kinetics | elementary steps, complex networks, catalysis in solution, autocatalysis | concentration $c_i=[X_i]$ [mol·L⁻¹ or mol·m⁻³], extent $\xi$ [mol], rate $r_j$ [mol·L⁻¹·s⁻¹] | rate law, $k(T)$, mechanism discrimination, selectivity $S$ |
| Heterogeneous & biocatalysis | porous pellets, surface $k_s$, enzyme $E+S\rightleftharpoons ES\to P$, deactivation | coverage $\theta$ [-], pellet profile $c_i(r)$ [mol·m⁻³], turnover $TOF$ [1/s] | effectiveness $\eta$, Thiele $\phi$, $K_M$ |
| Equilibrium thermodynamics | reaction/solubility/acid-base, $\gamma$ corrections, $K_{eq}(T)$ | activity $a_i$ [-], $K_{eq}$ [-], $\Delta_r G$ [J·mol⁻¹], $Q$ [-] | yield ceiling $Y_{eq}$, pH/speciation, swing $T$/$p$ |
| Transport & heat-coupled | Fick diffusion, film $k_L a$, ADR, non-isothermal hotspot | $c_i(\mathbf r,t)$ [mol·m⁻³], $T(\mathbf r,t)$ [K], flux $\mathbf J_i$ [mol·m⁻²·s⁻¹] | regime map $Da$, $Pe$, $\phi$, safety margin |

Out of scope: ab initio DFT/electronic-structure prediction of $A,E_a$; detailed turbulent CFD with full micro-kinetics; plasma/electrochemical double-layer beyond Butler,Volmer; polymer chain-statistical distributions (needs separate RF approach).

Scale rule: continuum deterministic ODE/PDE holds when molecules per control volume $N=c N_A V\gtrsim 10^4$ and Knudsen $Kn=\lambda/L\lesssim 0.1$. When $N\lesssim 10^3$ (nanodroplet, single enzyme) or burst nucleation, promote `skills/axiomize/perspectives/stochastic.md:1` (Gillespie SSA) to primary. When $Da_{II}\gg1$ and $\phi>3$, pellet interior is starved, do not fit $k_{obs}$ as chemistry.

## Archetypes

### A1: Mass-action kinetics & stoichiometric network

**When:** any set of reactions with defined stoichiometry, well-mixed (or CSTR/PFR element), constant $V$ or $p$, elementary step order = stoichiometry.

$$r_j = k_j \prod_i [X_i]^{\nu_{ij}^f} \tag{A1a}$$

for elementary forward orders $\nu_{ij}^f$; reversible net $r_{j,net}=k_{j,f}\prod_i c_i^{\nu_{ij}^f}-k_{j,r}\prod_i c_i^{\nu_{ij}^r}$.

$$\frac{d[X_i]}{dt}=\sum_j \nu_{ij}\,r_j,\quad \nu_{ij}=\nu_{ij}^r-\nu_{ij}^f \tag{A1b}$$

Network: $d\mathbf c/dt = \boldsymbol\nu^{\!T}\mathbf r(\mathbf c,T)$, $\mathbf c\in\mathbb R^{n_s}$, $\boldsymbol\nu\in\mathbb R^{n_r\times n_s}$. CSTR: $+(\mathbf c_{in}-\mathbf c)/\tau$; PFR: $d\mathbf c/dz=(1/v)\boldsymbol\nu^{\!T}\mathbf r$; batch: Eq. A1b alone.

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $[X_i]=c_i$ | concentration of $i$ | mol·L⁻¹ (=10³ mol·m⁻³) | $a_i=\gamma_i c_i/c^\circ$ for non-ideal |
| $k_j$ | rate constant | (mol·L⁻¹)$^{1-n}$·s⁻¹, $n$ = overall order | $T$-dependent via A2 |
| $\nu_{ij}$ | net stoichiometric coeff. | , | $\nu_{ij}<0$ reactant, $>0$ product |
| $r_j$ | rate of reaction $j$ | mol·L⁻¹·s⁻¹ | elementary $n=\sum_i \nu_{ij}^f$ |
| $\boldsymbol\nu$ | stoichiometric matrix | , | rank = # independent reactions |
| $\tau=V/q$ | residence time | s | CSTR/PFR only |

Pseudo-first-order: when $[B]\gg[A]$, $r=k[A][B]\approx k'[A]$, $k'=k[B]_0$. Invariants: left nullspace $\mathbf u^T\boldsymbol\nu=0\Rightarrow \mathbf u^T\mathbf c=$const (atom balances). Steady states solve $\boldsymbol\nu^{\!T}\mathbf r=0$.

Sources: Atkins & de Paula *Physical Chemistry* 11e Ch.20; Fogler *Elements of Chemical Reaction Engineering* Ch.3-5; Laidler *Chemical Kinetics* Ch.2.

### A2: Arrhenius & Eyring (temperature dependence)

$$k_j(T)=A_j\exp\!\left(-\frac{E_{a,j}}{RT}\right),\quad \ln k_j=\ln A_j -\frac{E_{a,j}}{R}\frac1T \tag{A2a}$$

$$k_j(T)=\kappa\,\frac{k_B T}{h}\exp\!\left(-\frac{\Delta G^\ddagger_j}{RT}\right) \tag{A2b}$$

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $A_j$ | pre-exponential | same as $k_j$ | collision/orientation |
| $E_{a,j}$ | activation energy | J·mol⁻¹ | slope $-E_a/R$ in $\ln k$ vs $1/T$ |
| $R$ | gas constant | 8.314 J·mol⁻¹·K⁻¹ | |
| $T$ | absolute temp. | K | |
| $k_B$ | Boltzmann | 1.3806e-23 J·K⁻¹ | Eyring only |
| $h$ | Planck | 6.626e-34 J·s | Eyring only |
| $\Delta G^\ddagger$ | activation free energy | J·mol⁻¹ | |
| $Arr=E_a/(RT_0)$ | Arrhenius number | , | stiffness of $k(T)$ |

Groups: Arrhenius number $Arr$, Frank-Kamenetskii $\delta$ for thermal runaway. Two-point estimate $E_a=R\ln(k_2/k_1)/(1/T_1-1/T_2)$ doubles error if $\Delta(1/T)$ narrow.

Sources: Atkins Ch.20B; Laidler Ch.4; Fogler Ch.3.

### A3: Equilibrium thermodynamics (yield ceiling)

$$\Delta_r G = \Delta_r G^\circ + RT\ln Q,\quad \Delta_r G^\circ =-RT\ln K_{eq} \tag{A3a}$$

$$K_{eq}=\exp(-\Delta_r G^\circ/RT)=\prod_i a_i^{\nu_i,eq},\quad Q=\prod_i a_i^{\nu_i} \tag{A3b}$$

$$a_i=\gamma_i c_i/c^\circ,\quad \frac{d\ln K_{eq}}{dT}=\frac{\Delta_r H^\circ}{RT^2}\tag{A3c}$$

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $\Delta_r G^\circ$ | standard reaction Gibbs | J·mol⁻¹ | $T,p^\circ$ or $c^\circ$, state standard |
| $K_{eq}$ | equilibrium constant | , | dimensionless after $c^\circ,p^\circ$ |
| $Q$ | reaction quotient | , | same form at non-eq. |
| $a_i$ | activity | , | $\gamma_i\to1$ only $\lesssim0.1$ M |
| $c^\circ=1$ M, $p^\circ=1$ bar | standard states | mol·L⁻¹, bar | mismatch flips $K$ by $10^{\sum\nu}$ |

Derived: equilibrium conversion $X_{eq}$ from $K_{eq}=f(X_{eq})$; yield ceiling $Y_B\le Y_{eq}(T)$.

Sources: Atkins Ch.6, Ch.7; Smith & Van Ness Ch.13.

### A4: Diffusion, film & ADR with Thiele modulus

$$\mathbf J_i = -D_i\nabla c_i \tag{A4a}$$

$$\frac{\partial c_i}{\partial t}= \nabla\!\cdot\!(D_i\nabla c_i)-\mathbf v\!\cdot\!\nabla c_i +\sum_j \nu_{ij}r_j \tag{A4b}$$

Film: $J_i = k_c (c_{i,bulk}-c_{i,s})=k_L a\,(c_i^*-c_{i,bulk})$; pellet effectiveness:

$$\phi = L\sqrt{k_1/D_{eff}},\quad \eta_{slab}=\frac{\tanh\phi}{\phi},\;\eta_{sphere}=\frac{3}{\phi^2}(\phi\coth\phi-1) \tag{A4c}$$

Observed $k_{obs}=\eta\,k_{intrinsic}$.

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $D_i,D_{eff}$ | molecular/effective diffusivity | m²·s⁻¹ | $D_{eff}=D\varepsilon/\tau_{tort}$ |
| $\mathbf v$ | convective velocity | m·s⁻¹ | |
| $k_c,k_L a$ | mass-transfer coeff. | m·s⁻¹, 1/s | $Sh=k_c L/D$ |
| $L$ | diffusion length | m | slab half-thick; $R_p/3$ sphere |
| $\phi$ | Thiele modulus | , | $\phi>3\Rightarrow\eta<0.3$ diffusion-limited |
| $\eta$ | effectiveness factor | , | $0<\eta\le1$ (isothermal) |
| $Da_I=k c_0^{n-1}\tau$ | Damköhler I | , | reaction vs residence |
| $Da_{II}=k L^2/D_{eff}=\phi^2$ | Damköhler II | , | reaction vs diffusion |
| $Pe=vL/D$ | Péclet | , | advection vs diffusion |

Criterion: external film controls when $Bi_m\ll1$, internal when $Bi_m\gg1$ and $\phi>1$.

Sources: Bird-Stewart-Lightfoot *Transport Phenomena* Eq.17.1-1, Ch.18; Fogler Ch.14-15; Levenspiel Ch.18.

## Lens-to-archetype mapping

| Archetype | Primary lens | Secondary |
|---|---|---|
| A1 Network | `deterministic.md` (ODE/PFR $dc/dt=\nu^T r$) | `stochastic.md` if $N<10^4$ (Gillespie) |
| A2 Arrhenius/Eyring | `deterministic.md` ($k(T)$ drives ODE) | `thermodynamic.md` literal, `reliability.md` for T-safety |
| A3 Equilibrium | `thermodynamic.md` literal ($\Delta_r G$, $K_{eq}$ ceiling) | `optimization.md` for $Y_{eq}$ under $T/p$ choice |
| A4 ADR/film/Thiele | `spatial.md` for field $c(\mathbf r)$ | `deterministic.md` (lumped $\eta$), `control.md` if feed steers hotspot |

Composition rule: build ≥2 lenses; **deterministic (mean) + spatial/transport ($\eta,\phi$)** is highest-value pair for chemistry.

## Worked mini-example

**Idea:** "Batch $A\to B$, $c_{A0}=0.5$ M, $k=0.02$ s⁻¹ at 300 K, $E_a=52$ kJ/mol, porous pellet $R_p=2$ mm, $D_{eff}=1\times10^{-9}$ m²/s. Will 350 K double rate? Will pellets limit?"

- Deterministic A1+A2: $k(350)=0.02\exp[-E_a/R(1/350-1/300)]=0.246$ s⁻¹ (12×, not 2×, $Arr=20.9$).
- Spatial A4: $L=R_p/3=0.67$ mm, $\phi=3.0$ → $\eta_{sphere}=0.48$ at 300 K, $\phi=10.5$ → $\eta=0.26$ at 350 K. Observed $k_{obs}=\eta k$ actually 0.064 s⁻¹, only 6.7× gain.
- Optimization: choose $R_p\le0.5$ mm or crush → $\phi<1$ → $\eta>0.93$ and recover intrinsic gain.

## Lens priorities

1. Deterministic 2. Spatial/Transport 3. Thermodynamic literal 4. Stochastic/Gillespie when $N$ small 5. Optimization 6. Control

## Examples to imitate

- `examples/chemistry-reaction.md` (scale-up diagnosis. ODE + Thiele sweep + stir-speed ladder)
- `examples/control-greenhouse.md` (thermal ODE pattern)
- `examples/epidemic-sir.md` (ledger/comparison structure)

## Tools pattern

```bash
# 1. dimension check: k [1/s]*c [M] -> M/s ; Ea/R/T dimensionless
# 2. solve_ivp batch ODE: dc/dt = nu^T r(c,T)*eta(phi) with Arrhenius
# 3. van't Hoff K(T) ceiling check; eta = tanh(phi)/phi sweep over Rp
# 4. MC N>=1e4 for gamma, k, Ea uncertainty
```

Order: dimension check → equilibrium $Y_{eq}$ → ideal-mixed ODE/PFR → Thiele/$\eta$ regime map → Monte Carlo → sensitivity sweep → stir-speed/$R_p$ ladder.

## Domain gotchas

- $k_{obs}=\eta\,k$ illusion, crushing pellets changes $\eta$, not chemistry
- Narrow $T$-window extrapolation. $E_a$ from $\Delta T<20$ K amplifies noise
- $\gamma_i=1$ fiction above $I>0.01$ M
- First-order $\phi$ misused for $n\neq1$, generalized $\phi_n=L\sqrt{k c_s^{n-1}/D_{eff}}$
- Non-isothermal pellet can have $\eta>1$ (super-effectiveness)

## Typical falsifiers

- $r$ scales as $[A]^{0.7}$ not $[A]^1$ (log-log slope) → kills first-order
- Arrhenius plot curved $R^2<0.95$ → kills single-step Arrhenius
- Yield independent of $R_p$ while $C_{WP}<0.3$ → kills diffusion hypothesis
- $Y_{obs}>Y_{eq}(T)$ by >2$\sigma$ → kills mass balance or $\Delta_r G^\circ$
