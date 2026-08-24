# Perspective: Information Theory (What Can Be Known)

Use when the binding constraint is **information, not physics**: channel capacity, data compression, experiment design, privacy leakage, feature relevance, model complexity budget.

## When Applicable

- Questions of the form "how much can we know / transmit / hide / distinguish?"
- Choosing measurements: which observation reduces uncertainty about the state the most?
- Comparing models or explanations: which description compresses reality better? (MDL principle)
- Phase 3 sensitivity is high precisely because data are scarce — quantify that scarcity

## Model Forms

1. **Entropy & distributions:** H(X) = −Σ p log p (bits) — variability of a source; conditional entropy H(X|Y) — what remains unknown after seeing Y.
2. **Mutual information:** I(X;Y) = H(X) − H(X|Y) — how many bits an observation carries about the state. Use for: sensor placement (maximize I), feature selection (rank by I with target), privacy budgets (cap I about sensitive attribute).
3. **Channel capacity:** C = max_{p(x)} I(X;Y) — the hard ceiling on reliable communication/compression rates; Shannon source coding: cannot compress below entropy.
4. **Model comparison as coding:** description length L(model) + L(data|model); MDL/AIC/BIC are all entropy-flavored — connects directly to [rigor ladder](../rigor.md) research tier.

## Standard Analysis Output

1. Entropy table of key variables (bits, from stated or estimated distributions — flag estimates)
2. Ranked information gains for candidate observations/features/sensors
3. Capacity/limit statement where relevant ("this telemetry channel caps at X bits/day ⇒ state estimation error ≥ Y")
4. Redundancy check: correlated measurements share information — report joint I, not naive sums
5. Compression/model-size verdict under MDL

## Strengths / Blind Spots

- (+) Universal currency across domains; hard limits instead of engineering guesses; exposes when more data cannot help
- (-) Needs distributions to compute anything (estimation error compounds); says nothing about semantics/value of information; assumes the probabilistic model itself

---

**See also:** sharpens [stochastic](stochastic.md) (entropy justifies distribution choices) · feeds [causal-inference](causal-inference.md) experiment design (which intervention reveals most bits) · research-tier AIC/BIC comparisons in Phase 6 are this lens in disguise
