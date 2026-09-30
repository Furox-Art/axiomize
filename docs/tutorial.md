# Your First Axiomize Session (Beginner Walkthrough)

No math background required. This walks through what happens when you use the skill, and what to type.

## 1. Install (once)

Copy the skill folder into your agent's skills directory:

```bash
git clone https://github.com/Furox-Art/axiomize
cp -r axiomize/skills/axiomize ~/.config/opencode/skills/   # opencode
cp -r axiomize/skills/axiomize ~/.claude/skills/            # Claude Code
```

Restart your agent so it discovers the skill.

## 2. Ask anything

Type a real question in your own words:

> Model this idea mathematically: my gym keeps losing members after 3 months; how do I stop the churn?

The skill announces its recommended rigor level (**medium** unless the signals say otherwise)
and works through nine phases, Phase 0 to Phase 8. You will see, in order:

- **Phase 0, clarify** , it recommends a depth with one short reason, and asks a targeting question if your goal is vague ("do you want to PREDICT churn, DECIDE on actions, or CONTROL retention to a target?")
- **Phase 1, parse** , full system, state, goal, and horizon
- **Phase 2, decompose** , your idea split into sub-problems, each tagged flow / interaction / decision / uncertainty, with a coupling map
- **Phase 3, parameters** , every quantity that matters, with units and realistic ranges
- **Phase 4, assumptions** , each one tagged, with the consequence of it being violated
- **Phase 5, perspectives** , independent analyses from different mathematical angles (a probability view, an optimization view, ...)
- **Phase 6, compare** , the lenses scored against YOUR goal question, with the conditions under which each wins and one winner recommended
- **Phase 7, implement** , runnable Python with sanity checks that PASS or FAIL visibly
- **Phase 8, deliver** , plain-language summary first, then technical detail: uncertainty, sensitivity, and what future observation would falsify the model

The per-phase expectations for each depth are tabulated in
[rigor.md](https://github.com/Furox-Art/axiomize/blob/main/skills/axiomize/rigor.md).

## 3. Control the depth

| You say | You get |
|---------|---------|
| "just quickly" | **weak** , top parameters, plain words, short answer |
| *(nothing)* | **medium** , the balanced analysis |
| "this is for my thesis" | **strong** , independent verification, uncertainty intervals, reproducibility record |

The older names **basic**, **standard**, and **research** still work as aliases for weak,
medium, and strong. Change depth mid-session by saying "deeper" or "quicker".

## 4. Read the two most important parts

Every deliverable is layered, and you control how much detail you are shown:

1. **Plain-language summary** first. Start here.
2. **Technical detail** after it: equations, evidence, validation, uncertainty, and what
   would have to be observed for the model to be wrong.

Important conclusions carry a **high / medium / low confidence** label. Do not make a
large decision on a low-confidence conclusion.

## 5. Keep your archive

The skill records enough state to reproduce a session: problem definition, input data and
any cleaning applied, parameters and provenance, assumptions, candidate and selected
models, solver settings, random seeds, library versions, and validation results. Working
through the Python engine, that state is stored with `RunState`.

To keep an index of report files yourself, run the shipped tool in the directory holding
them:

```bash
axiomize-index-reports   # rebuilds reports/INDEX.md from reports/*.md
```

Next month you can ask "does this change my earlier barista report?" and point the agent at
your saved reports.

## 6. Give it data (optional but powerful)

Have a CSV of observations? The skill calibrates parameters from it instead of guessing:

> Here's monthly_signups.csv, fit the growth model to real numbers.

You get fitted values with parameter uncertainty and honest fit-quality scores. When the
same task is better served from the CLI:

```bash
axiomize-csv-check --data monthly_signups.csv --time-col time --value-col value
axiomize fit --data monthly_signups.csv
```

## Where to go next

- [Quickstart](quickstart.md) for the Python and CLI paths with real output
- [Integrations](integrations.md) for MCP, REST, and CLI surfaces
- [Example gallery](example-gallery.md) for full worked problems
- [Security](security.md) for what is and is not a trust boundary

## A note on agent spending

Extra subagents, repeated alternative-method runs, and paid provider calls are off by
default. Inspect what the agent is permitted to do with `axiomize policy`; each guarded
action needs an explicit approval.
