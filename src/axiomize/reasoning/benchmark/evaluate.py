"""Evaluate baseline and quantum-reasoning runs from JSONL files.

The evaluator uses only the Python standard library. It does not call a model.
External runners can write one result row per case and this script will validate,
score, summarize, and compare those runs without inventing missing measurements.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable


REQUIRED_RESULT_FIELDS = {
    "case_id",
    "answer",
    "tokens",
    "tool_calls",
    "latency_ms",
}

OPTIONAL_TELEMETRY_FIELDS = {
    "branches_total",
    "branches_distinct",
    "revived_branches",
    "recovered_errors",
    "contradictions_found",
    "contradictions_resolved",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: row must be a JSON object")
            rows.append(value)
    return rows


def normalize_answer(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split())


def validate_case(case: dict[str, Any]) -> None:
    for field in ("id", "domain", "prompt", "accepted_answers"):
        if field not in case:
            raise ValueError(f"case missing required field: {field}")
    if not isinstance(case["accepted_answers"], list) or not case["accepted_answers"]:
        raise ValueError(f"case {case['id']!r}: accepted_answers must be a non-empty list")


def validate_result(result: dict[str, Any]) -> None:
    missing = REQUIRED_RESULT_FIELDS - set(result)
    if missing:
        raise ValueError(
            f"result {result.get('case_id', '<unknown>')!r} missing fields: "
            + ", ".join(sorted(missing))
        )
    for field in ("tokens", "tool_calls", "latency_ms"):
        value = result[field]
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"result {result['case_id']!r}: {field} must be non-negative")
    for field in OPTIONAL_TELEMETRY_FIELDS:
        if field in result:
            value = result[field]
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(
                    f"result {result['case_id']!r}: {field} must be non-negative"
                )
    if "branches_distinct" in result and "branches_total" in result:
        if result["branches_distinct"] > result["branches_total"]:
            raise ValueError(
                f"result {result['case_id']!r}: branches_distinct cannot exceed branches_total"
            )
    if "contradictions_resolved" in result and "contradictions_found" in result:
        if result["contradictions_resolved"] > result["contradictions_found"]:
            raise ValueError(
                f"result {result['case_id']!r}: contradictions_resolved cannot exceed contradictions_found"
            )


def answer_is_correct(case: dict[str, Any], answer: Any) -> bool:
    normalized = normalize_answer(answer)
    accepted = {normalize_answer(value) for value in case["accepted_answers"]}
    return normalized in accepted


def safe_mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    if not materialized:
        return None
    return statistics.fmean(materialized)


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def summarize(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    for case in cases:
        validate_case(case)
    for result in results:
        validate_result(result)

    case_by_id = {str(case["id"]): case for case in cases}
    if len(case_by_id) != len(cases):
        raise ValueError("case ids must be unique")

    result_by_id: dict[str, dict[str, Any]] = {}
    for result in results:
        case_id = str(result["case_id"])
        if case_id in result_by_id:
            raise ValueError(f"duplicate result for case_id {case_id!r}")
        if case_id not in case_by_id:
            raise ValueError(f"result references unknown case_id {case_id!r}")
        result_by_id[case_id] = result

    missing_cases = sorted(set(case_by_id) - set(result_by_id))
    evaluated = []
    for case_id, result in result_by_id.items():
        case = case_by_id[case_id]
        evaluated.append((case, result, answer_is_correct(case, result["answer"])))

    total = len(evaluated)
    correct = sum(int(is_correct) for _, _, is_correct in evaluated)

    branch_rows = [
        result
        for _, result, _ in evaluated
        if "branches_total" in result and "branches_distinct" in result
    ]
    contradiction_rows = [
        result
        for _, result, _ in evaluated
        if "contradictions_found" in result and "contradictions_resolved" in result
    ]

    total_branches = sum(row["branches_total"] for row in branch_rows)
    distinct_branches = sum(row["branches_distinct"] for row in branch_rows)
    contradictions_found = sum(row["contradictions_found"] for row in contradiction_rows)
    contradictions_resolved = sum(
        row["contradictions_resolved"] for row in contradiction_rows
    )

    return {
        "cases_defined": len(cases),
        "cases_evaluated": total,
        "missing_case_ids": missing_cases,
        "accuracy": safe_ratio(correct, total),
        "mean_tokens": safe_mean(float(result["tokens"]) for _, result, _ in evaluated),
        "mean_tool_calls": safe_mean(
            float(result["tool_calls"]) for _, result, _ in evaluated
        ),
        "mean_latency_ms": safe_mean(
            float(result["latency_ms"]) for _, result, _ in evaluated
        ),
        "branch_diversity_ratio": safe_ratio(distinct_branches, total_branches),
        "revival_rate_per_case": safe_mean(
            float(result.get("revived_branches", 0)) for _, result, _ in evaluated
        ),
        "error_recovery_rate_per_case": safe_mean(
            float(result.get("recovered_errors", 0)) for _, result, _ in evaluated
        ),
        "contradiction_resolution_rate": safe_ratio(
            contradictions_resolved, contradictions_found
        ),
    }


def percent_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return ((new - old) / old) * 100.0


def absolute_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None:
        return None
    return new - old


def compare(baseline: dict[str, Any], skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "accuracy_delta": absolute_change(skill["accuracy"], baseline["accuracy"]),
        "tokens_percent_change": percent_change(
            skill["mean_tokens"], baseline["mean_tokens"]
        ),
        "tool_calls_percent_change": percent_change(
            skill["mean_tool_calls"], baseline["mean_tool_calls"]
        ),
        "latency_percent_change": percent_change(
            skill["mean_latency_ms"], baseline["mean_latency_ms"]
        ),
        "branch_diversity_delta": absolute_change(
            skill["branch_diversity_ratio"], baseline["branch_diversity_ratio"]
        ),
        "contradiction_resolution_delta": absolute_change(
            skill["contradiction_resolution_rate"],
            baseline["contradiction_resolution_rate"],
        ),
    }


def ensure_finite(value: Any, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} is not finite")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = read_jsonl(args.cases)
    skill_results = read_jsonl(args.skill)
    skill_summary = summarize(cases, skill_results)

    payload: dict[str, Any] = {"skill": skill_summary}
    if args.baseline:
        baseline_results = read_jsonl(args.baseline)
        baseline_summary = summarize(cases, baseline_results)
        payload["baseline"] = baseline_summary
        payload["comparison"] = compare(baseline_summary, skill_summary)

    for section_name, section in payload.items():
        if isinstance(section, dict):
            for key, value in section.items():
                ensure_finite(value, f"{section_name}.{key}")

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
