"""Contract tests for the recorded-run CanvasXpress MCP bridge."""

from __future__ import annotations

import hashlib
import json

import pytest

from axiomize.runs.state import RunState
from axiomize.server.mcp_server import _call_tool, handle_message, list_tools
from axiomize.visualization.mcp_charts import visualize_recorded_run


def _record(root, scores=None):
    run = RunState(
        problem_definition="recorded sensitivity",
        sensitivity_results=scores if scores is not None else {"beta": 0.82, "gamma": -0.44, "N": 0.21},
        results={"outcome": 1.0},
        validation_results={"status": "PASS"},
        solver_settings={"rtol": 1e-9},
    )
    run.save(root / "case")
    return root / "case"


def test_tool_is_discoverable_with_strict_schema():
    entry = next(item for item in list_tools() if item["name"] == "axiomize.model_visualize")
    schema = entry["inputSchema"]
    assert schema["required"] == ["run_dir"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["chart_type"]["enum"] == ["sensitivity"]


def test_recorded_sensitivity_exports_renderer_payload_and_original_versions(tmp_path):
    folder = _record(tmp_path)
    manifest = json.loads((folder / "manifest.json").read_text())
    result = _call_tool("axiomize.model_visualize", {"run_dir": "case"}, run_root=tmp_path)
    chart, provenance = result["chart"], result["metadata"]
    assert list(chart) == ["data", "config"]
    assert chart["data"]["y"]["vars"] == ["Sensitivity"]
    assert chart["data"]["y"]["smps"] == ["N", "gamma", "beta"]
    assert chart["data"]["y"]["data"] == [[0.21, -0.44, 0.82]]
    assert chart["config"]["graphType"] == "Bar"
    assert chart["config"]["xAxisTitle"] == "Sensitivity score"
    assert provenance["run_sha256"] == manifest["run_sha256"]
    assert provenance["tool_versions"] == manifest["tool_versions"]
    assert provenance["solver_settings"] == {"rtol": 1e-9}
    assert provenance["validation_status"] == "PASS"
    expected = hashlib.sha256(
        json.dumps(chart, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        .encode("utf-8")
    ).hexdigest()
    assert provenance["chart_spec_sha256"] == expected
    assert sorted(p.name for p in folder.iterdir()) == ["manifest.json", "run.json"]


def test_chart_hash_is_stable_across_recorded_score_key_order(tmp_path):
    _record(tmp_path, {"a": 0.3, "b": -0.3})
    first = visualize_recorded_run(tmp_path, "case")
    _record(tmp_path, {"b": -0.3, "a": 0.3})
    second = visualize_recorded_run(tmp_path, "case")
    assert first["chart"] == second["chart"]
    assert first["metadata"]["chart_spec_sha256"] == second["metadata"]["chart_spec_sha256"]


def test_works_with_explicit_nested_scores_and_no_fabricated_fallback(tmp_path):
    _record(tmp_path, {"scores": {"b": -0.5, "a": 0.1}, "method": "screening"})
    assert visualize_recorded_run(tmp_path, "case")["chart"]["data"]["y"]["smps"] == ["a", "b"]
    _record(tmp_path, {})
    # No invented sensitivity values from a generic result such as 'outcome'.
    with pytest.raises(ValueError, match="no recorded sensitivity"):
        visualize_recorded_run(tmp_path, "case")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "0.3"])
def test_rejects_invalid_sensitivity_scores(tmp_path, value):
    _record(tmp_path, {"beta": value})
    with pytest.raises(ValueError, match="must be"):
        visualize_recorded_run(tmp_path, "case")


def test_rejects_unrecorded_visualization_type(tmp_path):
    _record(tmp_path)
    with pytest.raises(ValueError, match="chart_type"):
        visualize_recorded_run(tmp_path, "case", chart_type="surface")


@pytest.mark.parametrize("path", ["../elsewhere", "/etc", ""])
def test_cannot_escape_configured_run_root(tmp_path, path):
    _record(tmp_path)
    with pytest.raises(ValueError):
        visualize_recorded_run(tmp_path, path)


def test_rejects_modified_record(tmp_path):
    folder = _record(tmp_path)
    path = folder / "run.json"
    content = json.loads(path.read_text())
    content["sensitivity_results"]["beta"] = 999.0
    path.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="integrity"):
        visualize_recorded_run(tmp_path, "case")


def test_rejects_missing_manifest(tmp_path):
    folder = _record(tmp_path)
    (folder / "manifest.json").unlink()
    with pytest.raises(ValueError, match="manifest.json"):
        visualize_recorded_run(tmp_path, "case")


def test_rejects_symlink_to_external_manifest(tmp_path):
    folder = _record(tmp_path)
    external = tmp_path / "manifest-outside.json"
    external.write_text((folder / "manifest.json").read_text())
    (folder / "manifest.json").unlink()
    (folder / "manifest.json").symlink_to(external)
    with pytest.raises(ValueError, match="regular manifest.json"):
        visualize_recorded_run(tmp_path, "case")


def test_jsonrpc_roundtrip_and_error_response(tmp_path):
    _record(tmp_path)
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "axiomize.model_visualize",
            "arguments": {"run_dir": "case"},
        },
    }
    response = handle_message(request, run_root=tmp_path)
    assert response["id"] == 7
    assert response["result"]["isError"] is False
    result = json.loads(response["result"]["content"][0]["text"])
    assert result["chart"]["data"]["y"]["smps"] == ["N", "gamma", "beta"]
    request["params"]["arguments"]["run_dir"] = "../outside"
    error = handle_message(request, run_root=tmp_path)
    assert error["error"]["code"] == -32602
