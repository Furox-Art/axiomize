from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.capabilities import get_capabilities
from axiomize.general_engine import recommend_model_families, simulate_model
from axiomize.model_ir import ModelFamily, ModelIR


def _model(payload: dict) -> ModelIR:
    return ModelIR.from_dict({"schema_version": "1.0", "domain": "general", **payload})


def test_pde_method_of_lines_executes_uniform_reaction_diffusion() -> None:
    model = _model({
        "name": "reaction-diffusion",
        "family": "pde",
        "variables": [{"name": "u", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 0.5}],
        "equations": [{"target": "u", "expression": "-k*u", "kind": "derivative"}],
        "metadata": {
            "pde": {
                "grid_points": 10,
                "space_span": [0.0, 1.0],
                "diffusion": {"u": 0.1},
                "boundary_conditions": {
                    "u": {
                        "left": {"type": "neumann", "value": 0.0},
                        "right": {"type": "neumann", "value": 0.0},
                    }
                },
            }
        },
    })
    out = simulate_model(model, t_span=(0.0, 1.0), points=25)
    assert out["status"] == "PASS"
    grid = np.asarray(out["states"]["u"], dtype=float)
    assert grid.shape == (25, 10)
    assert np.mean(grid[-1]) == pytest.approx(math.exp(-0.5), rel=2e-4)
    assert out["solver"]["spatial_method"] == "method_of_lines"


def test_index1_dae_executes_and_checks_algebraic_residual() -> None:
    model = _model({
        "name": "index1-dae",
        "family": "dae",
        "variables": [
            {"name": "x", "initial": 1.0},
            {"name": "z", "initial": 1.0, "role": "latent"},
        ],
        "parameters": [{"name": "k", "value": 1.0}],
        "equations": [
            {"target": "x", "expression": "-z", "kind": "derivative"},
            {"target": "", "expression": "z-k*x", "kind": "residual"},
        ],
    })
    out = simulate_model(model, t_span=(0.0, 1.0), points=30)
    assert out["status"] == "PASS"
    assert out["states"]["x"][-1] == pytest.approx(math.exp(-1.0), rel=5e-3)
    assert out["diagnostics"]["max_algebraic_residual"] < 1e-7


def test_generic_nonlinear_optimization_executes() -> None:
    model = _model({
        "name": "quadratic-optimum",
        "family": "optimization",
        "variables": [{"name": "x", "role": "decision", "initial": 0.0, "bounds": [-10.0, 10.0]}],
        "parameters": [],
        "equations": [{"target": "", "expression": "(x-3)**2", "kind": "objective"}],
        "metadata": {"optimization": {"objective": "(x-3)**2", "sense": "minimize"}},
    })
    out = simulate_model(model)
    assert out["status"] == "PASS"
    assert out["states"]["x"] == pytest.approx(3.0, abs=2e-4)
    assert out["objective"]["value"] < 1e-7


def test_state_space_control_executes_and_reports_stability() -> None:
    model = _model({
        "name": "stable-control-plant",
        "family": "control",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "0", "kind": "state_space"}],
        "metadata": {
            "control": {
                "A": [[-1.0]],
                "B": [[0.0]],
                "C": [[1.0]],
                "D": [[0.0]],
                "input": 0.0,
            }
        },
    })
    out = simulate_model(model, t_span=(0.0, 1.0), points=30)
    assert out["status"] == "PASS"
    assert out["states"]["x"][-1] == pytest.approx(math.exp(-1.0), rel=2e-3)
    assert out["diagnostics"]["stability"] == "stable"


def test_network_graph_dynamics_executes_and_conserves_mean() -> None:
    model = _model({
        "name": "network-diffusion",
        "family": "network",
        "variables": [{"name": "x", "initial": 0.5}],
        "parameters": [{"name": "c", "value": 0.5}],
        "equations": [{"target": "x", "expression": "c*laplacian_x", "kind": "derivative"}],
        "metadata": {
            "network": {
                "nodes": ["a", "b"],
                "edges": [["a", "b"]],
                "initial": {"x": [1.0, 0.0]},
            }
        },
    })
    out = simulate_model(model, t_span=(0.0, 2.0), points=25)
    assert out["status"] == "PASS"
    values = np.asarray(out["states"]["x"], dtype=float)
    assert values.shape == (25, 2)
    assert np.mean(values[-1]) == pytest.approx(0.5, abs=1e-8)
    assert abs(values[-1, 0] - values[-1, 1]) < 0.2


def test_bayesian_sampling_is_approval_gated_and_executes() -> None:
    model = _model({
        "name": "bayesian-line",
        "family": "bayesian",
        "variables": [{"name": "y", "role": "output", "initial": 0.0}],
        "parameters": [
            {"name": "a", "value": 0.5, "fit": True, "prior": {"dist": "normal", "mu": 0.0, "sigma": 3.0}},
        ],
        "equations": [{"target": "y", "expression": "a*x", "kind": "observation"}],
        "metadata": {
            "bayesian": {
                "data": {"x": [0.0, 1.0, 2.0, 3.0]},
                "observations": [0.0, 2.0, 4.0, 6.0],
                "mean_expression": "a*x",
                "sigma": 0.15,
                "draws": 500,
                "burn": 150,
                "proposal_scale": {"a": 0.08},
            }
        },
    })
    blocked = simulate_model(model, seed=42)
    assert blocked["status"] == "APPROVAL_REQUIRED"
    out = simulate_model(model, seed=42, approve_heavy=True)
    assert out["status"] == "PASS"
    assert out["posterior"]["a"]["mean"] == pytest.approx(2.0, abs=0.15)
    assert 0.02 < out["diagnostics"]["acceptance_rate"] < 0.95


def test_agent_based_execution_keeps_per_agent_trajectories() -> None:
    model = _model({
        "name": "agent-decay",
        "family": "agent_based",
        "variables": [{"name": "x", "initial": 1.0, "bounds": [0.0, None]}],
        "parameters": [{"name": "k", "value": 0.5}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
        "metadata": {"agents": {"count": 4, "noise_std": 0.0}},
    })
    out = simulate_model(model, t_span=(0.0, 1.0), points=41, seed=7)
    assert out["status"] == "PASS"
    values = np.asarray(out["states"]["x"], dtype=float)
    assert values.shape == (41, 4)
    assert np.max(np.ptp(values, axis=1)) == pytest.approx(0.0)
    assert np.mean(values[-1]) == pytest.approx(math.exp(-0.5), rel=8e-3)


def test_discrete_event_execution_is_reproducible() -> None:
    model = _model({
        "name": "poisson-arrivals",
        "family": "discrete_event",
        "variables": [{"name": "n", "initial": 0.0}],
        "parameters": [{"name": "lam", "value": 8.0}],
        "equations": [{"target": "n", "expression": "0", "kind": "event_state"}],
        "metadata": {
            "discrete_event": {
                "events": [{"name": "arrival", "rate": "lam", "delta": {"n": 1.0}}],
            }
        },
    })
    first = simulate_model(model, t_span=(0.0, 2.0), points=20, seed=123)
    second = simulate_model(model, t_span=(0.0, 2.0), points=20, seed=123)
    assert first["status"] == "PASS"
    assert first["states"] == second["states"]
    assert first["diagnostics"]["event_counts"]["arrival"] > 0
    assert np.all(np.diff(first["states"]["n"]) >= 0)


def test_hybrid_continuous_discrete_execution() -> None:
    model = _model({
        "name": "resetting-ramp",
        "family": "hybrid",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "-1", "kind": "derivative"}],
        "metadata": {
            "hybrid": {
                "events": [
                    {"name": "reset", "expression": "x", "direction": -1, "reset": {"x": "1"}},
                ]
            }
        },
    })
    out = simulate_model(model, t_span=(0.0, 2.4), points=49)
    assert out["status"] == "PASS"
    assert out["diagnostics"]["event_count"] >= 2
    assert min(out["states"]["x"]) >= -1e-7


def test_causal_execution_requires_identification_and_estimates_effect() -> None:
    base = {
        "name": "identified-effect",
        "family": "causal",
        "variables": [{"name": "y", "role": "output", "initial": 0.0}],
        "parameters": [],
        "equations": [{"target": "y", "expression": "0", "kind": "causal"}],
        "metadata": {
            "causal": {
                "treatment": "treat",
                "outcome": "outcome",
                "data": {
                    "treat": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
                    "outcome": [1.0, 3.0, 1.0, 3.0, 1.0, 3.0],
                },
            }
        },
    }
    unidentified = simulate_model(_model(base))
    assert unidentified["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"

    identified_payload = dict(base)
    identified_payload["metadata"] = {
        **base["metadata"],
        "causal_identification": {"randomized": True},
        "causal": {**base["metadata"]["causal"], "identification": {"randomized": True}},
    }
    out = simulate_model(_model(identified_payload))
    assert out["status"] == "PASS"
    assert out["causal_effect"]["estimate"] == pytest.approx(2.0, abs=1e-10)


def test_multiphysics_cosimulation_is_approval_gated_and_converges() -> None:
    source = _model({
        "name": "source",
        "family": "ode",
        "variables": [{"name": "x", "initial": 2.0}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "0", "kind": "derivative"}],
    }).to_dict()
    target = _model({
        "name": "target",
        "family": "ode",
        "variables": [{"name": "y", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 1.0}],
        "equations": [{"target": "y", "expression": "-k*y", "kind": "derivative"}],
    }).to_dict()
    coupled = _model({
        "name": "coupled-system",
        "family": "multiphysics",
        "variables": [{"name": "q", "initial": 0.0}],
        "parameters": [],
        "equations": [{"target": "q", "expression": "0", "kind": "coupling"}],
        "metadata": {
            "multiphysics": {
                "components": {"source": source, "target": target},
                "couplings": [
                    {
                        "from_component": "source",
                        "from_state": "x",
                        "to_component": "target",
                        "to_parameter": "k",
                        "reduction": "final",
                        "scale": 0.5,
                    }
                ],
                "tolerance": 1e-10,
                "max_iterations": 4,
            }
        },
    })
    blocked = simulate_model(coupled, t_span=(0.0, 1.0), points=20)
    assert blocked["status"] == "APPROVAL_REQUIRED"
    out = simulate_model(coupled, t_span=(0.0, 1.0), points=20, approve_heavy=True)
    assert out["status"] == "PASS"
    assert out["diagnostics"]["converged"] is True
    assert out["coupling_overrides"]["target"]["k"] == pytest.approx(1.0)
    assert out["components"]["target"]["states"]["y"][-1] == pytest.approx(math.exp(-1.0), rel=5e-5)


def test_advanced_families_are_reported_as_native_and_multiphysics_is_ranked() -> None:
    capabilities = get_capabilities()
    native = set(capabilities["general_modeling"]["native_execution"])
    assert native == {family.value for family in ModelFamily}
    assert capabilities["general_modeling"]["routed_specialized_execution"] == []
    ranked = recommend_model_families(
        domain="physics",
        signals=["coupled_physics"],
        idea="coupled thermal mechanical multiphysics model",
    )
    assert ranked[0]["family"] == "multiphysics"
