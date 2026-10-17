"""Recorded scientific-run comparison separates inputs, software, and stochastic results."""

from __future__ import annotations

import json

import pytest

from axiomize.runs.compare import (
    _changed_mapping,
    _load_manifest,
    compare_run_directories,
    compare_run_states,
)
from axiomize.runs.state import RunState


def state(**kwargs):
    return RunState(problem_definition="fixed scientific problem", **kwargs)


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ({}, {}, {}),
        ({"x": 1}, {"x": 1}, {}),
        ({"x": 1}, {"x": 2}, {"x": {"before": 1, "after": 2}}),
        ({"x": 1}, {}, {"x": {"before": 1, "after": None}}),
        ({}, {"x": 1}, {"x": {"before": None, "after": 1}}),
    ],
)
def test_scientific_comparison_reports_explicit_mapping_delta(first, second, expected):
    assert _changed_mapping(first, second) == expected


@pytest.mark.parametrize(
    ("field", "old", "new", "reason"),
    [
        ("parameters", {"k": 0.1}, {"k": 0.3}, "model parameters changed"),
        ("solver_settings", {"rtol": 1e-3}, {"rtol": 1e-5}, "solver/numerical settings changed"),
        ("workflow_policy", {"rigor": "standard"}, {"rigor": "research"}, "workflow rigor/permissions changed"),
        ("datasets", ["dataset-A"], ["dataset-B"], "dataset references changed"),
        ("data_transformations", [], [{"sort": True}], "data cleaning/transformation changed"),
        ("assumptions", ["constant k"], ["variable k"], "model assumptions changed"),
        ("selected_model", "ode", "pde", "different candidate model"),
        ("equations", ["dx/dt=-x"], ["dx/dt=-2*x"], "model equations changed"),
    ],
)
def test_run_comparison_identifies_exact_source_of_difference(field, old, new, reason):
    before = state(**{field: old})
    after = state(**{field: new})
    report = compare_run_states(before, after)
    assert field in report["differences"]
    assert any(reason in entry for entry in report["likely_reasons"])
    assert report["same_input_hash"] is False or field == "selected_model"


def test_identical_recorded_inputs_results_and_tool_versions_have_no_claimed_differences():
    a = state(parameters={"k": 0.2}, results={"status": "PASS"})
    b = state(parameters={"k": 0.2}, results={"status": "PASS"})
    out = compare_run_states(a, b)
    assert out["same_input_hash"] is True
    assert out["same_results"] is True
    assert out["differences"] == {}
    assert out["likely_reasons"] == ["no recorded reproducibility difference detected"]


def test_same_inputs_different_results_are_flagged_as_reproducibility_risk():
    a = state(parameters={"k": 0.2}, results={"outcome": 1.0})
    b = state(parameters={"k": 0.2}, results={"outcome": 2.0})
    out = compare_run_states(a, b)
    assert out["same_input_hash"] is True
    assert out["same_results"] is False
    assert out["differences"]["results"]["outcome"] == {"before": 1.0, "after": 2.0}
    assert any("randomness" in entry for entry in out["likely_reasons"])


def test_software_version_mismatch_is_distinct_from_changed_physical_parameters():
    a = state(parameters={"k": 0.2}, results={"value": 1.0})
    b = state(parameters={"k": 0.2}, results={"value": 1.0})
    before = {"tool_versions": {"numpy": "old"}}
    after = {"tool_versions": {"numpy": "new"}}
    out = compare_run_states(a, b, before_manifest=before, after_manifest=after)
    assert out["same_input_hash"] is True
    assert out["same_results"] is True
    assert out["differences"]["tool_versions"]["numpy"] == {"before": "old", "after": "new"}
    assert "software/tool versions changed" in out["likely_reasons"]


def test_result_difference_with_version_change_does_not_falsely_claim_same_environment():
    a = state(parameters={"k": 0.2}, results={"value": 1.0})
    b = state(parameters={"k": 0.2}, results={"value": 2.0})
    out = compare_run_states(
        a, b, before_manifest={"tool_versions": {"numpy": "old"}}, after_manifest={"tool_versions": {"numpy": "new"}}
    )
    assert "software/tool versions changed" in out["likely_reasons"]
    assert not any("tool versions match" in reason for reason in out["likely_reasons"])


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, {}),
        ("[]", {}),
        ("{}", {}),
        ('{"tool_versions":{"numpy":"1.0"}}', {"tool_versions": {"numpy": "1.0"}}),
    ],
)
def test_manifest_read_is_conservative_on_absence_or_invalid_top_level_shape(tmp_path, content, expected):
    if content is not None:
        (tmp_path / "manifest.json").write_text(content)
    assert _load_manifest(tmp_path) == expected


def test_compare_directories_uses_recorded_manifest_and_not_ambient_tool_versions(monkeypatch, tmp_path):
    import axiomize.runs.compare as comparison

    first = tmp_path / "before"
    second = tmp_path / "after"
    first.mkdir()
    second.mkdir()
    (first / "manifest.json").write_text(json.dumps({"tool_versions": {"backend": "v1"}}))
    (second / "manifest.json").write_text(json.dumps({"tool_versions": {"backend": "v2"}}))
    old = state(results={"status": "PASS"})
    new = state(results={"status": "PASS"})
    monkeypatch.setattr(comparison.RunState, "load", lambda path: old if str(path) == str(first) else new)
    report = compare_run_directories(first, second)
    assert report["differences"]["tool_versions"]["backend"] == {"before": "v1", "after": "v2"}
    assert report["same_results"] is True
