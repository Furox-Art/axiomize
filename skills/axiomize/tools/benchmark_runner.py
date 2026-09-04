"""Axiomize benchmark runner.

Automated layer of benchmarks/rubric.md: grades a produced report against a
test case from ideas.json. The default benchmark dataset is resolved both from
a source checkout and from the PyPI wheel.
"""

import argparse
import json
import re
import sys
from pathlib import Path


def load_cases(path):
    if not path:
        raise SystemExit("benchmark dataset not found; pass --benchmarks <ideas.json>")
    target = Path(path)
    if not target.is_file():
        raise SystemExit(f"benchmark dataset not found: {target}")
    data = json.loads(target.read_text(encoding="utf-8"))
    return {c["id"]: c for c in data["cases"]}


_STOPWORDS = {"a", "an", "the", "and", "or", "of", "on", "in", "with", "for", "to"}


def _alt_tokens_present(alt, text_lower):
    tokens = re.findall(r"[a-z0-9][a-z0-9./-]*", alt.lower())
    for tok in tokens:
        if tok in _STOPWORDS:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(tok)}s?(?![a-z0-9])"
        if not re.search(pattern, text_lower):
            return False
    return True


def grade(text, case):
    checks = {}
    for i, token in enumerate(case["must_contain"], 1):
        alternatives = token.split("|")
        checks[f"must_contain[{i}]: {token[:40]}"] = any(
            re.search(alt, text, re.IGNORECASE) is not None for alt in alternatives
        )

    archetype = case["expected_archetype"]
    if archetype:
        alts = [a.strip() for a in archetype.split(" / ") if a.strip()]
        text_lower = text.lower()
        present = any(_alt_tokens_present(alt, text_lower) for alt in alts)
        checks[f"archetype '{archetype}' present"] = present
    else:
        checks["archetype present"] = False

    lenses = 0
    m = re.search(r"^##\s+4\.?\s+Perspective models.*?\n", text, re.MULTILINE | re.IGNORECASE)
    if m:
        start = m.end()
        nxt = re.search(r"^##\s+\d+\.", text[start:], re.MULTILINE)
        section = text[start : start + nxt.start()] if nxt else text[start:]
        lenses = len(re.findall(r"^###\s+", section, re.MULTILINE))
        non_lens = len(re.findall(r"^###\s+(?:Excluded|Derived)", section, re.MULTILINE | re.IGNORECASE))
        lenses = max(0, lenses - non_lens)
    if lenses == 0:
        lenses = len(
            re.findall(
                r"^###\s+(?:Lens|Perspective|\d+\.\d+|Deterministic|Stochastic|Network|Control|Optimization|Game|Causal|Information|Reliability|Thermodynamic|Decision|Demographic|Spatial|Agent)",
                text,
                re.MULTILINE | re.IGNORECASE,
            )
        )
    checks[f"perspectives built >= {case['min_lenses_built']} (found {lenses})"] = lenses >= case["min_lenses_built"]

    if case.get("must_reject_at_least_one"):
        rejected = bool(
            re.search(r"rejected?\s*(lenses?)?\s*[:(]", text, re.IGNORECASE)
            or re.search(r"\(\s*rejected", text, re.IGNORECASE)
        )
        checks["rejection with reason present"] = rejected

    checks["parameter Unit column non-empty"] = bool(
        re.search(r"\|\s*Unit\s*\|", text)
        and re.search(r"\|\s*\S+\s*\|\s*(?:exo|endo)", text, re.IGNORECASE | re.MULTILINE)
    )
    checks["assumptions have consequences column"] = bool(re.search(r"[Vv]iolation consequence", text))
    checks["falsifiability section"] = bool(re.search(r"[Ff]alsif", text))

    if "numeric_oracle" in case:
        oracle = case["numeric_oracle"]
        kw = oracle["keyword"]
        expected = float(oracle["expected"])
        tol = float(oracle["tolerance"])
        match = re.search(rf"{re.escape(kw)}[^0-9]*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1))
                ok = abs(value - expected) <= tol
            except ValueError:
                ok = False
        else:
            ok = False
        checks[f"numeric oracle {kw} ~ {expected} ±{tol}"] = ok

    return checks, lenses


def _default_benchmark_path() -> str:
    here = Path(__file__).resolve().parent
    candidates = [
        # Source checkout: skills/axiomize/tools -> repository root.
        here.parents[2] / "benchmarks" / "ideas.json",
        Path.cwd() / "benchmarks" / "ideas.json",
        # Installed wheel: axiomize/tools -> axiomize/data.
        here.parent / "data" / "benchmark_ideas.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--benchmarks", default=_default_benchmark_path())
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", help="case id from ideas.json")
    group.add_argument("--case-list", action="store_true")
    parser.add_argument("--report", help="produced report .md to grade")
    args = parser.parse_args()

    cases = load_cases(args.benchmarks)
    if args.case and args.case not in cases:
        print(f"unknown case '{args.case}'. Available:")
        print("\n".join(cases.keys()))
        return 1
    if args.case_list or not args.report:
        print("\n".join(f"{cid}: {c['prompt'][:70]}" for cid, c in cases.items()))
        return 0

    text = Path(args.report).read_text(encoding="utf-8", errors="replace")
    checks, _ = grade(text, cases[args.case])
    passed = sum(checks.values())
    total = len(checks)
    for key, value in checks.items():
        print(f"{key:60s} {'PASS' if value else 'FAIL'}")
    score = 10 * passed / total
    verdict = "PASS" if score >= 7.5 else "FAIL"
    print(f"\nautomated score: {passed}/{total} -> {score:.1f}/10 ({verdict}; human rubric layer still required)")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
