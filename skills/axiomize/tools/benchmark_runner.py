"""Axiomize benchmark runner.

Automated layer of benchmarks/rubric.md: grades a produced report against a
test case from ideas.json.

Usage:
    python benchmark_runner.py --case epidemic-threshold --report reports/2026-08-24-epidemic.md
    python benchmark_runner.py --report-dir reports/   # auto-match by content
"""

import argparse
import json
import re
import sys
from pathlib import Path


def load_cases(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {c["id"]: c for c in data["cases"]}


def grade(text, case):
    checks = {}

    for i, token in enumerate(case["must_contain"], 1):
        alternatives = token.split("|")
        checks[f"must_contain[{i}]: {token[:40]}"] = any(
            re.search(alt, text, re.I) is not None for alt in alternatives
        )

    archetype = case["expected_archetype"]
    key = re.match(r"\w+", archetype).group(0) if archetype else ""
    checks[f"archetype concept '{key}' present"] = bool(key) and re.search(key, text, re.I) is not None

    lenses = len(re.findall(r"^#{3,4}\s+(?:Perspective|Lens)\b.*$", text, re.M))
    if lenses == 0:
        lenses = len(re.findall(r"^###\s+.*[Ll]ens", text, re.M))
    checks[f"perspectives built >= {case['min_lenses_built']} (found {lenses})"] = (
        lenses >= case["min_lenses_built"]
    )

    if case.get("must_reject_at_least_one"):
        rejected = bool(
            re.search(r"rejected?\s*(lens)?\s*[:(]", text, re.I)
            or re.search(r"\(\s*rejected", text, re.I)
        )
        checks["rejection with reason present"] = rejected

    checks["parameter Unit column non-empty"] = bool(
        re.search(r"\|\s*Unit\s*\|", text) and re.search(r"\|\s*\S+\s*\|\s*(?:exo|endo)", text, re.I | re.M)
    )
    checks["assumptions have consequences column"] = bool(
        re.search(r"[Vv]iolation consequence", text)
    )
    checks["falsifiability section"] = bool(
        re.search(r"[Ff]alsif", text)
    )
    return checks, lenses


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    here = Path(__file__).resolve().parent
    default_bench = here.parent.parent / "benchmarks" / "ideas.json"
    p.add_argument("--benchmarks", default=str(default_bench))
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--case", help="case id from ideas.json")
    g.add_argument("--case-list", action="store_true")
    p.add_argument("--report", help="produced report .md to grade")
    args = p.parse_args()

    cases = load_cases(args.benchmarks)
    if args.case_list or not args.report:
        print("\n".join(f"{cid}: {c['prompt'][:70]}" for cid, c in cases.items()))
        return 0

    if args.case not in cases:
        print(f"unknown case '{args.case}'. Available:")
        print("\n".join(cases.keys()))
        return 1

    text = Path(args.report).read_text(encoding="utf-8", errors="replace")
    checks, _ = grade(text, cases[args.case])
    passed = sum(checks.values())
    total = len(checks)

    for k, v in checks.items():
        print(f"{k:60s} {'PASS' if v else 'FAIL'}")
    score = 10 * passed / total
    verdict = "PASS" if score >= 7.5 else "FAIL"
    print(f"\nautomated score: {passed}/{total} -> {score:.1f}/10 ({verdict}; human rubric layer still required)")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
