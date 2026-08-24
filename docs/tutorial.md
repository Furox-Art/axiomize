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

The skill announces its rigor level (**standard** unless you say otherwise) and starts an 8-phase workflow. You will see, in order:

- **Parse** — it restates your idea and asks a targeting question if your goal is vague ("do you want to PREDICT churn, DECIDE on actions, or CONTROL retention to a target?")
- **Decompose** — your idea split into 3–7 sub-problems, each tagged flow / interaction / decision / uncertainty, with a coupling diagram
- **Parameter table** — every quantity that matters, with units and realistic ranges
- **Assumptions** — each one tagged Established / Reasonable / Speculative, with what breaks if it's wrong
- **Multiple models** — independent analyses from different mathematical angles (a probability view, an optimization view, ...)
- **Comparison table** — the lenses scored against YOUR goal question; one winner recommended
- **Code + validation** — runnable Python with sanity checks that PASS or FAIL visibly
- **Falsifiability** — what future observation would prove this model wrong

## 3. Control the depth

| You say | You get |
|---------|---------|
| "just quickly" | basic — top parameters, plain words, 5-minute answer |
| *(nothing)* | standard — the full discipline |
| "this is for my thesis" | research — model criticism, uncertainty intervals, reproducibility notes |

Change anytime mid-session by saying **deeper** or **quicker**.

## 4. Read the two most important parts

Every report has:

1. **Plain-language summary** at the top — ≤ 5 sentences anyone can follow. Start here.
2. **Confidence ledger** near the bottom — every claim tagged established / assumption / speculation. Never trust a speculation-tagged claim for a big decision.

## 5. Keep your archive

The session saves `reports/YYYY-MM-DD-your-topic.md` and maintains an index. Next month, ask "does this change my earlier barista report?" — the skill cross-references your own history.

## 6. Give it data (optional but powerful)

Have a CSV of observations? The skill calibrates parameters from it instead of guessing:

> Here's monthly_signups.csv — fit the growth model to real numbers.

You get fitted values WITH confidence intervals and honest fit-quality scores.
