# Maintaining this documentation

This page is for people changing the docs, the README, or the benchmark numbers. It is not
needed to use Axiomize.

## What builds what

| Source of truth | Built into |
|---|---|
| `README.md` | GitHub repository page, and the PyPI project description |
| `docs/*.md` | <https://furox-art.github.io/axiomize/> via `mkdocs build --strict` |
| `skills/axiomize/*.md` | the agent skill pack; `skills/axiomize/tools/*.py` are also packaged inside the wheel |
| `.github/scripts/stage_docs.py` | copies a few `skills/axiomize/` pages into `docs/` before the site builds |

`docs/rigor.md`, `docs/archetypes.md`, `docs/adaptive-workflow.md`, `docs/skill.md` and
`docs/examples.md` are **generated** by `.github/scripts/stage_docs.py` and are git-ignored. Edit
the source under `skills/axiomize/`, never the generated page.

## Pages that are not in the site nav

These exist under `docs/`, are excluded from the nav by `exclude_docs` in `mkdocs.yml`, and are
reachable only through direct repository links:

- `publishing-checklist.md` — prepared text for third-party skill registries. Internal process,
  not user documentation.
- `security-ci-contract.md` — how CI enforces the security rules. Maintainer-facing.
- `security-maintenance.md` — dependency and advisory upkeep.
- `security-release-checklist.md` — release-time security steps.
- `security-audit-1.11.2.md` — engineering scope of the 1.11.2 hardening pass.

User-facing security documentation is `docs/security.md`, `docs/security-non-goals.md` and
`docs/security-versioning.md`, all of which stay in the nav.

## Rules that CI enforces

`python .github/scripts/readme_example_check.py` fails the build when:

1. `pip install axiomize` is missing from `README.md` or `docs/quickstart.md`.
2. A relative link or in-document anchor in `README.md` or `docs/quickstart.md` does not resolve.
   Absolute `http(s)` URLs are not fetched, so a broken external link is your responsibility.
3. The output block quoted in `README.md` or `docs/quickstart.md` differs from a real
   `examples/quickstart_sir.py` run.
4. A documented CLI entry point is missing from the installed distribution or does not answer.
5. A page named in the `mkdocs.yml` nav does not exist under `docs/`.

`python -m mkdocs build --strict` fails the build on any broken internal link or missing page.

## Adding a benchmark number

Anything numeric you publish has to be reproducible by someone else. Before adding a score:

1. Record the commit, the sha256 of `skills/axiomize/tools/benchmark_runner.py`,
   `benchmarks/ideas.json` and `benchmarks/rubric.md`, the interpreter version and the run
   timestamp. `docs/benchmark-results.md` carries a table in exactly this shape; follow it.
2. Give the command that regenerates the number verbatim.
3. State what the number does not prove. The automated layer checks report structure, not
   mathematics, and the rubric's real gate is a combined automatic plus human score that is not
   recorded in this repository.
4. If a run cannot be reproduced, put it under a clearly labelled history heading and say why.

Do not present an illustrative or placeholder figure as a measurement.

## Adding a worked example

Full examples follow the eight-phase structure in `examples/epidemic-sir.md`. Every example must
open with the parameter-provenance note, because the ranges in these files are illustrative and
carry no citation:

```markdown
> **Parameter provenance:** the values below are illustrative. `lit.` / `data.` / `est.`
> mark the intended weight of a range; this file cites no external source. Reading material
> for the workflow, not a literature-backed model.
```

Then add the file to `docs/example-gallery.md`, otherwise nothing links to it.

## Registry version claims in the README

`pyproject.toml`, `src/axiomize/__init__.py`, `package.json`, `.github/pypi-release-trigger` and
the first `## [version]` heading in `CHANGELOG.md` are kept in lockstep by
`.github/scripts/check_release_contract.py`. That gate checks the **repository**. It says nothing
about what a registry is currently serving, so the two can legitimately differ for a while:
between a release commit landing on `main` and the release actually running, the registry still
serves the previous tarball.

Check the registry directly before making any claim about a published version:

```bash
# npm: latest tag and the full version list
curl -s https://registry.npmjs.org/axiomize \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['dist-tags']['latest'], sorted(d['versions']))"

# npm: published digests for integrity checks
curl -s https://registry.npmjs.org/axiomize/1.12.4 \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['dist']['integrity'], d['dist']['shasum'])"

# PyPI: latest version and per-file digests
curl -s https://pypi.org/pypi/axiomize/json \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['info']['version']); [print(' ', u['filename'], u['digests']['sha256']) for u in d['urls']]"
```

The npm version badge follows the PyPI version. It is present only when the registry version
matches; otherwise the README must say which of the two states it is in, because a repository fix
is not a published fix. The badges are live; when the two registries disagree, per-registry
availability is documented here instead of claiming a single "current" version for both.

At the time of writing (2026-10-30), PyPI and npm both serve **1.14.2**.

## Supply-chain attestations: what exists and what does not

Do not write "published with provenance" without checking which registry you mean, and check the
version as well as the registry. State at `1.14.2`:

| Registry | Mechanism | Endpoint | State |
|---|---|---|---|
| PyPI | PEP 740 attestations, Sigstore/Fulcio + transparency log | `https://pypi.org/integrity/<project>/<version>/<filename>/provenance` | **present** for both the wheel and the sdist at `1.14.2` |
| npm | Sigstore attestations, only with trusted publishing (OIDC/provenance) | `https://registry.npmjs.org/-/npm/v1/attestations/<pkg>@<version>` | **present** at `1.14.2` (SLSA provenance + npm publish attestation); **absent** for `1.14.1` and every earlier npm release |

Both registries attest `1.14.2`, and the version matters. Both PyPI files serve a bundle naming
`GitHub / Furox-Art/axiomize / release.yml`, environment `pypi`, predicate
`https://docs.pypi.org/attestations/publish/v1`, one transparency-log entry each, and the attested
subject digest equals the digest of the file a consumer downloads. The npm tarball serves SLSA
provenance naming `Furox-Art/axiomize` and `.github/workflows/npm-publish.yml`, and its attested
subject digest equals `dist.integrity`. npm `1.14.1`, the previous latest, is digest-verifiable
only.

### Reading a 404 correctly

The two registries use different URL shapes, and getting them wrong looks like an absent
attestation when it is not:

```bash
# PyPI: PER-FILE. A directory-style URL names no artifact and 404s even when every
# file in that release is attested, so it proves nothing either way.
curl -s -o /dev/null -w '%{http_code}\n' \
  https://pypi.org/integrity/axiomize/1.14.2/axiomize-1.14.2.tar.gz/provenance      # 200
curl -s -o /dev/null -w '%{http_code}\n' \
  https://pypi.org/integrity/axiomize/1.14.2/                                                        # 404, meaningless

# npm: PER-VERSION.
curl -s -o /dev/null -w '%{http_code}\n' \
  https://registry.npmjs.org/-/npm/v1/attestations/axiomize@1.14.2                                      # 200
curl -s -o /dev/null -w '%{http_code}\n' \
  https://registry.npmjs.org/-/npm/v1/attestations/axiomize@1.14.1                                      # 404, genuinely absent
```

A 404 on a correct URL means no attestation for that artifact. Confirm the endpoint can also say
"yes" and "no" before trusting either answer, by querying a package known to publish with trusted
publishing and one known not to:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://registry.npmjs.org/-/npm/v1/attestations/vite@6.0.5     # 200
curl -s -o /dev/null -w '%{http_code}\n' https://registry.npmjs.org/-/npm/v1/attestations/left-pad@1.3.0   # 404
```

`.github/scripts/check_provenance_claims.py` runs that negative control on every CI run, and fails
if the endpoint stops discriminating.

### Three different things, easy to confuse

| Thing | Where it lives | What it proves | What it does not prove |
|---|---|---|---|
| **PEP 740 attestation** | `pypi.org/integrity/.../provenance` | A build workflow signed this exact file digest, through the Sigstore transparency log | That the build was correct, or that its inputs were trustworthy |
| **npm `dist.signatures`** | registry metadata, ECDSA under npm's registry key | The **registry** has not altered its own metadata for this version | **Anything about the build.** Every npm version has these, published or broken, token or OIDC. Transport integrity, not provenance. |
| **`dist.integrity` / `digests.sha256`** | registry metadata | The bytes you downloaded are the bytes the registry published | That anyone built them, or from which commit |

A package can have all three, two, or none. At `1.14.2` both registries provide an attestation and
digests, and npm metadata signatures as well; npm `1.14.1` has registry metadata signatures plus
digests, but no attestation.

## What a consumer can verify today

### PyPI — attestation or digest

```bash
# 1. attestation: confirm the bundle names this repo and workflow, and that its
#    subject digest matches what you downloaded
curl -s https://pypi.org/integrity/axiomize/1.14.2/axiomize-1.14.2.tar.gz/provenance \
  | python -c "import base64,json,sys; b=json.load(sys.stdin)['attestation_bundles'][0]; s=json.loads(base64.b64decode(b['attestations'][0]['envelope']['statement'])); print(b['publisher']); print([(x['name'],x['digest']['sha256']) for x in s['subject']])"

# 2. digest: pin it
pip download axiomize==1.14.2 --no-deps -d /tmp/ax
python -c "import hashlib; print(hashlib.sha256(open('/tmp/ax/axiomize-1.14.2-py3-none-any.whl','rb').read()).hexdigest())"
```

Compare against `fb36d958bdfcf14490644ffc4751ea5b7da708d06679d7ed27f79b23d34a72bc` (wheel) and
`80da3f62aebbeee14faee0559dbf7ed6860e9121b0f9e4a7e328f2fad8393a74` (sdist) at `1.14.2`.

### npm — attestation or digest

```bash
# 1. attestation: confirm the bundle names this repo and workflow
curl -s -o /dev/null -w '%{http_code}\n' \
  https://registry.npmjs.org/-/npm/v1/attestations/axiomize@1.14.2                 # 200

# 2. digest: pin it
npm view axiomize@1.14.2 dist.integrity
# sha512-fG3/KAQyg1+0HufLOROOOXKiOLSiXLVPytQxYrrF7GzLWyL9Ca5ZiWkVbLaIQgeoCAfcqnT6MGQTTSHiJmEItw==

npm view axiomize@1.14.2 dist.shasum
# a622fcc08100346c0a41c0d01330de447deec360
```

The attested subject digest of the `1.14.2` bundle is the SHA-512 hex form of that
`dist.integrity` value. `npm ci` and `npm install` enforce `dist.integrity` automatically when a
`package-lock.json` pins it, which is the practical pinning mechanism on the npm side.

npm `1.14.1` has no attestation, so for that version the digest is the only check available:

```bash
npm view axiomize@1.14.1 dist.integrity
# sha512-v9/AzLG2wkIswdH6+9pBgu1cRT8s3p7Gw1tkg0kD5C0EzVw6zeoA58RkYNw6GTCzko5ZVYEhSIAY7BrIlCGQwg==

npm view axiomize@1.14.1 dist.shasum
# 5fecdcce36e0bc9c6edacfbb801bc1f84ec09d05
```

**Pinning by digest remains a sound baseline.** It proves the bytes you review are the bytes that
were published, and on `1.14.2` it is backed by a published attestation as well.

### The in-repo integrity stories, which are different again

Do not conflate package provenance with the hashes this project computes at runtime:

- `axiomize.portable-bundle.v1` export carries a SHA-256 over the canonical Model IR
- the run ledger records a content hash and verifies it when a stored run is loaded
- `docs/benchmark-results.md` records commit plus runner, case-set and rubric sha256

Those bind artifacts to their content and inputs. None of them is a registry or build attestation.

## Trusted publishers: both satisfied

Attestations require a registered trusted publisher; a long-lived API token cannot mint one. Both
registries are configured. PyPI is evidenced by the PEP 740 bundles above; npm is evidenced by the
`1.14.2` SLSA bundle naming `.github/workflows/npm-publish.yml`.

| Registry | Owner / org | Repository | Workflow | Environment | Status |
|---|---|---|---|---|---|
| PyPI | `Furox-Art` | `axiomize` | `release.yml` | `pypi` | **satisfied** — evidenced by the `1.14.2` bundles naming this repo and workflow |
| npm | `Furox-Art` | `axiomize` | `npm-publish.yml` | `npm` | **satisfied** — evidenced by the `1.14.2` SLSA bundle naming this repo and workflow |

Both release paths default to OIDC and fail loudly if `id-token:write` is not granted; the token
path is an explicit `use_token_fallback` opt-in and produces no attestation. The npm job runs only
after the PyPI release succeeds, so an unavailable npm credential cannot block or undo the Python
distribution; the run still fails so the missing channel is visible rather than masked.

**Do not backfill an attestation onto an already-published version:** attestations are bound to a
publish event. `1.14.1` and every earlier npm release stay unattested.

## Machine-checked claim block

`.github/scripts/check_provenance_claims.py` parses this block on every CI run and fails the build
if a documented `attested` value disagrees with the live registry. Editing the value here to match
what you *want* to be true does not help: the check reads the registry, not the file.

The current block, verified 2026-10-30 against the live endpoints:

<!-- provenance-claims:begin -->
```json
[
  {"registry": "pypi", "package": "axiomize", "version": "1.14.2",
   "filename": "axiomize-1.14.2-py3-none-any.whl", "attested": true},
  {"registry": "pypi", "package": "axiomize", "version": "1.14.2",
   "filename": "axiomize-1.14.2.tar.gz", "attested": true},
  {"registry": "npm", "package": "axiomize", "version": "1.14.2", "attested": true},
  {"registry": "npm", "package": "axiomize", "version": "1.14.1", "attested": false}
]
```
<!-- provenance-claims:end -->

How the check behaves, so it is not mistaken for something weaker than it is:

- a claim of `attested: true` that resolves to 404 fails
- a claim of `attested: false` that resolves to a real bundle fails
- a 200 that is not a parseable bundle with a `publisher` and at least one attestation fails
- a registry that cannot be reached at all **fails** the check; an unconfirmed claim never passes
  silently
- the npm endpoint is negative-controlled against `left-pad@1.3.0` on every run; if that stops
  returning 404 the gate fails, because a 200 would no longer mean anything
- removing this block entirely fails, since a claim that cannot be parsed cannot be trusted

Run it locally with `python .github/scripts/check_provenance_claims.py`. Use `--offline` only to
inspect the table without network access; CI never passes that flag.

## PyPI description sync (manual step)

`README.md` is the `readme` in `pyproject.toml`, so the PyPI long description is whatever
`README.md` said **at the moment the release wheel was built**. Nothing republishes it
automatically, which means README edits merged after a release do not reach the PyPI page until
the next release. That is the whole reason the published description can lag the repository.

After each release, confirm the two agree:

```bash
# what PyPI currently renders as the description
curl -s https://pypi.org/pypi/axiomize/json | python -c "import json,sys; print(json.load(sys.stdin)['info']['description'])"

# what this checkout would render
python -c "print(open('README.md', encoding='utf-8').read())"
```

If they differ, the published description is stale. The only correct fix is a new release built
from a commit whose `README.md` is current; do not edit the PyPI page by hand, and do not upload
a file to a released version. Until that release exists, the repository README is the accurate
document.

Checklist before tagging:

- [ ] `README.md` states the version being released.
- [ ] `docs/quickstart.md` and `README.md` output blocks match a real run.
- [ ] `CHANGELOG.md` has an entry for the new version.
- [ ] `CITATION.cff` `version` and `date-released` match the release.
- [ ] PyPI metadata refreshed and re-checked with the commands above.

After tagging, confirm the registries actually moved. This is the step that catches a release that
published Python but not npm, or the reverse:

- [ ] `curl -s https://pypi.org/pypi/axiomize/json` reports the new version, and each file's
      `provenance` link returns 200.
- [ ] `curl -s https://registry.npmjs.org/axiomize` lists the new version in `versions` **and** the
      new version under `dist-tags.latest`.
- [ ] `node --check` passes on `index.js` and `bin/axiomize.js` as published, not just in the repo.
- [ ] If npm was published with trusted publishing, its attestations URL returns 200. If it was
      published with a token, the README table says so rather than implying provenance.

## Local commands

```bash
pip install -r requirements-test.txt
pip install -e .
pip install mkdocs-material

pytest tests/ -v                                    # test suite
python skills/axiomize/tools/check_skill.py         # skill frontmatter, links, compile
python .github/scripts/check_release_contract.py    # version lockstep
python .github/scripts/stage_docs.py                # stage generated docs pages
python .github/scripts/readme_example_check.py      # README/docs claims vs real behavior
python -m mkdocs build --strict                     # site build, warnings are failures
```
