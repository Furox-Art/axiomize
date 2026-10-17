"""Charts contain only recorded finite values and explicit source provenance."""

from __future__ import annotations

import pytest

from axiomize.runs.state import RunState
from axiomize.visualization.canvasxpress_export import (
    _matrix,
    attach_run_record,
    chart_definition,
    dependency_chart,
    response_surface_3d_chart,
    response_surface_chart,
    sensitivity_chart,
    trajectory_chart,
)
from axiomize.visualization.mcp_charts import _scores_from_run


@pytest.mark.parametrize(
    ("value", "pattern"),
    [
        ("not a value", "numeric"),
        (None, "numeric"),
        (float("nan"), "finite"),
        (float("inf"), "finite"),
    ],
)
def test_sensitivity_chart_never_accepts_missing_or_nonfinite_measured_score(value, pattern):
    with pytest.raises(ValueError, match=pattern):
        sensitivity_chart({"parameter": value})


@pytest.mark.parametrize(
    ("rows", "pattern"),
    [
        ([], "at least one row"),
        ([[], []], "at least one column"),
        ([[1.0, 2.0], [3.0]], "same length"),
        ([[1.0, 2.0, float("nan")]], "must be finite"),
    ],
)
def test_chart_mathematical_array_shape_has_no_silent_row_drops(rows, pattern):
    with pytest.raises(ValueError, match=pattern):
        _matrix(rows, name="data")


def test_chart_data_have_exact_declared_coordinates_and_no_hidden_proxy_values():
    out = chart_definition(
        vars=["x", "y"],
        smps=["t0", "t1"],
        data=[[1.0, 2.0], [3.0, 4.0]],
        sample_annotations={"epoch": [0, 1]},
        variable_annotations={"units": ["ms", "V"]},
        config={"graphType": "Line"},
        title="real observations",
    )
    assert out["y"] == {"vars": ["x", "y"], "smps": ["t0", "t1"], "data": [[1.0, 2.0], [3.0, 4.0]]}
    assert out["x"]["epoch"] == [0, 1]
    assert out["z"]["units"] == ["ms", "V"]
    assert out["config"]["title"] == "real observations"


@pytest.mark.parametrize(
    ("vars", "smps", "data", "message"),
    [
        (["x", "x"], ["a"], [[1.0], [2.0]], "variable names must be unique"),
        (["x"], ["a", "a"], [[1.0, 2.0]], "sample names must be unique"),
        (["x"], ["a", "b"], [[1.0]], "exactly 2 columns"),
        (["x", "y"], ["a"], [[1.0]], "exactly 2 rows"),
    ],
)
def test_chart_axes_and_matrix_dimensions_cannot_drift(vars, smps, data, message):
    with pytest.raises(ValueError, match=message):
        chart_definition(vars=vars, smps=smps, data=data)


def test_wrong_annotation_lengths_are_rejected_before_visualization():
    with pytest.raises(ValueError, match="misalign every sample"):
        chart_definition(vars=["x"], smps=["t0", "t1"], data=[[1.0, 2.0]], sample_annotations={"invalid": [1]})


def test_sensitivity_ranking_is_by_absolute_recorded_magnitude_not_sign():
    out = sensitivity_chart({"p1": -0.8, "p2": 0.4, "p3": 0.2})
    assert out["y"]["smps"] == ["p3", "p2", "p1"]
    assert out["y"]["data"] == [[0.2, 0.4, -0.8]]
    assert out["config"]["graphType"] == "Bar"


def test_trajectory_real_time_and_state_data_remain_aligned():
    out = trajectory_chart([0.0, 1.0, 2.0], {"I": [1.0, 3.0, 2.0]})
    assert out["y"]["data"] == [[1.0, 3.0, 2.0]]
    assert out["y"]["smps"] == ["0", "1", "2"]
    assert out["x"]["t"] == [0.0, 1.0, 2.0]
    assert "smpOverlays" not in out["config"]


@pytest.mark.parametrize(
    ("t", "states", "pattern"),
    [
        ([0.0], {"x": [1.0]}, "at least two time"),
        ([0.0, 1.0], {}, "series must not be empty"),
        ([0.0, 1.0], {"x": [1.0]}, "exactly 2 samples"),
    ],
)
def test_trajectory_does_not_infer_missing_timepoints(t, states, pattern):
    with pytest.raises(ValueError, match=pattern):
        trajectory_chart(t, states)


def test_response_surface_2d_and_3d_use_same_recorded_dense_measurements():
    x = [1.0, 2.0]
    y = [3.0, 4.0]
    z = [[5.0, 6.0], [7.0, 8.0]]
    heat = response_surface_chart(x, y, z)
    points = response_surface_3d_chart(x, y, z)
    assert heat["y"]["data"] == z
    assert points["y"]["data"] == [[1.0, 2.0, 1.0, 2.0], [3.0, 3.0, 4.0, 4.0], [5.0, 6.0, 7.0, 8.0]]
    assert heat["config"]["graphType"] == "Heatmap"
    assert points["config"]["graphType"] == "Scatter3D"


def test_graph_dependency_chart_rejects_unknown_mechanism_not_fabricated():
    with pytest.raises(ValueError, match="undeclared node"):
        dependency_chart(["a", "b"], [["a", "unobserved"]])
    out = dependency_chart(["a", "b"], [["a", "b"]])
    assert out["y"]["data"] == [[0.0, 1.0], [0.0, 0.0]]


@pytest.mark.parametrize(
    ("node_names", "edges", "pattern"),
    [
        ([], [], "nodes must not be empty"),
        (["a", "a"], [], "node names must be unique"),
        (["a"], [[]], "source, target"),
    ],
)
def test_invalid_graph_visualizations_refuse_implicit_nodes(node_names, edges, pattern):
    with pytest.raises(ValueError, match=pattern):
        dependency_chart(node_names, edges)


@pytest.mark.parametrize(
    ("source", "pattern"),
    [
        (RunState(sensitivity_results={}), "no recorded"),
        (RunState(results={"sensitivity_results": {"scores": {}}}), "no recorded"),
        (RunState(sensitivity_results={"scores": {"beta": float("nan")}}), "must be finite"),
        (RunState(sensitivity_results={"scores": {"beta": True}}), "must be numeric"),
        (RunState(sensitivity_results={"scores": {"": 1.0}}), "non-empty strings"),
    ],
)
def test_mcp_chart_reads_only_actual_recorded_sensitivity_values(source, pattern):
    with pytest.raises(ValueError, match=pattern):
        _scores_from_run(source)


def test_mcp_chart_preserves_exact_signed_and_explicitly_recorded_scores():
    run = RunState(sensitivity_results={"scores": {"gamma": -0.2, "beta": 1.0}})
    assert _scores_from_run(run) == {"beta": 1.0, "gamma": -0.2}


def test_canvasxpress_provenance_is_separate_from_numeric_renderer_and_immutable_source():
    run = RunState(parameters={"beta": 0.3}, sensitivity_results={"scores": {"beta": 1.0}})
    chart = sensitivity_chart({"beta": 1.0})
    original = chart.copy()
    provenance = attach_run_record(chart, run)
    assert "axiomize" in provenance
    assert "axiomize" not in chart
    assert chart == original
    assert provenance["axiomize"]["run_input_sha256"] == run.input_hash()
