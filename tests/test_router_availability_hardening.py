"""Regression for router/backend availability truthfulness."""

from axiomize.routing import router
from axiomize.tools.base import ToolMetadata
from axiomize.tools.pde.fenics_tool import FEniCSAdapter


def test_router_follows_real_fenics_adapter_availability(monkeypatch) -> None:
    monkeypatch.setattr(FEniCSAdapter,"availability",classmethod(lambda cls: ToolMetadata(name="fenics",capabilities=list(cls.capabilities),available=False,reason="test unavailable")))
    assert router._is_available("fenics") is False
    unavailable=router.classify({"signals":["pde","fem"]})
    assert "fenics" not in unavailable.primary_tools
    assert "fenics:TOOL_UNAVAILABLE" in unavailable.alternatives

    monkeypatch.setattr(FEniCSAdapter,"availability",classmethod(lambda cls: ToolMetadata(name="fenics",capabilities=list(cls.capabilities),available=True,version="test")))
    assert router._is_available("fenics") is True
    available=router.classify({"signals":["pde","fem"]})
    assert "fenics" in available.primary_tools
