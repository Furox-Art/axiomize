"""Additional verification of residual scientific façade failure boundaries."""
from __future__ import annotations

import sys

import numpy as np
import pytest
import sympy as sp

from axiomize.application import services as svc


def test_nonphysical_symbolic_root_cannot_be_reported_as_scientific_result(monkeypatch):
    # Fault-inject invalid symbolic solver output and test the REAL domain gate.
    monkeypatch.setattr(sp, "LambertW", lambda *args: 1)
    with pytest.raises(ValueError, match="outside the physical domain"):
        svc._sir_asymptotic_final_size_symbolic(0.3, 0.1, 10, 1000)


def test_oversized_uncertainty_request_fails_before_statistical_allocation():
    rows = {str(i): [0.5, 0.1] for i in range(2001)}
    with pytest.raises(ValueError, match="hard limit 2000"):
        svc.uncertainty_service({"params": rows})


def test_unavailable_scipy_stats_is_not_a_fabricated_gaussian_interval(monkeypatch):
    monkeypatch.setitem(sys.modules, "scipy.stats", None)
    actual = svc.uncertainty_service({"params": {"x": [1.0, 0.2]}})
    assert actual["status"] == "TOOL_UNAVAILABLE"
    assert actual["intervals"] == {}


def test_real_sir_fit_is_included_only_after_population_is_supplied():
    x = np.linspace(0, 12, 40)
    y = 20 / (1 + np.exp(-0.6 * (x - 5)))
    result = svc.compare_service({
        "t": x.tolist(), "y": y.tolist(), "N": 1000.0, "I0": 1.0,
    })
    assert "logistic" in result["fits"]
    assert "sir" in result["fits"]
    assert result["best"] in {"sir", "logistic"}
