# Engineering Pack

Curated pointers for control, queueing, reliability, optimization.

## Scope

In: feedback control, M/M/c queues, Weibull lifetimes, LP/ILP, SPC. Out: FEA/CFD beyond lumped, strategic pricing.

## Archetypes

### 1. PID Control

$$u(t)=K_p e(t)+K_i\int e+K_d de/dt,\quad \dot x=Ax+Bu+Ew,\ y=Cx+v$$

$K_p$ [[u]/[e]], $T_s$ [s], $w$ disturbance, $v$ noise. LQR cost $J=\int(x^TQx+u^TRu)dt$.

### 2. M/M/c Queue

$$\rho=\lambda/(c\mu)<1,\quad C(c,\rho)=\frac{(c\rho)^c/c!}{(c\rho)^c/c!+(1-\rho)\sum_{k=0}^{c-1}(c\rho)^k/k!}$$

$$E[W_q]=C(c,\rho)/(c\mu-\lambda),\quad L=\lambda W$$

$\lambda,\mu$ [jobs/s], $c$ [–].

### 3. Weibull Reliability

$$h(t)=\beta/\eta (t/\eta)^{\beta-1},\ S(t)=\exp(-(t/\eta)^\beta),\ R_{series}=\prod R_i$$

$\beta$ [–], $\eta$ [h], $A=MTBF/(MTBF+MTTR)$.

### 4. LP/ILP

$$\max c^Tx\ \text{s.t. } Ax\le b,\ x\ge0$$

Dual shadow price $y^*=\partial opt/\partial b$.

## Lens priorities

1. Control (when setpoint exists) 2. Optimization 3. Stochastic/Reliability 4. SPC

## Gotchas

- Integrator windup when |u|>u_max
- Utilization ρ→1 nonlinear cliff
- β≤1 flips maintenance policy
