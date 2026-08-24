# Perspective: Spatial Statistics (Where Matters)

Use when **location itself carries information**: observations at nearby sites are correlated, so methods that assume independent samples are silently wrong. This lens asks WHERE patterns cluster — and whether the clustering is real or noise.

## When Applicable

- Data arrive tagged with coordinates (points: incidents, sensors, cases) or polygons (census tracts, districts, grid cells) AND nearby values move together — Tobler's first law holds
- Phase 2 found `interaction` through geographic space plus `uncertainty` in measurements; questions like: is this pattern clustered or random? where exactly are the hotspots? what value should we expect at an unmeasured site?
- Typical subjects: crime/incident hotspots, environmental monitoring networks, store catchments and demand fields, disease maps
- This lens answers what others cannot: which locations matter, whether concentration exceeds chance, and how confident any interpolated value is — none of which a location-blind regression or average can say

## Model Forms

### Premise: Tobler's first law as a modeling commitment

Nearby observations are more alike than distant ones: correlation ρ(d) decays with separation distance d (d in meters or km, ρ dimensionless). Everything downstream encodes this through either a **weights matrix** (areal data), a **covariance function** (point samples), or a **null process** (event patterns).

Analysis ladder (cheap → expensive):
1. Global autocorrelation test (one number: is clustering present?)
2. Local indicators (where are the clusters?)
3. Kernel density (smoothed intensity map from points alone)
4. Kriging / Gaussian process (best estimates + full uncertainty, needs variogram fitting)

### Global autocorrelation: Moran's I

```
I = (n / S0) * sum_i sum_j w_ij (x_i - xbar)(x_j - xbar) / sum_i (x_i - xbar)^2
```

where `n` = number of areal units (count, dimensionless), `x_i` = attribute value at unit i (native units, e.g., cases per 10k residents), `xbar` = mean of x (units of x), `w_ij` = entry i,j of the spatial weights matrix W (dimensionless; nonzero only for neighbor pairs), `S0 = sum_i sum_j w_ij` (dimensionless). I ≈ [-1, +1]; expectation under no clustering is `E[I] = -1/(n-1)`. Significance by **permutation**: reshuffle x across locations B ≥ 999 times and compare.

### Local indicators (LISA): locating the clusters

Local Moran statistic for each unit i:

```
I_i = z_i * sum_j w_ij z_j,   z_i = (x_i - xbar) / s
```

where `z_i` = standardized value at unit i (dimensionless), `s` = sample standard deviation of x (units of x). Permutation significance at level alpha flags four regimes: **high–high** (hotspot: large z_i surrounded by large z_j), **low–low** (coldspot), high–low / low–high (spatial outliers). Sum of all I_i relates directly to global I.

### Kernel density estimation: intensity from raw points

```
lambda_hat(s) = (1/h^2) * sum_i K( ||s - s_i|| / h )
```

where `s` = query location (coordinates, km), `s_i` = observed event location i, `h` = bandwidth (km; controls smoothness — small h reproduces points, large h blurs everything), `K(u)` = bivariate kernel integrating to 1 over 2D (e.g., Gaussian), `lambda_hat` = estimated event intensity (events/km²). Choose h by cross-validation or a stated rule; report it — the map is only as honest as h.

### Kriging / Gaussian process: interpolation with honest uncertainty

Model the field `Z(s)` as a Gaussian process with mean m(s) and covariance `C(d)` (C in units of x², d = separation in km), typically parameterized by a variogram:

```
gamma(d) = nugget tau^2 + sill sigma^2 * (1 - exp(-d/range a))
```

with `tau^2` = nugget: sub-grid/measurement variance as d → 0 (x²), `sigma^2` = partial sill (variance contributed by spatially structured process; total sill = tau^2 + sigma^2), `a` = correlation range parameter (km; practical correlation extends to ≈ 3a for this exponential model). Prediction at unsampled s0: weighted average `Z_hat(s0) = sum_i lambda_i Z(s_i)` with weights lambda_i solving the kriging system; kriging variance (x²) yields sqrt → standard error map in units of x.

### Point-process view: clustered vs chance

Null hypothesis of complete spatial randomness: homogeneous Poisson process, constant intensity `lambda` (events/km²). Diagnostic: Ripley's `K(r)` = expected number of further events within radius r of a typical event, divided by lambda (r in km; under the null `K(r) = pi r^2`). Empirical `K(r) > pi r^2` → clustering at that scale; `<` → inhibition. Fit clustered alternatives (e.g., Neyman–Scott) only if the null is rejected.

## Standard Analysis Output

1. Weights-matrix (or bandwidth) justification, since ALL results depend on it: distance band delta (km) vs k-nearest-neighbors (k count), why this choice (no disconnected "islands", plausible interaction reach), plus sensitivity check against at least one alternative specification
2. Global autocorrelation statistic (Moran's I, dimensionless) with permutation p-value (state B, e.g., B = 999; pseudo-p = (rank+1)/(B+1))
3. Hotspot map description: significant high–high zones flagged at stated alpha, coldspots and spatial outliers named separately — not just "the north is bad"
4. Interpolated surface WITH uncertainty shading: predicted field in units of x alongside standard-error map; wide-error regions must be visible, not hidden
5. MAUP caveat: results depend on zone scale and zonation (Modifiable Areal Unit Problem); report key statistics at two or more aggregation levels, or state explicitly that conclusions are scale-bound

## Strengths / Blind Spots

- (+) Prevents treating location-independent methods' outputs as valid: spatial dependence inflates effective sample size claims and shrinks naive confidence intervals falsely; this lens catches it before the wrong decision ships
- (+) Quantifies WHERE interventions should concentrate — actionable targets (patrol here, monitor these wells), not just aggregate effects
- (+) Kriging delivers predictions whose uncertainty is part of the answer, supporting risk-based decisions
- (-) Results sensitive to weights-matrix and aggregation choices `[S]` — same data, different W or zoning, different hotspots; always show the sensitivity check
- (-) Ecological fallacy: cluster-level findings do NOT transfer to individuals inside the cluster; aggregated zones hide within-zone heterogeneity
- (-) Needs enough points/zones: sparse data makes permutation tests powerless and kriging variance explode near edges; boundary effects bias edge estimates

---

**See also:** [network](network.md) (discrete structure counterpart — who-connects-to-whom vs who-is-near-whom), [information-theory](information-theory.md) (sensor placement uses spatial covariance directly), worked example [sensor placement](../../../examples/sensor-placement.md).
