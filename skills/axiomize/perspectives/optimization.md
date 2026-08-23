# Perspective: Optimization & Equilibrium (Decisions Under Constraints)

Use when someone is **choosing** — allocating resources, designing a policy, setting prices — or when multiple actors' choices interact.

## When Applicable

- Phase 2 classified the core as `decision`
- The user's goal contains words like: best, optimal, minimum cost, maximum profit, allocate, schedule, design
- Multiple self-interested parties → game-theoretic equilibrium questions

## Model Forms

### Constrained optimization
Formulate explicitly:
```
maximize    f(x)          ← objective, with units!
subject to  g_i(x) ≤ b_i  ← every real constraint listed
            x ∈ X         ← domain (integer? continuous? nonnegative?)
```
Checklist:
1. Decision variables: what CAN be chosen? (with units)
2. Objective: ONE scalar. If multiple objectives exist → weighted sum (state weights) or Pareto analysis.
3. Constraints: physical, budgetary, logical. Missing constraints produce absurd optima — always sanity-check the solution.
4. Solver choice: linear → `scipy.optimize.linprog`; smooth nonlinear → `minimize`; integer/mixed → `milp`.

### Dynamic optimization
Choices over time: optimal control (` Pontryagin`) or dynamic programming (Bellman equation: `V(s) = max_a [r(s,a) + γ·V(s')]`). Use when today's choice changes tomorrow's options.

### Game theory / equilibrium
Multiple actors, each optimizing against others:
1. Players, strategies, payoffs per combination.
2. Find Nash equilibria (best-response intersections).
3. KEY QUESTION: does equilibrium hurt everyone? (tragedy of the commons / price war) — compare Nash payoff vs cooperative optimum.

## Standard Analysis Output

1. Formal problem statement (variables, objective, constraints — all with units)
2. Optimal solution + active constraints (which constraints bind?)
3. Shadow prices / dual values: what is one more unit of each scarce resource worth?
4. Sensitivity: how much can parameters move before the solution changes?
5. For games: equilibria + welfare comparison

## Strengths / Blind Spots

- (+) Directly answers "what should we do"; shadow prices quantify trade-offs
- (-) Assumes rationality and known objectives; optimal-for-model ≠ good-for-reality; garbage objective = garbage decision

---

**See also:** worked examples — [retail inventory](../../examples/supply-chain-inventory.md) ((s,Q) policy), [coffee shop](../../examples/coffee-shop-staffing.md) (staffing ILP fed by Erlang-C waits — lenses composing). Templates: [parameter table](../templates/parameters.md)
