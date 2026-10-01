---
name: Bug report
about: Something in the Python package, CLI, agent skill or docs is wrong
title: "[BUG] "
labels: bug
---

**What happened**

<!-- What you observed, and what you expected instead. -->

**Reproduction**

<!-- Smallest input that shows it. For the CLI, the exact command with its full JSON
     output. For the Python API, a short snippet run against the installed package.
     For the agent skill, the prompt you used and the phase where it went wrong. -->

```text
# paste the command or snippet here
```

**Environment**

| Field | Value |
|---|---|
| Axiomize version | `python -c "import axiomize; print(axiomize.__version__)"` |
| Python | `python --version` |
| Install | `pip install axiomize` / `pip install -e .` / extras (`full`, `playground`) |
| Optional backends | output of `axiomize capabilities` |
| OS | |
| Surface | Python API / `axiomize` CLI / `axiomize-validate` etc. / MCP / REST / agent skill |

**Documented behavior that did not hold**

<!-- If a written guarantee was broken, quote it: README "What it actually does",
     docs/quickstart.md, or the relevant part of skills/axiomize/SKILL.md. -->

**Anything else**

Logs, tracebacks, screenshots. Please redact anything sensitive.

Do not report security vulnerabilities here. Use the private channel in
[SECURITY.md](https://github.com/Furox-Art/axiomize/blob/main/SECURITY.md) instead.
