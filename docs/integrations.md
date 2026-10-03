# Using Axiomize with AI Agents

Axiomize is an independent scientific engine. AI providers are clients. All three
interfaces (MCP, CLI, REST) call the same core services, so validation behavior never
depends on which agent calls it.

## Capability discovery

Every agent starts here:

```bash
axiomize capabilities
```

or the `axiomize.get_capabilities` tool / `GET /v1/capabilities`. Only truly installed
backends are reported as available.

## Console scripts

Eight entry points ship in the distribution. `axiomize` is the main one; the rest are
standalone tools.

| Command | Purpose |
|---|---|
| `axiomize` | 14 subcommands over the Model IR engine, plus `serve` and `mcp` |
| `axiomize-validate` | Closed-form checks for `sir`, `gillespie`, `queue` |
| `axiomize-fit` | Calibrate `sir` or `logistic` against a `time,value` CSV |
| `axiomize-csv-check` | Gaps, duplicates and outliers in observation data |
| `axiomize-benchmark` | Grade a produced report against `benchmarks/ideas.json` |
| `axiomize-to-latex` | Report to LaTeX, optionally `--pdf` |
| `axiomize-index-reports` | Rebuild `reports/INDEX.md` from report files |
| `axiomize-sweep` | Parallel parameter sweeps, `--job sweep` or `--job mc` |

## `axiomize` subcommands

| Command | Does |
|---|---|
| `intake` | Clarify a vague idea, recommend a rigor level, ask a targeting question |
| `policy` | Report what the agent may spend and which actions are guarded |
| `model` | 16 `--action` values over versioned Model IR (below) |
| `clean-data` | Conservative data cleaning with a preserved audit trail |
| `compare-runs` | Explain why two recorded runs differ |
| `solve` | Backward-compatible reference SIR |
| `fit` | Backward-compatible logistic calibration from CSV |
| `validate` | Reference SIR solve plus dimensional and cross-validation checks |
| `tools` | Scientific backends and live availability |
| `capabilities` | Machine-readable capability map |
| `reproduce` | Inspect a stored run and verify its integrity hash |
| `benchmark` | Run the install-safe scientific benchmark suite |
| `serve` | REST API v1, loopback by default |
| `mcp` | MCP over stdio |

## `axiomize model --action`

| Family | Values |
|---|---|
| Lifecycle | `plan` · `validate` · `simulate` · `fit` · `compare` · `repair` · `export` |
| Analysis | `stability` · `validity` · `discover` · `experiment-design` · `uncertainty` · `bifurcation` |
| Verification | `numerical-verify` · `stop-check` · `surrogate` |

Every action takes `--input-json <file>` holding the Model IR request. The heavy
verification actions also need `--approve-heavy`; without it they return
`APPROVAL_REQUIRED` and name the study and its cost instead of running.

```bash
axiomize model --action numerical-verify --input-json request.json --approve-heavy
```

Approval authorizes compute. It never disables a resource ceiling.

## Via MCP (stdio)

```json
{"command": "axiomize", "args": ["mcp"]}
```

34 tools, named `axiomize.<verb>`. `axiomize.model_*` mirrors the `model --action`
values above. The unprefixed tools cover the surrounding workflow: `solve`, `fit_model`,
`validate`, `cross_validate`, `sensitivity_analysis`, `uncertainty_analysis`, `falsify`,
`compare_models`, `intake`, `workflow_policy`, `clean_data`, `compare_runs`,
`experiment_design`, `inspect_run`, `reproduce`, `get_capabilities`, `list_tools`,
`select_tools`.

Enumerate them rather than trusting a list:

```bash
axiomize mcp        # then send a tools/list request over stdin
```

Structured JSON in, structured JSON out (API v1). Five unnamespaced legacy aliases
(`solve_sir`, `validate_sir`, `fit_model`, `list_tools`, `get_capabilities`) are still
accepted by `tools/call` for older clients, but `tools/list` advertises only the 34
canonical names.

## Via REST API (v1)

Loopback only by default; remote binding needs `--allow-remote` plus a bearer token.

| Method | Paths |
|---|---|
| `GET` | `/tools` · `/capabilities` · `/workflow-policy` · `/runs/{id}` |
| `POST` | `/intake` · `/workflow-policy` · `/clean-data` · `/compare-runs` · `/model` · `/solve` · `/simulate` · `/fit` · `/validate` · `/cross-validate` · `/falsify` · `/compare` · `/sensitivity` · `/uncertainty` |
| `POST` | `/model/compare` · `/model/repair` · `/model/export` · `/model/stability` · `/model/validity-scan` · `/model/discover` · `/model/experiment-design` · `/model/numerical-verify` · `/model/surrogate` · `/model/uncertainty` · `/model/bifurcation` · `/model/stop-check` · `/runs/{id}/reproduce` |

```bash
axiomize serve --port 8765
curl -s http://127.0.0.1:8765/v1/capabilities
```

## Agent status

| Agent | MCP | CLI | REST | Status |
|---|---|---|---|---|
| Claude Code | yes | yes | yes | EXPERIMENTAL (protocol-tested, not field-tested) |
| OpenAI Codex | yes | yes | yes | EXPERIMENTAL |
| Cursor | yes | yes | yes | EXPERIMENTAL |
| OpenCode | yes | yes | yes | EXPERIMENTAL |
| Hermes Agent | yes | yes | yes | SUPPORTED (built and tested here) |
| Other agents | yes | yes | yes | PLANNED (any MCP/HTTP/CLI client works) |

## MCP registry

`server.json` at the repository root is the MCP registry manifest. It publishes
`io.github.Furox-Art/axiomize`, backed by the PyPI package with `mcp` as the runtime
argument over stdio. The `mcp-name` line is repeated at the top of `README.md` for
clients that scrape it instead.

## Portable runs

A run (`run.json` + `manifest.json`) can be zipped, moved to another machine, and
inspected by another agent. Start in one agent, continue in another; the science, not
the chat, carries the state.
