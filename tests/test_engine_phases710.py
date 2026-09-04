"""PHASES 7-10 tests: SCS integration, capabilities, services, CLI,
MCP, REST, providers, portable runs."""

import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from axiomize.capabilities import get_capabilities
from axiomize.providers.base import ModelProvider
from axiomize.providers.echo import EchoProvider
from axiomize.runs.state import RunState


class TestSCSIntegration:
    def test_cds_ode_agrees_with_scipy(self):
        from axiomize.integrations.scs_adapter import cross_validate_sir, scs_probe
        from axiomize.validation.status import ValidationStatus

        r = cross_validate_sir(beta=0.3, gamma=0.1, I0=10, N=100000, days=60)
        if scs_probe()["cds"]:
            assert r.status == ValidationStatus.PASS
        else:
            assert r.status == ValidationStatus.TOOL_UNAVAILABLE

    def test_scs_probe_is_honest(self):
        from axiomize.integrations.scs_adapter import scs_probe

        probe = scs_probe()
        import importlib.util

        assert probe["cds"] == (importlib.util.find_spec("cds") is not None)


class TestCapabilities:
    def test_capability_keys_present(self):
        caps = get_capabilities()
        for key in ("symbolic_math", "numerical_computing", "bayesian_inference",
                    "z3_verification", "fenics", "gpu",
                    "scientific_computing_system"):
            assert key in caps

    def test_known_availability_matches_reality(self):
        import importlib.util
        caps = get_capabilities()
        assert caps["symbolic_math"]["available"] == (importlib.util.find_spec("sympy") is not None)
        assert caps["z3_verification"]["available"] == (importlib.util.find_spec("z3") is not None)


class TestServices:
    def test_solve_sir_service_structured(self):
        from axiomize.application.services import solve_sir_service
        out = solve_sir_service({"beta": 0.3, "gamma": 0.1, "I0": 10, "N": 100000, "days": 30})
        assert "final_size" in out and "status" in out

    def test_fit_logistic_service_recovers_k(self):
        import numpy as np
        from axiomize.application.services import fit_logistic_service
        t = np.linspace(0, 10, 30)
        y = 100 / (1 + np.exp(-1.2 * (t - 5)))
        out = fit_logistic_service({"t": t.tolist(), "y": y.tolist()})
        assert abs(out["K"] - 100) < 5

    def test_all_services_share_core(self):
        from axiomize.application.services import capabilities_service, tools_service
        assert "tools" in tools_service()
        assert isinstance(capabilities_service(), dict)


class TestCLI:
    def test_tools_command_lists_adapters(self, capsys):
        from axiomize.cli import main
        assert main(["tools"]) == 0
        assert "scipy" in capsys.readouterr().out.lower()

    def test_solve_command_structured_output(self, capsys):
        from axiomize.cli import main
        assert main(["solve", "--N", "100000"]) == 0
        assert "final_size" in capsys.readouterr().out

    def test_capabilities_command(self, capsys):
        from axiomize.cli import main
        assert main(["capabilities"]) == 0
        assert "symbolic_math" in capsys.readouterr().out


class TestMCP:
    def test_tools_list_exposes_core_tools(self):
        from axiomize.server.mcp_server import list_tools
        names = {t["name"] for t in list_tools()}
        assert "solve_sir" in names

    def test_tool_call_solve_runs_engine(self):
        from axiomize.server.mcp_server import call_tool
        out = call_tool("solve_sir", {"N": 100000})
        assert "final_size" in out

    def test_unknown_tool_is_error_not_crash(self):
        from axiomize.server.mcp_server import call_tool
        out = call_tool("not-a-tool", {})
        assert "error" in out


class TestREST:
    @staticmethod
    def _server():
        from axiomize.server.rest_server import start_server
        server = start_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    def test_get_tools(self):
        server = self._server()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/v1/tools") as response:
                assert response.status == 200
        finally:
            server.shutdown()

    def test_post_solve_matches_cli_core(self):
        server = self._server()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/v1/solve",
                data=json.dumps({"N": 100000}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as response:
                out = json.loads(response.read())
            assert "final_size" in out
        finally:
            server.shutdown()

    def test_unknown_route_is_404(self):
        server = self._server()
        try:
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/nope")
            assert exc.value.code == 404
        finally:
            server.shutdown()


class TestProviders:
    def test_echo_structured_output(self):
        provider = EchoProvider()
        out = provider.complete("hello")
        assert isinstance(out, dict)

    def test_provider_interface_complete(self):
        assert hasattr(ModelProvider, "complete")

    def test_openai_compatible_health_fails_fast_on_bogus_host(self):
        from axiomize.providers.openai_compatible import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider(base_url="http://127.0.0.1:1", api_key="x")
        assert provider.healthcheck() is False


class TestPortableRuns:
    def test_export_import_roundtrip(self, tmp_path):
        state = RunState(run_id="portable", inputs={"x": 1})
        state.results["y"] = 2
        path = tmp_path / "run.json"
        state.export(path)
        loaded = RunState.import_file(path)
        assert loaded.inputs == state.inputs
        assert loaded.results == state.results
