# Security and trust boundaries

Axiomize treats all externally supplied Model IR, REST/MCP payloads, provider responses, file paths, and document content as untrusted unless a caller explicitly opts into a stronger trust boundary.

## Mathematical expressions

Model equations and constraints are parsed through a restricted arithmetic grammar with an explicit symbol namespace and hard complexity limits before SymPy is invoked. Python attribute access, imports, subscripting, lambdas, comprehensions, and arbitrary function calls are rejected.

## Compute limits

Approval flags authorize expensive scientific work; they do not disable resource-safety ceilings. Array sizes, samples, model dimensions, graph sizes, expression complexity, iteration counts, and generated result sizes have hard upper bounds.

## Arbitrary code and theorem elaboration

Local Python execution and Lean theorem elaboration are not kernel-level sandboxes. They require explicit trust, use isolated temporary working directories, reduce inherited environment data, avoid a shell, and enforce time/resource limits where supported. For hostile code, use an external container or OS sandbox.

## REST and MCP

REST binds to loopback by default. Remote binding requires explicit opt-in plus a bearer token. Request/message sizes are bounded, file-backed run access is confined to a configured run root, and server responses avoid exposing internal tracebacks.

## Provider endpoints

OpenAI-compatible provider URLs must use approved HTTP(S) schemes, requests and responses are size/time bounded, and authenticated requests do not follow redirects that could forward an Authorization header to another origin.

## Reproducible run state

Run records are written atomically and include integrity metadata. Loading a run verifies the recorded content hash before returning the result.
