"""Axiomize benchmark runner.

Automated layer of benchmarks/rubric.md: grades a produced report against a
test case from ideas.json. Custom benchmark files are treated as untrusted data:
matching uses a small literal-alternative grammar rather than arbitrary regex.
"""

import argparse
import json
import re
import sys
from pathlib import Path

MAX_BENCHMARK_BYTES = 4 * 1024 * 1024
MAX_REPORT_BYTES = 64 * 1024 * 1024
MAX_CASES = 10_000
MAX_PATTERNS_PER_CASE = 1_000


def _bounded_text(path, maximum, label):
    target = Path(path)
    if not target.is_file():
        raise SystemExit(f"{label} not found: {target}")
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise SystemExit(f"cannot stat {label}: {exc}") from exc
    if size > maximum:
        raise SystemExit(f"{label} exceeds hard size limit {maximum} bytes")
    try:
        return target.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise SystemExit(f"cannot read {label}: {exc}") from exc


def load_cases(path):
    if not path:
        raise SystemExit("benchmark dataset not found; pass --benchmarks <ideas.json>")
    text = _bounded_text(path, MAX_BENCHMARK_BYTES, "benchmark dataset")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"benchmark dataset is invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise SystemExit("benchmark dataset must contain a cases array")
    if len(data["cases"]) > MAX_CASES:
        raise SystemExit(f"benchmark dataset exceeds hard case limit {MAX_CASES}")
    cases = {}
    for index, case in enumerate(data["cases"]):
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"].strip():
            raise SystemExit(f"benchmark case {index} needs a non-empty string id")
        must = case.get("must_contain", [])
        if not isinstance(must, list) or len(must) > MAX_PATTERNS_PER_CASE or not all(isinstance(v, str) for v in must):
            raise SystemExit(f"benchmark case {case['id']!r} has invalid must_contain")
        if case["id"] in cases:
            raise SystemExit(f"duplicate benchmark case id: {case['id']}")
        cases[case["id"]] = case
    return cases


_STOPWORDS = {"a", "an", "the", "and", "or", "of", "on", "in", "with", "for", "to"}
_WORD_BOUNDARY_LITERAL = re.compile(r"^\\b([A-Za-z0-9_.+/-]+)\\b$")


def _literal_alt_present(alt, text_lower):
    """Safe matching grammar: ``a|b`` alternatives + optional ``\bword\b``.

    No caller-controlled text is compiled as a regular expression, preventing a
    custom benchmark file from turning grading into a regex denial-of-service.
    """
    alt = alt.strip()
    if not alt:
        return False
    word = _WORD_BOUNDARY_LITERAL.fullmatch(alt)
    if word:
        token = word.group(1).lower()
        return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text_lower) is not None
    return alt.lower() in text_lower


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
    if not isinstance(text, str):
        raise ValueError("report must be text")
    checks = {}
    text_lower = text.lower()
    for i, token in enumerate(case["must_contain"], 1):
        alternatives = token.split("|")
        checks[f"must_contain[{i}]: {token[:40]}"] = any(
            _literal_alt_present(alt, text_lower) for alt in alternatives
        )

    archetype = case.get("expected_archetype", "")
    if archetype:
        alts = [a.strip() for a in str(archetype).split(" / ") if a.strip()]
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
    minimum_lenses = int(case.get("min_lenses_built", 0))
    if minimum_lenses < 0 or minimum_lenses > 1000:
        raise ValueError("min_lenses_built must be in [0, 1000]")
    checks[f"perspectives built >= {minimum_lenses} (found {lenses})"] = lenses >= minimum_lenses

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
        if not isinstance(oracle, dict) or "keyword" not in oracle or "expected" not in oracle or "tolerance" not in oracle:
            raise ValueError("numeric_oracle requires keyword, expected, tolerance")
        kw = str(oracle["keyword"])
        expected = float(oracle["expected"])
        tol = float(oracle["tolerance"])
        if not (math.isfinite(expected) and math.isfinite(tol) and tol >= 0):
            raise ValueError("numeric oracle expected/tolerance must be finite and tolerance non-negative")
        match = re.search(rf"{re.escape(kw)}[^0-9\n]{{0,128}}([0-9]*\.?[0-9]+)", text, re.IGNORECASE)
        ok = bool(match and abs(float(match.group(1)) - expected) <= tol)
        checks[f"numeric oracle {kw} ~ {expected} ±{tol}"] = ok

    return checks, lenses


def _default_benchmark_path():
    here = Path(__file__).resolve().parent
    candidates = [
        here.parents[2] / "benchmarks" / "ideas.json",
        Path.cwd() / "benchmarks" / "ideas.json",
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
        print("\n".join(f"{cid}: {str(c.get('prompt', ''))[:70]}" for cid, c in cases.items()))
        return 0

    text = _bounded_text(args.report, MAX_REPORT_BYTES, "benchmark report")
    try:
        checks, _ = grade(text, cases[args.case])
    except (TypeError, ValueError, OverflowError) as exc:
        print(f"benchmark definition error: {exc}")
        return 1
    passed = sum(checks.values())
    total = len(checks)
    for key, value in checks.items():
        print(f"{key:60s} {'PASS' if value else 'FAIL'}")
    score = 10 * passed / total
    verdict = "PASS" if score >= 7.5 else "FAIL"
    print(f"\nautomated score: {passed}/{total} -> {score:.1f}/10 ({verdict}; human rubric layer still required)")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    import math
    sys.exit(main())
