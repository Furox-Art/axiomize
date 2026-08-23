# Axiomize

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-informational)
![CI](https://github.com/Furox88/axiomize/actions/workflows/ci.yml/badge.svg)

**Turn any idea into a rigorous mathematical model.** An [Agent Skill](https://github.com/anthropics/skills) for AI coding agents (Claude Code, opencode, Cursor, ...) that takes a vague idea and returns formal mathematics: decomposed sub-problems, active parameter tables, models from **six perspectives**, an honest comparison, runnable validation code — and what would falsify the model.

## Why

LLMs answer "how do I model X?" with a single plausible guess. Real modeling discipline is different: you decompose, extract parameters with units, attack from several mathematical lenses, compare honestly, and state falsifiable predictions. This skill enforces that discipline.

## The workflow

```
idea ──▶ 1. Parse (system / state / goal / horizon)
     ──▶ 2. Decompose into sub-problems (flow · interaction · decision · uncertainty)
     ──▶ 3. Parameter table   (symbol, unit, range, sensitivity)
     ──▶ 4. Assumptions       (each with its violation consequence)
     ──▶ 5. Multi-perspective modeling:
              deterministic · stochastic · optimization ·
              agent-based · network · control
     ──▶ 6. Compare & recommend
     ──▶ 7. Implement in Python + validate + sensitivity sweep
     ──▶ 8. Falsifiability    (what observation kills this model?)
```

## Install

Copy `skills/axiomize/` into your agent's skills directory:

```bash
# Claude Code
git clone https://github.com/Furox88/axiomize
cp -r axiomize/skills/axiomize ~/.claude/skills/

# opencode
cp -r axiomize/skills/axiomize ~/.config/opencode/skills/
```

Then just ask your agent:

> "Model this idea mathematically: a coffee shop wants to decide how many baristas to schedule"

## The six lenses

| Lens | Answers | Signature tool |
|------|---------|----------------|
| [Deterministic](skills/axiomize/perspectives/deterministic.md) | trends, equilibria, thresholds | ODEs, fixed-point & stability analysis |
| [Stochastic](skills/axiomize/perspectives/stochastic.md) | risk, rare events, fade-out | Markov chains, Monte Carlo |
| [Optimization](skills/axiomize/perspectives/optimization.md) | best decision under constraints | LP/NLP/ILP, shadow prices |
| [Agent-based](skills/axiomize/perspectives/agent-based.md) | emergence from heterogeneous local rules | parameter sweeps over N-agent sims |
| [Network](skills/axiomize/perspectives/network.md) | who-connects-to-whom effects | centrality, R_eff = R₀·⟨k²⟩/⟨k⟩ |
| [Control](skills/axiomize/perspectives/control.md) | how to steer & regulate | feedback laws, stability margins |

Lenses **compose**: e.g., queueing theory computes the wait, an integer program schedules the staff ([example](examples/coffee-shop-staffing.md)).

## Worked examples

| Idea | Becomes | File |
|------|---------|------|
| "A disease appears in a city of 1M" | SIR + R₀ threshold + stochastic fade-out check | [epidemic-sir.md](examples/epidemic-sir.md) |
| "How much stock should a retailer hold with uncertain demand?" | (s,Q) policy via newsvendor + safety stock + control view | [supply-chain-inventory.md](examples/supply-chain-inventory.md) |
| "How many baristas per hour?" | Erlang-C wait cliff inside a staffing ILP | [coffee-shop-staffing.md](examples/coffee-shop-staffing.md) |

## Validate the reference implementation

```bash
pip install numpy scipy

# deterministic SIR vs final-size theory + sensitivity sweep
python tools/validate.py --model sir --beta 0.3 --gamma 0.1 --sweep

# exact CTMC simulation -> extinction probability matches (1/(1+R0))^I0
python tools/validate.py --model gillespie --N 10000 --I0 1

# M/M/c staffing cliff -> minimal baristas for a 3-minute wait promise
python tools/validate.py --model queue --lam 60 --mu 20 --target-wait 3
```

Each mode prints internal-consistency checks (conservation laws, bounds, monotonicity, theory match) — the same checks Phase 7 demands from every model the skill produces.

## Repository layout

```
skills/axiomize/
├── SKILL.md              # the 8-phase workflow (the brain)
├── perspectives/         # one file per mathematical lens
│   ├── deterministic.md  # ODEs, difference equations, thresholds
│   ├── stochastic.md     # Markov chains, Monte Carlo, risk
│   ├── optimization.md   # objectives, constraints, equilibria
│   ├── agent-based.md    # local rules → emergence
│   ├── network.md        # graphs, centrality, dynamics on networks
│   └── control.md        # feedback, regulation, steering
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

See [CONTRIBUTING.md](CONTRIBUTING.md). Perspective files follow a fixed contract; PRs adding lenses (information-theoretic, thermodynamic analogies, game-theoretic...) are welcome.

## License

MIT
