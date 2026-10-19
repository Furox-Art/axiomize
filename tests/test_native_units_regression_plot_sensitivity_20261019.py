"""Native units, provider, statistical and sensitivity behavior; no proxy data.

Local examples establish API correctness and failure behavior, not external
scientific validation or model accuracy on independent observations.
"""
from __future__ import annotations

import numpy as np
import pytest

from axiomize.providers.echo import EchoProvider
from axiomize.sensitivity.analysis import local_sensitivity, mc_sensitivity
from axiomize.tools.statistics.statsmodels_tool import StatsmodelsTool, ols_fit
from axiomize.validation.dimensions import (
    Dimension,
    DimensionalMismatch,
    Quantity,
    check_add,
    check_mul,
    dimension_of,
)
from axiomize.validation.status import ValidationStatus
from axiomize.visualization import plots


def test_real_echo_provider_preserves_text_and_explicit_schema_contract():
    provider = EchoProvider()
    assert provider.generate("scientific question") == "echo: scientific question"
    assert provider.health_check() is True
    assert provider.generate_structured("unused", {}) == {}
    result = provider.generate_structured("unused", {
        "properties": {"estimate": {"type": "number"}, "reason": {"type": "string"}},
        "required": ["estimate", "reason", "missing"],
    })
    assert result == {"estimate": 0.0, "reason": None, "missing": None}


def test_dimension_multiplication_and_division_obey_si_algebra():
    length = Dimension({"L": 1, "T": 0})
    second = Dimension({"T": 1})
    assert length.exponents == {"L": 1}
    assert (length * second).exponents == {"L": 1, "T": 1}
    assert (length / second).exponents == {"L": 1, "T": -1}
    assert (length / length).is_dimensionless
    assert dimension_of("m/s") == length / second
    assert dimension_of("newton").exponents == {"L": 1, "M": 1, "T": -2}


@pytest.mark.parametrize("bad", ["", "unknown-unit", "M/s", "fake"])
def test_unknown_or_missing_physical_units_fail_closed(bad):
    with pytest.raises(DimensionalMismatch, match="empty unit|unknown unit"):
        dimension_of(bad)


def test_quantities_keep_units_and_report_range_decisions():
    length = Quantity(name="distance", symbol="x", unit="metre", value=2.0, valid_range=(0, 3))
    time = Quantity(name="duration", symbol="t", unit="second", value=5.0, valid_range=(0, 3))
    assert length.range_check().status is ValidationStatus.PASS
    assert time.range_check().status is ValidationStatus.FAIL
    assert Quantity(name="unknown", symbol="z", unit="dimensionless").range_check().status is ValidationStatus.INCONCLUSIVE
    assert Quantity(name="unknown", symbol="z", unit="dimensionless", value=1).range_check().status is ValidationStatus.INCONCLUSIVE
    assert check_add(length, Quantity(name="y", symbol="y", unit="cm")).status is ValidationStatus.PASS
    result, status = check_mul(length, time)
    assert result.exponents == {"L": 1, "T": 1}
    assert status.status is ValidationStatus.PASS
    with pytest.raises(DimensionalMismatch, match="cannot add"):
        check_add(length, time)


def test_real_ols_recovers_known_slope_and_intercept_without_changing_measurements():
    x = np.arange(1, 14, dtype=float)
    y = 2.0 * x + 1.0 + np.asarray([0, 0.1, -0.1, 0.2, -0.2, 0.1, 0, -0.1, 0.1, 0, -0.1, 0.2, -0.2])
    result = ols_fit(x, y)
    assert result["n_obs"] == len(x)
    assert result["n_predictors"] == 1
    assert result["params"][0] == pytest.approx(1.0, abs=0.3)
    assert result["params"][1] == pytest.approx(2.0, abs=0.03)
    assert result["rsquared"] > 0.99
    assert len(result["stderr"]) == 2
    assert len(result["pvalues"]) == 2


def test_statsmodels_tool_calls_actual_backend_and_validates_payload():
    x = np.array([[0., 2.], [1., 0.], [2., 3.], [3., 1.], [4., 5.], [5., 4.]])
    y = 1.0 + x[:, 0] + 2.0 * x[:, 1]
    result = StatsmodelsTool().execute({"x": x.tolist(), "y": y.tolist()})
    assert result["n_predictors"] == 2
    assert result["params"] == pytest.approx([1, 1, 2], abs=1e-9)
    assert result["rsquared"] == pytest.approx(1.0)


@pytest.mark.parametrize("payload,pattern", [
    (None, "payload needs"),
    ({}, "payload needs"),
    ({"x": "wrong", "y": [1, 2]}, "numeric arrays"),
    ({"x": [1, 2], "y": [1]}, "1D with"),
    ({"x": [1, 2, 3], "y": [1, 2]}, "same observation count"),
    ({"x": [[1], [2]], "y": [1, 2, 3]}, "rows must match"),
    ({"x": [[[1]], [[2]]], "y": [1, 2]}, "1D predictor or 2D"),
    ({"x": [1, 2, 3], "y": [1, float("nan"), 3]}, "only finite"),
    ({"x": [[1, 2], [3, 4]], "y": [1, 2]}, "observations must exceed"),
])
def test_real_ols_rejects_invalid_design_or_untrusted_numeric_data(payload, pattern):
    with pytest.raises(ValueError, match=pattern):
        StatsmodelsTool().validate_input(payload)


def test_regression_requires_at_least_one_predictor():
    with pytest.raises(ValueError, match="predictor count"):
        StatsmodelsTool().validate_input({"x": np.empty((3, 0)).tolist(), "y": [1, 2, 3]})


def test_plot_sensitivity_creates_real_png_and_rejects_empty_ranking(tmp_path):
    with pytest.raises(ValueError, match="not be empty"):
        plots.plot_sensitivity({}, tmp_path / "empty.png")
    output = plots.plot_sensitivity({"a": -1.0, "b": 2.0}, tmp_path / "nested" / "sensitivity.png")
    assert output.is_file()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_surface_and_dependency_graph_render_valid_pngs(tmp_path):
    x = [0., 1., 2.]
    y = [0., 1.]
    z = np.asarray([[0., 1., 2.], [1., 2., 3.]])
    surface = plots.plot_surface_3d(x, y, z, tmp_path / "surface.png")
    graph = plots.plot_dependency_graph(["rate", "population"], [("rate", "population")], tmp_path / "dependency.png")
    assert surface.read_bytes().startswith(b"\x89PNG")
    assert graph.read_bytes().startswith(b"\x89PNG")


@pytest.mark.parametrize("call,pattern", [
    (lambda p: plots.plot_surface_3d([[1]], [1], [[1]], p), "one-dimensional"),
    (lambda p: plots.plot_surface_3d([1], [1], [1], p), "z shape"),
    (lambda p: plots.plot_surface_3d([1], [1], [[float("nan")]], p), "must be finite"),
    (lambda p: plots.plot_dependency_graph([], [], p), "not be empty"),
    (lambda p: plots.plot_dependency_graph(["a"], [("a", "b")], p), "undeclared nodes"),
])
def test_plot_guards_do_not_emit_false_scientific_artifacts(tmp_path,call,pattern):
    with pytest.raises(ValueError, match=pattern):
        call(tmp_path / "invalid.png")
    assert not (tmp_path / "invalid.png").exists()


def test_local_sensitivity_matches_analytic_linear_and_constant_functions():
    result = local_sensitivity(lambda p: 3.0 * p["x"] + 2.0, {"x": 2.0})
    assert result["x"] == pytest.approx(0.75, rel=0.005)
    result = local_sensitivity(lambda p: 0.0, {"x": 2.0})
    assert result["x"] == pytest.approx(0.0)


def test_real_mc_screening_normalizes_importances_and_preserves_zero_variance():
    result = mc_sensitivity(
        lambda p: 3 * p["x"] + 0.0 * p["y"],
        {"x": (0, 1), "y": (0, 1)}, n=150, seed=9,
    )
    assert sum(result.values()) == pytest.approx(1.0)
    assert result["x"] > result["y"]
    constant = mc_sensitivity(lambda p: 1.0, {"x": (0, 1)}, n=20, seed=9)
    assert constant == {"x": 0.0}


@pytest.mark.parametrize("parameters,pattern", [
    ({}, "params must contain"),
    ({str(i): 1.0 for i in range(65)}, "params must contain"),
    ({"x": "invalid"}, "must be numeric"),
    ({"x": float("inf")}, "finite"),
])
def test_local_sensitivity_refuses_unsupported_parameter_domains(parameters,pattern):
    with pytest.raises(ValueError, match=pattern):
        local_sensitivity(lambda p: p.get("x", 1), parameters)


@pytest.mark.parametrize("bounds,pattern", [
    ({}, "bounds must contain"),
    ({"x": [0]}, "must be"),
    ({"x": ["bad", 2]}, "numeric"),
    ({"x": [1, 1]}, "high must exceed low"),
    ({"x": [float("nan"), 1]}, "finite"),
])
def test_mc_sensitivity_refuses_invalid_or_nonfinite_bounds(bounds,pattern):
    with pytest.raises(ValueError, match=pattern):
        mc_sensitivity(lambda p: 1.0, bounds, n=10)


def test_nonfinite_model_observations_do_not_generate_sensitivity_indices():
    with pytest.raises(ValueError, match="finite"):
        local_sensitivity(lambda p: float("nan"), {"x": 1.0})
    with pytest.raises(ValueError, match="finite"):
        mc_sensitivity(lambda p: float("inf"), {"x": (0, 1)}, n=10)


@pytest.mark.parametrize("step", [0, -1, 1.01])
def test_relative_sensitivity_step_must_stay_inside_valid_domain(step):
    with pytest.raises(ValueError, match="rel_step must be in"):
        local_sensitivity(lambda p: p["x"] * 2, {"x": 1.0}, rel_step=step)


def test_overflowed_difference_quotient_is_detected_before_reporting_index():
    def finite_but_discontinuous(p):
        return 1e308 if p["x"] > 1.0 else -1e308

    with pytest.raises(ValueError, match="non-finite local sensitivity"):
        local_sensitivity(finite_but_discontinuous, {"x": 1.0})


def test_statsmodels_backend_availability_has_actual_version():
    version = StatsmodelsTool._probe_version()
    assert isinstance(version, str)
    assert version.count(".") >= 1
