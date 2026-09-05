#!/usr/bin/env python3
"""Fail fast on package import-graph and facade compatibility regressions.

This gate exists because a package can pass many focused unit tests while an
adapter path still fails at import time.  It runs both against the source tree
and against the exact installed wheel used by CI/release.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from pathlib import Path


CRITICAL_MODULES = (
    "axiomize",
    "axiomize.general_engine_core",
    "axiomize.general_engine",
    "axiomize.advanced_diagnostics",
    "axiomize.advanced_family_engine",
    "axiomize.application.general_services",
    "axiomize.application.advanced_services",
    "axiomize.cli",
    "axiomize.server.rest_server",
    "axiomize.server.mcp_server",
)


class ContractFailure(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _configure_import_path(mode: str) -> None:
    root = _repo_root()
    src = root / "src"
    if mode == "source":
        sys.path.insert(0, str(src))
        return

    # Installed-wheel mode must not accidentally succeed by importing the
    # checkout's source tree.  Remove any explicit src entry if one leaked in.
    src_resolved = src.resolve()
    cleaned: list[str] = []
    for entry in sys.path:
        try:
            if Path(entry).resolve() == src_resolved:
                continue
        except (OSError, RuntimeError):
            pass
        cleaned.append(entry)
    sys.path[:] = cleaned


def _import(name: str):
    try:
        return importlib.import_module(name)
    except Exception as exc:  # import failures are the contract being tested
        raise ContractFailure(f"cannot import {name}: {type(exc).__name__}: {exc}") from exc


def _check_critical_modules() -> None:
    for name in CRITICAL_MODULES:
        _import(name)


def _check_facade_compatibility() -> None:
    engine = _import("axiomize.general_engine")
    # Advanced diagnostics historically imported these compatibility symbols.
    # Keep them as an explicit contract so a facade refactor cannot silently
    # remove them and break CLI/REST/MCP import paths again.
    for name in ("_parameter_values", "_sympy_expression"):
        value = getattr(engine, name, None)
        if not callable(value):
            raise ContractFailure(f"axiomize.general_engine missing callable compatibility symbol {name}")


def _check_all_discoverable_modules() -> int:
    package = _import("axiomize")
    failures: list[str] = []
    names = sorted(info.name for info in pkgutil.walk_packages(package.__path__, prefix="axiomize."))
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    if failures:
        joined = "\n  - ".join(failures)
        raise ContractFailure(f"package import graph has {len(failures)} failure(s):\n  - {joined}")
    return len(names)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="store_true", help="import from repository src/")
    parser.add_argument("--installed", action="store_true", help="import the installed wheel")
    args = parser.parse_args()
    if args.source == args.installed:
        parser.error("choose exactly one of --source or --installed")

    mode = "source" if args.source else "installed"
    _configure_import_path(mode)
    _check_critical_modules()
    _check_facade_compatibility()
    count = _check_all_discoverable_modules()
    print(f"PASS {mode} import contract: {count} discoverable axiomize modules imported")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractFailure as exc:
        print(f"FAIL import contract: {exc}", file=sys.stderr)
        raise SystemExit(1)
