"""Read-only CanvasXpress chart export for recorded MCP runs.

The tool consumes an integrity-checked RunState and returns a CanvasXpress
renderer payload separately from its recorded provenance. It never guesses
sensitivity scores from arbitrary numerical results or writes files.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from axiomize.limits import MAX_RUN_JSON_BYTES
from axiomize.runs.state import RunState, resolve_run_directory
from axiomize.visualization.canvasxpress_export import sensitivity_chart


def _scores_from_run(run: RunState) -> dict[str, float]:
    source: Any = run.sensitivity_results
    if not source:
        for key in ("sensitivity_results", "sensitivity_scores"):
            candidate = run.results.get(key)
            if isinstance(candidate, dict) and candidate:
                source = candidate
                break
    if isinstance(source, dict) and "scores" in source:
        source = source["scores"]
    if not isinstance(source, dict) or not source:
        raise ValueError("run has no recorded sensitivity scores")
    scores: dict[str, float] = {}
    for name, value in source.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("sensitivity parameter names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"sensitivity score for {name!r} must be numeric")
        try:
            number = float(value)
        except (OverflowError, ValueError) as exc:
            raise ValueError(f"sensitivity score for {name!r} must be finite") from exc
        if not math.isfinite(number):
            raise ValueError(f"sensitivity score for {name!r} must be finite")
        scores[name] = number
    # Sort by name before the existing magnitude sort; equal-magnitude ties
    # must not depend on the order of JSON object keys in a run record.
    return dict(sorted(scores.items()))


def visualize_recorded_run(
    run_root: str | Path, run_dir: str, *, chart_type: str = "sensitivity"
) -> dict[str, Any]:
    """Return a serializable renderer spec and an independent provenance record.

    The run is read strictly beneath run_root. Only explicitly recorded
    sensitivity scores are accepted; there is no inferred or fabricated chart.
    """
    if chart_type != "sensitivity":
        raise ValueError("chart_type must be 'sensitivity'")
    directory = resolve_run_directory(run_root, run_dir)
    for filename in ("run.json", "manifest.json"):
        candidate = directory / filename
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError(f"recorded run requires a regular {filename} file")

    run = RunState.load_under_root(run_root, run_dir)
    manifest_path = directory / "manifest.json"
    raw_manifest = manifest_path.read_bytes()
    if len(raw_manifest) > MAX_RUN_JSON_BYTES:
        raise ValueError("manifest.json exceeds the run-state size limit")
    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest.json is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must be an object")
    if not isinstance(manifest.get("run_sha256"), str):
        raise ValueError("manifest.json must record run_sha256")
    if manifest.get("input_hash") != run.input_hash():
        raise ValueError("recorded input hash does not match the run")
    versions = manifest.get("tool_versions")
    if not isinstance(versions, dict):
        raise ValueError("manifest.json must record tool_versions")

    definition = sensitivity_chart(_scores_from_run(run))
    # CanvasXpress receives only the supported data/config keys. Axiomize
    # provenance is not injected into the renderer's configuration schema.
    chart: dict[str, Any] = {
        "data": {"y": definition["y"]},
        "config": definition["config"],
    }
    canonical = json.dumps(chart, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    chart_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "chart": chart,
        "metadata": {
            "chart_spec_sha256": chart_hash,
            "run_input_sha256": run.input_hash(),
            "run_sha256": manifest["run_sha256"],
            "tool_versions": versions,
            "solver_settings": manifest.get("solver_settings", {}),
            "validation_status": run.validation_results.get("status"),
            "source": "recorded_run",
        },
    }
