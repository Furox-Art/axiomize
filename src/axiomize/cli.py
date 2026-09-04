"""Axiomize command-line interface (PHASE 8).

``axiomize solve --beta 0.3 --gamma 0.1 --N 1000000`` runs the same
application service the MCP and REST adapters call.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _dump(payload: dict, path: str | None) -> int:
    text = json.dumps(payload, indent=2, default=str)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {path}")
    else:
        print(text)
    return 0


def _load_object(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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


def cmd_solve(args: argparse.Namespace) -> int:
    from axiomize.application.services import solve_sir_service

    out = solve_sir_service({"beta": args.beta, "gamma": args.gamma,
                             "I0": args.I0, "N": args.N, "days": args.days})
    return _dump(out, args.json)


def cmd_fit(args: argparse.Namespace) -> int:
    import numpy as np

    from axiomize.application.services import fit_logistic_service

    with open(args.data, encoding="utf-8-sig") as fh:
        lines = fh.read().splitlines()[1:]
    rows = [line.split(",") for line in lines if line.strip()]
    t = np.array([float(r[0]) for r in rows])
    y = np.array([float(r[1]) for r in rows])
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
    print(json.dumps({"input_hash": run.input_hash(),
                      "results": run.results}, indent=2, default=str))
    return 0


def cmd_benchmark(_args: argparse.Namespace) -> int:
    """Run the package-native suite; works from a wheel without repo tests."""
    from axiomize.benchmark_suite import run_suite

    result = run_suite()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] == "PASS" else 1


def cmd_serve(args: argparse.Namespace) -> int:
    from axiomize.server import rest_server

    server = rest_server.start_server(args.host, args.port)
    print(f"axiomize REST v1 on http://{args.host}:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_mcp(_args: argparse.Namespace) -> int:
    from axiomize.server import mcp_server

    mcp_server.serve_stdio()
    return 0


def _add_consumption_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-subtasks", action="store_true",
                        help="explicitly allow spawning additional agent/subtasks")
    parser.add_argument("--allow-repeat", action="store_true",
                        help="explicitly allow repeating the analysis with alternative methods")
    parser.add_argument("--allow-extra-paid-calls", action="store_true",
                        help="explicitly allow extra paid/provider calls")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axiomize",
                                     description="Axiomize scientific engine CLI (API v1)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("intake", help="clarify a vague idea before mathematical modeling")
    p.add_argument("idea")
    p.add_argument("--context-json", default=None,
                   help="JSON object containing known system_boundary/goal/measurable_outcome/horizon/mechanism")
    p.add_argument("--signals-json", default=None,
                   help="JSON object with rigor signals such as high_stakes or mechanism_unclear")
    p.add_argument("--question-mode", choices=["adaptive", "one_by_one", "all_at_once"],
                   default="adaptive")
    p.add_argument("--preferred-question-mode", choices=["one_by_one", "all_at_once"],
                   default="one_by_one")
    p.add_argument("--rigor", choices=["weak", "medium", "strong", "basic", "standard", "research"],
                   default=None)
    p.add_argument("--json", default=None)
    _add_consumption_flags(p)
    p.set_defaults(func=cmd_intake)

    p = sub.add_parser("policy", help="show adaptive workflow policy and consumption guard")
    p.add_argument("--signals-json", default=None)
    p.add_argument("--question-mode", choices=["adaptive", "one_by_one", "all_at_once"],
                   default="adaptive")
    p.add_argument("--json", default=None)
    _add_consumption_flags(p)
    p.set_defaults(func=cmd_policy)

    p = sub.add_parser("solve", help="solve the SIR model through the full pipeline")
    p.add_argument("--beta", type=float, default=0.3)
    p.add_argument("--gamma", type=float, default=0.1)
    p.add_argument("--I0", type=float, default=10.0)
    p.add_argument("--N", type=float, required=True)
    p.add_argument("--days", type=float, default=180.0)
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_solve)

    p = sub.add_parser("fit", help="fit logistic growth to a CSV (time,value)")
    p.add_argument("--data", required=True)
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_fit)

    p = sub.add_parser("validate", help="solve + dimensional + cross-validation")
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

    p = sub.add_parser("benchmark", help="run the install-safe 12-case scientific benchmark suite")
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("serve", help="start the REST API (v1)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("mcp", help="serve MCP over stdio")
    p.set_defaults(func=cmd_mcp)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
