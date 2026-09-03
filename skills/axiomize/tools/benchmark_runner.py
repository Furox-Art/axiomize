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


_STOPWORDS = {"a", "an", "the", "and", "or", "of", "on", "in", "with", "for", "to"}


def _alt_tokens_present(alt, text_lower):
    """True if every significant token of `alt` occurs in `text_lower` as a
    whole word (optional trailing plural "s"). A lone letter like "m" from a
    mangled "M/M/c" split can never satisfy this."""
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

    # Archetype gate. Two traps to avoid:
    #   - splitting alternatives on "/" alone breaks "M/M/c queueing" into
    #     ["M", "M", "c queueing"], and the bare "M" matches nearly every
    #     report - the gate always passed. Alternatives are separated by
    #     " / " (with spaces); slashes inside a term are part of it.
    #   - requiring the exact phrase is too brittle ("Bertrand duopoly" vs
    #     "differentiated Bertrand ... duopoly"). Instead every significant
    #     token of the alternative must appear as a whole word (plural folded),
    #     so "m/m/c" AND "queueing" are both required while word order and
    #     qualifiers stay free.
    archetype = case["expected_archetype"]
    if archetype:
        alts = [a.strip() for a in archetype.split(" / ") if a.strip()]
        text_lower = text.lower()
        present = any(_alt_tokens_present(alt, text_lower) for alt in alts)
        checks[f"archetype '{archetype}' present"] = present
    else:
        checks["archetype present"] = False

    # Lens count: reports use varied heading shapes ("### Lens A:", "### Perspective:",
    # "### Deterministic", "### 4.1 Deterministic"). The old regex only matched
    # "Perspective" and "Lens", so epidemic-threshold and app-adoption-ceiling
    # both scored 0 despite having 4 lenses. Count headings inside the
    # "## 4. Perspective models" section instead, falling back to any lens-like
    # heading elsewhere.
    lenses = 0
    # Try to isolate the perspective-models section
    m = re.search(r"^##\s+4\.?\s+Perspective models.*?\n", text, re.MULTILINE | re.IGNORECASE)
    if m:
        start = m.end()
        nxt = re.search(r"^##\s+\d+\.", text[start:], re.MULTILINE)
        section = text[start : start + nxt.start()] if nxt else text[start:]
        lenses = len(re.findall(r"^###\s+", section, re.MULTILINE))
        # Exclude non-lens subsections like "Excluded parameters" if present
        non_lens = len(re.findall(r"^###\s+(?:Excluded|Derived)", section, re.MULTILINE | re.IGNORECASE))
        lenses = max(0, lenses - non_lens)
    if lenses == 0:
        # Fallback: any heading that looks like a lens
        lenses = len(
            re.findall(
                r"^###\s+(?:Lens|Perspective|\d+\.\d+|Deterministic|Stochastic|Network|Control|Optimization|Game|Causal|Information|Reliability|Thermodynamic|Decision|Demographic|Spatial|Agent)",
                text,
                re.MULTILINE | re.IGNORECASE,
            )
        )
    checks[f"perspectives built >= {case['min_lenses_built']} (found {lenses})"] = (
        lenses >= case["min_lenses_built"]
    )

    if case.get("must_reject_at_least_one"):
        # The report template's section heading is "Rejected lenses (one line
        # each)", so the optional word must allow the plural too, the old
        # pattern only accepted "lens" and silently missed every report that
        # used the template verbatim.
        rejected = bool(
            re.search(r"rejected?\s*(lenses?)?\s*[:(]", text, re.IGNORECASE)
            or re.search(r"\(\s*rejected", text, re.IGNORECASE)
        )
        checks["rejection with reason present"] = rejected

    checks["parameter Unit column non-empty"] = bool(
        re.search(r"\|\s*Unit\s*\|", text) and re.search(r"\|\s*\S+\s*\|\s*(?:exo|endo)", text, re.IGNORECASE | re.MULTILINE)
    )
    checks["assumptions have consequences column"] = bool(
        re.search(r"[Vv]iolation consequence", text)
    )
    checks["falsifiability section"] = bool(
        re.search(r"[Ff]alsif", text)
    )

    # Numeric oracle (optional), if present, the report must contain a number
    # near the expected value after the keyword. This is the first step toward
    # verifying correctness, not just template compliance. Example: the
    # deliberately nonsensical R0=beta+gamma report scored 10/10 because every
    # check was structural; a numeric oracle would have caught it.
    if "numeric_oracle" in case:
        oracle = case["numeric_oracle"]
        kw = oracle["keyword"]
        expected = float(oracle["expected"])
        tol = float(oracle["tolerance"])
        m = re.search(rf"{re.escape(kw)}[^0-9]*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1))
                ok = abs(val - expected) <= tol
            except ValueError:
                ok = False
        else:
            ok = False
        checks[f"numeric oracle {kw} ~ {expected} ±{tol}"] = ok

    return checks, lenses


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    here = Path(__file__).resolve().parent
    candidates = [
        here.parents[2] / "benchmarks" / "ideas.json",
        Path.cwd() / "benchmarks" / "ideas.json",
    ]
    default_bench = next((str(c) for c in candidates if c.exists()), "")
    p.add_argument("--benchmarks", default=str(default_bench))
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--case", help="case id from ideas.json")
    g.add_argument("--case-list", action="store_true")
    p.add_argument("--report", help="produced report .md to grade")
    args = p.parse_args()

    cases = load_cases(args.benchmarks)
    if args.case and args.case not in cases:
        print(f"unknown case '{args.case}'. Available:")
        print("\n".join(cases.keys()))
        return 1
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
