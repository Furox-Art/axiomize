"""Z3 logical-constraint verification adapter (PHASE 5).

Checks whether a set of inequality/equality constraints over bounded
real variables is jointly satisfiable. A contradiction is reported,
never hidden.
"""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.tools.base import ScientificTool
from axiomize.validation.status import ValidationStatus


class Z3Tool(ScientificTool):
    name: ClassVar[str] = "z3"
    capabilities: ClassVar[list[str]] = ["sat_check", "constraint_verification", "model_sampling"]

    @classmethod
    def _probe_version(cls) -> str:
        import z3  # type: ignore[import-untyped]

        return str(z3.get_version_string())

    def validate_input(self, payload: dict[str, Any]) -> None:
        if "constraints" not in payload or "variables" not in payload:
            raise ValueError("z3: payload needs 'constraints' and 'variables'")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        result = check_constraints(payload["constraints"], payload["variables"])
        return {"sat": result["sat"], "model": result["model"],
                "status": result["status"].value}


def check_constraints(constraints: list[str],
                      variables: dict[str, tuple[float, float]]) -> dict[str, Any]:
    """Check satisfiability of real-arithmetic constraints.

    Constraints are strings like ``"x > 1"`` or ``"x + y <= 5"`` over
    the declared variables. Evaluated with no builtins and only the
    declared Z3 reals plus And/Or/Not in scope.
    """
    import z3  # type: ignore[import-untyped]

    scope: dict[str, Any] = {name: z3.Real(name) for name in variables}
    scope.update({"And": z3.And, "Or": z3.Or, "Not": z3.Not})
    solver = z3.Solver()
    for name, (low, high) in variables.items():
        solver.add(scope[name] >= low, scope[name] <= high)
    for text in constraints:
        solver.add(eval(text, {"__builtins__": {}}, scope))
    verdict = solver.check()
    if verdict == z3.sat:
        model = solver.model()
        values = {}
        for name in variables:
            val = model[scope[name]]
            values[name] = float(val.as_decimal(12)) if val is not None else float("nan")
        return {"sat": True, "model": values, "status": ValidationStatus.PASS}
    if verdict == z3.unsat:
        return {"sat": False, "model": None, "status": ValidationStatus.FAIL}
    return {"sat": None, "model": None, "status": ValidationStatus.INCONCLUSIVE}
