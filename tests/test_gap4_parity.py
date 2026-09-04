"""GAP-4 ajan-saha parite testi: CLI / MCP / REST ayni core davranisi mi?

Kapsam (kod okuma ile dogrulandi):
- src/axiomize/cli.py -> cmd_solve: solve_sir_service, cmd_validate: validate_sir_service
- src/axiomize/server/rest_server.py -> POST /solve|/simulate|/model: solve_sir_service,
  /validate: validate_sir_service, /cross-validate: solve_sir_service(...)[cross_validation],
  /fit: fit_logistic_service, /falsify, /compare, GET /tools, /capabilities.
  NOT: /sensitivity ve /uncertainty rotasi YOK (404).
- src/axiomize/server/mcp_server.py -> _call_tool: solve/simulate/validate hepsi
  validate_sir_service cagirir (solve icin solve_sir_service DEGIL);
  uncertainty_analysis gercek servis cagirmaz, echo stub dondurur.
- src/axiomize/application/services.py -> tek core: solve_sir_service,
  validate_sir_service (= solve + validation_checks), fit_logistic_service,
  sensitivity_service, falsify_service, compare_service, tools/capabilities.

Bu dosya gercek durumu assert eder: parite olan yerde PASS, kirik yerde
acik mesajla FAIL (sahte PASS yok). Bilinen 3 kirik:
  1) MCP solve, solve degil validate dondurur (fazladan 'validation_checks').
  2) MCP uncertainty_analysis echo stub'dur, core servis cagirmaz.
  3) REST'te /sensitivity rotasi yoktur (404), oysa sensitivity_service + MCP vardir.
"""

from __future__ import annotations

import argparse
import io
import json
import threading
import urllib.request
from contextlib import redirect_stdout

PAR = {"beta": 0.3, "gamma": 0.1, "I0": 10.0, "N": 100000.0, "days": 180.0}


def _cli_solve_output(params: dict) -> dict:
    from axiomize.cli import cmd_solve

    args = argparse.Namespace(
        beta=params["beta"], gamma=params["gamma"], I0=params["I0"],
        N=params["N"], days=params["days"], json=None,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_solve(args)
    assert rc == 0
    return json.loads(buf.getvalue())


def _cli_validate_output(params: dict) -> dict:
    from axiomize.cli import cmd_validate

    args = argparse.Namespace(
        beta=params["beta"], gamma=params["gamma"], I0=params["I0"],
        N=params["N"], days=params["days"], json=None,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_validate(args)
    return json.loads(buf.getvalue())


def _rest_post(port: int, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, {"raw": body}


# --- smoke: uc katman da import edilebiliyor ve ayni core modulu goruyor ---

def test_adapter_import_smoke():
    import axiomize.cli  # noqa: F401
    import axiomize.server.mcp_server  # noqa: F401
    import axiomize.server.rest_server  # noqa: F401
    from axiomize.application import services  # noqa: F401

    assert hasattr(services, "solve_sir_service")
    assert hasattr(services, "validate_sir_service")
    assert hasattr(services, "sensitivity_service")


# --- PARITE OLANLAR (PASS beklenir) ---

def test_cli_solve_matches_core_service():
    """CLI solve, solve_sir_service ile birebir ayni sonucu verir (PASS)."""
    from axiomize.application import services

    assert _cli_solve_output(PAR) == services.solve_sir_service(dict(PAR))


def test_cli_validate_matches_core_service():
    """CLI validate, validate_sir_service ile birebir aynidir (PASS)."""
    from axiomize.application import services

    assert _cli_validate_output(PAR) == services.validate_sir_service(dict(PAR))


def test_mcp_validate_matches_core_service():
    """MCP validate, validate_sir_service ile aynidir (PASS)."""
    from axiomize.application import services
    from axiomize.server import mcp_server

    assert mcp_server._call_tool("axiomize.validate", dict(PAR)) == \
        services.validate_sir_service(dict(PAR))


def test_rest_solve_matches_core_service_live():
    """REST POST /solve, solve_sir_service ile birebir aynidir (canli, PASS)."""
    from axiomize.application import services
    from axiomize.server.rest_server import start_server

    srv = start_server("127.0.0.1", 0)
    port = srv.server_address[1]
    thr = threading.Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    try:
        code, body = _rest_post(port, "/solve", dict(PAR))
        assert code == 200, f"REST /solve HTTP {code}: {body}"
        assert body == services.solve_sir_service(dict(PAR))
    finally:
        srv.shutdown()


# --- PARITE KIRIKLARI (FAIL beklenir; mesajlar eksigi gosterir) ---

def test_mcp_solve_matches_solve_service():
    """MCP solve, CLI/REST solve ile ayni core ciktiyi vermeli.

    GERCEK: MCP _call_tool('axiomize.solve') validate_sir_service cagirir,
    CLI/REST solve_sir_service cagirir -> fazladan 'validation_checks' anahtari.
    Bu test parite kirik oldugu icin FAIL verir (duzeltme: MCP solve'un
    solve_sir_service cagirmasi gerekir).
    """
    from axiomize.application import services
    from axiomize.server import mcp_server

    mcp_out = mcp_server._call_tool("axiomize.solve", dict(PAR))
    core_out = services.solve_sir_service(dict(PAR))
    assert mcp_out == core_out, (
        "PARITE KIRIK (MCP solve vs core solve): MCP 'axiomize.solve' "
        f"validate donduruyor; farkli anahtarlar={sorted(set(mcp_out) ^ set(core_out))} "
        "(beklenen: MCP solve == solve_sir_service)"
    )


def test_mcp_uncertainty_calls_core_service():
    """MCP uncertainty_analysis gercek core servis cagirmali.

    GERCEK: _call_tool('axiomize.uncertainty_analysis') echo stub dondurur
    ({'note': ..., 'echo': ...}), hicbir application servisini cagirmaz.
    Bu test parite kirik oldugu icin FAIL verir.
    """
    from axiomize.server import mcp_server

    out = mcp_server._call_tool("axiomize.uncertainty_analysis", {"fit": {}})
    assert "echo" not in out, (
        f"PARITE KIRIK (MCP uncertainty): echo stub donduruluyor: {out} "
        "(beklenen: gercek core servis ciktisi, 'echo' anahtari olmamali)"
    )
    assert any(k in out for k in ("intervals", "ci", "quantiles", "uncertainty")), (
        f"PARITE KIRIK (MCP uncertainty): belirsizlik araliklari yok: {sorted(out)}"
    )


def test_rest_sensitivity_route_exists_live():
    """REST sensitivity endpointi core sensitivity_service'e bagli olmali.

    GERCEK: rest_server.py'de /sensitivity rotasi yok (404); oysa
    sensitivity_service ve MCP sensitivity_analysis mevcut.
    Bu test parite kirik oldugu icin FAIL verir.
    """
    from axiomize.server.rest_server import start_server

    srv = start_server("127.0.0.1", 0)
    port = srv.server_address[1]
    thr = threading.Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    try:
        code, body = _rest_post(
            port, "/sensitivity",
            {"params": {"beta": 0.3, "gamma": 0.1}, "N": 100000.0, "I0": 10.0},
        )
        assert code == 200, (
            f"PARITE KIRIK (REST sensitivity): HTTP {code}: {body} "
            "(beklenen: 200 + sensitivity_service ciktisi)"
        )
        assert "local" in body and "mc_screening" in body, (
            f"PARITE KIRIK (REST sensitivity): beklenen anahtarlar yok: {sorted(body)}"
        )
    finally:
        srv.shutdown()
