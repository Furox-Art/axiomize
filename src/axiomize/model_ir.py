"""Versioned, machine-readable model intermediate representation.

The IR is intentionally provider-agnostic. Natural-language agents may propose a
model, but solve/simulate/fit/validate/export consume this explicit structure so
that scientific checks, user-consent gates and reproducibility can be enforced
by deterministic code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

CURRENT_SCHEMA_VERSION = "1.0"


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
    CAUSAL = "causal"

    @classmethod
    def parse(cls, value: str) -> "ModelFamily":
        normalized = str(value).strip().lower().replace("-", "_")
        aliases = {
            "sde": cls.STOCHASTIC,
            "abm": cls.AGENT_BASED,
            "des": cls.DISCRETE_EVENT,
            "differential_algebraic": cls.DAE,
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
        bounds = payload.get("bounds")
        if bounds is not None:
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise ValueError(f"variable {payload.get('name', '<unknown>')} bounds must have length 2")
            bounds = (bounds[0], bounds[1])
        return cls(
            name=str(payload["name"]),
            unit=str(payload.get("unit", "dimensionless")),
            role=str(payload.get("role", "state")),
            initial=None if payload.get("initial") is None else float(payload["initial"]),
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
        bounds = payload.get("bounds")
        if bounds is not None:
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise ValueError(f"parameter {payload.get('name', '<unknown>')} bounds must have length 2")
            bounds = (bounds[0], bounds[1])
        return cls(
            name=str(payload["name"]),
            value=None if payload.get("value") is None else float(payload["value"]),
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
        return cls(
            target=str(payload.get("target", payload.get("lhs", ""))),
            expression=str(payload.get("expression", payload.get("rhs", ""))),
            kind=str(payload.get("kind", "derivative")),
            unit=None if payload.get("unit") is None else str(payload["unit"]),
            description=str(payload.get("description", "")),
        )


@dataclass(frozen=True)
class ConstraintSpec:
    """Explicit scientific or mathematical constraint.

    ``expression`` must evaluate to a numeric residual/observable. The check is
    visible and deterministic; it is never silently repaired. Supported
    relations are ``ge``, ``le``, ``eq`` and ``between``.
    """

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
        return cls(
            name=str(payload["name"]),
            expression=str(payload["expression"]),
            relation=str(payload.get("relation", "ge")),
            threshold=float(payload.get("threshold", 0.0)),
            upper=None if payload.get("upper") is None else float(payload["upper"]),
            tolerance=float(payload.get("tolerance", 1e-8)),
            severity=str(payload.get("severity", "error")),
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
        payload = dict(payload or {})
        return cls(
            backend=str(payload.get("backend", "auto")),
            method=str(payload.get("method", "auto")),
            rtol=float(payload.get("rtol", 1e-7)),
            atol=float(payload.get("atol", 1e-9)),
            max_steps=None if payload.get("max_steps") is None else int(payload["max_steps"]),
            fallbacks=tuple(str(v) for v in payload.get("fallbacks", [])),
        )


@dataclass(frozen=True)
class ProvenanceEvent:
    action: str
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProvenanceEvent":
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
        migrated = migrate_payload(payload, allow_migration=allow_migration)
        return cls(
            name=str(migrated.get("name", "model")),
            domain=str(migrated.get("domain", "general")),
            family=ModelFamily.parse(str(migrated["family"])),
            variables=[VariableSpec.from_dict(v) for v in migrated.get("variables", [])],
            parameters=[ParameterSpec.from_dict(p) for p in migrated.get("parameters", [])],
            equations=[EquationSpec.from_dict(e) for e in migrated.get("equations", [])],
            independent_variable=str(migrated.get("independent_variable", "t")),
            independent_unit=str(migrated.get("independent_unit", "dimensionless")),
            constraints=[ConstraintSpec.from_dict(c) for c in migrated.get("constraints", [])],
            boundary_conditions=dict(migrated.get("boundary_conditions", {})),
            assumptions=[str(v) for v in migrated.get("assumptions", [])],
            validity_domain=dict(migrated.get("validity_domain", {})),
            solver=SolverSpec.from_dict(migrated.get("solver")),
            metadata=dict(migrated.get("metadata", {})),
            provenance=[ProvenanceEvent.from_dict(v) for v in migrated.get("provenance", [])],
            schema_version=str(migrated.get("schema_version", CURRENT_SCHEMA_VERSION)),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["family"] = self.family.value
        payload["solver"]["fallbacks"] = list(self.solver.fallbacks)
        payload["schema_version"] = CURRENT_SCHEMA_VERSION
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

        variable_names = [v.name for v in self.variables]
        parameter_names = [p.name for p in self.parameters]
        add("unique_variables", len(variable_names) == len(set(variable_names)), str(variable_names))
        add("unique_parameters", len(parameter_names) == len(set(parameter_names)), str(parameter_names))
        overlap = sorted(set(variable_names) & set(parameter_names))
        add("symbol_namespace", not overlap, f"overlap={overlap}")

        if self.family in {ModelFamily.ODE, ModelFamily.STOCHASTIC}:
            state_names = {v.name for v in self.variables if v.role == "state"}
            targets = {e.target for e in self.equations if e.kind == "derivative"}
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


def migration_preview(payload: dict[str, Any]) -> dict[str, Any]:
    source = str(payload.get("schema_version", "0.9"))
    if source == CURRENT_SCHEMA_VERSION:
        return {"required": False, "from": source, "to": CURRENT_SCHEMA_VERSION, "changes": []}
    changes: list[str] = []
    if "model_family" in payload and "family" not in payload:
        changes.append("rename model_family -> family")
    if "states" in payload and "variables" not in payload:
        changes.append("rename states -> variables")
    if "rhs" in payload and "equations" not in payload:
        changes.append("convert rhs mapping -> derivative equations")
    changes.append(f"set schema_version -> {CURRENT_SCHEMA_VERSION}")
    return {"required": True, "from": source, "to": CURRENT_SCHEMA_VERSION, "changes": changes}


def migrate_payload(payload: dict[str, Any], *, allow_migration: bool = False) -> dict[str, Any]:
    out = dict(payload)
    preview = migration_preview(out)
    if not preview["required"]:
        return out
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
