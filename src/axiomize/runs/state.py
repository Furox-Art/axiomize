"""Portable, agent-independent run state (PHASE 1 v1).

A scientific run lives on disk (``run.json`` + ``manifest.json``), not in
chat context, so another agent on another machine can inspect and reproduce it.
Server/tool interfaces must use :meth:`RunState.load_under_root` rather than
passing an untrusted filesystem path directly to :meth:`load`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import axiomize
from axiomize.limits import MAX_RUN_JSON_BYTES

RUN_FORMAT_VERSION = 1


def _read_json_bounded(path: Path, *, maximum: int = MAX_RUN_JSON_BYTES) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"cannot read run-state file {path.name!r}: {exc}") from exc
    if size < 0 or size > maximum:
        raise ValueError(f"{path.name} exceeds hard size limit of {maximum} bytes")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid run-state JSON in {path.name!r}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _atomic_write_text(path: Path, text: str) -> None:
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_RUN_JSON_BYTES:
        raise ValueError(f"{path.name} exceeds hard size limit of {MAX_RUN_JSON_BYTES} bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", delete=False, dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def resolve_run_directory(root: str | Path, run_id: str) -> Path:
    """Resolve an untrusted run identifier strictly beneath ``root``."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string")
    if "\x00" in run_id:
        raise ValueError("run_id contains NUL")
    root_path = Path(root).expanduser().resolve()
    candidate_input = Path(run_id)
    if candidate_input.is_absolute():
        raise ValueError("absolute run paths are not allowed through this interface")
    candidate = (root_path / candidate_input).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("run_id escapes the configured run root") from exc
    return candidate


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
        canonical = json.dumps(self._input_payload(), sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _tool_versions() -> dict[str, str]:
        packages = {
            "numpy": "numpy", "scipy": "scipy", "sympy": "sympy",
            "networkx": "networkx", "statsmodels": "statsmodels",
            "matplotlib": "matplotlib", "z3": "z3-solver", "control": "control",
            "cvxpy": "cvxpy", "casadi": "casadi", "pymc": "pymc", "jax": "jax",
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

    def _run_text(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str, sort_keys=True)

    def manifest(self, *, run_sha256: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "run_format_version": RUN_FORMAT_VERSION,
            "axiomize_version": getattr(axiomize, "__version__", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_hash": self.input_hash(),
            "tool_versions": self._tool_versions(),
            "solver_settings": self.solver_settings,
            "tools_used": self.tools_used,
            "workflow_policy": self.workflow_policy,
        }
        if run_sha256 is not None:
            payload["run_sha256"] = run_sha256
        return payload

    def save(self, run_dir: str | Path) -> Path:
        directory = Path(run_dir)
        directory.mkdir(parents=True, exist_ok=True)
        run_text = self._run_text()
        run_sha256 = hashlib.sha256(run_text.encode("utf-8")).hexdigest()
        manifest_text = json.dumps(self.manifest(run_sha256=run_sha256), indent=2, default=str, sort_keys=True)
        # Each file is atomic. Write run first and manifest last so a manifest
        # never advertises a run payload that was not fully persisted.
        _atomic_write_text(directory / "run.json", run_text)
        _atomic_write_text(directory / "manifest.json", manifest_text)
        return directory

    def export(self, path: str | Path) -> Path:
        target = Path(path)
        _atomic_write_text(target, self._run_text())
        return target

    @classmethod
    def _from_payload(cls, payload: dict[str, Any]) -> "RunState":
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in payload.items() if k in known})

    @classmethod
    def import_file(cls, path: str | Path) -> "RunState":
        return cls._from_payload(_read_json_bounded(Path(path)))

    @classmethod
    def load(cls, run_dir: str | Path, *, verify_integrity: bool = True) -> "RunState":
        directory = Path(run_dir)
        run_path = directory / "run.json"
        payload = _read_json_bounded(run_path)
        run = cls._from_payload(payload)
        if not verify_integrity:
            return run

        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            manifest = _read_json_bounded(manifest_path)
            declared_version = manifest.get("run_format_version")
            if declared_version is not None and int(declared_version) != RUN_FORMAT_VERSION:
                raise ValueError(f"unsupported run format version: {declared_version}")
            expected_run_hash = manifest.get("run_sha256")
            if expected_run_hash is not None:
                actual_run_hash = hashlib.sha256(run_path.read_bytes()).hexdigest()
                if actual_run_hash != str(expected_run_hash):
                    raise ValueError("run.json integrity check failed against manifest run_sha256")
            expected_input_hash = manifest.get("input_hash")
            if expected_input_hash is not None and run.input_hash() != str(expected_input_hash):
                raise ValueError("run input_hash integrity check failed against manifest")
        return run

    @classmethod
    def load_under_root(cls, root: str | Path, run_id: str) -> "RunState":
        """Load an untrusted run ID without allowing filesystem traversal."""
        return cls.load(resolve_run_directory(root, run_id), verify_integrity=True)
