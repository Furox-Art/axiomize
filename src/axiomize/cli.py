"""Axiomize command-line interface.

All adapters call the shared application-service layer. Legacy SIR/logistic
commands remain backward-compatible; ``axiomize model`` exposes the versioned
general Model IR engine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from axiomize.limits import MAX_ARRAY_ITEMS, MAX_RUN_JSON_BYTES


def _dump(payload: dict, path: str | None) -> int:
    text = json.dumps(payload, indent=2, default=str, allow_nan=False)
    if path:
        target = Path(path)
        target.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    else:
        print(text)
    return 0


def _load_object(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    source = Path(path)
    if source.stat().st_size > MAX_RUN_JSON_BYTES:
        raise ValueError(f"{path} exceeds hard JSON input limit of {MAX_RUN_JSON_BYTES} bytes")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def cmd_intake(args: argparse.Namespace) -> int:
    from axiomize.application.services import intake_service
    permissions = {
        "allow_spawn_subtasks": bool(args.allow_subtasks),
        "allow_repeat_alternative_methods": bool(args.allow_repeat),
        "allow_extra_paid_model_calls": bool(args.allow_extra_paid_calls),
    }
    payload = {
        "idea": args.idea,
        "context": _load_object(args.context_json),
        "signals": _load_object(args.signals_json),
        "question_mode": args.question_mode,
        "preferred_question_mode": args.preferred_question_mode,
        "rigor": args.rigor,
        "permissions": permissions,
    }
    return _dump(intake_service(payload), args.json)


def cmd_policy(args: argparse.Namespace) -> int:
    from axiomize.application.services import workflow_policy_service
    permissions = {
        "allow_spawn_subtasks": bool(args.allow_subtasks),
        "allow_repeat_alternative_methods": bool(args.allow_repeat),
        "allow_extra_paid_model_calls": bool(args.allow_extra_paid_calls),
    }
    out = workflow_policy_service({
        "signals": _load_object(args.signals_json),
        "question_mode": args.question_mode,
        "permissions": permissions,
    })
    return _dump(out, args.json)


def cmd_model(args: argparse.Namespace) -> int:
    """Dispatch versioned general-model operations through one JSON contract."""
    from axiomize.application import advanced_services as ads
    from axiomize.application import general_services as gs
    from axiomize.application import surrogate_services as ss

    payload = _load_object(args.input_json)
    if args.approve_heavy:
        payload["approve_heavy"] = True
    if args.approve_migration:
        payload["approve_migration"] = True
    if args.approve_repair:
        payload["approve_repair"] = True
    dispatch = {
        "plan": gs.model_plan_service,
        "validate": gs.model_validate_service,
        "simulate": gs.model_simulate_service,
        "fit": gs.model_fit_service,
        "compare": gs.model_compare_service,
        "repair": gs.model_repair_service,
        "export": gs.model_export_service,
        "stability": gs.model_stability_service,
        "validity": gs.model_validity_service,
        "discover": gs.model_discovery_service,
        "experiment-design": gs.experiment_design_service,
        "uncertainty": ads.model_uncertainty_service,
        "bifurcation": ads.model_bifurcation_service,
        "numerical-verify": ads.model_numerical_verification_service,
        "stop-check": ads.model_stopping_service,
        "surrogate": ss.model_surrogate_service,
    }
    out = dispatch[args.action](payload)
    rc = _dump(out, args.json)
    return 1 if out.get("status") in {"FAIL", "SURROGATE_REJECTED", "OUT_OF_DOMAIN"} else rc


def cmd_clean_data(args: argparse.Namespace) -> int:
    from axiomize.application.services import clean_data_service
    payload = _load_object(args.input_json)
    payload["drop_nonfinite"] = not args.reject_nonfinite
    payload["sort_time"] = not args.keep_order
    payload["duplicate_policy"] = args.duplicate_policy
    return _dump(clean_data_service(payload), args.json)


def cmd_compare_runs(args: argparse.Namespace) -> int:
    from axiomize.application.services import compare_runs_service
    return _dump(compare_runs_service({"before_dir": args.before_dir, "after_dir": args.after_dir}), args.json)


def cmd_solve(args: argparse.Namespace) -> int:
    from axiomize.application.services import solve_sir_service
    out = solve_sir_service({"beta": args.beta, "gamma": args.gamma,
                             "I0": args.I0, "N": args.N, "days": args.days})
    return _dump(out, args.json)


def cmd_fit(args: argparse.Namespace) -> int:
    import csv
    import numpy as np
    from axiomize.application.services import fit_logistic_service

    source = Path(args.data)
    if source.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("CSV input exceeds hard CLI limit of 64 MiB")
    rows: list[tuple[float, float]] = []
    with source.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row_number, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) < 2:
                raise ValueError(f"CSV row {row_number} needs at least two columns")
            rows.append((float(row[0]), float(row[1])))
            if len(rows) > MAX_ARRAY_ITEMS:
                raise ValueError(f"CSV exceeds hard row limit of {MAX_ARRAY_ITEMS}")
    if len(rows) < 2:
        raise ValueError("CSV requires at least two data rows")
    t = np.asarray([row[0] for row in rows], dtype=float)
    y = np.asarray([row[1] for row in rows], dtype=float)
    return _dump(fit_logistic_service({"t": t.tolist(), "y": y.tolist()}), args.json)


def cmd_validate(args: argparse.Namespace) -> int:
    from axiomize.application.services import validate_sir_service
    out = validate_sir_service({"beta": args.beta, "gamma": args.gamma,
                                "I0": args.I0, "N": args.N, "days": args.days})
    rc = _dump(out, args.json)
    return rc if out["status"] == "PASS" else 1


def cmd_tools(_args: argparse.Namespace) -> int:
    from axiomize.application.services import tools_service
    info = tools_service()
    for name, meta in info["tools"].items():
        flag = "available" if meta["available"] else f"UNAVAILABLE ({meta['reason']})"
        print(f"{name:12s} {meta['version']:10s} {flag}")
    return 0


def cmd_capabilities(_args: argparse.Namespace) -> int:
    from axiomize.application.services import capabilities_service
    print(json.dumps(capabilities_service(), indent=2))
    return 0


def cmd_reproduce(args: argparse.Namespace) -> int:
    from axiomize.runs.state import RunState
    run = RunState.load(args.run_id)
    print(json.dumps({"input_hash": run.input_hash(), "results": run.results}, indent=2, default=str))
    return 0


def cmd_benchmark(_args: argparse.Namespace) -> int:
    from axiomize.benchmark_suite import run_suite
    result = run_suite()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] == "PASS" else 1


def cmd_serve(args: argparse.Namespace) -> int:
    from axiomize.server import rest_server

    token = args.auth_token or os.getenv(args.auth_token_env)
    server = rest_server.start_server(
        args.host,
        args.port,
        run_root=args.run_root,
        allow_remote=bool(args.allow_remote),
        auth_token=token,
        max_concurrent_requests=args.max_concurrent_requests,
    )
    print(f"axiomize REST v1 on http://{args.host}:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from axiomize.server import mcp_server
    mcp_server.serve_stdio(run_root=args.run_root)
    return 0


def _add_consumption_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-subtasks", action="store_true",
                        help="explicitly allow spawning additional agent/subtasks")
    parser.add_argument("--allow-repeat", action="store_true",
                        help="explicitly allow repeating the analysis with alternative methods")
    parser.add_argument("--allow-extra-paid-calls", action="store_true",
                        help="explicitly allow extra paid/provider calls")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axiomize", description="Axiomize scientific engine CLI (API v1)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("intake", help="clarify a vague idea before mathematical modeling")
    p.add_argument("idea")
    p.add_argument("--context-json", default=None)
    p.add_argument("--signals-json", default=None)
    p.add_argument("--question-mode", choices=["adaptive", "one_by_one", "all_at_once"], default="adaptive")
    p.add_argument("--preferred-question-mode", choices=["one_by_one", "all_at_once"], default="one_by_one")
    p.add_argument("--rigor", choices=["weak", "medium", "strong", "basic", "standard", "research"], default=None)
    p.add_argument("--json", default=None)
    _add_consumption_flags(p)
    p.set_defaults(func=cmd_intake)

    p = sub.add_parser("policy", help="show adaptive workflow policy and consumption guard")
    p.add_argument("--signals-json", default=None)
    p.add_argument("--question-mode", choices=["adaptive", "one_by_one", "all_at_once"], default="adaptive")
    p.add_argument("--json", default=None)
    _add_consumption_flags(p)
    p.set_defaults(func=cmd_policy)

    p = sub.add_parser("model", help="plan/validate/simulate/fit/diagnose/export a versioned general Model IR")
    p.add_argument("--input-json", required=True, help="JSON request containing idea or model_ir")
    p.add_argument("--action", choices=[
        "plan", "validate", "simulate", "fit", "compare", "repair", "export",
        "stability", "validity", "discover", "experiment-design", "uncertainty",
        "bifurcation", "numerical-verify", "stop-check", "surrogate",
    ], default="plan")
    p.add_argument("--approve-heavy", action="store_true", help="approve heavy local compute for this invocation")
    p.add_argument("--approve-migration", action="store_true", help="approve displayed Model IR migration")
    p.add_argument("--approve-repair", action="store_true", help="approve constraint-driven rebuild/refit intent")
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_model)

    p = sub.add_parser("clean-data", help="clean paired numeric observations with a preserved audit trail")
    p.add_argument("--input-json", required=True)
    p.add_argument("--duplicate-policy", choices=["mean", "first", "error"], default="mean")
    p.add_argument("--reject-nonfinite", action="store_true")
    p.add_argument("--keep-order", action="store_true")
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_clean_data)

    p = sub.add_parser("compare-runs", help="explain why two recorded runs differ")
    p.add_argument("before_dir")
    p.add_argument("after_dir")
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_compare_runs)

    p = sub.add_parser("solve", help="solve the backward-compatible reference SIR model")
    p.add_argument("--beta", type=float, default=0.3)
    p.add_argument("--gamma", type=float, default=0.1)
    p.add_argument("--I0", type=float, default=10.0)
    p.add_argument("--N", type=float, required=True)
    p.add_argument("--days", type=float, default=180.0)
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_solve)

    p = sub.add_parser("fit", help="fit backward-compatible logistic growth to CSV (time,value)")
    p.add_argument("--data", required=True)
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_fit)

    p = sub.add_parser("validate", help="backward-compatible SIR solve + dimensional + cross-validation")
    p.add_argument("--beta", type=float, default=0.3)
    p.add_argument("--gamma", type=float, default=0.1)
    p.add_argument("--I0", type=float, default=10.0)
    p.add_argument("--N", type=float, required=True)
    p.add_argument("--days", type=float, default=180.0)
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("tools", help="list scientific backends and availability")
    p.set_defaults(func=cmd_tools)
    p = sub.add_parser("capabilities", help="machine-readable capability map")
    p.set_defaults(func=cmd_capabilities)
    p = sub.add_parser("reproduce", help="inspect a stored run")
    p.add_argument("run_id")
    p.set_defaults(func=cmd_reproduce)
    p = sub.add_parser("benchmark", help="run the install-safe scientific benchmark suite")
    p.set_defaults(func=cmd_benchmark)
    p = sub.add_parser("serve", help="start the REST API (v1)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--run-root", default=".", help="root directory containing REST-visible run directories")
    p.add_argument("--allow-remote", action="store_true", help="allow a non-loopback bind; requires an auth token")
    p.add_argument("--auth-token", default=None, help="REST bearer token (prefer the environment option below)")
    p.add_argument("--auth-token-env", default="AXIOMIZE_REST_TOKEN", help="environment variable containing REST bearer token")
    p.add_argument("--max-concurrent-requests", type=int, default=32)
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("mcp", help="serve MCP over stdio")
    p.add_argument("--run-root", default=".", help="root directory containing MCP-visible run directories")
    p.set_defaults(func=cmd_mcp)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
