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
        from axiomize.integrations.scs_adapter import cross_validate_sir

        r = cross_validate_sir(beta=0.3, gamma=0.1, I0=10, N=100000, days=60)
        from axiomize.validation.status import ValidationStatus

        assert r.status == ValidationStatus.PASS

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
        assert caps["symbolic_math"] == (importlib.util.find_spec("sympy") is not None)
        assert caps["fenics"] is False
        assert caps["gpu"] == (importlib.util.find_spec("torch") is not None
                               or importlib.util.find_spec("jax") is not None)


class TestServices:
    def test_solve_sir_service_structured(self):
        from axiomize.application.services import solve_sir_service

        out = solve_sir_service({"beta": 0.3, "gamma": 0.1, "I0": 10, "N": 1000000})
        assert out["status"] == "PASS"
        assert abs(out["final_size"] - 0.9404) < 0.01
        assert out["cross_validation"]["status"] == "PASS"
        assert "router" in out and "run_dir" not in out

    def test_fit_logistic_service_recovers_k(self):
        import numpy as np
        from axiomize.application.services import fit_logistic_service

        t = np.linspace(0, 30, 22).tolist()
        y = (5000 / (1 + (5000 / 40 - 1) * np.exp(-0.4 * np.array(t)))).tolist()
        out = fit_logistic_service({"t": t, "y": y})
        assert out["success"] is True
        assert abs(out["params"]["K"]["value"] - 5000) / 5000 < 0.05

    def test_all_services_share_core(self):
        from axiomize.application import services

        for name in ("solve_sir_service", "fit_logistic_service",
                     "sensitivity_service", "validate_sir_service",
                     "compare_service", "falsify_service", "tools_service",
                     "capabilities_service"):
            assert callable(getattr(services, name)), name


class TestCLI:
    def test_tools_command_lists_adapters(self):
        from axiomize.cli import main

        assert main(["tools"]) == 0

    def test_solve_command_structured_output(self, tmp_path, capsys):
        from axiomize.cli import main

        out = tmp_path / "out.json"
        rc = main(["solve", "--beta", "0.3", "--gamma", "0.1", "--N", "1000000",
                   "--json", str(out)])
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["status"] == "PASS"

    def test_capabilities_command(self):
        from axiomize.cli import main

        assert main(["capabilities"]) == 0


class TestMCP:
    def _session(self):
        from axiomize.server import mcp_server

        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = mcp_server.handle_message(init)
        assert resp["result"]["serverInfo"]["name"] == "axiomize"
        return mcp_server

    def test_tools_list_exposes_core_tools(self):
        mcp_server = self._session()
        resp = mcp_server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = [t["name"] for t in resp["result"]["tools"]]
        for expected in ("axiomize.solve", "axiomize.validate",
                         "axiomize.select_tools", "axiomize.get_capabilities"):
            assert expected in names

    def test_tool_call_solve_runs_engine(self):
        mcp_server = self._session()
        resp = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "axiomize.solve",
                       "arguments": {"beta": 0.3, "gamma": 0.1,
                                     "I0": 10, "N": 1000000}}})
        assert resp["result"]["status"] == "PASS"

    def test_unknown_tool_is_error_not_crash(self):
        mcp_server = self._session()
        resp = mcp_server.handle_message(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "axiomize.teleport", "arguments": {}}})
        assert "error" in resp


class TestREST:
    @pytest.fixture
    def base_url(self):
        from axiomize.server import rest_server

        server = rest_server.start_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{server.server_address[1]}"
        server.shutdown()

    def _get(self, base_url, path):
        with urllib.request.urlopen(base_url + path, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())

    def _post(self, base_url, path, payload):
        req = urllib.request.Request(
            base_url + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())

    def test_get_tools(self, base_url):
        status, body = self._get(base_url, "/tools")
        assert status == 200
        assert "scipy" in body["tools"]

    def test_post_solve_matches_cli_core(self, base_url):
        status, body = self._post(base_url, "/solve",
                                  {"beta": 0.3, "gamma": 0.1,
                                   "I0": 10, "N": 1000000})
        assert status == 200
        assert body["status"] == "PASS"

    def test_unknown_route_is_404(self, base_url):
        import urllib.error

        with pytest.raises(urllib.error.HTTPError) as exc:
            self._get(base_url, "/teleport")
        assert exc.value.code == 404


class TestProviders:
    def test_echo_structured_output(self):
        provider = EchoProvider()
        out = provider.generate_structured(
            prompt="solve",
            schema={"type": "object", "properties": {"a": {"type": "number"}},
                    "required": ["a"]})
        assert out["a"] == 0.0
        assert provider.health_check() is True

    def test_provider_interface_complete(self):
        for name in ("generate", "generate_structured", "health_check"):
            assert hasattr(ModelProvider, name), name

    def test_openai_compatible_health_fails_fast_on_bogus_host(self):
        from axiomize.providers.openai_compatible import OpenAICompatibleProvider

        p = OpenAICompatibleProvider(base_url="http://127.0.0.1:9", model="x")
        assert p.health_check() is False


class TestPortableRuns:
    def test_export_import_roundtrip(self, tmp_path):
        from axiomize.runs.bundle import export_run, import_run

        run = RunState(problem_definition="portable test")
        run.add_result("x", 1.5)
        src = tmp_path / "run1"
        run.save(src)
        bundle = tmp_path / "run1.zip"
        export_run(src, bundle)
        dest = tmp_path / "run1_copy"
        import_run(bundle, dest)
        assert RunState.load(dest).results["x"] == 1.5
