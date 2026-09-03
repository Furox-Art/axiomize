# Physics Pack: Classical Mechanics, Thermodynamics & Statistical Physics

Curated pointers for physics modeling sessions where quantities obey conservation laws, constitutive transport relations, and statistical equilibria. Covers regimes where equations are **literal** (Newton, Fourier, ideal gas, Langevin), distinct from the *analogy* lens `skills/axiomize/perspectives/thermodynamic.md:1` which borrows thermodynamic structure for social systems.

## Scope: What belongs here

| Sub-domain | Phenomena | State variables | Typical goal |
|---|---|---|---|
| Classical mechanics | Pendula, oscillators, projectiles, collisions, vibrations | position $x$, angle $\theta$, velocity $v$, energy $E$ | predict period/drift, amplitude, stability |
| Continuum transport & heat | Conduction, thermal circuits, diffusion, thermal expansion | temperature $T(\mathbf{r},t)$, heat flux $\mathbf{q}$, concentration $c$ | steady profile, relaxation time $\tau$ |
| Equilibrium thermodynamics | Ideal gases, first/second law balances, $pV$ work, entropy | $p,V,T,U,S$ | equilibrium state, available work, efficiency |
| Statistical physics | Brownian motion, noise spectra, Boltzmann populations | distribution $p(v)$, variance, $k_B T$ | jitter, rare excursion |

Out of scope: quantum coherence, relativistic, plasma, chemically reacting flow (needs coupled kinetics), full turbulence.

Scale rule: classical pack assumes continuum holds. When $N\lesssim100$ particles or Knudsen $Kn\gtrsim0.1$, promote `stochastic.md` to primary.

## Archetypes

### A1: Damped (and driven) harmonic oscillator / Pendulum

**When:** any restoring force $\propto$ displacement near equilibrium.

$$m\,\frac{d^2x}{dt^2} + b\,\frac{dx}{dt} + k\,x = F_0\cos(\omega t) \tag{A1a}$$

$$\frac{d^2\theta}{dt^2} + 2\gamma\,\frac{d\theta}{dt} + \omega_0^2\sin\theta = \frac{\tau_{\text{drive}}(t)}{mL^2} \tag{A1b}$$

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $m$ | mass | kg | |
| $b$ | viscous damping coeff. | kg/s = N·s/m | $b=2m\gamma$ |
| $\gamma$ | damping rate | 1/s | amplitude $e^{-\gamma t}$ |
| $k$ | stiffness | N/m | $\omega_0=\sqrt{k/m}$ |
| $Q=\omega_0/(2\gamma)$ | quality factor | , | rings before decay |
| $\omega_d=\sqrt{\omega_0^2-\gamma^2}$ | damped frequency | rad/s | $T_d=2\pi/\omega_d$ |
| $E=\tfrac12 m\dot x^2+\tfrac12 kx^2$ | mechanical energy | J | decays $e^{-2\gamma t}$ |

Underdamped: $x(t)=A e^{-\gamma t}\cos(\omega_d t+\phi)$; Pendulum correction $T(\theta_0)\approx T_0(1+\theta_0^2/16+11\theta_0^4/3072)$; resonance $|\omega-\omega_0|\lesssim\gamma$.

Sources: French *Vibrations and Waves* Ch.3-4; Taylor *Classical Mechanics* Ch.5; Marion & Thornton §3.6.

### A2: Heat transport (Fourier + heat equation)

$$\mathbf{q} = -k\,\nabla T \tag{A2a}$$
$$\frac{\partial T}{\partial t} = \alpha\,\nabla^2 T,\quad \alpha \equiv \frac{k}{\rho c_p} \tag{A2b}$$
$$C_{\text{th}}\frac{dT}{dt} = -G_{\text{th}}(T-T_\infty)+P(t),\quad \tau=C_{\text{th}}/G_{\text{th}} \tag{A2c}$$
$$L(T)=L_0[1+\alpha_L(T-T_0)] \tag{A2d}$$

Groups: Biot $Bi=hL_c/k$ (uniform-$T$ iff $Bi<0.1$), Fourier $Fo=\alpha t/L^2$.

Sources: Incropera et al. *Fundamentals of Heat and Mass Transfer* Eq.1.1, Ch.5.

### A3: Equilibrium thermodynamics

$$pV = nR_u T = Nk_BT,\quad dU = \delta Q - p\,dV \tag{A3a,b}$$
$$pV^\gamma=\text{const (adiabatic)},\quad \Delta S=n c_v\ln(T_2/T_1)+nR_u\ln(V_2/V_1) \tag{A3c}$$

$R_u=8.314$ J/mol/K, $k_B=1.38e-23$ J/K, $c_p-c_v=R_u$.

Sources: Callen *Thermodynamics* Ch.2-5; Kittel & Kroemer Ch.3.

### A4: Statistical fluctuations (Langevin / Boltzmann)

$$m\frac{dv}{dt} = -\gamma v + \xi(t),\quad \langle\xi(t)\xi(t')\rangle=2\gamma k_B T\,\delta(t-t') \tag{A4a}$$
$$p(E)\propto e^{-E/k_BT},\quad D=k_BT/\gamma \tag{A4b}$$

Sources: Reif Ch.15; van Kampen Ch.VII; Gardiner §3.7.

## Lens-to-archetype mapping

| Archetype | Primary lens | Secondary |
|---|---|---|
| A1 Oscillator | `deterministic.md` (ODE, $Q$, resonance) | `control.md` if driven, `stochastic.md` if low $Q$ |
| A2 Heat | `deterministic.md` + `thermodynamic.md` literal | `spatial.md` for field $T(\mathbf r)$ |
| A3 Ideal gas | `thermodynamic.md` literal | `optimization.md` for max work |
| A4 Langevin | `stochastic.md` (SDE, MC) | `thermodynamic.md` (FDT) |

Composition rule: build ≥2 lenses; deterministic (mean) + stochastic (variance) is highest-value pair for physics.

## Worked mini-example

**Idea:** "1 m steel rod, clearance 0.2 mm at 20°C, will it jam at 55°C?"

- Deterministic: $\Delta L=12e-6×1.0×35≈0.42$mm >0.2mm → jams.
- Thermodynamic: $Q=m c_p\Delta T$ confirms hours, not minutes.
- Stochastic: tolerances ±0.05mm, $\alpha_L$ ±10% → MC $P(jam)≈0.93$.
- Optimization: required clearance 0.55mm or Invar $\alpha_L≈1.3e-6$.

## Lens priorities

1. Deterministic 2. Thermodynamic (literal) 3. Stochastic 4. Control (when goal is “keep at”)

Add `spatial.md` when answer is field $T(\mathbf r)$.

## Examples to imitate

- `examples/control-greenhouse.md` (thermal ODE)
- `examples/epidemic-sir.md` (ledger/comparison structure)

## Tools pattern

```bash
python -c "from scipy.integrate import solve_ivp; ..."
# Period via zero-crossings; Q from ring-down; MC N≥1e4
```

Order: dimension check → steady → linear stability → MC → sensitivity sweep.

## Domain gotchas

- Small-angle delusion: $T(\theta_0)$ growth $\propto\theta_0^2/16$
- Linear damping fiction at $Re\gtrsim10^3$
- Isothermal vs adiabatic swap flips $T$ by ~40% for air
- Lumped-$T$ overreach when $Bi>0.1$
- Ignoring thermal expansion $\delta T/T=0.5\alpha_L\Delta T$ (≈0.5 s/day per K steel)

## Typical falsifiers

- Period decreases with amplitude (kills small-angle)
- Ring-down vs linewidth $Q$ disagree >20% (kills linear $b$)
- $q$ nonlinear in $\Delta T$ (kills Fourier)
