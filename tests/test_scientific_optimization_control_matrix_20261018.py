"""Real constrained optimization and state-space control executable contracts."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize import advanced_family_engine as engine
from axiomize.model_ir import ModelIR


def optimization(*, objective="(x-3)**2", constraint=None, cfg=None, variables=None):
    settings = {"objective": objective, "sense": "minimize"}
    if constraint is not None:
        settings["constraints"] = [constraint]
    if cfg:
        settings.update(cfg)
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "general", "name": "constrained-real-optimization",
        "family": "optimization",
        "variables": variables if variables is not None else [
            {"name": "x", "initial": 0.0, "role": "decision", "bounds": [-10.0, 10.0]},
        ],
        "parameters": [],
        "equations": [{"target": "", "expression": objective or "x", "kind": "objective"}],
        "metadata": {"optimization": settings},
    })


def optimize(model):
    return engine._solve_optimization(
        model, t_span=(0.0, 1.0), points=12, parameter_overrides=None, seed=7,
    )


@pytest.mark.parametrize("relation, threshold, upper, expected", [
    ("ge", 4.0, None, 4.0),
    ("le", 2.0, None, 2.0),
    ("eq", 1.5, None, 1.5),
    ("between", 4.0, 5.0, 4.0),
])
def test_real_optimization_respects_each_supported_constraint(relation, threshold, upper, expected):
    spec = {"expression": "x", "relation": relation, "threshold": threshold}
    if upper is not None:
        spec["upper"] = upper
    result = optimize(optimization(constraint=spec))
    assert result["status"] == "PASS", result
    assert result["states"]["x"] == pytest.approx(expected, abs=5e-3)
    assert result["solver"]["attempts"]


def test_real_optimization_maximizes_without_losing_objective_sign():
    result = optimize(optimization(objective="-(x-2)**2", cfg={"sense": "maximize"}))
    assert result["status"] == "PASS", result
    assert result["states"]["x"] == pytest.approx(2.0, abs=5e-3)
    assert result["objective"]["sense"] == "maximize"
    assert result["objective"]["value"] >= -1e-7


def test_native_optimization_can_fallback_to_state_variable():
    result = optimize(optimization(variables=[{"name": "x", "initial": 0.0, "role": "state"}]))
    assert result["status"] == "PASS"
    assert result["states"]["x"] == pytest.approx(3.0, abs=5e-3)


@pytest.mark.parametrize("cfg, match", [
    ({"constraints": {}}, "constraints must be an array"),
    ({"constraints": [1]}, "each optimization constraint must be an object"),
    ({"constraints": [{"expression": "x", "relation": "unknown"}]}, "unsupported optimization constraint"),
    ({"constraints": [{"expression": "x", "relation": "between"}]}, "requires upper"),
])
def test_native_optimization_rejects_invalid_constraint_metadata(cfg, match):
    with pytest.raises(ValueError, match=match):
        optimize(optimization(cfg=cfg))


def control(*, control_cfg=None, variables=None):
    meta = {"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]], "input": 0.0}
    if control_cfg:
        meta.update(control_cfg)
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "general", "name": "native-state-space",
        "family": "control", "variables": variables if variables is not None else [
            {"name": "x", "initial": 1.0, "role": "state"},
        ],
        "equations": [{"target": "x", "kind": "state_space", "expression": "0"}],
        "metadata": {"control": meta},
    })


def control_run(model, *, t_span=(0.0, 1.0), points=21):
    return engine._simulate_control(model, t_span=t_span, points=points, parameter_overrides=None, seed=11)


def test_native_state_space_dynamics_reproduce_stable_decay():
    result = control_run(control())
    assert result["status"] == "PASS"
    assert result["diagnostics"]["stability"] == "stable"
    assert result["states"]["x"][-1] == pytest.approx(math.exp(-1), rel=2e-3)
    assert len(result["time"]) == 21
    assert result["outputs"]["y0"][-1] == pytest.approx(math.exp(-1), rel=2e-3)


def test_real_feedback_changes_unstable_plant_to_stable_closed_loop():
    open_plant = control_run(control(control_cfg={"A": [[1.0]], "B": [[1.0]]}))
    closed = control_run(control(control_cfg={"A": [[1.0]], "B": [[1.0]], "feedback_gain": [3.0]}))
    assert open_plant["diagnostics"]["stability"] == "unstable"
    assert closed["diagnostics"]["stability"] == "stable"
    assert closed["solver"]["closed_loop"] is True
    assert closed["states"]["x"][-1] < open_plant["states"]["x"][-1]


def test_neutral_plant_is_declared_marginal_not_stable():
    result = control_run(control(control_cfg={"A": [[0.0]]}))
    assert result["diagnostics"]["stability"] == "marginal"


@pytest.mark.parametrize("overrides, pattern", [
    ({"A": [[1.0, 0.0]]}, "A must be square"),
    ({"B": [[1.0], [0.0]]}, "matrix dimensions are inconsistent"),
    ({"C": [[1.0, 0.0]]}, "matrix dimensions are inconsistent"),
    ({"D": [[0.0, 0.0]]}, "matrix dimensions are inconsistent"),
    ({"feedback_gain": [[1.0, 2.0]]}, "feedback_gain shape"),
    ({"input": [1.0, 2.0, 3.0]}, "input vector shape is ambiguous"),
    ({"input": {"time": [0.0, 1.0], "values": [1.0]}}, "values/time length mismatch"),
])
def test_control_fails_closed_on_inconsistent_physics(overrides, pattern):
    with pytest.raises(ValueError, match=pattern):
        control_run(control(control_cfg=overrides))


def test_control_requires_strictly_increasing_time():
    with pytest.raises(ValueError, match="t_span must be increasing"):
        control_run(control(), t_span=(1.0, 0.0))


def test_native_multichannel_input_is_interpolated_from_measured_points():
    result = control_run(control(control_cfg={"B": [1.0], "C": [1.0], "D": 0.0,
        "input": {"time": [0.0, 1.0], "values": [0.0, 1.0]}}))
    assert result["status"] == "PASS"
    assert len(result["states"]["x"]) == 21
    assert all(np.isfinite(result["states"]["x"]))
