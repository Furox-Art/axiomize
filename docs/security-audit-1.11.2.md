# Axiomize 1.11.2 root-hardening audit

This document records the engineering scope of the 1.11.2 hardening pass. It is intentionally concise; exploit details are not published here.

## Hardened surfaces

- Model IR structural validation and schema migration behavior.
- Mathematical-expression parsing and symbol namespaces.
- Hard compute/allocation ceilings independent of approval flags.
- Generated Python execution trust gate, environment isolation, time/output/resource controls.
- REST request limits, remote-binding authentication, file path confinement, response hardening.
- MCP message limits, path confinement, and error normalization.
- Provider endpoint validation, redirect handling, response limits, and timeouts.
- Run-state integrity and atomic persistence.
- Formal-tool execution trust boundaries and limits.
- Finite-horizon SIR validation versus asymptotic final-size theory.
- Adversarial regression coverage and release/CI gates.

## Completion criterion

The hardening branch is not considered releasable until the full test suite, source/import checks, exact-wheel installed CLI contracts, cross-platform wheel CLI jobs, security regression tests, documentation build, and release preflight all pass on the final commit.
