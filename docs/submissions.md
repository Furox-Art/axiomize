# Registry Submission Kit

Ready-to-paste entries for external skill registries and communities. Facts reflect axiomize v1.2.0: twelve lenses, 30 archetypes, 11 worked examples, three rigor tiers, parallel subagent dispatch, bundled calibration tools, MIT license.

## awesome-list PR entry

```markdown
- [axiomize](https://github.com/Furox-Art/axiomize) - Agent Skill that turns vague ideas into rigorous, falsifiable mathematical models

Axiomize installs into Claude Code, opencode, or Cursor and runs an eight-phase workflow that decomposes an idea, extracts parameters with units, attacks it through up to twelve mathematical lenses, and returns a recommended model with runnable validation code and explicit falsifiers. It recognizes 30 canonical archetypes (SIR, newsvendor, M/M/c), offers three rigor tiers from quick sketch to thesis-grade analysis, includes bundled calibration tools, parallel subagent lens dispatch, 11 worked examples, and ships under the MIT license.
```

## Reddit post (r/ClaudeAI style)

Title: **I gave Claude Code one sentence about a disease outbreak - it returned an SIR model with an R0 threshold and instructions for proving itself wrong**

```markdown
I typed "model this idea mathematically: a disease appears in a city of 1M" into Claude Code with my skill installed. Instead of the usual confident paragraph, I got an SIR system with every term defined, a parameter table with units, the R0 = beta/gamma = 3 threshold above which the outbreak grows, and a falsifier: if measured R0 drops below 1 while cases still rise, the model is wrong. It even flagged stochastic fade-out - a single introduction usually dies out even when R0 > 1.

The trick is an eight-phase workflow: decompose, extract parameters, attack from multiple mathematical lenses (twelve total, run in parallel as subagents), compare honestly, implement Python validation code, then state what would kill the model. Thirty recognized archetypes, three rigor tiers from quick sketch to thesis-grade.

Install:

    git clone https://github.com/Furox-Art/axiomize
    cp -r axiomize/skills/axiomize ~/.claude/skills/

MIT licensed, with 11 worked examples to browse first.
```

## Hacker News Show HN

Title options:

1. `Show HN: Axiomize - turn any idea into a falsifiable mathematical model`
2. `Show HN: An agent skill that makes LLMs model like scientists instead of guessing`
3. `Show HN: Twelve mathematical lenses for your AI coding agent`

First comment draft:

```text
I built this out of frustration: asking an LLM "how do I model X?" returns one plausible guess, when real modeling means decomposing, extracting parameters with units, attacking from several angles, and saying what would refute you. Axiomize enforces exactly that as an installable agent skill. Unlike OptiMUS-style research prototypes, which focus on a single optimization lens and live as paper artifacts, this covers twelve perspectives including stochastic, network, control, game theory, and causal inference; recognizes 30 archetypes like SIR and M/M/c; runs lenses as independent parallel subagents so they cannot anchor on each other; and demands falsifiers plus a confidence ledger in every report. Bundled tools validate against known ground truth before touching your data. Criticism welcome, especially on whether breadth across twelve lenses actually beats deep single-lens reasoning.
```

## LinkedIn/Mastodon short post

```markdown
Axiomize is an open-source (MIT) Agent Skill that turns vague ideas into rigorous mathematical models. Give it "a disease appears in a city of 1M" and it returns an SIR system with defined terms, an R0 threshold, runnable validation code, and explicit falsifiers. Twelve mathematical lenses, thirty recognized archetypes, eleven worked examples, three rigor tiers, and calibration tools included. Works with Claude Code, opencode, and Cursor - install by copying one folder: https://github.com/Furox-Art/axiomize
```

## Submission tracker

| Target | Entry ready | Submitted | Date | Response |
|--------|-------------|-----------|------|----------|
| awesome-claude-skills | [ ] | [ ] | | |
| awesome-claude-code | [ ] | [ ] | | |
| opencode docs showcase | [ ] | [ ] | | |
| r/ClaudeAI | [ ] | [ ] | | |
| r/LocalLLaMA | [ ] | [ ] | | |
| HN (Show HN) | [ ] | [ ] | | |
