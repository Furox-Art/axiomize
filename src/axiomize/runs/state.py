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
from importlib import metadata
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
    candidate_rankings: list[dict[str, Any]] = field(default_factory=list)
    selected_model: str = ""
    tools_used: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    data_transformations: list[dict[str, Any]] = field(default_factory=list)
    source_checks: list[dict[str, Any]] = field(default_factory=list)
    solver_settings: dict[str, Any] = field(default_factory=dict)
    equations: list[str] = field(default_factory=list)
    intermediate_results: dict[str, Any] = field(default_factory=dict)
    validation_results: dict[str, Any] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    uncertainty: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, str] = field(default_factory=dict)
    validity_domain: dict[str, Any] = field(default_factory=dict)
    sensitivity_results: dict[str, Any] = field(default_factory=dict)
    falsification_results: dict[str, Any] = field(default_factory=dict)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    visualizations: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    workflow_policy: dict[str, Any] = field(default_factory=dict)
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
            "data_transformations": self.data_transformations,
            "workflow_policy": self.workflow_policy,
        }

    def input_hash(self) -> str:
        canonical = json.dumps(self._input_payload(), sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _tool_versions() -> dict[str, str]:
        packages = {
            "numpy": "numpy",
            "scipy": "scipy",
            "sympy": "sympy",
            "networkx": "networkx",
            "statsmodels": "statsmodels",
            "matplotlib": "matplotlib",
            "z3": "z3-solver",
            "control": "control",
            "cvxpy": "cvxpy",
            "casadi": "casadi",
            "pymc": "pymc",
            "jax": "jax",
        }
        versions: dict[str, str] = {
            "python": sys.version.split()[0],
            "axiomize": getattr(axiomize, "__version__", "unknown"),
        }
        for name, distribution in packages.items():
            try:
                versions[name] = metadata.version(distribution)
            except metadata.PackageNotFoundError:
                versions[name] = "not-installed"
        return versions

    def manifest(self) -> dict[str, Any]:
        return {
            "axiomize_version": getattr(axiomize, "__version__", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_hash": self.input_hash(),
            "tool_versions": self._tool_versions(),
            "solver_settings": self.solver_settings,
            "tools_used": self.tools_used,
            "workflow_policy": self.workflow_policy,
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
