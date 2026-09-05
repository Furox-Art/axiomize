from __future__ import annotations

import importlib


def test_general_engine_facade_preserves_diagnostics_compatibility() -> None:
    engine = importlib.import_module("axiomize.general_engine")
    assert callable(getattr(engine, "_parameter_values", None))
    assert callable(getattr(engine, "_sympy_expression", None))

    diagnostics = importlib.import_module("axiomize.advanced_diagnostics")
    assert callable(diagnostics.propagate_parameter_uncertainty)
    assert callable(diagnostics.bifurcation_scan)


def test_critical_adapter_modules_import_together() -> None:
    for name in (
        "axiomize.application.general_services",
        "axiomize.application.advanced_services",
        "axiomize.cli",
        "axiomize.server.rest_server",
        "axiomize.server.mcp_server",
    ):
        importlib.import_module(name)
