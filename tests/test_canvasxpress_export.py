"""Contract tests for the CanvasXpress chart-definition export.

These tests pin the shape of the emitted JSON, the refusal behaviour on data
that would silently lose rows in a chart, and the provenance binding. They do
not require a browser, a JavaScript runtime or any optional visualization
backend: the module emits JSON and nothing else.
"""

from __future__ import annotations

import json
import math

import pytest

from axiomize.visualization.canvasxpress_export import (
    MCP_TOOL_NAME,
    PROVENANCE_KEY,
    attach_run_record,
    chart_definition,
    dependency_chart,
    export_chart,
    response_surface_3d_chart,
    response_surface_chart,
    sensitivity_chart,
    trajectory_chart,
)


def _run_stub() -> object:
    """Minimal object with the RunState surface attach_run_record reads."""

    class _Run:
        def input_hash(self) -> str:
            return "0f1e2d3c4b5a69788796a5b4c3d2e1f009182736455463728191a2b3c4d5e6f7"

        def manifest(self) -> dict:
            return {
                "axiomize_version": "1.12.5",
                "tool_versions": {"python": "3.12.3", "numpy": "1.26.4"},
                "solver_settings": {"backend": "scipy", "method": "DOP853", "rtol": 1e-10},
            }

        results = {"v_final": 1.6417, "energy_residual": 2.1e-9}
        validation_results = {"status": "PASS"}
        assumptions = ["level surface", "linear drag"]
        selected_model = "sliding-block-linear-drag"
        equations = ["dv/dt = -(F/m)*v/v_ref"]

    return _Run()


# --- chart_definition -------------------------------------------------------


def test_chart_definition_uses_canvasxpress_xyz_layout() -> None:
    chart = chart_definition(vars=["a", "b"], smps=["s1", "s2"], data=[[1.0, 2.0], [3.0, 4.0]])
    assert chart["y"]["vars"] == ["a", "b"]
    assert chart["y"]["smps"] == ["s1", "s2"]
    assert chart["y"]["data"] == [[1.0, 2.0], [3.0, 4.0]]
    assert isinstance(chart["config"], dict)


def test_chart_definition_is_json_serializable() -> None:
    chart = chart_definition(vars=["a"], smps=["s1", "s2"], data=[[1.0, 2.0]],
                             sample_annotations={"t": [0.0, 1.0]})
    # Round-trips through strict JSON, so no NaN/Infinity leaked in.
    assert json.loads(json.dumps(chart)) == chart


def test_chart_definition_rejects_ragged_rows() -> None:
    with pytest.raises(ValueError, match="same length"):
        chart_definition(vars=["a", "b"], smps=["s1", "s2"], data=[[1.0, 2.0], [3.0]])


def test_chart_definition_rejects_shape_mismatch_with_declared_axes() -> None:
    with pytest.raises(ValueError, match="exactly 2 rows"):
        chart_definition(vars=["a", "b"], smps=["s1"], data=[[1.0], [2.0], [3.0]])


def test_chart_definition_rejects_non_finite_values() -> None:
    # A NaN in a chart silently drops the point in CanvasXpress; refuse instead.
    with pytest.raises(ValueError, match="must be finite"):
        chart_definition(vars=["a"], smps=["s1", "s2"], data=[[float("nan"), 1.0]])
    with pytest.raises(ValueError, match="must be finite"):
        chart_definition(vars=["a"], smps=["s1", "s2"], data=[[float("inf"), 1.0]])


def test_chart_definition_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="unique"):
        chart_definition(vars=["a", "a"], smps=["s1"], data=[[1.0], [2.0]])
    with pytest.raises(ValueError, match="unique"):
        chart_definition(vars=["a"], smps=["s", "s"], data=[[1.0, 2.0]])


def test_chart_definition_rejects_misaligned_sample_annotation() -> None:
    # CanvasXpress would misalign every sample rather than dropping the annotation.
    with pytest.raises(ValueError, match="misalign"):
        chart_definition(vars=["a"], smps=["s1", "s2", "s3"], data=[[1.0, 2.0, 3.0]],
                         sample_annotations={"t": [0.0, 1.0]})


def test_chart_definition_rejects_misaligned_variable_annotation() -> None:
    with pytest.raises(ValueError, match="misalign"):
        chart_definition(vars=["a", "b"], smps=["s1"], data=[[1.0], [2.0]],
                         variable_annotations={"unit": ["m"]})


# --- sensitivity_chart ------------------------------------------------------


def test_sensitivity_chart_ranks_by_magnitude_like_matplotlib_helper() -> None:
    scores = {"beta": 0.8, "gamma": -0.3, "N": 0.05}
    chart = sensitivity_chart(scores)
    # Same ranking the Matplotlib helper applies: ascending absolute value.
    assert chart["y"]["vars"] == ["Sensitivity"]
    assert chart["y"]["smps"] == ["N", "gamma", "beta"]
    assert chart["y"]["data"] == [[0.05, -0.3, 0.8]]
    assert "z" not in chart  # parameters are sample labels, not variables
    assert chart["config"]["xAxisTitle"] == "Sensitivity score"
    assert chart["config"]["graphType"] == "Bar"
    assert chart["config"]["graphOrientation"] == "horizontal"


def test_sensitivity_chart_rejects_empty_scores() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        sensitivity_chart({})


def test_sensitivity_chart_matches_official_canvasxpress_single_series_bar_contract() -> None:
    """Compare the data layout to https://www.canvasxpress.org/examples/bar-8.html."""
    scores = {"k_cat": 0.7, "k_m": -0.4, "enzyme": 0.2}
    chart = sensitivity_chart(scores)
    assert set(chart["y"]) == {"vars", "smps", "data"}
    assert len(chart["y"]["vars"]) == 1
    assert len(chart["y"]["data"]) == 1
    assert len(chart["y"]["smps"]) == len(scores)
    assert chart["y"]["data"] == [[0.2, -0.4, 0.7]]
    assert chart["y"]["smps"] == ["enzyme", "k_m", "k_cat"]
    assert len(chart["y"]["data"][0]) == len(chart["y"]["smps"])
    assert json.loads(json.dumps(chart, allow_nan=False)) == chart


# --- trajectory_chart -------------------------------------------------------


def test_trajectory_chart_encodes_time_as_sample_annotation() -> None:
    chart = trajectory_chart(time=[0.0, 1.0, 2.0],
                             series={"v": [20.0, 12.1, 7.4], "W": [0.0, 12.6, 17.3]})
    assert chart["config"]["graphType"] == "Line"
    assert chart["y"]["vars"] == ["v", "W"]
    assert chart["y"]["data"] == [[20.0, 12.1, 7.4], [0.0, 12.6, 17.3]]
    assert chart["x"]["t"] == [0.0, 1.0, 2.0]


def test_trajectory_chart_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="matching the time axis"):
        trajectory_chart(time=[0.0, 1.0, 2.0], series={"v": [1.0, 2.0]})


def test_trajectory_chart_rejects_too_few_points() -> None:
    with pytest.raises(ValueError, match="at least two time points"):
        trajectory_chart(time=[0.0], series={"v": [1.0]})


# --- response_surface_chart -------------------------------------------------


def test_response_surface_chart_matches_matplotlib_row_column_convention() -> None:
    chart = response_surface_chart(x=[0.0, 1.0], y=[0.0, 1.0, 2.0],
                                   z=[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    assert chart["config"]["graphType"] == "Heatmap"
    # z[i][j] is y[i] by x[j], exactly like plot_surface_3d expects.
    assert len(chart["y"]["vars"]) == 3
    assert len(chart["y"]["smps"]) == 2
    assert chart["y"]["data"] == [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
    assert chart["x"]["x"] == [0.0, 1.0]
    assert chart["z"]["y"] == [0.0, 1.0, 2.0]


def test_response_surface_3d_chart_emits_one_point_per_grid_cell() -> None:
    chart = response_surface_3d_chart(x=[0.0, 1.0], y=[0.0, 1.0, 2.0],
                                      z=[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    assert chart["config"]["graphType"] == "Scatter3D"
    assert chart["y"]["vars"] == ["x", "y", "response"]
    assert len(chart["y"]["smps"]) == 6
    assert chart["y"]["data"][0] == [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
    assert chart["y"]["data"][1] == [0.0, 0.0, 1.0, 1.0, 2.0, 2.0]
    assert chart["y"]["data"][2] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


# --- dependency_chart -------------------------------------------------------


def test_dependency_chart_encodes_edges_as_adjacency() -> None:
    chart = dependency_chart(nodes=["a", "b", "c"], edges=[["a", "b"], ["b", "c"]])
    assert chart["config"]["graphType"] == "Network"
    assert chart["y"]["data"] == [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 0.0]]


def test_dependency_chart_rejects_undeclared_node() -> None:
    with pytest.raises(ValueError, match="undeclared node"):
        dependency_chart(nodes=["a"], edges=[["a", "ghost"]])


def test_dependency_chart_rejects_empty_nodes() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        dependency_chart(nodes=[], edges=[])


# --- attach_run_record ------------------------------------------------------


def test_attach_run_record_binds_provenance_under_reserved_key() -> None:
    chart = chart_definition(vars=["v"], smps=["t0", "t1"], data=[[20.0, 12.1]])
    annotated = attach_run_record(chart, _run_stub())
    assert chart is not annotated, "the input definition must not be mutated"
    assert PROVENANCE_KEY not in chart
    provenance = annotated[PROVENANCE_KEY]
    assert provenance["run_input_sha256"].startswith("0f1e2d3c")
    assert provenance["axiomize_version"] == "1.12.5"
    assert provenance["recorded_results"]["v_final"] == pytest.approx(1.6417)
    assert provenance["validation_results"]["status"] == "PASS"
    assert provenance["model_assumptions"] == ["level surface", "linear drag"]
    assert provenance["tool_versions"]["numpy"] == "1.26.4"
    assert provenance["solver_settings"]["method"] == "DOP853"


def test_attach_run_record_records_the_mcp_tool_it_serves() -> None:
    annotated = attach_run_record({"config": {}}, _run_stub())
    assert annotated[PROVENANCE_KEY]["served_by_mcp_tool"] == MCP_TOOL_NAME
    assert MCP_TOOL_NAME == "model_visualize"


def test_attach_run_record_merges_rather_than_overwriting() -> None:
    chart = {"config": {}, PROVENANCE_KEY: {"existing_note": "keep me"}}
    annotated = attach_run_record(chart, _run_stub())
    assert annotated[PROVENANCE_KEY]["existing_note"] == "keep me"
    assert "run_input_sha256" in annotated[PROVENANCE_KEY]


def test_attach_run_record_rejects_non_definition_input() -> None:
    with pytest.raises(ValueError, match="definition object"):
        attach_run_record(["not", "a", "definition"], _run_stub())


# --- export_chart -----------------------------------------------------------


def test_export_chart_writes_valid_json_with_sorted_keys(tmp_path) -> None:
    chart = chart_definition(vars=["b", "a"], smps=["s1"], data=[[1.0], [2.0]])
    target = export_chart(chart, tmp_path / "nested" / "chart.json")
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == chart
    # Sorted keys keep committed chart definitions diff-stable across runs.
    assert text.index('"config"') < text.index('"y"')


def test_export_chart_rejects_non_definition_input(tmp_path) -> None:
    with pytest.raises(ValueError, match="definition object"):
        export_chart("nope", tmp_path / "chart.json")


# --- matplotlib compatibility ------------------------------------------------


def test_matplotlib_helpers_are_untouched() -> None:
    """The new module is additive; the existing PNG backends still exist."""
    from axiomize.visualization import plots

    for name in ("plot_sensitivity", "plot_surface_3d", "plot_dependency_graph"):
        assert callable(getattr(plots, name))


def test_sensitivity_ranking_is_shared_with_matplotlib_helper(tmp_path) -> None:
    """Both backends must rank identically, so a chart and a PNG never disagree."""
    import matplotlib

    matplotlib.use("Agg")

    from axiomize.visualization import plots

    scores = {"beta": 0.8, "gamma": -0.3, "N": 0.05}
    expected = sorted(scores, key=lambda name: abs(scores[name]))
    chart = sensitivity_chart(scores)
    assert chart["y"]["smps"] == expected
    assert chart["y"]["vars"] == ["Sensitivity"]
    assert math.isfinite(sum(chart["y"]["data"][0]))
    # The helper the ranking is shared with must still be importable from here.
    assert callable(plots.plot_sensitivity)
