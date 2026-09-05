"""Versioned, machine-readable model intermediate representation.

The IR is intentionally provider-agnostic. Natural-language agents may propose a
model, but solve/simulate/fit/validate/export consume this explicit structure so
that scientific checks, user-consent gates and reproducibility can be enforced
by deterministic code.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from axiomize.limits import (
    MAX_MODEL_CONSTRAINTS,
    MAX_MODEL_EQUATIONS,
    MAX_MODEL_PARAMETERS,
    MAX_MODEL_VARIABLES,
)
from axiomize.safe_expression import validate_identifier

CURRENT_SCHEMA_VERSION = "1.0"
_SUPPORTED_LEGACY_SCHEMA_VERSIONS = frozenset({"0.9"})

_VARIABLE_ROLES = frozenset({"state", "latent", "output", "input", "decision", "algebraic"})
_EQUATION_KINDS = frozenset({
    "derivative", "residual", "algebraic", "constraint", "objective",
    "update", "difference", "likelihood", "observation", "mean",
})
_CONSTRAINT_RELATIONS = frozenset({"ge", "le", "eq", "between"})
_CONSTRAINT_SEVERITIES = frozenset({"error", "warning", "info"})


def _finite(value: Any, *, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _bounds(payload: Any, *, name: str) -> tuple[float | None, float | None] | None:
    if payload is None:
        return None
    if not isinstance(payload, (list, tuple)) or len(payload) != 2:
        raise ValueError(f"{name} bounds must have length 2")
    low = None if payload[0] is None else _finite(payload[0], name=f"{name} lower bound")
    high = None if payload[1] is None else _finite(payload[1], name=f"{name} upper bound")
    if low is not None and high is not None and low > high:
        raise ValueError(f"{name} lower bound must be <= upper bound")
    return (low, high)


def _bounded_list(payload: Any, *, name: str, maximum: int) -> list[Any]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError(f"{name} must be an array")
    if len(payload) > maximum:
        raise ValueError(f"{name} exceeds hard safety limit of {maximum}")
    return payload


class ModelFamily(str, Enum):
    ALGEBRAIC = "algebraic"
    ODE = "ode"
    PDE = "pde"
    DAE = "dae"
    STOCHASTIC = "stochastic"
    OPTIMIZATION = "optimization"
    CONTROL = "control"
    NETWORK = "network"
    BAYESIAN = "bayesian"
    AGENT_BASED = "agent_based"
    DISCRETE_EVENT = "discrete_event"
    HYBRID = "hybrid"
    MULTIPHYSICS = "multiphysics"
    CAUSAL = "causal"

    @classmethod
    def parse(cls, value: str) -> "ModelFamily":
        normalized = str(value).strip().lower().replace("-", "_")
        aliases = {
            "sde": cls.STOCHASTIC,
            "abm": cls.AGENT_BASED,
            "des": cls.DISCRETE_EVENT,
            "differential_algebraic": cls.DAE,
            "multi_physics": cls.MULTIPHYSICS,
            "coupled_physics": cls.MULTIPHYSICS,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return cls(normalized)
        except ValueError as exc:
            supported = ", ".join(item.value for item in cls)
            raise ValueError(f"unsupported model family {value!r}; choose one of: {supported}") from exc


@dataclass(frozen=True)
class VariableSpec:
    name: str
    unit: str = "dimensionless"
    role: str = "state"
    initial: float | None = None
    bounds: tuple[float | None, float | None] | None = None
    description: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VariableSpec":
        if not isinstance(payload, dict):
            raise ValueError("variable entry must be an object")
        name = validate_identifier(str(payload["name"]), what="variable name")
        role = str(payload.get("role", "state")).strip().lower()
        if role not in _VARIABLE_ROLES:
            raise ValueError(f"variable {name!r} has unsupported role {role!r}")
        initial = None if payload.get("initial") is None else _finite(payload["initial"], name=f"variable {name} initial")
        bounds = _bounds(payload.get("bounds"), name=f"variable {name}")
        return cls(
            name=name,
            unit=str(payload.get("unit", "dimensionless")),
            role=role,
            initial=initial,
            bounds=bounds,
            description=str(payload.get("description", "")),
        )


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    value: float | None = None
    unit: str = "dimensionless"
    bounds: tuple[float | None, float | None] | None = None
    fit: bool = False
    prior: dict[str, Any] | None = None
    description: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ParameterSpec":
        if not isinstance(payload, dict):
            raise ValueError("parameter entry must be an object")
        name = validate_identifier(str(payload["name"]), what="parameter name")
        value = None if payload.get("value") is None else _finite(payload["value"], name=f"parameter {name} value")
        bounds = _bounds(payload.get("bounds"), name=f"parameter {name}")
        return cls(
            name=name,
            value=value,
            unit=str(payload.get("unit", "dimensionless")),
            bounds=bounds,
            fit=bool(payload.get("fit", False)),
            prior=dict(payload["prior"]) if isinstance(payload.get("prior"), dict) else None,
            description=str(payload.get("description", "")),
        )


@dataclass(frozen=True)
class EquationSpec:
    """A machine-readable equation.

    For ODE/SDE models, ``target`` names a state and ``expression`` is its time
    derivative. For algebraic models, ``target = expression`` is interpreted as
    an equation. ``kind='residual'`` means ``expression == 0``.
    """

    target: str
    expression: str
    kind: str = "derivative"
    unit: str | None = None
    description: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EquationSpec":
        if not isinstance(payload, dict):
            raise ValueError("equation entry must be an object")
        target = str(payload.get("target", payload.get("lhs", ""))).strip()
        if target:
            target = validate_identifier(target, what="equation target")
        expression = str(payload.get("expression", payload.get("rhs", ""))).strip()
        if not expression:
            raise ValueError("equation expression must be non-empty")
        kind = str(payload.get("kind", "derivative")).strip().lower()
        if kind not in _EQUATION_KINDS:
            raise ValueError(f"unsupported equation kind {kind!r}")
        if kind not in {"residual", "objective"} and not target:
            raise ValueError(f"equation kind {kind!r} requires a target")
        return cls(
            target=target,
            expression=expression,
            kind=kind,
            unit=None if payload.get("unit") is None else str(payload["unit"]),
            description=str(payload.get("description", "")),
        )


@dataclass(frozen=True)
class ConstraintSpec:
    """Explicit scientific or mathematical constraint."""

    name: str
    expression: str
    relation: str = "ge"
    threshold: float = 0.0
    upper: float | None = None
    tolerance: float = 1e-8
    severity: str = "error"
    scientific_basis: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ConstraintSpec":
        if not isinstance(payload, dict):
            raise ValueError("constraint entry must be an object")
        relation = str(payload.get("relation", "ge")).strip().lower()
        if relation not in _CONSTRAINT_RELATIONS:
            raise ValueError(f"unsupported constraint relation {relation!r}")
        severity = str(payload.get("severity", "error")).strip().lower()
        if severity not in _CONSTRAINT_SEVERITIES:
            raise ValueError(f"unsupported constraint severity {severity!r}")
        tolerance = _finite(payload.get("tolerance", 1e-8), name="constraint tolerance")
        if tolerance < 0:
            raise ValueError("constraint tolerance must be non-negative")
        threshold = _finite(payload.get("threshold", 0.0), name="constraint threshold")
        upper = None if payload.get("upper") is None else _finite(payload["upper"], name="constraint upper")
        if relation == "between":
            if upper is None:
                raise ValueError("constraint relation='between' requires upper")
            if upper < threshold:
                raise ValueError("constraint upper must be >= threshold")
        expression = str(payload["expression"]).strip()
        if not expression:
            raise ValueError("constraint expression must be non-empty")
        return cls(
            name=str(payload["name"]),
            expression=expression,
            relation=relation,
            threshold=threshold,
            upper=upper,
            tolerance=tolerance,
            severity=severity,
            scientific_basis=str(payload.get("scientific_basis", "")),
        )


@dataclass(frozen=True)
class SolverSpec:
    backend: str = "auto"
    method: str = "auto"
    rtol: float = 1e-7
    atol: float = 1e-9
    max_steps: int | None = None
    fallbacks: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "SolverSpec":
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("solver must be an object")
        payload = dict(payload or {})
        rtol = _finite(payload.get("rtol", 1e-7), name="solver.rtol")
        atol = _finite(payload.get("atol", 1e-9), name="solver.atol")
        if rtol <= 0 or atol <= 0:
            raise ValueError("solver rtol and atol must be positive")
        max_steps = None if payload.get("max_steps") is None else int(payload["max_steps"])
        if max_steps is not None and max_steps <= 0:
            raise ValueError("solver.max_steps must be positive")
        fallbacks = payload.get("fallbacks", [])
        if not isinstance(fallbacks, (list, tuple)) or len(fallbacks) > 32:
            raise ValueError("solver.fallbacks must be an array with at most 32 entries")
        return cls(
            backend=str(payload.get("backend", "auto")),
            method=str(payload.get("method", "auto")),
            rtol=rtol,
            atol=atol,
            max_steps=max_steps,
            fallbacks=tuple(str(v) for v in fallbacks),
        )


@dataclass(frozen=True)
class ProvenanceEvent:
    action: str
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProvenanceEvent":
        if not isinstance(payload, dict):
            raise ValueError("provenance event must be an object")
        return cls(action=str(payload["action"]), detail=dict(payload.get("detail", {})))


@dataclass
class ModelIR:
    name: str
    domain: str
    family: ModelFamily
    variables: list[VariableSpec]
    parameters: list[ParameterSpec]
    equations: list[EquationSpec]
    independent_variable: str = "t"
    independent_unit: str = "dimensionless"
    constraints: list[ConstraintSpec] = field(default_factory=list)
    boundary_conditions: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    validity_domain: dict[str, Any] = field(default_factory=dict)
    solver: SolverSpec = field(default_factory=SolverSpec)
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: list[ProvenanceEvent] = field(default_factory=list)
    schema_version: str = CURRENT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, allow_migration: bool = False) -> "ModelIR":
        if not isinstance(payload, dict):
            raise ValueError("Model IR must be an object")
        migrated = migrate_payload(payload, allow_migration=allow_migration)
        variables = _bounded_list(migrated.get("variables", []), name="variables", maximum=MAX_MODEL_VARIABLES)
        parameters = _bounded_list(migrated.get("parameters", []), name="parameters", maximum=MAX_MODEL_PARAMETERS)
        equations = _bounded_list(migrated.get("equations", []), name="equations", maximum=MAX_MODEL_EQUATIONS)
        constraints = _bounded_list(migrated.get("constraints", []), name="constraints", maximum=MAX_MODEL_CONSTRAINTS)
        independent = validate_identifier(
            str(migrated.get("independent_variable", "t")), what="independent variable"
        )
        model = cls(
            name=str(migrated.get("name", "model")),
            domain=str(migrated.get("domain", "general")),
            family=ModelFamily.parse(str(migrated["family"])),
            variables=[VariableSpec.from_dict(v) for v in variables],
            parameters=[ParameterSpec.from_dict(p) for p in parameters],
            equations=[EquationSpec.from_dict(e) for e in equations],
            independent_variable=independent,
            independent_unit=str(migrated.get("independent_unit", "dimensionless")),
            constraints=[ConstraintSpec.from_dict(c) for c in constraints],
            boundary_conditions=dict(migrated.get("boundary_conditions", {})),
            assumptions=[str(v) for v in migrated.get("assumptions", [])],
            validity_domain=dict(migrated.get("validity_domain", {})),
            solver=SolverSpec.from_dict(migrated.get("solver")),
            metadata=dict(migrated.get("metadata", {})),
            provenance=[ProvenanceEvent.from_dict(v) for v in migrated.get("provenance", [])],
            schema_version=str(migrated.get("schema_version", CURRENT_SCHEMA_VERSION)),
        )
        failed = [c for c in model.validate_structure() if c["status"] == "FAIL"]
        if failed:
            details = "; ".join(f"{c['name']}: {c['detail']}" for c in failed)
            raise ValueError(f"invalid Model IR structure: {details}")
        return model

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["family"] = self.family.value
        payload["solver"]["fallbacks"] = list(self.solver.fallbacks)
        # Preserve the object's version exactly.  Changing it here would be a
        # silent migration and would violate the Model IR audit contract.
        payload["schema_version"] = self.schema_version
        return payload

    def validate_structure(self) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []

        def add(name: str, ok: bool, detail: str) -> None:
            checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})

        add("schema_version", self.schema_version == CURRENT_SCHEMA_VERSION,
            f"schema={self.schema_version}; expected={CURRENT_SCHEMA_VERSION}")
        add("name", bool(self.name.strip()), "model name must be non-empty")
        add("variables", bool(self.variables), f"n={len(self.variables)}")
        add("equations", bool(self.equations), f"n={len(self.equations)}")
        add("variable_limit", len(self.variables) <= MAX_MODEL_VARIABLES, f"n={len(self.variables)}")
        add("parameter_limit", len(self.parameters) <= MAX_MODEL_PARAMETERS, f"n={len(self.parameters)}")
        add("equation_limit", len(self.equations) <= MAX_MODEL_EQUATIONS, f"n={len(self.equations)}")
        add("constraint_limit", len(self.constraints) <= MAX_MODEL_CONSTRAINTS, f"n={len(self.constraints)}")

        variable_names = [v.name for v in self.variables]
        parameter_names = [p.name for p in self.parameters]
        add("unique_variables", len(variable_names) == len(set(variable_names)), str(variable_names))
        add("unique_parameters", len(parameter_names) == len(set(parameter_names)), str(parameter_names))
        overlap = sorted(set(variable_names) & set(parameter_names))
        add("symbol_namespace", not overlap, f"overlap={overlap}")
        independent_collision = self.independent_variable in set(variable_names) | set(parameter_names)
        add("independent_namespace", not independent_collision,
            f"independent_variable={self.independent_variable}")

        variable_set = set(variable_names)
        targeted_kinds = {"derivative", "algebraic", "constraint", "update", "difference", "likelihood", "observation", "mean"}
        bad_targets = sorted({e.target for e in self.equations if e.kind in targeted_kinds and e.target not in variable_set})
        add("equation_targets_known", not bad_targets, f"unknown_targets={bad_targets}")

        derivative_targets = [e.target for e in self.equations if e.kind == "derivative"]
        duplicates = sorted({name for name in derivative_targets if derivative_targets.count(name) > 1})
        add("unique_derivative_targets", not duplicates, f"duplicates={duplicates}")

        if self.family in {ModelFamily.ODE, ModelFamily.STOCHASTIC}:
            state_names = {v.name for v in self.variables if v.role == "state"}
            targets = set(derivative_targets)
            missing = sorted(state_names - targets)
            unknown = sorted(targets - state_names)
            add("state_equations_complete", not missing and not unknown,
                f"missing={missing}; unknown_targets={unknown}")

        for v in self.variables:
            if v.bounds is not None and v.initial is not None:
                low, high = v.bounds
                ok = (low is None or v.initial >= low) and (high is None or v.initial <= high)
                add(f"initial_in_bounds:{v.name}", ok,
                    f"initial={v.initial}; bounds={v.bounds}")
        for p in self.parameters:
            if p.bounds is not None and p.value is not None:
                low, high = p.bounds
                ok = (low is None or p.value >= low) and (high is None or p.value <= high)
                add(f"parameter_in_bounds:{p.name}", ok,
                    f"value={p.value}; bounds={p.bounds}")
        return checks


class MigrationApprovalRequired(ValueError):
    def __init__(self, preview: dict[str, Any]):
        self.preview = preview
        super().__init__(
            "model IR migration requires explicit approval; inspect preview and retry with allow_migration=true"
        )


class UnsupportedSchemaVersion(ValueError):
    """Raised when a schema is newer/unknown and no deterministic migration exists."""


def migration_preview(payload: dict[str, Any]) -> dict[str, Any]:
    source = str(payload.get("schema_version", "0.9"))
    if source == CURRENT_SCHEMA_VERSION:
        return {
            "required": False,
            "supported": True,
            "from": source,
            "to": CURRENT_SCHEMA_VERSION,
            "changes": [],
        }
    if source not in _SUPPORTED_LEGACY_SCHEMA_VERSIONS:
        return {
            "required": True,
            "supported": False,
            "from": source,
            "to": CURRENT_SCHEMA_VERSION,
            "changes": [],
            "reason": "no deterministic migration is registered for this schema version",
        }
    changes: list[str] = []
    if "model_family" in payload and "family" not in payload:
        changes.append("rename model_family -> family")
    if "states" in payload and "variables" not in payload:
        changes.append("rename states -> variables")
    if "rhs" in payload and "equations" not in payload:
        changes.append("convert rhs mapping -> derivative equations")
    changes.append(f"set schema_version -> {CURRENT_SCHEMA_VERSION}")
    return {
        "required": True,
        "supported": True,
        "from": source,
        "to": CURRENT_SCHEMA_VERSION,
        "changes": changes,
    }


def migrate_payload(payload: dict[str, Any], *, allow_migration: bool = False) -> dict[str, Any]:
    out = dict(payload)
    preview = migration_preview(out)
    if not preview["required"]:
        return out
    if not preview.get("supported", False):
        raise UnsupportedSchemaVersion(
            f"unsupported Model IR schema {preview['from']!r}; current schema is {CURRENT_SCHEMA_VERSION!r}"
        )
    if not allow_migration:
        raise MigrationApprovalRequired(preview)

    if "model_family" in out and "family" not in out:
        out["family"] = out.pop("model_family")
    if "states" in out and "variables" not in out:
        states = out.pop("states")
        if isinstance(states, dict):
            out["variables"] = [
                {"name": name, **(spec if isinstance(spec, dict) else {"initial": spec})}
                for name, spec in states.items()
            ]
        else:
            out["variables"] = states
    if "rhs" in out and "equations" not in out:
        rhs = out.pop("rhs")
        if not isinstance(rhs, dict):
            raise ValueError("legacy rhs must be a mapping of state -> expression")
        out["equations"] = [
            {"target": name, "expression": expr, "kind": "derivative"}
            for name, expr in rhs.items()
        ]
    out["schema_version"] = CURRENT_SCHEMA_VERSION
    metadata = dict(out.get("metadata", {}))
    history = list(metadata.get("migration_history", []))
    history.append(preview)
    metadata["migration_history"] = history
    out["metadata"] = metadata
    provenance = list(out.get("provenance", []))
    provenance.append({"action": "model_ir_migration", "detail": preview})
    out["provenance"] = provenance
    return out
