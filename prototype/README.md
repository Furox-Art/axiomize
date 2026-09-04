# Hosted Scientific Provider Prototype

This prototype turns Axiomize into a centrally hosted scientific-skill service.

## Goal

- Users do not install skills locally.
- Users connect their own model API key (BYOK).
- The service selects a pinned Axiomize skill release and runs requests through the hosted runtime.
- The provider stores only metadata needed for execution; API keys are never written to disk.
- Future releases can be promoted from GitHub after tests/benchmarks pass.

## Prototype flow

1. `POST /v1/session` creates an in-memory session and accepts provider/model metadata.
2. `GET /v1/skills` lists the hosted skills and their pinned versions.
3. `POST /v1/run` executes the selected skill using the caller-supplied API key from the request header.
4. `GET /health` reports service status.

## Security boundaries in this prototype

- API keys are accepted only in the `X-Provider-Key` header and are not persisted.
- Session state is in memory and disappears on restart.
- Each execution receives its own temporary working directory.
- No user file is retained after the execution context closes.
- Production deployment must replace process-local isolation with a real sandbox/container boundary.

## Run locally

```bash
pip install -e .
python prototype/provider_server.py
```

Then open `http://127.0.0.1:8787/health`.

## Not production-ready yet

This deliberately excludes billing, OAuth, durable accounts, encrypted secrets storage, organization controls, SSO, audit retention, data residency, and a hardened remote sandbox. Those belong in the next stage after the core hosted-skill flow is validated.
