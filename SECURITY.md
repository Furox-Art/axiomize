# Security Policy

## Supported versions

The latest published Axiomize release is the supported line. Security fixes are developed on protected branches and released as patch versions when they affect distributed code.

## Reporting a vulnerability

Please do not publish an exploit or sensitive reproduction in a public issue. Use GitHub's private vulnerability reporting for this repository when available, or contact the repository maintainer privately through the contact information on the project profile.

Include the affected version, entry point, minimal reproduction, impact, and any proposed mitigation. Reports are evaluated against the actual trust boundary: Model IR, REST/MCP inputs, provider endpoints, generated-code execution, formal-tool adapters, file paths, and document conversion are all treated as untrusted-input surfaces unless explicitly documented otherwise.

## Security model

Axiomize distinguishes three classes of execution:

1. **Deterministic scientific expressions** are parsed through a restricted mathematical grammar and explicit symbol namespace.
2. **Potentially expensive computations** require approval when applicable and are always subject to non-bypassable hard resource ceilings.
3. **Arbitrary code / theorem elaboration** is not an operating-system sandbox. It requires explicit trust and runs with reduced environment exposure, time limits, and process/resource controls where the platform supports them.

Network-facing REST service binding is loopback-only by default. Remote binding requires an explicit opt-in and bearer token. File-backed run inspection is confined to the configured run root.
