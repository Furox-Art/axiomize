"""Explain why two reproducible Axiomize runs differ."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from axiomize.runs.state import RunState


def _changed_mapping(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key in sorted(set(a) | set(b)):
        av = a.get(key)
        bv = b.get(key)
        if av != bv:
            changed[key] = {"before": av, "after": bv}
    return changed


def _load_manifest(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir) / "manifest.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def compare_run_states(before: RunState, after: RunState,
                       *, before_manifest: dict[str, Any] | None = None,
                       after_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a structured explanation of reproducibility differences."""
    categories: dict[str, Any] = {}

    parameter_changes = _changed_mapping(before.parameters, after.parameters)
    if parameter_changes:
        categories["parameters"] = parameter_changes

    solver_changes = _changed_mapping(before.solver_settings, after.solver_settings)
    if solver_changes:
        categories["solver_settings"] = solver_changes

    policy_changes = _changed_mapping(before.workflow_policy, after.workflow_policy)
    if policy_changes:
        categories["workflow_policy"] = policy_changes

    if before.datasets != after.datasets:
        categories["datasets"] = {"before": before.datasets, "after": after.datasets}
    if before.data_transformations != after.data_transformations:
        categories["data_transformations"] = {
            "before": before.data_transformations,
            "after": after.data_transformations,
        }
    if before.assumptions != after.assumptions:
        categories["assumptions"] = {"before": before.assumptions, "after": after.assumptions}
    if before.selected_model != after.selected_model:
        categories["selected_model"] = {
            "before": before.selected_model,
            "after": after.selected_model,
        }
    if before.equations != after.equations:
        categories["equations"] = {"before": before.equations, "after": after.equations}

    before_manifest = dict(before_manifest or {})
    after_manifest = dict(after_manifest or {})
    version_changes = _changed_mapping(
        dict(before_manifest.get("tool_versions", {})),
        dict(after_manifest.get("tool_versions", {})),
    )
    if version_changes:
        categories["tool_versions"] = version_changes

    result_changes = _changed_mapping(before.results, after.results)
    if result_changes:
        categories["results"] = result_changes

    reasons: list[str] = []
    reason_map = {
        "parameters": "model parameters changed",
        "solver_settings": "solver/numerical settings changed",
        "workflow_policy": "workflow rigor/permissions changed",
        "datasets": "dataset references changed",
        "data_transformations": "data cleaning/transformation changed",
        "assumptions": "model assumptions changed",
        "selected_model": "a different candidate model was selected",
        "equations": "model equations changed",
        "tool_versions": "software/tool versions changed",
    }
    for category, reason in reason_map.items():
        if category in categories:
            reasons.append(reason)

    same_inputs = before.input_hash() == after.input_hash()
    if same_inputs and "tool_versions" not in categories and result_changes:
        reasons.append(
            "recorded inputs and tool versions match; investigate randomness, hidden environment differences, or nondeterministic external data"
        )
    if not reasons and not result_changes:
        reasons.append("no recorded reproducibility difference detected")

    return {
        "same_input_hash": same_inputs,
        "same_results": not bool(result_changes),
        "differences": categories,
        "likely_reasons": reasons,
    }


def compare_run_directories(before_dir: str | Path, after_dir: str | Path) -> dict[str, Any]:
    before = RunState.load(before_dir)
    after = RunState.load(after_dir)
    return compare_run_states(
        before,
        after,
        before_manifest=_load_manifest(before_dir),
        after_manifest=_load_manifest(after_dir),
    )
