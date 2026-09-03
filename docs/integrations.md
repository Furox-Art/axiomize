# Using Axiomize with AI Agents

Axiomize is an independent scientific engine. AI providers are clients.
All three interfaces (MCP, CLI, REST) call the same core services, so
validation behavior never depends on which agent calls it.

## Capability discovery

Every agent starts here:

```bash
axiomize capabilities
```

or the `axiomize.get_capabilities` tool / `GET /capabilities`.
Only truly installed backends are reported as available.

## Via MCP (stdio)

```json
{"command": "axiomize", "args": ["mcp"]}
```

Tools: `axiomize.solve`, `axiomize.fit_model`, `axiomize.simulate`,
`axiomize.validate`, `axiomize.cross_validate`,
`axiomize.sensitivity_analysis`, `axiomize.uncertainty_analysis`,
`axiomize.falsify`, `axiomize.compare_models`, `axiomize.select_tools`,
`axiomize.list_tools`, `axiomize.get_capabilities`, `axiomize.inspect_run`,
`axiomize.reproduce`. Structured JSON in, structured JSON out (API v1).

## Via CLI

```bash
axiomize solve --beta 0.3 --gamma 0.1 --N 1000000 --json out.json
axiomize validate --N 1000000
axiomize reproduce runs/<id>
```

## Via REST API (v1)

`POST /solve /fit /simulate /validate /cross-validate /falsify /compare`,
`GET /tools /capabilities /runs/{id}`, `POST /runs/{id}/reproduce`.

## Agent status

| Agent | MCP | CLI | REST | Status |
|---|---|---|---|---|
| Claude Code | ✅ | ✅ | ✅ | EXPERIMENTAL (protocol-tested, not field-tested) |
| OpenAI Codex | ✅ | ✅ | ✅ | EXPERIMENTAL |
| Cursor | ✅ | ✅ | ✅ | EXPERIMENTAL |
| OpenCode | ✅ | ✅ | ✅ | EXPERIMENTAL |
| Hermes Agent | ✅ | ✅ | ✅ | SUPPORTED (built and tested here) |
| Other agents | ✅ | ✅ | ✅ | PLANNED (any MCP/HTTP/CLI client works) |

## Portable runs

A run (`run.json` + `manifest.json`) can be zipped, moved to another
machine, and inspected by another agent. Start in one agent, continue
in another — the science, not the chat, carries the state.
