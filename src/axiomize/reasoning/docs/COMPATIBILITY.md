# Host compatibility

Quantum Reasoning is model-agnostic, but not every host exposes the same controls. Compatibility is therefore defined by capabilities rather than by provider branding.

## Compatibility levels

| Level | Required capabilities | What works |
| --- | --- | --- |
| Protocol-only | Host can persist or inject `SKILL.md` instructions | Multi-branch protocol, falsification rules, stopping/collapse policy |
| Measurable | Protocol-only plus aggregate run telemetry | Benchmark result schema, diversity/revival/contradiction measurements |
| Controller-assisted | Measurable plus a host-side loop that can call `reference/branch_controller.py` or equivalent logic | Deterministic scoring, state transitions, uncertainty-based width and collapse checks |

A host is incompatible only when it cannot reliably apply the skill instructions, truncates/replaces them in a way that changes the protocol, or prevents the requested task/tool access.

## Required host contract

A compatible integration should preserve these invariants:

1. `SKILL.md` is supplied as a persistent system/developer/skill instruction, not as untrusted task content.
2. The same task constraints and tool permissions apply to all candidate branches.
3. Tool observations are treated as evidence and are not fabricated.
4. Private chain-of-thought is not required or stored. Only aggregate control-plane telemetry may be emitted.
5. If numeric branch telemetry is unavailable, the host follows the qualitative protocol and omits unavailable measurements rather than inventing them.
6. Baseline-vs-skill benchmarks keep the model/version, tools, sampling and budget policy fixed.

## Integration patterns

### 1. Native skill directory

If a host supports a skill/plugin directory, install the repository so that `SKILL.md` is the skill entry point and keep its YAML front matter intact.

### 2. Persistent instruction wrapper

If the host has no native skill format, load the contents of `SKILL.md` into the persistent system/developer instruction layer before the user task. Do not prepend it to benchmark prompts only in the skill condition unless the baseline wrapper is otherwise identical.

### 3. Controller-assisted agent

A host with an explicit agent loop can map observable aggregate branch measurements to `BranchMetrics` and use `reference/branch_controller.py` for ranking, state changes and collapse decisions. The reference controller does not generate hidden reasoning or call an LLM.

See [`../examples/host-integration.md`](../examples/host-integration.md) for concrete generic examples.

## Provider/model claims

This repository intentionally does not label specific commercial models as "supported" without a reproducible third-party run. Community results may document a provider/model combination under `benchmark/results/community/`, but those results are measurements from the submitter, not a permanent compatibility guarantee.
