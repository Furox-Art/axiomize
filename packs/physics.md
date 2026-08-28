# Physics Pack — Classical Mechanics, Thermodynamics & Statistical Physics

Curated pointers for physics modeling sessions where quantities obey conservation laws, constitutive transport relations, and statistical equilibria. Covers regimes where equations are **literal** (Newton, Fourier, ideal gas, Langevin) — distinct from the *analogy* lens `skills/axiomize/perspectives/thermodynamic.md:1` which borrows thermodynamic structure for social systems.

## Scope — What belongs here

| Sub-domain | Phenomena | State variables | Typical goal |
|---|---|---|---|
| Classical mechanics | Pendula, oscillators, projectiles, collisions | position $x$, angle $\theta$, velocity $v$, energy $E$ | predict period/drift, stability |
| Continuum transport & heat | Conduction, thermal circuits, diffusion | temperature $T$, heat flux $\mathbf{q}$, concentration $c$ | steady profile, relaxation time $\tau$ |
| Equilibrium thermodynamics | Ideal gases, $pV$ work, entropy | $p,V,T,U,S$ | equilibrium state, efficiency limit |
| Statistical physics | Brownian motion, noise spectra | distribution $p(v)$, variance, $k_B T$ | jitter, rare excursion |

Out of scope: quantum coherence, relativistic, plasma, chemically reacting flow (needs coupled kinetics), full turbulence (Navier-Stokes beyond `pV` balance).

## Archetypes

### A1 — Damped harmonic oscillator / Pendulum

$$m\,\frac{d^2x}{dt^2} + b\,\frac{dx}{dt} + k\,x = F_0\cos(\omega t)$$

$$\frac{d^2\theta}{dt^2} + 2\gamma\,\frac{d\theta}{dt} + \omega_0^2\sin\theta = \frac{\tau_{\text{drive}}(t)}{mL^2}$$

| Symbol | Name | Unit |
|---|---|---|
| $m$ | mass | kg |
| $b$ | viscous damping coeff. | kg/s |
| $\gamma$ | damping rate | 1/s |
| $k$ | stiffness | N/m |
| $\omega_0=\sqrt{k/m}$ | natural frequency | rad/s |
| $Q=\omega_0/(2\gamma)$ | quality factor | – |

Small-angle: $\sin\theta\approx\theta$ ($|\theta|\lesssim0.2$ rad). Underdamped solution $x(t)=A e^{-\gamma t}\cos(\omega_d t+\phi)$.

### A2 — Heat transport (Fourier + heat equation)

$$\mathbf{q} = -k\,\nabla T$$
$$\frac{\partial T}{\partial t} = \alpha\,\nabla^2 T,\quad \alpha \equiv \frac{k}{\rho c_p}$$

Lumped: $C_{\text{th}}dT/dt = -G_{\text{th}}(T-T_\infty)+P(t)$, $\tau=C_{\text{th}}/G_{\text{th}}$.

### A3 — Equilibrium thermodynamics

$$pV = nR_u T,\quad dU = \delta Q - p\,dV,\quad pV^\gamma=\text{const (adiabatic)}$$

### A4 — Statistical fluctuations (Langevin)

$$m\frac{dv}{dt} = -\gamma v + \xi(t),\quad \langle\xi(t)\xi(t')\rangle=2\gamma k_B T\,\delta(t-t')$$

## Lens priorities

1. **Deterministic** — thresholds, periods, profiles
2. **Thermodynamic (literal)** — conservation audits
3. **Stochastic** — fluctuations, jitter
4. **Control** — regulation to setpoint

## Gotchas

- Small-angle delusion: $T\approx2\pi\sqrt{L/g}$ only for $\theta_0\to0$
- Linear damping fiction at high Re
- Lumped-$T$ overreach when $Bi>0.1$
- Thermal expansion coupling $\delta T/T=\tfrac12\alpha_L\Delta T$

## Typical falsifiers

- Period decreases with amplitude (kills small-angle)
- Ring-down vs linewidth $Q$ disagreement >20% (kills linear damping)
- Heat flux nonlinear in $\Delta T$ (kills Fourier)
