# Perspective: Statistical Process Control (Is This Normal or a Signal?)

Use when the question is not "what will happen?" but **"has something shifted?"**: monitoring a running process for change, manufacturing defects, service KPIs, website latency, fill volumes, error rates. Complements [control](control.md) (regulation): this lens DETECTS change rather than correcting it.

## When Applicable

- You observe a stream of measurements `x_t` (value at sample t, in native units such as mm, ms, %, defects per batch) from a process assumed stable except for possible shifts
- Phase 2 found `uncertainty` (common-cause noise around a stable mean) AND the user's goal contains monitor / detect / alarm / has-it-changed / is-this-out-of-spec
- The decision is binary per sample: keep running vs investigate, not "what value next?" ([stochastic](stochastic.md) answers that)
- No actuator is being designed; if you must correct, hand off to [control](control.md)

## Model Forms

### Analysis ladder (cheap → expensive)

Shewhart chart (cheapest, detects large shifts fast) → EWMA/CUSUM (moderate, small persistent shifts) → capability study (needs more baseline data, asks a different question: can we meet spec at all?)

### Shewhart variables chart (X-bar + R), subgroup size n

```
X-bar chart:  CL = x-doublebar (grand mean of subgroup means, units of x)
              UCL/LCL = x-doublebar ± A2 * R-bar     (A2 = table constant for n)
R chart:      CL = R-bar (mean subgroup range, units of x)
              UCL/LCL = D4*R-bar / D3*R-bar          (D3, D4 table constants for n)
```

Baseline: estimate `x-doublebar`, `R-bar` from m ≥ 20-25 in-control subgroups. Limits at ±3 standard errors; signals on any point outside.

### Memory charts for small persistent shifts

```
EWMA:   z_t = lambda*x_t + (1-lambda)*z_{t-1},   z_0 = mu_0
        limits: mu_0 ± L*sigma*sqrt(lambda/(2-lambda) * (1-(1-lambda)^(2t)))
CUSUM:  S+_t = max(0, S+_{t-1} + (x_t - mu_0 - K)/sigma),  signal when S+_t >= H
```

where `lambda` = smoothing weight in (0, 1] (dimensionless; typical 0.1-0.3), `L` = limit width multiplier (~3), `mu_0` = target/baseline mean (units of x), `sigma` = in-control standard deviation (units of x), `K` = allowance ≈ delta/2 for shift delta in sigma-units, `H` = decision threshold (dimensionless, typical h = 4-5). Both outperform Shewhart when shifts are ≤ 1.5 sigma.

### Capability indices (vs specification limits)

```
Cp  = (USL - LSL) / (6*sigma)                       potential spread fit
Cpk = min((USL - mu)/(3*sigma), (mu - LSL)/(3*sigma))  spread + centering
```

`USL`/`LSL` = upper/lower specification limits (units of x), `mu`, `sigma` = process mean and WITHIN-process std dev (units of x); indices are dimensionless. Verdict thresholds: Cpk < 1.00 incapable; 1.00-1.33 marginal; ≥ 1.33 capable.

### Attribute chart (p-chart) for defect rates

```
CL = p-bar (baseline defect proportion, dimensionless)
UCL/LCL = p-bar ± 3*sqrt(p-bar*(1-p-bar)/n_t)
```

`n_t` = items inspected at period t (units: count); use only when n*p-bar ≥ 5, else limits are invalid.

## Standard Analysis Output

1. Chart type choice justified: subgroups exist and shifts > 1.5 sigma expected → Shewhart; persistent small drift suspected or individual measurements → EWMA/CUSUM; count data → p-chart
2. Center line + limits with their estimation basis: baseline window length (e.g., 25 subgroups × n = 5), stated as in-control assumption with dates/range of data
3. Detected out-of-control points, each tagged with the rule fired (Western Electric): W1 = one point beyond 3 sigma; W2 = 2 of 3 consecutive beyond 2 sigma, same side; W3 = 4 of 5 consecutive beyond 1 sigma, same side; W4 = 8 consecutive on one side of the center line
4. Capability verdict vs spec limits: Cp, Cpk values with the threshold table above, plus estimated percent-out-of-spec (from normal fit)
5. False-alarm budget: in-control ARL (average run length, unit = samples) ≈ 370 per rule W1 for 3-sigma Shewhart under independence; report detection ARL at the shift size of interest (e.g., ARL ≈ 10 samples for a 1-sigma shift via CUSUM with K = 0.5, H = 4.5); flag if autocorrelation present, recompute limits on residuals or widen them

## Strengths / Blind Spots

- (+) Separates common-cause noise from special-cause signals cheaply, in real time, with an explicit and tunable false-alarm rate; no causal model needed
- (+) Memory charts give early warning for slow drifts that point rules miss entirely
- (-) Requires in-control baseline data, a contaminated baseline bakes the failure into the limits; assumes independence within limits (autocorrelation inflates alarms badly); blind to novel failure modes never seen in baseline; detects THAT something changed, never WHAT changed

---

**See also:** [control](control.md) (once detected, steer back, this lens finds the shift, control theory removes it) and [stochastic](stochastic.md) (the noise model these limits are built from).
