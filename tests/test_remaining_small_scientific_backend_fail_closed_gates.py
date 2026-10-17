"""Direct last-mile guards for tool inventories, physical data, and scientific outputs."""

from __future__ import annotations

from types import SimpleNamespace

import networkx as nx
import numpy as np
import pytest

from axiomize.control.pid import closed_loop_step
from axiomize.json_safety import json_safe
from axiomize.model_ir import ModelFamily, ModelIR, VariableSpec
from axiomize.models.candidates import CandidateModel
from axiomize.network import epidemic
from axiomize.routing.router import classify
from axiomize.runtime_guard import _extra_preflight
from axiomize.sensitivity.analysis import local_sensitivity
from axiomize.tools import inventory
from axiomize.validation.dimensions import Quantity, check_mul
from axiomize.validation.status import ValidationStatus


def test_candidate_model_serialization_preserves_declared_falsification_conditions():
    candidate = CandidateModel(
        model_family="ode",
        structure="state derivative",
        variables=["x"],
        parameters=["k"],
        assumptions=["constant k"],
        falsification_conditions=["data violate exponential prediction"],
    )
    candidate.family = "ode"
    assert candidate.validate() is True
    result = candidate.to_dict()
    assert result["family"] == "ode"
    assert result["falsification_conditions"] == ["data violate exponential prediction"]
    assert result["variables"] == ["x"]


def test_missing_distribution_metadata_cannot_be_claimed_as_known_backend_version(monkeypatch):
    monkeypatch.setattr(inventory.importlib.util, "find_spec", lambda name: SimpleNamespace(name=name))

    def unavailable(*_):
        raise inventory.metadata.PackageNotFoundError("intentionally unavailable metadata")

    monkeypatch.setattr(inventory.metadata, "version", unavailable)
    out = inventory._module_tool("numeric", "numpy", "numpy", ["linear algebra"])
    assert out["available"] is True
    assert out["version"] == "unknown"
    assert out["capabilities"] == ["linear algebra"]


def test_unavailable_backend_is_not_published_as_a_usable_scientific_tool(monkeypatch):
    monkeypatch.setattr(inventory.importlib.util, "find_spec", lambda _: None)
    out = inventory._module_tool("absent", "future_backend", "future_backend", ["computation"])
    assert out["available"] is False
    assert out["reason"] == "future_backend not installed"
    assert out["version"] == ""


def test_unstructured_scientific_router_signals_do_not_create_tool_assignments():
    with pytest.raises(ValueError, match="signals must be a sequence"):
        classify({"signals": "ode, bayesian, prove"})


def test_local_sensitivity_refuses_overflowed_finite_difference():
    def extreme(p):
        return -1e308 if p["k"] == 1.0 else 1e308

    with np.errstate(over="ignore"), pytest.raises(ValueError, match="non-finite local sensitivity"):
        local_sensitivity(extreme, {"k": 1.0})


@pytest.mark.parametrize(
    "measured",
    [
        np.array([float("nan")]),
        np.array([1.0, 2.0]),
    ],
)
def test_control_backend_rejects_nonfinite_or_missing_real_time_observations(monkeypatch, measured):
    import control as ct

    monkeypatch.setattr(ct, "step_response", lambda *a, **kw: SimpleNamespace(y=measured))
    with pytest.raises(RuntimeError, match="malformed or non-finite"):
        closed_loop_step(1.0, 0.1, 0.0, [1.0], [1.0, 1.0], t_end=10.0, n=10)


def test_control_step_exactly_settled_response_has_no_fabricated_delayed_settling(monkeypatch):
    import control as ct

    monkeypatch.setattr(ct, "step_response", lambda _loop, t: SimpleNamespace(y=np.ones(len(t))))
    out = closed_loop_step(1.0, 0.1, 0.0, [1.0], [1.0, 1.0], t_end=10.0, n=12)
    assert out["settled"] is True
    assert out["settling_time"] == 0.0


def test_network_adapter_refuses_more_edges_than_the_configured_hard_ceiling(monkeypatch):
    monkeypatch.setattr(nx, "number_of_edges", lambda graph: epidemic.MAX_NETWORK_EDGES + 1)
    with pytest.raises(ValueError, match="edge count"):
        epidemic._graph_size(nx.path_graph(3))


def test_network_adapter_rejects_nonfinite_degree_moments(monkeypatch):
    graph = nx.path_graph(3)
    monkeypatch.setattr(nx, "degree", lambda graph: [(0, float("inf")), (1, 1), (2, 1)])
    with (
        np.errstate(over="ignore", invalid="ignore"),
        pytest.raises(RuntimeError, match="heterogeneity factor is non-finite"),
    ):
        epidemic.heterogeneity_factor(graph)


def test_network_sir_rejects_pathological_work_before_starting_random_draws():
    graph = nx.path_graph(3000)
    with pytest.raises(ValueError, match="worst-case work"):
        epidemic.sir_on_network(graph, beta=0.2, gamma=0.1, I0=1, max_steps=10000, seed=1)


class BrokenSerializedArray:
    def item(self):
        raise TypeError("broken scalar export")

    def tolist(self):
        raise ValueError("broken array export")

    def __str__(self):
        return "<recorded but unserializable>"


def test_nonfinite_adapter_json_safety_failures_do_not_leak_non_json_objects():
    assert json_safe(BrokenSerializedArray()) == "<recorded but unserializable>"


def test_causal_input_budget_applies_before_high_dimensional_matrix_allocation(monkeypatch):
    from axiomize import runtime_guard

    monkeypatch.setattr(runtime_guard, "MAX_ARRAY_ITEMS", 3)
    model = ModelIR(
        name="causal test",
        domain="neuroscience",
        family=ModelFamily.CAUSAL,
        variables=[VariableSpec("x")],
        parameters=[],
        equations=[],
        metadata={"causal": {"data": {"outcome": [0, 1, 2, 3]}}},
    )
    with pytest.raises(ValueError, match="exceeds hard limit"):
        _extra_preflight(model, points=2)


def test_unspecified_physical_quantity_range_is_inconclusive_not_validated():

    quantity = Quantity(name="distance", symbol="x", unit="metre", value=None)
    assert quantity.range_check().status == ValidationStatus.INCONCLUSIVE


def test_physical_product_combines_dimensions_without_inventing_compatible_units():
    distance = Quantity(name="distance", symbol="x", unit="metre", value=2.0)
    duration = Quantity(name="duration", symbol="t", unit="second", value=3.0)
    dims, check = check_mul(distance, duration)
    assert dict(dims.exponents) == {"L": 1, "T": 1}
    assert check.status == ValidationStatus.PASS


def test_pde_preflight_accepts_explicit_none_for_unprovided_initial_profiles():
    model=ModelIR(
        name="pde bounds",domain="physics",family=ModelFamily.PDE,
        variables=[VariableSpec("x")],parameters=[],equations=[],
        metadata={"pde":{"grid_points":5,"initial_profiles":None}},
    )
    _extra_preflight(model,points=2)
