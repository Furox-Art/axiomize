"""Round-2 coverage: recorded-run charts, CanvasXpress export, run state/bundles.

Filesystem guards that are shadowed by stronger upstream checks (a manifest is
already parsed by :class:`RunState` before the chart bridge inspects it) are
exercised with a deterministic stub at that boundary so the *local* validation
in the module under test is still executed and asserted.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from axiomize.runs import bundle as bundles
from axiomize.runs import state as run_state
from axiomize.runs.state import RunState, resolve_run_directory
from axiomize.visualization import canvasxpress_export as cx
from axiomize.visualization import mcp_charts

# ---------------------------------------------------------------------------
# CanvasXpress export branches
# ---------------------------------------------------------------------------


def test_finite_rejects_non_numeric_object() -> None:
    with pytest.raises(ValueError, match="data\\[0\\]\\[0\\] must be numeric"):
        cx.chart_definition(vars=["a"], smps=["s1"], data=[[object()]])


def test_matrix_rejects_empty_row_set() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        cx._matrix([], name="data")


def test_matrix_rejects_more_rows_than_variable_limit() -> None:
    rows = [[float(index)] for index in range(cx._MAX_VARS + 1)]
    with pytest.raises(ValueError, match="hard variable limit"):
        cx._matrix(rows, name="data")


def test_matrix_rejects_zero_columns() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        cx._matrix([[]], name="data")


def test_matrix_rejects_more_columns_than_sample_limit() -> None:
    with pytest.raises(ValueError, match="hard sample limit"):
        cx._matrix([[0.0] * (cx._MAX_SMPS + 1)], name="data")


def test_matrix_rejects_column_count_mismatch_with_samples() -> None:
    with pytest.raises(ValueError, match="exactly 1 columns"):
        cx.chart_definition(vars=["a"], smps=["s1"], data=[[1.0, 2.0]])


def test_annotations_reject_more_entries_than_limit() -> None:
    payload = {f"k{index}": [0.0, 1.0] for index in range(cx._MAX_ANNOTATION_ENTRIES + 1)}
    with pytest.raises(ValueError, match="hard annotation limit"):
        cx._annotations("x", payload, n_smps=2)


def test_annotations_reject_blank_keys() -> None:
    with pytest.raises(ValueError, match="keys must be non-empty"):
        cx._annotations("x", {"   ": [0.0, 1.0]}, n_smps=2)


def test_trajectory_chart_rejects_empty_series() -> None:
    with pytest.raises(ValueError, match="series must not be empty"):
        cx.trajectory_chart(time=[0.0, 1.0], series={})


def test_dependency_chart_rejects_duplicate_nodes() -> None:
    with pytest.raises(ValueError, match="node names must be unique"):
        cx.dependency_chart(nodes=["a", "a"], edges=[])


def test_dependency_chart_rejects_malformed_edge() -> None:
    with pytest.raises(ValueError, match=r"\[source, target\] pair"):
        cx.dependency_chart(nodes=["a"], edges=[["a"]])


# ---------------------------------------------------------------------------
# Recorded-run CanvasXpress bridge
# ---------------------------------------------------------------------------


def _saved_run(root: Path, **fields) -> Path:
    run = RunState(problem_definition="recorded sensitivity", **fields)
    return run.save(root / "case")


def test_chart_bridge_rejects_non_object_results(tmp_path: Path) -> None:
    _saved_run(tmp_path, sensitivity_results={}, results=[])
    with pytest.raises(ValueError, match="recorded results must be an object"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def test_chart_bridge_falls_back_to_recorded_sensitivity_results(tmp_path: Path) -> None:
    _saved_run(tmp_path, sensitivity_results={}, results={"sensitivity_results": {"b": 0.3}})
    chart = mcp_charts.visualize_recorded_run(tmp_path, "case")["chart"]
    assert chart["data"]["y"]["smps"] == ["b"]
    assert chart["data"]["y"]["data"] == [[0.3]]


def test_chart_bridge_falls_back_to_legacy_sensitivity_scores_key(tmp_path: Path) -> None:
    _saved_run(
        tmp_path,
        sensitivity_results={},
        results={"sensitivity_results": {}, "sensitivity_scores": {"c": 0.4}},
    )
    chart = mcp_charts.visualize_recorded_run(tmp_path, "case")["chart"]
    assert chart["data"]["y"]["smps"] == ["c"]


def test_chart_bridge_rejects_blank_parameter_name(tmp_path: Path) -> None:
    _saved_run(tmp_path, sensitivity_results={"  ": 0.1})
    with pytest.raises(ValueError, match="non-empty strings"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def test_chart_bridge_rejects_integer_that_overflows_float(tmp_path: Path) -> None:
    _saved_run(tmp_path, sensitivity_results={"beta": 10**400})
    with pytest.raises(ValueError, match="must be finite"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def test_chart_bridge_rejects_non_string_chart_type(tmp_path: Path) -> None:
    _saved_run(tmp_path, sensitivity_results={"beta": 0.1})
    with pytest.raises(ValueError, match="chart_type"):
        mcp_charts.visualize_recorded_run(tmp_path, "case", chart_type=1)


def test_chart_bridge_enforces_manifest_size_before_parsing(tmp_path: Path, monkeypatch) -> None:
    _saved_run(tmp_path, sensitivity_results={"beta": 0.1})
    monkeypatch.setattr(mcp_charts, "MAX_RUN_JSON_BYTES", 10)
    with pytest.raises(ValueError, match="size limit"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def test_chart_bridge_enforces_manifest_read_size(tmp_path: Path, monkeypatch) -> None:
    _saved_run(tmp_path, sensitivity_results={"beta": 0.1})
    real_read_bytes = Path.read_bytes
    oversized = b"x" * (mcp_charts.MAX_RUN_JSON_BYTES + 1)

    def _read(self: Path) -> bytes:
        if self.name == "manifest.json":
            return oversized
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _read)
    with pytest.raises(ValueError, match="size limit"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def _manifest_case(
    tmp_path: Path,
    monkeypatch,
    manifest_bytes: bytes,
    *,
    validation_results: dict | list | None = None,
) -> None:
    """Write a run directory and return a real RunState through a loader stub."""
    folder = tmp_path / "case"
    folder.mkdir(parents=True)
    run = RunState(
        problem_definition="recorded sensitivity",
        sensitivity_results={"beta": 0.1},
        validation_results={"status": "PASS"} if validation_results is None else validation_results,
    )
    (folder / "run.json").write_text(run._run_text(), encoding="utf-8")
    (folder / "manifest.json").write_bytes(manifest_bytes)
    monkeypatch.setattr(mcp_charts.RunState, "load_under_root", lambda root, run_id: run)


@pytest.mark.parametrize("manifest_bytes", [b"not json", b"\xff\xfe\x00", b"{} trailing"])
def test_chart_bridge_rejects_invalid_manifest_json(tmp_path, monkeypatch, manifest_bytes) -> None:
    _manifest_case(tmp_path, monkeypatch, manifest_bytes)
    with pytest.raises(ValueError, match="not valid UTF-8 JSON"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def test_chart_bridge_rejects_non_object_manifest(tmp_path, monkeypatch) -> None:
    _manifest_case(tmp_path, monkeypatch, b"[]")
    with pytest.raises(ValueError, match="must be an object"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def test_chart_bridge_requires_manifest_run_sha256(tmp_path, monkeypatch) -> None:
    run = RunState(problem_definition="x", sensitivity_results={"b": 0.1})
    manifest = {"input_hash": run.input_hash(), "tool_versions": {}}
    _manifest_case(tmp_path, monkeypatch, json.dumps(manifest).encode())
    with pytest.raises(ValueError, match="record run_sha256"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def test_chart_bridge_rejects_manifest_input_hash_mismatch(tmp_path, monkeypatch) -> None:
    manifest = {"run_sha256": "deadbeef", "input_hash": "wrong", "tool_versions": {}}
    _manifest_case(tmp_path, monkeypatch, json.dumps(manifest).encode())
    with pytest.raises(ValueError, match="input hash does not match"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def test_chart_bridge_requires_tool_versions_object(tmp_path, monkeypatch) -> None:
    run = RunState(
        problem_definition="recorded sensitivity",
        sensitivity_results={"beta": 0.1},
        validation_results={"status": "PASS"},
    )
    manifest = {"run_sha256": "deadbeef", "input_hash": run.input_hash(), "tool_versions": []}
    _manifest_case(tmp_path, monkeypatch, json.dumps(manifest).encode())
    with pytest.raises(ValueError, match="record tool_versions"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


def test_chart_bridge_rejects_non_object_validation_results(tmp_path: Path) -> None:
    _saved_run(tmp_path, sensitivity_results={"beta": 0.1}, validation_results=[])
    with pytest.raises(ValueError, match="validation_results must be an object"):
        mcp_charts.visualize_recorded_run(tmp_path, "case")


# ---------------------------------------------------------------------------
# RunState disk contract
# ---------------------------------------------------------------------------


def test_read_json_bounded_rejects_oversized_json(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="hard size limit"):
        run_state._read_json_bounded(path, maximum=5)


def test_import_file_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid run-state JSON"):
        RunState.import_file(path)


def test_import_file_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a JSON object"):
        RunState.import_file(path)


def test_export_rejects_oversized_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(run_state, "MAX_RUN_JSON_BYTES", 5)
    target = tmp_path / "run.json"
    with pytest.raises(ValueError, match="hard size limit"):
        RunState(problem_definition="too long").export(target)
    assert not target.exists()


def test_save_survives_temp_file_cleanup_failure(tmp_path: Path, monkeypatch) -> None:
    def _locked_unlink(self: Path, *args, **kwargs) -> None:
        raise OSError("file is locked")

    monkeypatch.setattr(Path, "unlink", _locked_unlink)
    saved = RunState(problem_definition="cleanup").save(tmp_path / "run")
    assert (saved / "run.json").is_file()
    assert (saved / "manifest.json").is_file()


def test_resolve_run_directory_rejects_nul_byte(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="NUL"):
        resolve_run_directory(tmp_path, "run\x00id")


def test_resolve_run_directory_rejects_absolute_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute run paths"):
        resolve_run_directory(tmp_path, str(tmp_path / "run"))


def test_load_without_integrity_verification_returns_recorded_state(tmp_path: Path) -> None:
    RunState(problem_definition="unverified", results={"x": 1}).save(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["run_sha256"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    loaded = RunState.load(tmp_path, verify_integrity=False)
    assert loaded.problem_definition == "unverified"
    assert loaded.results == {"x": 1}


def test_load_rejects_input_hash_mismatch_with_valid_run_hash(tmp_path: Path) -> None:
    RunState(problem_definition="original", solver_settings={"rtol": 1e-9}).save(tmp_path)
    run_file = tmp_path / "run.json"
    payload = json.loads(run_file.read_text(encoding="utf-8"))
    payload["problem_definition"] = "edited outside the manifest"
    text = json.dumps(payload, indent=2, sort_keys=True)
    run_file.write_text(text, encoding="utf-8")
    manifest_file = tmp_path / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest["run_sha256"] = hashlib.sha256(run_file.read_bytes()).hexdigest()
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="input_hash integrity check failed"):
        RunState.load(tmp_path)


# ---------------------------------------------------------------------------
# Run bundles
# ---------------------------------------------------------------------------


def test_export_run_requires_zip_suffix(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must end in .zip"):
        bundles.export_run(tmp_path, tmp_path / "bundle.tar")


@pytest.mark.parametrize(
    "name, fragment",
    [
        ("", "empty name"),
        (".", "empty name"),
        ("a\x00b", "NUL byte"),
        ("/absolute", "absolute path"),
        ("\\absolute", "absolute path"),
        ("C:/drive", "drive-letter"),
        ("a\\b", "backslash separator"),
        ("a/../b", "parent-directory traversal"),
        ("../escape", "parent-directory traversal"),
        ("././", "empty name"),
    ],
)
def test_safe_member_name_rejects_unsafe_paths(name: str, fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        bundles._safe_member_name(name)


def test_safe_member_name_normalizes_dot_components() -> None:
    assert str(bundles._safe_member_name("a/./b//c")) == "a/b/c"


def _make_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(f"could not create a directory junction: {result.stderr or result.stdout}")
    else:
        link.symlink_to(target, target_is_directory=True)


def test_resolve_member_refuses_existing_link_escape(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    destination.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = destination / "link"
    _make_directory_link(link, outside)
    try:
        with pytest.raises(ValueError, match="resolves outside the destination"):
            bundles._resolve_member(destination.resolve(), "link/escape.txt")
        assert not (outside / "escape.txt").exists()
    finally:
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()


def test_zip_directory_members_are_created(tmp_path: Path) -> None:
    archive = tmp_path / "dirs.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        info = zipfile.ZipInfo("onlydir/")
        handle.writestr(info, b"")
        handle.writestr("onlydir/data.txt", b"payload")
    destination = bundles.import_run(archive, tmp_path / "dest")
    assert (destination / "onlydir" / "data.txt").read_bytes() == b"payload"


def test_unreadable_tar_member_is_rejected(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "bundle.tar"
    with tarfile.open(archive, "w") as handle:
        info = tarfile.TarInfo("run.json")
        payload = b"{}"
        info.size = len(payload)
        import io

        handle.addfile(info, io.BytesIO(payload))
    monkeypatch.setattr(tarfile.TarFile, "extractfile", lambda self, member: None)
    with pytest.raises(ValueError, match="unreadable member"):
        bundles.import_run(archive, tmp_path / "dest")
    assert not (tmp_path / "dest" / "run.json").exists()


def test_member_budget_helpers_reject_excess() -> None:
    with pytest.raises(ValueError, match="hard member limit"):
        bundles._check_member_budget(bundles.MAX_BUNDLE_MEMBERS + 1, 0)
    with pytest.raises(ValueError, match="expands beyond the hard limit"):
        bundles._check_member_budget(1, bundles.MAX_BUNDLE_UNCOMPRESSED_BYTES + 1)
    assert bundles._check_member_budget(1, 1) is None
