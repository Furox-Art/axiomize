#!/usr/bin/env python3
"""Fail CI when a provenance claim in the docs is not backed by the live registry.

A documentation claim about build provenance is only worth making if the registry
agrees with it. This gate reads the machine-readable claim table in
``docs/documentation.md`` and checks every row against the real registry:

  * a row claiming a PyPI PEP 740 attestation must resolve to a 200 bundle at
    ``https://pypi.org/integrity/<project>/<version>/<filename>/provenance``,
  * a row claiming npm provenance must resolve to a 200 bundle at
    ``https://registry.npmjs.org/-/npm/v1/attestations/<pkg>@<version>``.

Two design decisions are load-bearing:

1. **A network failure is a failure, not a skip.** If the registry is unreachable,
   the claim cannot be confirmed, and an unconfirmed claim must not be allowed to
   pass. ``--offline`` exists so a developer can deliberately skip the whole gate
   locally while aware that CI is the enforcing context; CI never passes it.

2. **Negative controls run every time.** For every registry that reports an
   attestation, this also queries a package that is known *not* to have one. If
   that control unexpectedly succeeds, the endpoint is not discriminating and a
   200 from the real package proves nothing, so the gate fails rather than
   waving a claim through.

Run from a checkout with no arguments. Exit 0 only when every claim is confirmed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAIMS_DOC = ROOT / "docs" / "documentation.md"

BEGIN_MARKER = "<!-- provenance-claims:begin -->"
END_MARKER = "<!-- provenance-claims:end -->"

PYPI_ENDPOINT = "https://pypi.org/integrity/{project}/{version}/{filename}/provenance"
NPM_ENDPOINT = "https://registry.npmjs.org/-/npm/v1/attestations/{package}@{version}"

# A package published without trusted publishing, used as a negative control for
# the npm attestations endpoint. If this ever returns 200, the endpoint cannot be
# trusted to answer "is this attested?".
NPM_NEGATIVE_CONTROL = ("left-pad", "1.3.0")

TIMEOUT = 45


class Unreachable(RuntimeError):
    """A registry could not be queried at all, so nothing was confirmed."""


def _fetch(url: str) -> tuple[int, bytes]:
    """Return (status, body). A 404 is a real answer; anything else raising is not."""
    request = urllib.request.Request(url, headers={"User-Agent": "axiomize-provenance-guard"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Unreachable(f"{url}: {exc}") from exc


def _is_bundle(body: bytes) -> bool:
    """A 200 must carry a real attestation bundle, not an HTML error page."""
    try:
        doc = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(doc, dict):
        return False
    bundles = doc.get("attestation_bundles")
    if not isinstance(bundles, list) or not bundles:
        return False
    for bundle in bundles:
        if not isinstance(bundle, dict):
            return False
        if not bundle.get("publisher"):
            return False
        if not bundle.get("attestations"):
            return False
    return True


def parse_claims(text: str) -> list[dict[str, str]]:
    """Read the fenced JSON claim table that documentation.md publishes."""
    try:
        start = text.index(BEGIN_MARKER)
        end = text.index(END_MARKER)
    except ValueError as exc:
        raise RuntimeError(
            f"{CLAIMS_DOC.name} is missing the provenance claim markers "
            f"({BEGIN_MARKER} ... {END_MARKER}). A documented claim must be "
            f"machine-checkable, so the table cannot be removed silently."
        ) from exc

    region = text[start:end]
    match = re.search(r"```json\n(.+?)\n```", region, re.DOTALL)
    if not match:
        raise RuntimeError(
            f"{CLAIMS_DOC.name} claim block must contain a ```json fenced table of claims."
        )
    try:
        claims = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{CLAIMS_DOC.name} claim block is not valid JSON: {exc}") from exc
    if not isinstance(claims, list) or not claims:
        raise RuntimeError(f"{CLAIMS_DOC.name} claim block must be a non-empty JSON array.")
    return claims


def check_pypi_claim(claim: dict[str, str]) -> tuple[bool, str]:
    filename = claim["filename"]
    url = PYPI_ENDPOINT.format(
        project=claim["package"], version=claim["version"], filename=filename
    )
    status, body = _fetch(url)
    if status == 200:
        if not _is_bundle(body):
            return False, f"{url} returned 200 but the body is not an attestation bundle"
        return True, f"{url} -> 200 with an attestation bundle"
    if status == 404:
        return False, f"{url} -> 404, no attestation for this artifact"
    return False, f"{url} -> unexpected status {status}"


def check_npm_claim(claim: dict[str, str]) -> tuple[bool, str]:
    url = NPM_ENDPOINT.format(package=claim["package"], version=claim["version"])
    status, body = _fetch(url)
    if status == 200:
        if not _is_bundle(body):
            return False, f"{url} returned 200 but the body is not an attestation bundle"
        return True, f"{url} -> 200 with an attestation bundle"
    if status == 404:
        return False, f"{url} -> 404, no provenance attestation for this version"
    return False, f"{url} -> unexpected status {status}"


def negative_control() -> tuple[bool, str]:
    """Prove the npm endpoint can actually say 'no' before trusting its 'yes'."""
    package, version = NPM_NEGATIVE_CONTROL
    url = NPM_ENDPOINT.format(package=package, version=version)
    status, _ = _fetch(url)
    if status == 404:
        return True, f"{url} -> 404 as expected, endpoint discriminates correctly"
    return False, (
        f"{url} -> {status}, expected 404. The npm attestations endpoint is not "
        f"discriminating, so a 200 for this project would prove nothing."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="developer escape hatch: report claims without querying registries. CI never passes this.",
    )
    args = parser.parse_args()

    if not CLAIMS_DOC.is_file():
        print(f"FAIL: {CLAIMS_DOC.relative_to(ROOT)} does not exist", file=sys.stderr)
        return 1
    text = CLAIMS_DOC.read_text(encoding="utf-8")

    try:
        claims = parse_claims(text)
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"provenance claims found in {CLAIMS_DOC.relative_to(ROOT)}: {len(claims)}")

    if args.offline:
        print("\nOFFLINE: not verifying any claim. CI runs without --offline.")
        for claim in claims:
            print(f"  [{claim['registry']}] {claim['package']} {claim['version']} "
                  f"{claim.get('filename', '')} attested={claim['attested']}")
        return 0

    failures: list[str] = []
    checked_pypi = False

    try:
        ok, detail = negative_control()
        print(f"- negative control: {detail}")
        if not ok:
            failures.append(f"negative control: {detail}")

        for claim in claims:
            registry = claim.get("registry")
            if registry == "pypi":
                checked_pypi = True
                ok, detail = check_pypi_claim(claim)
            elif registry == "npm":
                ok, detail = check_npm_claim(claim)
            else:
                failures.append(f"claim has an unknown registry {registry!r}")
                continue

            wants = claim.get("attested")
            if wants is True and not ok:
                failures.append(f"CLAIMED attested but not attested -> {detail}")
            elif wants is False and ok:
                failures.append(f"CLAIMED not attested but registry serves an attestation -> {detail}")
            marker = "OK " if ok == bool(wants) else "BAD"
            print(f"- [{marker}] {registry} {claim['package']} {claim['version']} "
                  f"{claim.get('filename', '')} (documented attested={wants}): {detail}")
    except Unreachable as exc:
        # Deliberately fatal: silence is not consent.
        failures.append(f"registry unreachable, so no claim could be confirmed: {exc}")

    if not checked_pypi:
        failures.append("no PyPI claim is documented, so PyPI provenance is going unchecked")

    if failures:
        print("\nPROVENANCE CLAIM CHECK: FAIL", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("\nPROVENANCE CLAIM CHECK: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())