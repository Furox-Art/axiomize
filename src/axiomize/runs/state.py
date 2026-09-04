"""Portable, agent-independent run state (PHASE 1 v1).

A scientific run lives on disk (``run.json`` + ``manifest.json``), not in
chat context, so another agent on another machine can inspect and
reproduce it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import axiomize


@dataclass
class RunState:
    problem_definition: str = ""
    variables: list[dict[str, Any]] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    candidate_models: list[dict[str, Any]] = field(default_factory=list)
    selected_model: str = ""
    tools_used: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    solver_settings: dict[str, Any] = field(default_factory=dict)
    equations: list[str] = field(default_factory=list)
    intermediate_results: dict[str, Any] = field(default_factory=dict)
    validation_results: dict[str, Any] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    uncertainty: dict[str, Any] = field(default_factory=dict)
    falsification_results: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.inputs and not self.parameters:
            self.parameters = dict(self.inputs)
        elif self.parameters and not self.inputs:
            self.inputs = dict(self.parameters)

    def add_result(self, key: str, value: Any) -> None:
        self.results[key] = value

    def _input_payload(self) -> dict[str, Any]:
        if self.inputs:
            return dict(self.inputs)
        return {
            "problem_definition": self.problem_definition,
            "variables": self.variables,
            "parameters": self.parameters,
            "assumptions": self.assumptions,
            "equations": self.equations,
            "solver_settings": self.solver_settings,
            "datasets": self.datasets,
        }

    def input_hash(self) -> str:
        canonical = json.dumps(self._input_payload(), sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def manifest(self) -> dict[str, Any]:
        versions: dict[str, str] = {"python": sys.version.split()[0]}
        for mod in ("numpy", "scipy", "sympy", "axiomize"):
            try:
                versions[mod] = str(getattr(__import__(mod), "__version__", "unknown"))
            except ImportError:
                versions[mod] = "not-installed"
        return {
            "axiomize_version": getattr(axiomize, "__version__", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_hash": self.input_hash(),
            "tool_versions": versions,
            "solver_settings": self.solver_settings,
            "tools_used": self.tools_used,
        }

    def save(self, run_dir: str | Path) -> Path:
        directory = Path(run_dir)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "run.json").write_text(
            json.dumps(asdict(self), indent=2, default=str), encoding="utf-8")
        (directory / "manifest.json").write_text(
            json.dumps(self.manifest(), indent=2, default=str), encoding="utf-8")
        return directory

    def export(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self), indent=2, default=str), encoding="utf-8")
        return target

    @classmethod
    def import_file(cls, path: str | Path) -> "RunState":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in payload.items() if k in known})

    @classmethod
    def load(cls, run_dir: str | Path) -> "RunState":
        payload = json.loads((Path(run_dir) / "run.json").read_text(encoding="utf-8"))
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in payload.items() if k in known})
