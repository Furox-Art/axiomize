"""Coverage-completing tests for advanced_family_engine native executors.

These tests exercise validation and error branches of the deterministic native
executors directly. Every test asserts an observable result or exception.
"""

from __future__ import annotations

import importlib.util
import math
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.integrate
import scipy.optimize

import axiomize.advanced_family_engine as _shipped_module
from axiomize.model_ir import ModelIR


def _load_native_module():
    """Load the shipped module under a private name.

    ``axiomize.v120_runtime.install`` rebinds ``_infer_bayesian`` and
    ``_estimate_causal`` in the public module namespace, so the originally
    defined executors are only reachable through a direct source load. The
    loaded code is the production file itself, unmodified.
    """
    spec = importlib.util.spec_from_file_location(
        "axiomize_advanced_family_engine_native", _shipped_module.__file__
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


afe = _load_native_module()


def _model(payload: dict) -> ModelIR:
    return ModelIR.from_dict({"schema_version": "1.0", "domain": "general", **payload})


def _run(executor, model, *, t_span=(0.0, 1.0), points=8, overrides=None, seed=3):
    return executor(
        model,
        t_span=t_span,
        points=points,
        parameter_overrides=overrides,
        seed=seed,
    )


def test_expression_validation_and_compilation() -> None:
    with pytest.raises(SyntaxError):
        afe._validate_expression("x +", {"x"})
    with pytest.raises(ValueError, match="unsupported expression syntax"):
        afe._validate_expression("x if x else 1", {"x"})
    with pytest.raises(ValueError, match="unknown symbol"):
        afe._validate_expression("foo + x", {"x"})
    with pytest.raises(ValueError, match="approved mathematical functions"):
        afe._validate_expression("foo(x)", {"x"})
    compiled = afe._compile_expression("sin(x) + k", ["x", "k"])
    assert compiled(0.0, 2.0) == pytest.approx(2.0)
    assert compiled(math.pi / 2.0, 0.0) == pytest.approx(1.0)


def test_dispatch_without_native_executor_reports_tool_route() -> None:
    model = _model({
        "name": "algebraic-route",
        "family": "algebraic",
        "variables": [{"name": "y", "initial": 1.0}],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
    })
    out = afe.simulate_advanced_family(
        model,
        t_span=(0.0, 1.0),
        points=5,
        parameter_overrides=None,
        seed=1,
        validate_fn=lambda m, result: {"status": "PASS"},
        simulate_fn=lambda *a, **k: {"status": "PASS"},
    )
    assert out["status"] == "TOOL_ROUTE_REQUIRED"
    assert out["family"] == "algebraic"


def test_pde_validation_branches() -> None:
    base = {
        "name": "pde-validation",
        "family": "pde",
        "variables": [{"name": "u", "initial": 1.0}],
        "equations": [{"target": "u", "expression": "0", "kind": "derivative"}],
    }
    with pytest.raises(ValueError, match="metadata.pde must be an object"):
        _run(afe._simulate_pde, _model({**base, "metadata": {"pde": []}}))
    no_initial = {
        "name": "pde-no-initial",
        "family": "pde",
        "variables": [{"name": "u"}],
        "equations": [{"target": "u", "expression": "0", "kind": "derivative"}],
    }
    with pytest.raises(ValueError, match="needs initial"):
        _run(afe._simulate_pde, _model({**no_initial, "metadata": {"pde": {}}}))
    scalar = _model({
        **no_initial,
        "metadata": {"pde": {"initial_profiles": {"u": "1.0"}}},
    })
    out = _run(afe._simulate_pde, scalar, points=4)
    assert out["status"] == "PASS"
    first = np.asarray(out["states"]["u"], dtype=float)[0]
    assert np.allclose(first, 1.0)


def test_pde_profile_shape_mismatch_is_rejected(monkeypatch) -> None:
    model = _model({
        "name": "pde-bad-profile",
        "family": "pde",
        "variables": [{"name": "u"}],
        "equations": [{"target": "u", "expression": "0", "kind": "derivative"}],
        "metadata": {"pde": {"initial_profiles": {"u": "1.0"}}},
    })
    monkeypatch.setattr(afe, "_compile_expression", lambda *a, **k: lambda *args: np.array([1.0, 2.0]))
    with pytest.raises(ValueError, match="must evaluate to grid length"):
        _run(afe._simulate_pde, model, points=4)


def _dae_model(diff_initial=1.0, algebraic_kinds=("algebraic",), extra_var=None):
    variables = [{"name": "x", "initial": diff_initial}]
    equations = [{"target": "x", "expression": "-z", "kind": "derivative"}]
    for index, kind in enumerate(algebraic_kinds):
        name = "z" if index == 0 else f"z{index}"
        variables.append({"name": name, "role": "algebraic", "initial": 1.0})
        equations.append({"target": name, "expression": "x", "kind": kind})
    if extra_var:
        variables.append({"name": extra_var, "role": "algebraic", "initial": 0.0})
    return _model({
        "name": "dae-coverage",
        "family": "dae",
        "variables": variables,
        "equations": equations,
    })


def test_dae_requires_both_variable_classes() -> None:
    model = _model({
        "name": "dae-no-algebraic",
        "family": "dae",
        "variables": [{"name": "x", "initial": 1.0}],
        "equations": [{"target": "x", "expression": "0", "kind": "derivative"}],
    })
    with pytest.raises(ValueError, match="both differential and algebraic"):
        _run(afe._simulate_dae, model)


def test_dae_residual_equation_is_used_for_algebraic_rows() -> None:
    model = _model({
        "name": "dae-algebraic",
        "family": "dae",
        "variables": [
            {"name": "x", "initial": 1.0},
            {"name": "z", "role": "algebraic", "initial": 1.0},
        ],
        "equations": [
            {"target": "x", "expression": "-z", "kind": "derivative"},
            {"target": "z", "expression": "x", "kind": "algebraic"},
        ],
    })
    out = _run(afe._simulate_dae, model, points=6)
    assert out["status"] == "PASS"
    assert out["diagnostics"]["max_algebraic_residual"] < 1e-6
    assert out["states"]["z"][-1] == pytest.approx(out["states"]["x"][-1], rel=1e-5, abs=1e-6)


def test_dae_residual_count_mismatch_is_rejected() -> None:
    model = _dae_model(algebraic_kinds=("algebraic",), extra_var="z_extra")
    with pytest.raises(ValueError, match="one residual per algebraic variable"):
        _run(afe._simulate_dae, model)


def test_dae_requires_finite_differential_initial_values() -> None:
    model = _dae_model(diff_initial=None)
    with pytest.raises(ValueError, match="finite initial values"):
        _run(afe._simulate_dae, model)


def test_dae_algebraic_fallback_solver_is_used(monkeypatch) -> None:
    model = _dae_model()
    calls = {"count": 0}

    def fake_root(fun, x0, method="hybr"):
        calls["count"] += 1
        if calls["count"] == 1:
            return SimpleNamespace(success=False, x=np.asarray(x0, dtype=float), message="forced hybr failure")
        return SimpleNamespace(success=True, x=np.asarray([0.5]), message="lm ok")

    monkeypatch.setattr(scipy.optimize, "root", fake_root)
    out = _run(afe._simulate_dae, model, points=5)
    assert out["status"] == "PASS"
    assert calls["count"] >= 2
    assert out["solver"]["attempts"][0]["method"] == "BDF"


def test_dae_algebraic_solve_failure_raises(monkeypatch) -> None:
    model = _dae_model()

    def failing_root(fun, x0, method="hybr"):
        return SimpleNamespace(success=False, x=np.full_like(np.asarray(x0, dtype=float), np.nan), message="no root")

    monkeypatch.setattr(scipy.optimize, "root", failing_root)
    with pytest.raises(RuntimeError, match="algebraic solve failed"):
        _run(afe._simulate_dae, model)


def test_dae_solver_errors_produce_failed_attempts(monkeypatch) -> None:
    model = _dae_model()

    def exploding_solve(*args, **kwargs):
        raise RuntimeError("forced solve failure")

    monkeypatch.setattr(scipy.integrate, "solve_ivp", exploding_solve)
    out = _run(afe._simulate_dae, model)
    assert out["status"] == "FAIL"
    assert out["stage"] == "dae_solve"
    assert len(out["solver_attempts"]) == 3
    assert "forced solve failure" in out["solver_attempts"][0]["message"]


def _optimization_model(**metadata) -> ModelIR:
    return _model({
        "name": "opt-coverage",
        "family": "optimization",
        "variables": [{"name": "x", "role": "decision", "initial": 0.0, "bounds": [-10.0, 10.0]}],
        "parameters": [],
        "equations": [{"target": "", "expression": "(x-1)**2", "kind": "objective"}],
        "metadata": {"optimization": metadata},
    })


def test_optimization_validation_branches() -> None:
    with pytest.raises(ValueError, match="metadata.optimization must be an object"):
        _run(afe._solve_optimization, _model({
            "name": "opt-bad-config",
            "family": "optimization",
            "variables": [{"name": "x", "role": "decision", "initial": 0.0}],
            "equations": [{"target": "", "expression": "x**2", "kind": "objective"}],
            "metadata": {"optimization": []},
        }))
    with pytest.raises(ValueError, match="requires decision variables"):
        _run(afe._solve_optimization, _model({
            "name": "opt-no-decision",
            "family": "optimization",
            "variables": [{"name": "y", "role": "output", "initial": 0.0}],
            "equations": [{"target": "", "expression": "y**2", "kind": "objective"}],
        }))
    no_objective = _model({
        "name": "opt-no-objective",
        "family": "optimization",
        "variables": [{"name": "x", "role": "decision", "initial": 0.0}],
        "equations": [{"target": "x", "expression": "x", "kind": "algebraic"}],
        "metadata": {"optimization": {}},
    })
    with pytest.raises(ValueError, match="requires metadata.optimization.objective"):
        _run(afe._solve_optimization, no_objective)


def test_optimization_uses_objective_equation_when_config_lacks_one() -> None:
    out = _run(afe._solve_optimization, _optimization_model())
    assert out["status"] == "PASS"
    assert out["states"]["x"] == pytest.approx(1.0, abs=1e-3)


def test_optimization_solver_exception_and_duplicate_method_skip(monkeypatch) -> None:
    model = _optimization_model()
    model = ModelIR.from_dict({**model.to_dict(), "solver": {"method": "SLSQP"}})
    calls: list[str] = []

    def fake_minimize(fun, x0, **kwargs):
        method = kwargs["method"]
        calls.append(method)
        if method == "SLSQP":
            return SimpleNamespace(success=False, x=np.asarray([0.25]), message="forced SLSQP miss", nit=2)
        raise RuntimeError("forced trust-constr crash")

    monkeypatch.setattr(scipy.optimize, "minimize", fake_minimize)
    out = _run(afe._solve_optimization, model)
    assert out["status"] == "FAIL"
    assert out["stage"] == "optimization"
    assert calls == ["SLSQP", "trust-constr"]
    assert len(out["solver_attempts"]) == 2
    assert out["solver_attempts"][1]["message"].startswith("RuntimeError")


def _control_model(metadata: dict) -> ModelIR:
    return _model({
        "name": "control-coverage",
        "family": "control",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "0", "kind": "state_space"}],
        "metadata": {"control": metadata},
    })


def test_control_validation_branches() -> None:
    with pytest.raises(ValueError, match="metadata.control must be an object"):
        _run(afe._simulate_control, _control_model(5))
    with pytest.raises(ValueError, match="control.state_space must be an object"):
        _run(afe._simulate_control, _control_model({"state_space": []}))
    with pytest.raises(ValueError, match="matrix missing: D"):
        _run(afe._simulate_control, _control_model({"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]]}))
    with pytest.raises(ValueError, match="needs 2 state variables"):
        _run(afe._simulate_control, _control_model({
            "A": [[-1.0, 0.0], [0.0, -1.0]],
            "B": [[0.0], [0.0]],
            "C": [[1.0, 0.0]],
            "D": [[0.0]],
        }))


def test_control_vector_d_matrix_and_input_variants() -> None:
    vector_d = _run(afe._simulate_control, _control_model({
        "A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [0.0],
    }), points=4)
    assert vector_d["status"] == "PASS"

    sampled = _run(afe._simulate_control, _control_model({
        "A": [[-1.0]],
        "B": [[0.0]],
        "C": [[1.0]],
        "D": [[0.0]],
        "input": {"values": [1.0, 2.0, 1.0], "time": [0.0, 0.5, 1.0]},
    }), points=5)
    assert sampled["status"] == "PASS"
    assert sampled["outputs"]["y0"][0] == pytest.approx(1.0)

    untimed = _run(afe._simulate_control, _control_model({
        "A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]],
        "input": {"values": [0.0, 0.0, 0.0, 0.0, 0.0]},
    }), points=5)
    assert untimed["status"] == "PASS"

    reshaped = _run(afe._simulate_control, _control_model({
        "A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]],
        "input": [0.0, 0.0, 0.0, 0.0, 0.0],
    }), points=5)
    assert reshaped["status"] == "PASS"

    tiled = _run(afe._simulate_control, _control_model({
        "A": [[-1.0]], "B": [[0.0, 0.0]], "C": [[1.0]], "D": [[0.0, 0.0]],
        "input": [1.0, 2.0],
    }), points=5)
    assert tiled["status"] == "PASS"

    with pytest.raises(ValueError, match="control input must have shape"):
        _run(afe._simulate_control, _control_model({
            "A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]],
            "input": [[1.0], [2.0]],
        }), points=5)


def _network_model(metadata: dict, variables=None, equations=None) -> ModelIR:
    return _model({
        "name": "network-coverage",
        "family": "network",
        "variables": variables or [{"name": "x", "initial": 0.5}],
        "parameters": [],
        "equations": equations or [{"target": "x", "expression": "0", "kind": "derivative"}],
        "metadata": {"network": metadata},
    })


def test_network_validation_branches() -> None:
    with pytest.raises(ValueError, match="metadata.network must be an object"):
        _run(afe._simulate_network, _network_model(3))
    with pytest.raises(ValueError, match="network model requires state variables"):
        _run(afe._simulate_network, _network_model(
            {"nodes": ["a", "b"], "edges": [["a", "b"]]},
            variables=[{"name": "y", "role": "output", "initial": 0.0}],
            equations=[{"target": "y", "expression": "y", "kind": "algebraic"}],
        ))
    with pytest.raises(ValueError, match="needs an initial value"):
        _run(afe._simulate_network, _network_model({"nodes": ["a", "b"], "edges": [], "initial": {}},
                                                  variables=[{"name": "x"}]))
    scalar = _run(afe._simulate_network, _network_model(
        {"nodes": ["a", "b"], "edges": [["a", "b"]], "initial": {"x": 0.5}},
    ), points=4)
    assert scalar["status"] == "PASS"
    assert np.asarray(scalar["states"]["x"], dtype=float).shape == (4, 2)


def _bayesian_model(parameters, equations=None, variables=None) -> ModelIR:
    return _model({
        "name": "bayesian-coverage",
        "family": "bayesian",
        "variables": variables or [{"name": "y", "role": "output", "initial": 1.0}],
        "parameters": parameters,
        "equations": equations or [{"target": "y", "expression": "y", "kind": "algebraic"}],
    })


def _param(name, **kwargs) -> dict:
    return {"name": name, "value": kwargs.pop("value", 1.0), **kwargs}


def test_bayesian_validation_branches() -> None:
    model = _bayesian_model([_param("a", fit=True)])
    with pytest.raises(ValueError, match="metadata.bayesian must be an object"):
        _run(afe._infer_bayesian, ModelIR.from_dict({
            **model.to_dict(),
            "metadata": {"bayesian": []},
        }))
    with pytest.raises(ValueError, match="bayesian.data must be an object"):
        _run(afe._infer_bayesian, ModelIR.from_dict({
            **model.to_dict(),
            "metadata": {"bayesian": {"data": []}},
        }))
    with pytest.raises(ValueError, match="requires observations"):
        _run(afe._infer_bayesian, ModelIR.from_dict({
            **model.to_dict(),
            "metadata": {"bayesian": {"mean_expression": "a"}},
        }))
    with pytest.raises(ValueError, match="1D array with at least 2 values"):
        _run(afe._infer_bayesian, ModelIR.from_dict({
            **model.to_dict(),
            "metadata": {"bayesian": {"observations": [[1.0], [2.0]], "mean_expression": "a"}},
        }))
    with pytest.raises(ValueError, match="requires mean_expression or likelihood"):
        _run(afe._infer_bayesian, ModelIR.from_dict({
            **model.to_dict(),
            "metadata": {"bayesian": {"observations": [1.0, 2.0]}},
        }))
    no_parameters = _bayesian_model([])
    with pytest.raises(ValueError, match="at least one parameter"):
        _run(afe._infer_bayesian, ModelIR.from_dict({
            **no_parameters.to_dict(),
            "metadata": {"bayesian": {"observations": [1.0, 2.0], "mean_expression": "1.0"}},
        }))
    with pytest.raises(ValueError, match="sigma parameter name is unknown"):
        _run(afe._infer_bayesian, ModelIR.from_dict({
            **model.to_dict(),
            "metadata": {"bayesian": {
                "observations": [1.0, 2.0], "mean_expression": "a", "sigma": "nope",
            }},
        }))
    with pytest.raises(ValueError, match="draws must be in"):
        _run(afe._infer_bayesian, ModelIR.from_dict({
            **model.to_dict(),
            "metadata": {"bayesian": {"observations": [1.0, 2.0], "mean_expression": "a", "draws": 10}},
        }))
    with pytest.raises(ValueError, match="must be scalar or match observations"):
        _run(afe._infer_bayesian, ModelIR.from_dict({
            **model.to_dict(),
            "metadata": {"bayesian": {
                "outcome": "y",
                "data": {"y": [1.0, 2.0], "x": [1.0, 2.0, 3.0]},
                "observations": [1.0, 2.0],
                "mean_expression": "a",
            }},
        }))


def test_bayesian_metropolis_paths_and_samples() -> None:
    model = _bayesian_model([
        {"name": "a", "value": 1.0, "fit": True, "prior": {"dist": "normal", "mu": 1.0, "sigma": 0.5}},
        {"name": "b", "value": 1.0, "fit": True, "bounds": [0.0, 2.0]},
        {"name": "c", "value": 1.0, "fit": True},
        {"name": "d", "value": 1.0, "fit": True},
        {"name": "e", "value": 1.0, "fit": True, "prior": {"dist": "normal", "sigma": 0.5}},
    ])
    out = _run(afe._infer_bayesian, ModelIR.from_dict({
        **model.to_dict(),
        "metadata": {"bayesian": {
            "outcome": "y",
            "data": {
                "y": [1.0, 1.2, 0.9, 1.1],
                "x": [0.1, 0.2, 0.3, 0.4],
                "x2": 2.0,
            },
            "mean_expression": "a*x + b + 0*x2 + c + 0*d",
            "sigma": 0.5,
            "proposal_scale": {"a": 0.05},
            "draws": 50,
            "burn": 0,
            "return_samples": True,
        }},
    }), seed=11)
    assert out["status"] == "PASS"
    assert set(out["posterior"]) == {"a", "b", "c", "d", "e"}
    assert len(out["samples"]["a"]) == 50
    assert out["diagnostics"]["draws"] == 50
    assert 0.0 <= out["diagnostics"]["acceptance_rate"] <= 1.0
    assert out["parameters"]["b"] == pytest.approx(out["posterior"]["b"]["mean"])


def test_bayesian_constant_mean_broadcasts_and_scalar_proposal() -> None:
    model = _bayesian_model([{"name": "a", "value": 1.0, "fit": True}])
    out = _run(afe._infer_bayesian, ModelIR.from_dict({
        **model.to_dict(),
        "metadata": {"bayesian": {
            "observations": [1.0, 1.0, 1.0],
            "mean_expression": "1.0",
            "proposal_scale": 0.05,
            "draws": 50,
            "burn": 0,
        }},
    }), seed=2)
    assert out["status"] == "PASS"
    assert out["posterior"]["a"]["mean"] == pytest.approx(1.0, abs=0.3)
    assert out["diagnostics"]["finite"] is True


def test_bayesian_uses_likelihood_equation_and_rejects_bad_initial_density(monkeypatch) -> None:
    model = ModelIR.from_dict({
        **_bayesian_model(
            [{"name": "m", "value": 1.0, "fit": True}],
            equations=[{"target": "y", "expression": "m*x", "kind": "likelihood"}],
        ).to_dict(),
        "metadata": {"bayesian": {
            "outcome": "y",
            "data": {"y": [1.0, 2.0, 3.0], "x": [1.0, 2.0, 3.0]},
            "draws": 50,
            "burn": 0,
        }},
    })
    out = _run(afe._infer_bayesian, model, seed=5)
    assert out["status"] == "PASS"
    assert out["posterior"]["m"]["mean"] == pytest.approx(1.0, abs=0.3)

    zero_sigma = ModelIR.from_dict({
        **model.to_dict(),
        "metadata": {"bayesian": {
            "outcome": "y",
            "data": {"y": [1.0, 2.0, 3.0], "x": [1.0, 2.0, 3.0]},
            "mean_expression": "m*x",
            "sigma": 0.0,
        }},
    })
    with pytest.raises(ValueError, match="zero/invalid posterior density"):
        _run(afe._infer_bayesian, zero_sigma, seed=5)


def test_bayesian_mean_shape_mismatch_is_rejected(monkeypatch) -> None:
    model = _bayesian_model([{"name": "a", "value": 1.0, "fit": True}])
    model = ModelIR.from_dict({
        **model.to_dict(),
        "metadata": {"bayesian": {
            "observations": [1.0, 2.0],
            "mean_expression": "a",
        }},
    })
    monkeypatch.setattr(afe, "_compile_expression", lambda *a, **k: lambda *args: np.zeros(3))
    with pytest.raises(ValueError, match="zero/invalid posterior density"):
        _run(afe._infer_bayesian, model)


def _agent_model(variables=None, equations=None, metadata=None) -> ModelIR:
    return _model({
        "name": "agent-coverage",
        "family": "agent_based",
        "variables": variables or [{"name": "x", "initial": 1.0}],
        "parameters": [],
        "equations": equations or [{"target": "x", "expression": "x", "kind": "update"}],
        "metadata": metadata if metadata is not None else {"agents": {"count": 2, "initial": {"x": [1.0, 2.0]}}},
    })


def test_agent_based_validation_branches() -> None:
    with pytest.raises(ValueError, match="metadata.agents must be an object"):
        _run(afe._simulate_agent_based, _agent_model(metadata={"agents": 4}))
    with pytest.raises(ValueError, match="requires state variables"):
        _run(afe._simulate_agent_based, _agent_model(
            variables=[{"name": "y", "role": "output", "initial": 0.0}],
            equations=[{"target": "y", "expression": "y", "kind": "algebraic"}],
            metadata={"agents": {"count": 2}},
        ))
    with pytest.raises(ValueError, match="missing update/derivative equations"):
        _run(afe._simulate_agent_based, _agent_model(
            equations=[{"target": "x", "expression": "x", "kind": "algebraic"}],
            metadata={"agents": {"count": 2, "initial": {"x": [1.0, 2.0]}}},
        ))
    with pytest.raises(ValueError, match="needs an initial value"):
        _run(afe._simulate_agent_based, _agent_model(
            variables=[{"name": "x"}],
            metadata={"agents": {"count": 2, "initial": {}}},
        ))
    with pytest.raises(ValueError, match="t_span must be increasing"):
        _run(afe._simulate_agent_based, _agent_model(), t_span=(2.0, 1.0))


def test_agent_update_shape_error_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(afe, "_compile_expression", lambda *a, **k: lambda *args: np.array([1.0, 2.0, 3.0]))
    with pytest.raises(ValueError, match="scalar or one value per agent"):
        _run(afe._simulate_agent_based, _agent_model())


def _event_model(initial=1.0, metadata=None) -> ModelIR:
    return _model({
        "name": "event-coverage",
        "family": "discrete_event",
        "variables": [{"name": "x", "initial": initial}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "x", "kind": "update"}],
        "metadata": metadata if metadata is not None else {
            "discrete_event": {"events": [{"rate": "1.0", "delta": {"x": -1.0}}]},
        },
    })


def test_discrete_event_validation_branches() -> None:
    with pytest.raises(ValueError, match="metadata.discrete_event must be an object"):
        _run(afe._simulate_discrete_event, _event_model(metadata={"discrete_event": 9}))
    with pytest.raises(ValueError, match="finite initial values"):
        _run(afe._simulate_discrete_event, _event_model(initial=None))


def _hybrid_model(initial=1.0, metadata=None, equations=None) -> ModelIR:
    return _model({
        "name": "hybrid-coverage",
        "family": "hybrid",
        "variables": [{"name": "x", "initial": initial}],
        "parameters": [],
        "equations": equations or [{"target": "x", "expression": "0", "kind": "derivative"}],
        "metadata": metadata if metadata is not None else {"hybrid": {}},
    })


def test_hybrid_validation_branches() -> None:
    with pytest.raises(ValueError, match="missing derivative equations"):
        _run(afe._simulate_hybrid, _hybrid_model(
            equations=[{"target": "x", "expression": "x", "kind": "algebraic"}],
        ))
    with pytest.raises(ValueError, match="metadata.hybrid must be an object"):
        _run(afe._simulate_hybrid, _hybrid_model(metadata={"hybrid": 1}))
    with pytest.raises(ValueError, match="hybrid.events must be an array"):
        _run(afe._simulate_hybrid, _hybrid_model(metadata={"hybrid": {"events": {}}}))
    with pytest.raises(ValueError, match="each hybrid event requires expression"):
        _run(afe._simulate_hybrid, _hybrid_model(metadata={"hybrid": {"events": [{"reset": {}}]}}))
    with pytest.raises(ValueError, match="hybrid event reset must be an object"):
        _run(afe._simulate_hybrid, _hybrid_model(metadata={"hybrid": {
            "events": [{"expression": "t-0.5", "reset": []}],
        }}))
    with pytest.raises(ValueError, match="reset references unknown states"):
        _run(afe._simulate_hybrid, _hybrid_model(metadata={"hybrid": {
            "events": [{"expression": "t-0.5", "reset": {"z": "0"}}],
        }}))
    with pytest.raises(ValueError, match="finite initial values"):
        _run(afe._simulate_hybrid, _hybrid_model(initial=None))


def test_hybrid_continuous_failure_is_reported(monkeypatch) -> None:
    def failed_solve(*args, **kwargs):
        return SimpleNamespace(success=False, y=np.zeros((1, 2)), message="forced hybrid failure")

    monkeypatch.setattr(scipy.integrate, "solve_ivp", failed_solve)
    out = _run(afe._simulate_hybrid, _hybrid_model())
    assert out["status"] == "FAIL"
    assert out["stage"] == "hybrid_continuous_solve"


def test_hybrid_event_chatter_is_capped() -> None:
    model = _model({
        "name": "hybrid-chatter",
        "family": "hybrid",
        "variables": [{"name": "x", "initial": -0.01}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "1", "kind": "derivative"}],
        "metadata": {"hybrid": {
            "events": [{"name": "reset", "expression": "x", "reset": {"x": "-0.01"}}],
            "max_events_per_interval": 20,
        }},
    })
    out = _run(afe._simulate_hybrid, model, t_span=(0.0, 5.0), points=2)
    assert out["status"] == "FAIL"
    assert out["stage"] == "hybrid_event_chatter"


def _causal_model(metadata: dict) -> ModelIR:
    return _model({
        "name": "causal-coverage",
        "family": "causal",
        "variables": [{"name": "y", "role": "output", "initial": 0.0}],
        "parameters": [],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
        "metadata": {"causal": metadata},
    })


def test_causal_estimation_with_adjustment_and_counterfactuals() -> None:
    model = _causal_model({
        "treatment": "t",
        "outcome": "y",
        "identification": {
            "identified_dag": True,
            "adjustment_set": ["c"],
            "assumptions": ["backdoor sufficiency"],
        },
        "data": {
            "t": [0.0, 1.0, 2.0, 3.0],
            "y": [4.0, 3.0, 8.0, 7.0],
            "c": [1.0, 0.0, 1.0, 0.0],
        },
        "intervention_values": [0.0, 1.0],
    })
    out = _run(afe._estimate_causal, model)
    assert out["status"] == "PASS"
    assert out["causal_effect"]["estimate"] == pytest.approx(2.0, abs=1e-9)
    assert out["counterfactuals"][0]["predicted_outcome_mean"] == pytest.approx(2.5, abs=1e-9)
    assert out["counterfactuals"][1]["predicted_outcome_mean"] == pytest.approx(4.5, abs=1e-9)
    assert out["diagnostics"]["columns"] == ["intercept", "t", "c"]


def test_causal_insufficient_evidence_and_validation() -> None:
    insufficient = _run(afe._estimate_causal, _causal_model({}))
    assert insufficient["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"

    non_dict_identification = _run(afe._estimate_causal, _causal_model({
        "identification": [],
        "data": {},
    }))
    assert non_dict_identification["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"

    with pytest.raises(ValueError, match="metadata.causal must be an object"):
        _run(afe._estimate_causal, ModelIR.from_dict({
            **_causal_model({}).to_dict(),
            "metadata": {"causal": 7},
        }))
    with pytest.raises(ValueError, match="adjustment_set/covariates must be an array"):
        _run(afe._estimate_causal, _causal_model({
            "identification": {"randomized": True, "adjustment_set": "c"},
        }))
    with pytest.raises(ValueError, match="causal.data must be an object"):
        _run(afe._estimate_causal, _causal_model({
            "identification": {"randomized": True},
            "data": [],
        }))
    with pytest.raises(ValueError, match="treatment/outcome names present"):
        _run(afe._estimate_causal, _causal_model({
            "identification": {"randomized": True},
            "treatment": "t",
            "outcome": "y",
            "data": {"t": [0.0, 1.0, 2.0]},
        }))
    with pytest.raises(ValueError, match="same-length 1D arrays"):
        _run(afe._estimate_causal, _causal_model({
            "identification": {"randomized": True},
            "treatment": "t",
            "outcome": "y",
            "data": {"t": [0.0, 1.0], "y": [0.0, 1.0, 2.0]},
        }))
    with pytest.raises(ValueError, match="missing from data"):
        _run(afe._estimate_causal, _causal_model({
            "identification": {"identified_dag": True, "adjustment_set": ["c"]},
            "treatment": "t",
            "outcome": "y",
            "data": {"t": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 2.0]},
        }))
    with pytest.raises(ValueError, match="length mismatch"):
        _run(afe._estimate_causal, _causal_model({
            "identification": {"identified_dag": True, "adjustment_set": ["c"]},
            "treatment": "t",
            "outcome": "y",
            "data": {"t": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 2.0], "c": [1.0, 0.0]},
        }))


def test_multiphysics_metadata_validation(monkeypatch) -> None:
    model = _model({
        "name": "multiphysics-coverage",
        "family": "multiphysics",
        "variables": [{"name": "y", "role": "output", "initial": 0.0}],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
        "metadata": {"multiphysics": 7},
    })
    with pytest.raises(ValueError, match="metadata.multiphysics must be an object"):
        afe._simulate_multiphysics(
            model,
            t_span=(0.0, 1.0),
            points=4,
            parameter_overrides=None,
            seed=0,
            simulate_fn=lambda *a, **k: {"status": "PASS"},
        )


def test_local_vector_field_missing_derivative_is_rejected() -> None:
    model = _model({
        "name": "pde-missing-derivative",
        "family": "pde",
        "variables": [{"name": "u", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "u", "expression": "u", "kind": "algebraic"}],
    })
    with pytest.raises(ValueError, match="missing derivative equations"):
        afe._compile_local_vector_field(model, {})
