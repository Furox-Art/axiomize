"""Regression for router/backend availability truthfulness."""

from axiomize.routing import router
from axiomize.tools.pde.fenics_tool import FEniCSAdapter


def test_router_uses_real_fenics_adapter_availability(monkeypatch) -> None:
    # Even if a FEniCS import would succeed, the adapter must remain unavailable
    # until safe weak-form execution is actually implemented.
    monkeypatch.setattr(
        FEniCSAdapter,
        "_probe_version",
        classmethod(lambda cls: "99.0-test"),
    )
    assert router._is_available("fenics") is False

    decision = router.classify({"signals": ["pde", "fem"]})
    assert "fenics" not in decision.primary_tools
    assert "fenics:TOOL_UNAVAILABLE" in decision.alternatives
