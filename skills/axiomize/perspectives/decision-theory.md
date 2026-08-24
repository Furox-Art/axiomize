# Perspective: Decision Theory (Choosing Under Deep Uncertainty)

Use when someone must **commit now, once, irreversibly** — but the probabilities a clean expected-value calculation would need are unknown or disputed. Ambiguity dominates, not just risk.

## When Applicable

- Phase 2 classified the core as `decision` AND `uncertainty`, with probabilities that are contested, unavailable, or meaningless (one-off events)
- One-shot irreversible choices: infrastructure bets (build the plant? the levee?), career pivots, pandemic responses, launch/cancel calls
- Stakeholders argue about likelihoods ("how bad could it get?") more than about payoffs
- Distinct from [optimization](optimization.md): there probabilities are known model inputs; here ambiguity itself is the problem
- Questions only this lens answers: which option is least-regrettable across plausible worlds? Which choice survives the worst credible state? Is it worth buying more analysis before deciding?

## Model Forms

Build the skeleton first — every rule below consumes it:
```
Options   A = {a_1 … a_m}   ← actions genuinely on the table, incl. "do nothing" and "delay"
States    S = {s_1 … s_n}   ← mutually exclusive worlds (3–5; add "worst plausible", not just base case)
Payoffs   x_ij              ← outcome of option a_i in state s_j, ONE unit throughout (USD, persons, QALY)
```

### Expected utility (requires stated probabilities)
```
EU(a_i) = Σ_j p_j · u(x_ij)
```
where p_j = probability of state s_j (unitless, Σp_j = 1) and u(·) = utility mapping payoff to desirability — linear means risk-neutral; concave (e.g. u(x) = ln x) means risk-averse. State the u AND whose utility it encodes. Choose argmax_i EU(a_i).

### Maximin and Savage minimax regret (no probabilities needed)
- Maximin: choose argmax_i min_j x_ij — the best worst-case payoff. Deliberately pessimistic.
- Regret matrix: R_ij = max_k x_kj − x_ij (same units as payoff: what you lose versus the best move available in world s_j). Minimax regret: choose argmin_i max_j R_ij. Softer than maximin and usually closer to how people actually feel about irreversible choices.

### Minimax loss
If entries are costs/damages L_ij rather than gains, choose argmin_i max_j L_ij.

### Info-gap / robust-satisficing
Treat nominal payoffs as possibly wrong by an unknown horizon α (same units as payoff). Pick the option maximizing the horizon α\* it tolerates while still meeting the critical requirement r_c (e.g. "net position ≥ 0 USD"); report the robustness curve α\*(r_c). Use when even probability *ranges* are unknowable.

### Scenario-weighted payoffs
Too many states? Collapse to 3–5 named scenarios with weights w_j (unitless, Σw_j = 1) and compute SW(a_i) = Σ_j w_j · x_ij. This IS expected utility with hand-set probabilities — label it as such and record who set the weights.

### Value of information — buy more analysis, or decide?
```
EVPI = Σ_j p_j · max_i x_ij  −  max_i Σ_j p_j · x_ij
```
expected payoff if clairvoyant (state s_j revealed before choosing) minus expected payoff of the best single action; same units as payoff. Perfect information is worth **at most** EVPI, so any study, survey, pilot, or delay is bounded by it. If EVPI < cost of learning (USD, months), stop analyzing and commit.

Analysis ladder (cheap → expensive):
1. Payoff matrix + dominance checks — free; always do
2. Full criterion table (all rules above) — minutes
3. Sweep weights w_j / p_j across their contested ranges; find flip points
4. Robustness curves α\*(r_c) or Monte Carlo across scenario ensembles — hours
5. Commission information up to EVPI − cost; beyond that, decide

## Standard Analysis Output

1. Options × states × payoff matrix, units on every entry, source class per row/column (`lit.` / `data` / `est.` / `[S]`)
2. Criterion-by-criterion recommendation table — disagreements between criteria are findings, not noise:

| Criterion           | Winning option | Requires                  |
|---------------------|----------------|---------------------------|
| Expected utility    | argmax EU      | agreed p_j, stated u      |
| Maximin             |                | nothing                   |
| Minimax regret      |                | nothing                   |
| Robust-satisficing  |                | chosen r_c                |

3. Dominance checks: delete any option worse than another in every state; flag any never-worse (weakly dominant) option explicitly
4. EVPI statement, verbatim form: "Perfect information is worth at most X<unit> — stop analyzing past that."
5. Robustness note: which recommendation survives the worst plausible states, and which flips only under weights no stakeholder actually holds

## Strengths / Blind Spots

- (+) Honest structure exactly when probabilities are contested; makes disagreement about weights explicit in a column where it can be argued, instead of hidden inside "reasonable assumptions"
- (+) Prices catastrophe-avoidance that expected value averages away; regret framing matches how irreversible losses are actually felt
- (-) Payoff matrices are `[S]` speculation dressed in tables — tabular precision ≠ epistemic precision; sweep every guessed cell
- (-) Choosing the criterion is itself a value judgment (maximin = extreme risk aversion; EU = whose utility?) — say whose values each recommendation serves
- (-) The state list is never exhaustive; the world left out of S is the one that hurts (pair with [stochastic](stochastic.md) for rare-event tails)

---

**See also:** [optimization](optimization.md) (risk-neutral special case with known probabilities), [stochastic](stochastic.md) (repeated events where frequencies exist), [information-theory](information-theory.md) (EVPI connection — information content vs. decision value)
