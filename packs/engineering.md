# Engineering Pack — Control, Queueing, Reliability & Optimization

Curated pointers for engineering modeling sessions where quantities obey feedback regulation, stochastic congestion, lifetime hazard, and constrained resource allocation.

## Scope — What belongs here

| Sub-domain | Phenomena | State variables | Typical goal |
|---|---|---|---|
| Control systems | PID/LQR regulation, setpoint tracking, disturbance rejection | state $\mathbf{x}$, error $e$, control $u$, output $y$ | stability, $T_s$, overshoot $M_p$ |
| Queueing & service | arrivals, service, congestion, staffing | $\lambda$, $\mu$, queue length $L$, wait $W$ | $E[W_q]$, staffing $c^*$ |
| Reliability & maintenance | wear-out, random failure, redundancy | lifetime $T$, hazard $h(t)$, survival $S(t)$ | MTTF, availability $A$, $t_p^*$ |
| Optimization & allocation | resource assignment, scheduling | decision $\mathbf{x}$, objective $f(\mathbf{x})$, dual $y$ | feasible optimum, shadow price |
| Signal processing | filtering, sampling, SNR | signal $s(t)$, noise $n(t)$, PSD $S(\omega)$ | RMSE, detection delay |

Out of scope: full FEA/CFD beyond lumped, chemically reacting flow, quantum sensing.

## Archetypes

### A1 — PID / State-space Control + LQR

$$u(t) = K_p e(t) + K_i \int_0^t e(\tau)\,d\tau + K_d \frac{de(t)}{dt}$$

$$\dot{\mathbf{x}} = A\mathbf{x} + B u + E w,\quad y = C\mathbf{x} + v$$

$$J = \int_0^\infty (\mathbf{x}^T Q \mathbf{x} + u^T R u)\,dt,\quad K = R^{-1} B^T P$$

$A_{cl}=A-BK$, stability iff $\Re\{\lambda_i(A_{cl})\}<0$; $T_s\approx4/(\zeta\omega_n)$, $M_p=\exp(-\pi\zeta/\sqrt{1-\zeta^2})$.

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $e$ | tracking error $r-y$ | $[y]$ | |
| $K_p$ | proportional gain | $[u]/[y]$ | raises $\omega_c$ |
| $K_i$ | integral gain | $[u]/([y]·s)$ | kills $e_{ss}$, risks windup |
| $K_d$ | derivative gain | $[u]·s/[y]$ | adds phase lead |
| $T_s$ | sample period | s | need $T_s < T_{set}/10$ |
| $Q,R$ | state/effort weights | $1/[x^2]$, $1/[u^2]$ | design knob |
| $PM,GM$ | phase/gain margin | deg, dB | robustness |

Sources: Ogata Ch.3,8; Åström & Murray Ch.3–6; `skills/axiomize/perspectives/control.md:1`.

### A2 — M/M/c Queue + Little's Law + Erlang-C

$$a = \lambda/\mu,\quad \rho = a/c = \lambda/(c\mu) < 1$$

$$C(c,a) = \frac{a^c/c!\cdot c/(c-a)}{\sum_{k=0}^{c-1} a^k/k! + a^c/c!\cdot c/(c-a)}$$

$$L = \lambda W,\quad E[W_q] = \frac{C(c,a)}{c\mu - \lambda},\quad P(W_q>t)=C(c,a)e^{-(c\mu-\lambda)t}$$

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $\lambda$ | arrival rate | jobs/s | Poisson if $C_a=1$ |
| $\mu$ | service rate per server | jobs/s | $1/\mu = E[S]$ |
| $c$ | servers | – | staffing decision |
| $\rho$ | utilization | – | need $<1$ |
| $W_q,W$ | wait in queue/system | s | $W$ includes service |

Dimensionless groups: $\rho$, $a$, $c_a^2$, $c_s^2$.

Sources: Gross–Thompson Ch.3–4; Hillier & Lieberman Ch.17; Ross Ch.8.

### A3 — Weibull Reliability + Block Diagrams

$$h(t)=\frac{\beta}{\eta}\left(\frac{t}{\eta}\right)^{\beta-1},\quad S(t)=\exp[-(t/\eta)^\beta]$$

$$MTTF = \eta\,\Gamma(1+1/\beta),\quad A = \frac{MTBF}{MTBF+MTTR}$$

$$R_{series}=\prod R_i,\quad R_{parallel}=1-\prod(1-R_i)$$

$$L(t_p)=\frac{c_p + c_f F(t_p)}{\int_0^{t_p} S(t)\,dt}$$

Optimum $t_p^*$ iff $\beta>1$ and $c_f\gg c_p$.

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $\beta$ | Weibull shape | – | drives policy |
| $\eta$ | scale (char. life) | h | $S(\eta)=e^{-1}$ |
| $h(t)$ | hazard rate | 1/time | $h\uparrow$ iff $\beta>1$ |
| $t_p$ | preventive age | h | decision |

Sources: Meeker & Escobar Ch.4; Modarres Ch.3,7; `perspectives/reliability.md:15`.

### A4 — LP / ILP + Dual & Shadow Prices

$$\max_{\mathbf{x}} c^T\mathbf{x}\ \text{s.t.}\ A\mathbf{x}\le \mathbf{b},\ \mathbf{x}\ge0$$

$$\min_{\mathbf{y}} \mathbf{b}^T\mathbf{y}\ \text{s.t.}\ A^T\mathbf{y}\ge c,\ \mathbf{y}\ge0$$

Weak duality $c^T\mathbf{x}\le \mathbf{b}^T\mathbf{y}$; strong $c^T\mathbf{x}^*=\mathbf{b}^T\mathbf{y}^*$.

Shadow price $y_i^* = \partial z^*/\partial b_i$.

| Symbol | Name | Unit | Notes |
|---|---|---|---|
| $\mathbf{x}$ | decision vector | $[x_j]$ | continuous (LP)/integer (ILP) |
| $c$ | objective coeff | $[z]/[x_j]$ | |
| $A,b$ | constraint matrix/RHS | $[b_i]/[x_j]$, $[b_i]$ | |
| $y^*$ | dual/shadow prices | $[z]/[b_i]$ | marginal value |

Sources: Bertsimas & Tsitsiklis Ch.4; Wolsey Ch.2.

## Lens-to-archetype mapping

| Archetype | Primary lens | Secondary |
|---|---|---|
| A1 Control | `control.md` | `optimization.md` + `stochastic.md` if $w,v$ large |
| A2 Queue | `stochastic.md` | `optimization.md` (staffing ILP) |
| A3 Reliability | `reliability.md` | `stochastic.md` + `optimization.md` |
| A4 LP/ILP | `optimization.md` | `stochastic.md` (demand uncertainty) |

## Worked mini-example

**Idea:** "Call center with $\lambda=60$/h, $\mu=20$/h, promise $E[W_q]\le2$ min — how many agents?"

- Deterministic fluid: $\lceil a\rceil =\lceil3\rceil=3$ (ignores randomness).
- Queue A2: $c=4\Rightarrow C(4,3)=0.509$, $E[W_q]=0.509/(80-60)=0.025$h=1.53 min ✓
- Optimization A4: $\min c$ s.t. $E[W_q]\le2$ min $\Rightarrow c^*=4$.
- Stochastic: MC $N=2e4$ confirms $P(W_q>5\text{ min})\approx9\%$ at $c=4$.

## Lens priorities

1. Control (when setpoint exists) 2. Optimization 3. Stochastic/Reliability 4. SPC

## Examples to imitate

- `examples/control-greenhouse.md` (thermal ODE)
- `examples/physics-oscillator.md` (deterministic + stochastic + control)
- `examples/coffee-shop-staffing.md` (Erlang-C + ILP)

## Tools pattern

```bash
python skills/axiomize/tools/validate.py --model queue --lam 60 --mu 20 --target-wait 2
# PID/LQR via solve_ivp + scipy.linalg.solve_continuous_are
# MC N>=1e4 OU wind, EWMA lambda=0.2
```

Order: dimension check → steady → stability → MC → sensitivity sweep.

## Domain gotchas

- Integrator windup when $|u|\ge u_{max}$
- Utilization cliff $E[W_q]\propto1/(1-\rho)$
- $\beta\le1$ policy flip (preventive wasteful)
- LP integrality lie at small $c$

## Typical falsifiers

- Step overshoot >30% despite $PM\ge45°$ (kills delay-free)
- $E[W_q]$ vs Erlang-C disagree >25% (kills Poisson)
- Failure ages reject Weibull ($p<0.05$)
