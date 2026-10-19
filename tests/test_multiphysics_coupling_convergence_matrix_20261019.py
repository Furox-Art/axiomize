"""Evidence-preserving native multiphysics fixed-point and component failure gates."""
from __future__ import annotations

import pytest

from axiomize import advanced_family_engine as native
from axiomize.general_engine import simulate_model
from axiomize.model_ir import ModelFamily, ModelIR
from axiomize.scientific_stress import _models


def system(change=None):
    config = _models()[ModelFamily.MULTIPHYSICS].to_dict()
    if change:
        config["metadata"]["multiphysics"].update(change)
    return ModelIR.from_dict(config)


def simulate(model, *, engine=None):
    return native._simulate_multiphysics(
        model, t_span=(0.0, 0.5), points=9, parameter_overrides=None,
        seed=17, simulate_fn=simulate_model if engine is None else engine,
    )


def test_real_component_simulations_converge_under_declared_fixed_point_tolerance():
    result = simulate(system())
    assert result["status"] == "PASS"
    assert result["diagnostics"]["converged"]
    assert result["diagnostics"]["iterations"] >= 2
    assert result["components"]["source"]["status"] == "PASS"
    assert result["components"]["target"]["status"] == "PASS"
    assert result["coupling_overrides"]["target"]["k"] == pytest.approx(1.0)
    assert result["convergence"]


def test_uncoupled_components_execute_without_inventing_convergence_iterations():
    result = simulate(system({"couplings": []}))
    assert result["status"] == "PASS"
    assert result["diagnostics"]["converged"] is True
    assert result["diagnostics"]["iterations"] == 2
    assert result["coupling_overrides"]["source"] == {}
    assert result["coupling_overrides"]["target"] == {}


def test_component_catalog_can_be_explicitly_provided_as_named_array():
    base = system().to_dict()
    comps = base["metadata"]["multiphysics"]["components"]
    items = [{"name": key, "model_ir": value} for key, value in comps.items()]
    result = simulate(system({"components": items}))
    assert result["status"] == "PASS"


def test_no_claim_of_fixed_point_convergence_with_insufficient_iterations():
    result = simulate(system({"max_iterations": 1}))
    assert result["status"] == "FAIL"
    assert result["stage"] == "coupling_convergence"
    assert result["diagnostics"] if "diagnostics" in result else result["convergence"]
    assert len(result["convergence"]) == 1


@pytest.mark.parametrize("change, pattern", [
    ({"components": {}}, "at least two"),
    ({"components": [{"name": "source"}]}, "at least two"),
    ({"components": [{"model": {}}]}, "need name"),
    ({"components": "invalid"}, "object or array"),
    ({"couplings": {}}, "couplings must be an array"),
    ({"max_iterations": 0}, "between 1 and 100"),
    ({"max_iterations": 101}, "between 1 and 100"),
])
def test_invalid_component_topology_and_compute_budget_refused(change, pattern):
    with pytest.raises(ValueError, match=pattern):
        simulate(system(change))


def test_nonobject_component_model_is_rejected_before_execution():
    base = system().to_dict()["metadata"]["multiphysics"]["components"]
    base["target"] = "not an IR"
    with pytest.raises(ValueError, match="must contain Model IR"):
        simulate(system({"components": base}))


def test_nested_multiphysics_is_not_accepted_as_single_component():
    base = system().to_dict()["metadata"]["multiphysics"]["components"]
    base["target"] = system().to_dict()
    with pytest.raises(ValueError, match="nested multiphysics"):
        simulate(system({"components": base}))


@pytest.mark.parametrize("coupling, pattern", [
    (None, "each multiphysics coupling must be an object"),
    ({"from_component": "absent"}, "unknown component"),
    ({"from_component": "source", "from_state": "absent", "to_component": "target", "to_parameter": "k"}, "source state"),
    ({"from_component": "source", "from_state": "x", "to_component": "absent", "to_parameter": "k"}, "unknown component"),
    ({"from_component": "source", "from_state": "x", "to_component": "target", "to_parameter": "absent"}, "target parameter"),
])
def test_unknown_coupling_sources_and_targets_never_become_estimated_values(coupling, pattern):
    with pytest.raises(ValueError, match=pattern):
        simulate(system({"couplings": [coupling]}))


@pytest.mark.parametrize("reduction, expected", [
    ("mean", 2.0),
    ("min", 2.0),
    ("max", 2.0),
    ("final", 2.0),
    ("final_mean", 2.0),
])
def test_component_parameter_reductions_respect_measured_constant_source(reduction, expected):
    config = {
        "couplings": [{
            "from_component": "source", "from_state": "x",
            "to_component": "target", "to_parameter": "k",
            "reduction": reduction,
        }],
    }
    result = simulate(system(config))
    assert result["status"] == "PASS"
    assert result["coupling_overrides"]["target"]["k"] == pytest.approx(expected)


def test_coupling_scale_and_offset_are_applied_to_observed_source_values():
    config = {"couplings": [{
        "from_component": "source", "from_state": "x",
        "to_component": "target", "to_parameter": "k",
        "reduction": "final", "scale": 2, "offset": 0.5,
    }]}
    result = simulate(system(config))
    assert result["status"] == "PASS"
    assert result["coupling_overrides"]["target"]["k"] == pytest.approx(4.5)


def test_broken_child_solver_is_recorded_as_component_failure():
    original = simulate_model

    def fail_target(component, **kwargs):
        if component.name == "target":
            return {"status": "FAIL", "stage": "native solver rejected"}
        return original(component, **kwargs)

    result = simulate(system(), engine=fail_target)
    assert result["status"] == "FAIL"
    assert result["stage"] == "component_execution"
    assert result["component"] == "target"
    assert result["component_result"]["status"] == "FAIL"


def test_missing_real_source_observation_cannot_be_used_for_coupling():
    original = simulate_model

    def missing_source(component, **kwargs):
        if component.name == "source":
            return {"status": "PASS", "states": {"other": [1, 2]}}
        return original(component, **kwargs)

    with pytest.raises(ValueError, match="source state"):
        simulate(system(), engine=missing_source)
