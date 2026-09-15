"""Validate reproducible community benchmark result bundles."""
from __future__ import annotations
import argparse, json, re
from datetime import date
from pathlib import Path
import evaluate

REQUIRED_FILES = {"metadata.json", "cases.jsonl", "baseline.jsonl", "skill.jsonl", "comparison.json", "README.md"}
COND_FIELDS = {"instruction_config", "sampling", "tool_availability", "context_limit", "output_limit"}
META_FIELDS = {"provider", "model", "run_date", "skill_version", "repetitions_per_case", "baseline", "skill", "failures_recorded"}


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc


def validate_metadata(meta: dict) -> None:
    if not isinstance(meta, dict):
        raise ValueError("metadata.json must contain a JSON object")
    missing = META_FIELDS - set(meta)
    if missing:
        raise ValueError(f"metadata.json missing fields: {sorted(missing)}")
    for key in ("provider", "model", "skill_version"):
        if not isinstance(meta[key], str) or not meta[key].strip():
            raise ValueError(f"metadata.{key} must be a non-empty string")
    try:
        date.fromisoformat(meta["run_date"])
    except Exception as exc:
        raise ValueError("metadata.run_date must be YYYY-MM-DD") from exc
    if not isinstance(meta["repetitions_per_case"], int) or meta["repetitions_per_case"] < 1:
        raise ValueError("metadata.repetitions_per_case must be >= 1")
    if meta["failures_recorded"] is not True:
        raise ValueError("metadata.failures_recorded must be true")
    for name in ("baseline", "skill"):
        value = meta[name]
        if not isinstance(value, dict):
            raise ValueError(f"metadata.{name} must be an object")
        missing_cond = COND_FIELDS - set(value)
        if missing_cond:
            raise ValueError(f"metadata.{name} missing fields: {sorted(missing_cond)}")
        if not isinstance(value["instruction_config"], str) or not value["instruction_config"].strip():
            raise ValueError(f"metadata.{name}.instruction_config must be non-empty")
        if not isinstance(value["sampling"], dict):
            raise ValueError(f"metadata.{name}.sampling must be an object")
        for limit in ("context_limit", "output_limit"):
            v = value[limit]
            if v is not None and (not isinstance(v, int) or v < 1):
                raise ValueError(f"metadata.{name}.{limit} must be null or >= 1")


def _case_map(cases):
    out = {}
    for case in cases:
        evaluate.validate_case(case)
        cid = str(case["id"])
        if cid in out:
            raise ValueError(f"duplicate case id: {cid}")
        out[cid] = case
    return out


def validate_bundle(bundle: Path) -> None:
    missing = REQUIRED_FILES - {p.name for p in bundle.iterdir() if p.is_file()}
    if missing:
        raise ValueError(f"{bundle}: missing files: {sorted(missing)}")
    validate_metadata(load_json(bundle / "metadata.json"))
    cases = evaluate.read_jsonl(bundle / "cases.jsonl")
    case_by_id = _case_map(cases)
    baseline = evaluate.read_jsonl(bundle / "baseline.jsonl")
    skill = evaluate.read_jsonl(bundle / "skill.jsonl")
    for row in baseline + skill:
        evaluate.validate_result(row)
    for label, rows in (("baseline", baseline), ("skill", skill)):
        ids = [str(r["case_id"]) for r in rows]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{bundle}: duplicate {label} case_id")
        if set(ids) != set(case_by_id):
            raise ValueError(f"{bundle}: {label} must contain exactly one row for every case")
    expected = {
        "skill": evaluate.summarize(cases, skill),
        "baseline": evaluate.summarize(cases, baseline),
    }
    expected["comparison"] = evaluate.compare(expected["baseline"], expected["skill"])
    submitted = load_json(bundle / "comparison.json")
    if submitted != expected:
        raise ValueError(f"{bundle}: comparison.json does not match evaluator recomputation")
    if not (bundle / "README.md").read_text(encoding="utf-8").strip():
        raise ValueError(f"{bundle}: README.md must not be empty")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("benchmark/results/community"))
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()
    root = args.root
    if not root.exists():
        if args.allow_empty:
            return 0
        raise SystemExit(f"community benchmark root not found: {root}")
    bundles = sorted(p for p in root.iterdir() if p.is_dir())
    if not bundles and not args.allow_empty:
        raise SystemExit("no community benchmark bundles found")
    for bundle in bundles:
        validate_bundle(bundle)
        print(f"validated {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
