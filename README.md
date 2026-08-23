# Axiomize

**Turn any idea into a rigorous mathematical model.** An [Agent Skill](https://github.com/anthropics/skills) for AI coding agents (Claude Code, opencode, Cursor, ...) that takes a vague idea and returns formal mathematics: decomposed sub-problems, active parameter tables, models from **multiple perspectives**, a comparison, runnable validation code — and what would falsify the model.

## Why

LLMs answer "how do I model X?" with a single plausible guess. Real modeling discipline is different: you decompose, extract parameters with units, attack from several mathematical lenses, compare honestly, and state falsifiable predictions. This skill enforces that discipline.

## The workflow

```
idea ──▶ 1. Parse (system / state / goal / horizon)
     ──▶ 2. Decompose into sub-problems (flow · interaction · decision · uncertainty)
     ──▶ 3. Parameter table   (symbol, unit, range, sensitivity)
     ──▶ 4. Assumptions       (each with its violation consequence)
     ──▶ 5. Multi-perspective modeling:
             deterministic · stochastic · optimization · agent-based
     ──▶ 6. Compare & recommend
     ──▶ 7. Implement in Python + validate + sensitivity sweep
     ──▶ 8. Falsifiability    (what observation kills this model?)
```

## Install

Copy `skills/axiomize/` into your agent's skills directory:

```bash
# Claude Code
git clone https://github.com/<you>/Axiomize
cp -r Axiomize/skills/axiomize ~/.claude/skills/

# opencode
cp -r Axiomize/skills/axiomize ~/.config/opencode/skills/
```

Then just ask your agent:

> "Model this idea mathematically: a coffee shop wants to decide how many baristas to schedule"

## Example output

Full worked example: [`examples/epidemic-sir.md`](examples/epidemic-sir.md) — "a disease appears in a city of 1M" becomes an SIR system with R₀ threshold analysis, a stochastic fade-out check via Gillespie simulation, a policy optimization layer, and explicit falsification criteria.

Validate the reference implementation:

```bash
pip install numpy scipy
python tools/validate.py --model sir --beta 0.3 --gamma 0.1 --sweep
```

## Repository layout

```
skills/axiomize/
├── SKILL.md              # the 8-phase workflow (the brain)
├── perspectives/         # one file per mathematical lens
│   ├── deterministic.md  # ODEs, difference equations, thresholds
│   ├── stochastic.md     # Markov chains, Monte Carlo, risk
│   ├── optimization.md   # objectives, constraints, equilibria
│   └── agent-based.md    # local rules → emergence
└── templates/
    ├── assumptions.md    # checklist with violation consequences
    └── parameters.md     # active parameter table contract

examples/                 # full end-to-end case studies
tools/validate.py         # consistency checks & sensitivity sweeps
```

## Design principles

1. **No symbol undefined** — every equation comes with every term defined.
2. **Units or it didn't happen** — parameters carry units; dimensionless is a deliberate choice.
3. **Two lenses minimum** — one perspective is a guess; two are an argument.
4. **Assumptions have consequences** — if you can't say what breaks when it's violated, you haven't examined it.
5. **Falsifiability required** — a model that can't be wrong isn't a model.

## Contributing

Perspective files follow a fixed contract: *when applicable → model forms → standard analysis output → strengths/blind spots*. PRs adding lenses (control theory, information-theoretic, thermodynamic analogies...) are welcome.

## License

MIT
