"""Enforce runtime resource ceilings before allocating tensors or causal matrices.

Checks are deterministic safety invariants; negative cases invoke real public
preflight functions, never omit unreachable production source from coverage.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from axiomize import runtime_guard as guard
from axiomize.model_ir import ModelFamily


def model(family, metadata=None, *, states=1):
    return SimpleNamespace(
        family=family, metadata=metadata if metadata is not None else {},
        variables=[SimpleNamespace(role="state") for _ in range(states)],
    )


def test_legal_pde_geometry_passes_without_allocating_results():
    assert guard._extra_preflight(model(ModelFamily.PDE, {"pde": {
        "grid_points": 24, "initial_profiles": {"u": [0.0] * 24},
    }}, states=2), points=40) is None


@pytest.mark.parametrize("config,fragment", [
    ([], "metadata.pde must be an object"),
    ({"grid_points": 4}, "pde.grid_points"),
    ({"grid_points": 4097}, "pde.grid_points"),
    ({"grid_points": 5.5}, "pde.grid_points"),
    ({"grid_points": 24, "initial_profiles": []}, "pde.initial_profiles must be an object"),
    ({"grid_points": 24, "initial_profiles": {"u": [0.0] * 4097}}, "exceeds grid hard limit"),
])
def test_pde_preflight_rejects_invalid_geometry_and_profile_shape(config, fragment):
    with pytest.raises(ValueError, match=fragment):
        guard._extra_preflight(model(ModelFamily.PDE, {"pde": config}), points=10)


def test_pde_time_space_tensor_limit_rejected_without_large_allocation(monkeypatch):
    monkeypatch.setattr(guard, "enforce_result_cells", lambda *args, **kwargs: (_ for _ in ()).throw(
        ValueError("PDE trajectory exceeds hard result cell ceiling")
    ))
    with pytest.raises(ValueError, match="hard result cell ceiling"):
        guard._extra_preflight(model(ModelFamily.PDE, {"pde": {"grid_points": 100}}), points=10_000)


def test_no_metadata_dict_is_interpreted_as_empty_without_crash():
    assert guard._extra_preflight(model(ModelFamily.PDE, None), points=5) is None


@pytest.mark.parametrize("config,fragment", [
    ([], "metadata.causal must be an object"),
    ({"data": None}, "causal.data must be an object"),
    ({"data": {"treatment": 3}}, "causal.data.treatment must be an array"),
    ({"data": {"treatment": [0, 1], "outcome": [1]}}, "same length"),
    ({"data": {"treatment": [0, 1]}, "adjustment_set": "incorrect"}, "must be an array"),
])
def test_causal_preflight_rejects_invalid_data_shapes(config, fragment):
    with pytest.raises(ValueError, match=fragment):
        guard._extra_preflight(model(ModelFamily.CAUSAL, {"causal": config}), points=10)


def test_causal_row_count_limit_is_checked_before_design_allocation(monkeypatch):
    monkeypatch.setattr(guard, "MAX_ARRAY_ITEMS", 3)
    with pytest.raises(ValueError, match="exceeds hard limit"):
        guard._extra_preflight(model(ModelFamily.CAUSAL, {"causal": {
            "data": {"treatment": [0, 1, 0, 1]},
        }}), points=4)


def test_causal_adjustment_column_limit_is_checked_before_design_allocation(monkeypatch):
    monkeypatch.setattr(guard, "_MAX_CAUSAL_COVARIATES", 2)
    with pytest.raises(ValueError, match="causal covariates exceed hard limit"):
        guard._extra_preflight(model(ModelFamily.CAUSAL, {"causal": {
            "data": {"treatment": [0, 1]}, "adjustment_set": ["a", "b", "c"],
        }}), points=4)


def test_causal_design_matrix_cells_limit_is_checked_before_allocation(monkeypatch):
    monkeypatch.setattr(guard, "_MAX_CAUSAL_DESIGN_CELLS", 10)
    with pytest.raises(ValueError, match="causal design matrix exceeds hard limit"):
        guard._extra_preflight(model(ModelFamily.CAUSAL, {"causal": {
            "data": {"treatment": [0, 1, 0, 1], "outcome": [1, 2, 3, 4]},
            "adjustment_set": ["covariate"],
        }}), points=10)


def test_direct_valid_causal_dataset_is_allowed():
    assert guard._extra_preflight(model(ModelFamily.CAUSAL, {"causal": {
        "data": {"treatment": [0, 1], "outcome": [1, 3]},
        "adjustment_set": ["observed-covariate"],
    }}), points=10) is None


def test_unrelated_family_is_not_rejected_as_pde_or_causal():
    assert guard._extra_preflight(model(ModelFamily.ODE, {"pde": "nonsense"}), points=10) is None


def test_guard_installation_refuses_missing_critical_preflight_hook():
    with pytest.raises(RuntimeError, match="advanced preflight hook"):
        guard.install_general_engine_guards(SimpleNamespace())


def test_guard_installation_chains_exactly_once_and_cannot_bypass_preflight():
    recorded = []
    def old_preflight(*args, **kwargs):
        recorded.append(("old", kwargs["points"]))

    engine = SimpleNamespace(_advanced_preflight=old_preflight)
    guard.install_general_engine_guards(engine)
    first = engine._advanced_preflight
    guard.install_general_engine_guards(engine)
    assert first is engine._advanced_preflight
    engine._advanced_preflight(model(ModelFamily.ODE), points=11)
    assert recorded == [("old", 11)]


def test_guard_installation_executes_hardened_checks_after_original():
    seen = []
    def original(*args, **kwargs):
        seen.append("original")

    engine = SimpleNamespace(_advanced_preflight=original)
    guard.install_general_engine_guards(engine)
    with pytest.raises(ValueError, match="pde.grid_points"):
        engine._advanced_preflight(model(ModelFamily.PDE, {"pde": {"grid_points": 3}}), points=10)
    assert seen == ["original"]



def test_none_initial_profiles_does_not_invent_spatial_data():
    assert guard._extra_preflight(
        model(ModelFamily.PDE, {"pde": {"grid_points": 10, "initial_profiles": None}}),
        points=5,
    ) is None
