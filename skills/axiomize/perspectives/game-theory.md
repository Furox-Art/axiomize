# Perspective: Game Theory (Strategic Interaction)

Use when outcomes depend on **mutually anticipating choices**: pricing against competitors, negotiation, auctions, standard-setting, commons management. Distinct from [optimization](optimization.md): there, the environment is fixed; here, the environment is other optimizers.

## When Applicable

- Phase 2 found `decision` AND at least two decision-makers whose best choice depends on the others'
- The word "if they think we'll..." appears in reasoning, that's a game
- Commons/toll/overuse questions: individually rational, collectively harmful

## Model Forms

1. **Players, strategies, payoffs:** write the normal form (matrix for small games) or type space (incomplete info). Payoffs must carry units.
2. **Solution concepts, cheapest first:**
   - Dominant-strategy elimination, rare but bulletproof when present
   - Nash equilibrium (pure; mixed if none pure), best-response fixed points
   - Subgame-perfect Nash, when moves are sequential (solve by backward induction)
   - Mechanism design variant: choose the RULES so the desired outcome becomes an equilibrium
3. **Repeated interaction:** one-shot vs infinitely repeated changes everything, cooperation sustainable iff discount factor δ ≥ threshold from payoff spread.
4. **Equilibrium selection honesty:** multiple equilibria? Say which and why (focal, risk-dominant, evolutionary stable).

## Standard Analysis Output

1. Formal game statement (players/strategies/payoffs with units)
2. All equilibria + which refinement selects among them
3. **Welfare comparison:** equilibrium total payoff vs cooperative optimum, quantify the gap (price of anarchy)
4. Comparative statics: what parameter change dissolves the dilemma?
5. Mechanism suggestion when the equilibrium hurts everyone: change who moves first, information visibility, or side-payments

## Strengths / Blind Spots

- (+) Predicts outcomes of strategic reaction that single-actor optimization cannot see; quantifies exactly why collective action fails
- (-) Assumes rationality and common knowledge of it; equilibrium ≠ dynamics (how do players get there?); payoff functions often guessed, treat as `[S]` assumptions

---

**See also:** extends [optimization](optimization.md)'s equilibria section · complements [agent-based](agent-based.md) (ABM tests whether boundedly-rational agents actually reach the equilibrium) · worked example: [café pricing war](../../../examples/cafe-pricing-war.md)
