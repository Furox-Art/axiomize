"""Runnable version of the Axiomize README quickstart.

Keep this file and the quickstart snippets in ``README.md`` and
``docs/quickstart.md`` in sync. ``.github/scripts/readme_example_check.py``
executes this module and asserts that its output still matches the blocks
quoted in those documents, so a README example cannot silently rot.

Run it directly::

    python examples/quickstart_sir.py
"""

from axiomize.general_engine import simulate_model
from axiomize.model_ir import ModelIR

MODEL = {
    "schema_version": "1.0",
    "name": "sir-outbreak",
    "domain": "epidemiology",
    "family": "ode",
    "independent_variable": "t",
    "independent_unit": "day",
    "variables": [
        {"name": "S", "unit": "person", "initial": 990.0, "bounds": [0.0, None]},
        {"name": "I", "unit": "person", "initial": 10.0, "bounds": [0.0, None]},
    ],
    "parameters": [
        {"name": "beta", "unit": "1/day", "value": 0.3, "bounds": [0.0, None]},
        {"name": "gamma", "unit": "1/day", "value": 0.1, "bounds": [0.0, None]},
        {"name": "N", "unit": "persons", "value": 1000.0},
    ],
    "equations": [
        {"target": "S", "expression": "-beta*I*S/N", "kind": "derivative"},
        {"target": "I", "expression": "beta*I*S/N - gamma*I", "kind": "derivative"},
    ],
    "constraints": [
        {
            "name": "cases_nonnegative",
            "expression": "I",
            "relation": "ge",
            "threshold": 0.0,
            "scientific_basis": "case counts cannot be negative",
        }
    ],
    "assumptions": ["closed population of 1000", "homogeneous mixing"],
}

T_SPAN = (0.0, 30.0)
POINTS = 4
EXPECTED_INFECTED = [10.0, 65.393, 239.869, 290.024]


def main() -> int:
    model = ModelIR.from_dict(MODEL)
    result = simulate_model(model, t_span=T_SPAN, points=POINTS)

    print(f"status: {result['status']}")
    print(f"solver: {result['solver']['backend']} / {result['solver']['method']}")
    print(f"days:   {result['time']}")
    print(f"infected: {[round(value, 3) for value in result['states']['I']]}")
    print(f"checks: {result['validation']['status']} ({len(result['validation']['checks'])} of them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())