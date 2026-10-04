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

Private vulnerability reporting is enabled for this repository; the setting is visible at
`GET /repos/Furox-Art/axiomize/private-vulnerability-reporting` and currently returns
`{"enabled": true}`. Use **Security → Report a vulnerability** on
[github.com/Furox-Art/axiomize](https://github.com/Furox-Art/axiomize/security/advisories/new),
which opens a private channel visible only to the maintainer. If that path is unavailable or the
setting above ever reads `false`, contact the maintainer through the contact information on the
[project profile](https://github.com/Furox-Art).

Include the affected version, entry point, minimal reproduction, impact, and any proposed mitigation. Reports are evaluated against the actual trust boundary: Model IR, REST/MCP inputs, provider endpoints, generated-code execution, formal-tool adapters, file paths, and document conversion are all treated as untrusted-input surfaces unless explicitly documented otherwise.

## Security model

Axiomize distinguishes three classes of execution:

1. **Deterministic scientific expressions** are parsed through a restricted mathematical grammar and explicit symbol namespace.
2. **Potentially expensive computations** require approval when applicable and are always subject to non-bypassable hard resource ceilings.
3. **Arbitrary code / theorem elaboration** is not an operating-system sandbox. It requires explicit trust and runs with reduced environment exposure, time limits, and process/resource controls where the platform supports them.

Network-facing REST service binding is loopback-only by default. Remote binding requires an explicit opt-in and bearer token. File-backed run inspection is confined to the configured run root.

## Supply chain

Distribution integrity and build provenance are separate properties, and Axiomize publishes them
at different levels on purpose. State at `1.12.5`:

| Channel | Signed build provenance | What you can verify today |
|---|---|---|
| PyPI | **yes**, PEP 740 attestations for the wheel and the sdist | A Sigstore bundle naming `Furox-Art/axiomize` via `release.yml`, environment `pypi`, whose attested subject digest equals the file you downloaded |
| npm | **no** — published in token mode, which cannot mint an attestation | The tarball digest only, via `dist.integrity` |

What this does and does not mean for you:

- npm `dist.signatures` are present on every published version. They sign the *registry metadata*,
  proving the registry has not altered its own record. They are not build provenance, and they
  would be equally present on a broken release.
- `dist.integrity` and PyPI `digests.sha256` prove the bytes you received are the bytes the
  registry published. They do not identify who built them or from which commit.
- Only an attestation bundle carries the build-workflow identity, and today only the PyPI
  distributions do.

Pinning by digest is the honest recommendation for the npm shim. The gap closes when the npm
trusted publisher is registered (owner `Furox-Art`, repository `axiomize`, workflow `release.yml`,
environment `npm`) and a release is published through it; attestations cannot be backfilled onto an
already-published version.

`docs/documentation.md` carries the exact commands, the correct per-file PyPI endpoint shape, and
what each of the three mechanisms proves. `.github/scripts/check_provenance_claims.py` re-checks
the documented claims against both live registries on every CI run, and fails rather than skips when
a registry cannot be reached, so these statements cannot quietly go stale or wrong.
