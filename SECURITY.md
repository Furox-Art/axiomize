# Security Policy

## Supported versions

The latest published release is the supported line. Earlier lines receive fixes only when
a vulnerability also affects the current line, in which case both are patched.

| Version | Supported |
|---|---|
| 1.12.x | yes |
| < 1.12 | no |

A fix affecting distributed runtime behavior ships as a patch version built and tested
from the final merged commit on `main`. Unmerged branch artifacts are not release evidence
(see [docs/security-versioning.md](docs/security-versioning.md)).

## Reporting a vulnerability

Please do not publish an exploit or sensitive reproduction in a public issue.

Private vulnerability reporting is enabled for this repository. Use
**Security → Report a vulnerability** on
[github.com/Furox-Art/axiomize](https://github.com/Furox-Art/axiomize/security/advisories/new),
which opens a private channel visible only to the maintainer. If that path is unavailable,
contact the maintainer through the contact information on the project profile.

Include the affected version, entry point, minimal reproduction, impact, and any proposed mitigation. Reports are evaluated against the actual trust boundary: Model IR, REST/MCP inputs, provider endpoints, generated-code execution, formal-tool adapters, file paths, and document conversion are all treated as untrusted-input surfaces unless explicitly documented otherwise.

## Security model

Axiomize distinguishes three classes of execution:

1. **Deterministic scientific expressions** are parsed through a restricted mathematical grammar and explicit symbol namespace.
2. **Potentially expensive computations** require approval when applicable and are always subject to non-bypassable hard resource ceilings.
3. **Arbitrary code / theorem elaboration** is not an operating-system sandbox. It requires explicit trust and runs with reduced environment exposure, time limits, and process/resource controls where the platform supports them.

Network-facing REST service binding is loopback-only by default. Remote binding requires an explicit opt-in and bearer token. File-backed run inspection is confined to the configured run root.
