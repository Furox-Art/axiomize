"""Regression for router/backend availability truthfulness."""

from axiomize.routing import router
from axiomize.tools.pde import fenics_tool


def test_router_uses_real_fenics_adapter_availability(monkeypatch) -> None:
    monkeypatch.setattr(fenics_tool, "_backend", lambda: None)
    assert router._is_available("fenics") is False
    unavailable = router.classify({"signals": ["pde", "fem"]})
    assert "fenics" not in unavailable.primary_tools
    assert "fenics:TOOL_UNAVAILABLE" in unavailable.alternatives

    monkeypatch.setattr(fenics_tool, "_backend", lambda: ("dolfinx", "99.0-test"))
    assert router._is_available("fenics") is True
    available = router.classify({"signals": ["pde", "fem"]})
    assert "fenics" in available.primary_tools
