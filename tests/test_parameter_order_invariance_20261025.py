"""Monte Carlo helpers must not depend on the caller's mapping order.

Both ``mc_sensitivity`` and ``propagate`` drew one RNG column per parameter in
``dict`` insertion order. The same parameter set rebuilt from a different
source — or a JSON object re-emitted with another key order — therefore got
different columns for the same seed.
"""

from __future__ import annotations

from axiomize.sensitivity.analysis import mc_sensitivity
from axiomize.uncertainty.quantify import propagate


def _model(params: dict[str, float]) -> float:
    return params["a"] * 2.0 + params["b"] * 0.5


def test_mc_sensitivity_is_parameter_order_invariant() -> None:
    forward = mc_sensitivity(_model, {"a": (0.0, 1.0), "b": (0.0, 1.0)}, n=500, seed=7)
    reversed_order = mc_sensitivity(_model, {"b": (0.0, 1.0), "a": (0.0, 1.0)}, n=500, seed=7)
    assert list(forward) == ["a", "b"]
    assert reversed_order == forward


def test_propagate_is_parameter_order_invariant() -> None:
    forward = propagate(_model, {"a": (1.0, 0.1), "b": (1.0, 0.1)}, n=500, seed=7)
    reversed_order = propagate(_model, {"b": (1.0, 0.1), "a": (1.0, 0.1)}, n=500, seed=7)
    assert reversed_order == forward
