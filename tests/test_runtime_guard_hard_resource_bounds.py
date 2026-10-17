"""Resource limits for native causal matrices and PDE time-space trajectories."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from axiomize.model_ir import ModelFamily, ModelIR, VariableSpec
from axiomize.runtime_guard import _extra_preflight, install_general_engine_guards


def model(family, metadata=None):
    return ModelIR(
        name="bounded",
        domain="physics",
        family=family,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[],
        equations=[],
        metadata=metadata or {},
    )


@pytest.mark.parametrize(
    ("metadata", "points", "pattern"),
    [
        ({"pde": []}, 10, "metadata.pde"),
        ({"pde": {"grid_points": 4}}, 10, "grid_points"),
        ({"pde": {"grid_points": 4097}}, 10, "grid_points"),
        ({"pde": {"grid_points": 100, "initial_profiles": []}}, 10, "initial_profiles"),
        ({"pde": {"grid_points": 10, "initial_profiles": {"x": [0.0] * 4097}}}, 10, "grid hard limit"),
        ({"pde": {"grid_points": 4096}}, 200000, "numeric cells"),
    ],
)
def test_pde_preflight_bounds_space_times_time_without_allocation(metadata, points, pattern):
    with pytest.raises(ValueError, match=pattern):
        _extra_preflight(model(ModelFamily.PDE, metadata), points=points)


def test_pde_preflight_allows_small_valid_trajectory():
    _extra_preflight(
        model(ModelFamily.PDE, {"pde": {"grid_points": 8, "initial_profiles": {"x": [1.0] * 8}}}), points=12
    )


@pytest.mark.parametrize(
    ("metadata", "pattern"),
    [
        ({"causal": []}, "metadata.causal"),
        ({"causal": {"data": []}}, "causal.data"),
        ({"causal": {"data": {"t": "not an array"}}}, "must be an array"),
        ({"causal": {"data": {"t": [0.0, 1.0], "y": [1.0]}}}, "same length"),
        ({"causal": {"adjustment_set": "z"}}, "must be an array"),
        ({"causal": {"adjustment_set": ["x"] * 2049}}, "covariates exceed"),
    ],
)
def test_causal_preflight_blocks_invalid_or_unbounded_design_matrix(metadata, pattern):
    with pytest.raises(ValueError, match=pattern):
        _extra_preflight(model(ModelFamily.CAUSAL, metadata), points=10)


def test_large_but_admissible_rows_and_columns_cannot_exceed_matrix_cell_cap():
    metadata = {
        "causal": {
            "data": {"t": [0.0] * 10000, "y": [1.0] * 10000},
            "adjustment_set": ["cov"] * 2048,
        }
    }
    with pytest.raises(ValueError, match="design matrix exceeds"):
        _extra_preflight(model(ModelFamily.CAUSAL, metadata), points=10)


def test_causal_preflight_supports_small_complete_design():
    _extra_preflight(
        model(
            ModelFamily.CAUSAL,
            {
                "causal": {
                    "data": {"t": [0.0, 1.0, 0.0], "y": [2.0, 4.0, 2.0]},
                    "adjustment_set": [],
                }
            },
        ),
        points=10,
    )


def test_guard_installation_chains_once_and_is_idempotent():
    calls = []
    module = SimpleNamespace(_advanced_preflight=lambda _model, *, points: calls.append(points))
    install_general_engine_guards(module)
    original_wrapper = module._advanced_preflight
    install_general_engine_guards(module)
    assert module._advanced_preflight is original_wrapper
    module._advanced_preflight(model(ModelFamily.CAUSAL, {"causal": {}}), points=13)
    assert calls == [13]


def test_guard_installation_refuses_missing_base_preflight_hook():
    with pytest.raises(RuntimeError, match="expected advanced preflight hook"):
        install_general_engine_guards(SimpleNamespace())
