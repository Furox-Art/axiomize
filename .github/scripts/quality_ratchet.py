#!/usr/bin/env python3
"""Enforce non-regression on lint, type-check and coverage budgets.

The repository had no lint, type or coverage gate, and an audit found a real
backlog: 96 findings under the curated ruff rule set, 35 mypy errors and 69%
line coverage. Turning that into a hard "zero findings" gate would block every
pull request until the backlog is cleared, which is not a trade this change can
make unilaterally.

Instead this script enforces a *ratchet*: each measurement is compared against
the ceiling recorded in ``.github/quality-baseline.json``. A PR that adds
findings, type errors, or loses coverage fails. A PR that reduces any of them
passes and is told the baseline can be lowered.

Baseline regeneration is explicit and never happens implicitly:

    python .github/scripts/quality_ratchet.py --update-baseline

Ruff is additionally held to an absolute floor of zero findings for the rules
that indicate real breakage (``E9``, ``F63``, ``F7``, ``F82``: syntax errors,
undefined names, redefinitions). Those are never baselined; they always fail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / ".github" / "quality-baseline.json"

# Rules that mean the code is actually broken, not merely untidy. Never baselined.
# This is a separate, narrower selection so the check is exact: prefix matching
# here would wrongly classify F701/F702 (compact statements) as breakage.
RUFF_BREAKAGE_RULES = ("E9", "F63", "F7", "F82")

MYPY_SUMMARY = re.compile(r"Found (\d+) errors?(?: in (\d+) files?)?")
COVERAGE_XML = ROOT / "coverage.xml"


class RatchetError(RuntimeError):
    pass


def _load_baseline() -> dict:
    if not BASELINE.is_file():
        raise RatchetError(f"quality baseline is missing: {BASELINE.relative_to(ROOT)}")
    try:
        return json.loads(BASELINE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RatchetError(f"quality baseline is not valid JSON: {exc}") from exc


def _save_baseline(data: dict) -> None:
    BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _command(tool: str) -> list[str]:
    """Invoke the tool through the *current* interpreter.

    Resolving `ruff`/`mypy` from PATH silently measures whatever happens to be
    on PATH, which produced two different baselines on the same checkout
    (ruff 0.16.4 vs the pinned 0.16.9). `python -m` pins the measurement to the
    interpreter the ratchet itself runs under, so the job and the local run
    agree.
    """
    probe = subprocess.run(
        [sys.executable, "-m", tool, "--version"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        raise RatchetError(
            f"required tool is not importable by {sys.executable}: {tool}\n"
            f"install it with: {sys.executable} -m pip install -r requirements-test.txt"
        )
    return [sys.executable, "-m", tool]


def _run(command: list[str], label: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode not in (0, 1):
        # Anything other than a findings-exit means the tool itself broke.
        raise RatchetError(
            f"{label} failed to run ({completed.returncode})\n"
            f"--- stdout ---\n{completed.stdout[-4000:]}\n"
            f"--- stderr ---\n{completed.stderr[-4000:]}"
        )
    return completed


def _tool_version(tool: str) -> str:
    """Return the bare version number for a tool (e.g. ``0.16.9``).

    The raw banner differs between tools (``ruff 0.16.9`` vs
    ``mypy 2.3.1 (compiled: yes)``); only the number is recorded so the
    baseline file stays diffable.
    """
    completed = subprocess.run(
        [*_command(tool), "--version"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    banner = (completed.stdout or completed.stderr).strip()
    match = re.search(r"\d+\.\d+\.\d+", banner)
    return match.group(0) if match else banner


def _ruff_json_count(select: list[str], ignore: list[str]) -> int:
    """Count findings for an explicit rule selection.

    ``--isolated`` is deliberately *not* used: the rule selection is given
    explicitly here, but the rest of the ruff configuration (line length,
    ``extend-exclude``, per-file ignores) must still come from
    ``pyproject.toml`` so this measurement matches what a developer gets from a
    bare ``ruff check .``. Using ``--isolated`` measured a different number (96
    vs 88) purely because per-file ignores and the configured line length were
    dropped.
    """
    args = ["--select", ",".join(select)]
    if ignore:
        args += ["--ignore", ",".join(ignore)]
    completed = _run(
        [*_command("ruff"), "check", ".", *args, "--output-format=json"],
        "ruff check",
    )
    stdout = completed.stdout.strip()
    if not stdout:
        return 0
    try:
        findings = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RatchetError(f"ruff emitted output that is not JSON: {exc}") from exc
    return len(findings)


def measure_ruff(config: dict) -> tuple[int, int]:
    """Return ``(total_findings, breakage_findings)``.

    The total uses the curated baseline rule set. Breakage is counted from a
    second, narrower selection so the classification is exact rather than
    prefix-derived.
    """
    total = _ruff_json_count(list(config["select"]), list(config.get("ignore") or []))
    breakage = _ruff_json_count(list(RUFF_BREAKAGE_RULES), [])
    return total, breakage


def measure_mypy(targets: list[str]) -> int:
    completed = _run([*_command("mypy"), *targets], "mypy")
    combined = f"{completed.stdout}\n{completed.stderr}"
    match = MYPY_SUMMARY.search(combined)
    if not match:
        if "Success" in combined:
            return 0
        raise RatchetError(f"could not parse mypy output:\n{combined[-4000:]}")
    return int(match.group(1))


def measure_coverage() -> float:
    if not COVERAGE_XML.is_file():
        raise RatchetError(
            f"{COVERAGE_XML.relative_to(ROOT)} was not produced; run the coverage job first"
        )
    try:
        root = ET.parse(COVERAGE_XML).getroot()
    except ET.ParseError as exc:
        raise RatchetError(f"coverage.xml is not valid XML: {exc}") from exc

    line_rate = root.get("line-rate")
    if line_rate is not None:
        return float(line_rate) * 100.0

    covered = 0
    total = 0
    for klass in root.iter("class"):
        for line in klass.iter("line"):
            hits = line.get("hits")
            if hits is None:
                continue
            total += 1
            if int(hits) > 0:
                covered += 1
    if not total:
        raise RatchetError("coverage.xml contained no line data")
    return 100.0 * covered / total


def _round1(value: float) -> float:
    """Round to one decimal so a recorded floor never trips on float noise.

    Coverage is reported to two decimals by the XML report. A floor of 69.4
    compared against a measurement of 69.43 would otherwise report an
    improvement every run and nag for a baseline update that changes nothing.
    """
    return round(value, 1)


def _check(label: str, measured: float, ceiling: float, lower_is_better: bool) -> list[str]:
    if lower_is_better:
        if measured > ceiling:
            return [
                f"{label}: {measured:g} exceeds the baseline ceiling {ceiling:g} "
                f"(+{measured - ceiling:g} regression)"
            ]
        if measured < ceiling:
            return [f"NOTE {label}: improved to {measured:g} from {ceiling:g}; run with --update-baseline"]
        return [f"PASS {label}: {measured:g} (baseline {ceiling:g})"]

    measured = _round1(measured)
    ceiling = _round1(ceiling)
    if measured < ceiling:
        return [
            f"{label}: {measured:g}% is below the baseline floor {ceiling:g}% "
            f"({_round1(ceiling - measured):g} points lost)"
        ]
    if measured > ceiling:
        return [f"NOTE {label}: improved to {measured:g}% from {ceiling:g}%; run with --update-baseline"]
    return [f"PASS {label}: {measured:g}% (baseline {ceiling:g}%)"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="rewrite the baseline with the currently measured values",
    )
    parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="skip the coverage comparison when coverage.xml is absent",
    )
    args = parser.parse_args()

    if os.environ.get("GITHUB_ACTIONS") == "true" and args.update_baseline:
        print("REFUSING: --update-baseline is not allowed inside GitHub Actions")
        return 1

    baseline = _load_baseline()
    messages: list[str] = []

    ruff_config = baseline["ruff"]
    ruff_total, ruff_breakage = measure_ruff(ruff_config)
    print(f"ruff {_tool_version('ruff')}: {ruff_total} finding(s), {ruff_breakage} breakage")

    if ruff_breakage:
        messages.append(
            f"ruff: {ruff_breakage} breakage finding(s) under {', '.join(RUFF_BREAKAGE_RULES)}; "
            "these are never baselined"
        )
    messages += _check("ruff findings", float(ruff_total), float(ruff_config["max_errors"]), True)

    mypy_config = baseline["mypy"]
    mypy_errors = measure_mypy(list(mypy_config["targets"]))
    print(f"mypy {_tool_version('mypy')}: {mypy_errors} error(s)")
    messages += _check("mypy errors", float(mypy_errors), float(mypy_config["max_errors"]), True)

    if args.skip_coverage and not COVERAGE_XML.is_file():
        print("coverage: skipped by --skip-coverage")
    else:
        percent = measure_coverage()
        print(f"coverage: {percent:.1f}%")
        messages += _check(
            "coverage", percent, float(baseline["coverage"]["min_percent"]), False
        )

    if args.update_baseline:
        baseline["tool_versions"]["ruff"] = _tool_version("ruff")
        baseline["tool_versions"]["mypy"] = _tool_version("mypy")
        baseline["ruff"]["max_errors"] = ruff_total
        baseline["mypy"]["max_errors"] = mypy_errors
        if not args.skip_coverage or COVERAGE_XML.is_file():
            baseline["coverage"]["min_percent"] = _round1(measure_coverage())
        _save_baseline(baseline)
        print(f"\nBASELINE UPDATED: {BASELINE.relative_to(ROOT)}")

    print()
    failures: list[str] = []
    for message in messages:
        print(f"- {message}")
        if message.startswith("NOTE"):
            continue
        if message.startswith("PASS"):
            continue
        failures.append(message)

    if failures:
        print(f"\nQUALITY RATCHET: FAIL ({len(failures)} regression(s))")
        return 1
    print("\nQUALITY RATCHET: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RatchetError as error:
        print(f"QUALITY RATCHET ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
