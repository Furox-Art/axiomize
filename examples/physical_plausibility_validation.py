"""Physical-plausibility validation: three models that all pass dimensional analysis.

Dimensional consistency is necessary, not sufficient. The three models below
share one Model IR shape, one unit table and one solver, so every structural
check and every unit check passes. They differ only in the *sign* and the
*magnitude* of a drag force. Dimensional analysis cannot tell them apart.
Conservation laws and an independent closed-form reference can.

Run it::

    python examples/physical_plausibility_validation.py

It prints the real captured output, writes it to
``examples/physical_plausibility_validation_output.txt`` next to this file, and
exits non-zero if any claim in that file stops holding.

The physics
-----------
A 1 kg block slides on a level surface at 20 m/s, slowed by a linear
speed-dependent drag force. There is no slope, no contact friction and no
rolling resistance, so *no external work is done on the block*.

    dv/dt  = -a(v)                     a(v) is the drag deceleration
    dW/dt  =  m * a(v) * v              W = cumulative heat delivered to the surroundings

Because no external work crosses the boundary, mechanical energy is not
conserved but *total* energy is:

    0.5*m*v^2 + W  ==  0.5*m*v0^2      for all t      (conservation of energy)

Two further constraints follow from the physics alone, with no reference
solution needed:

    v(t) <= v0                  a purely dissipative force can only slow the block
    W(t) >= 0, non-decreasing   cumulative heat cannot be negative or un-happen

And the model has a closed-form solution, the strongest check of all:

    a(v) = (F/m)(v/v_ref)   =>   v(t) = v0 * exp(-F*t/(m*v_ref))

The three candidate models
--------------------------
==================  ====================================  ===============================
Model               dv/dt                                 Verdict
==================  ====================================  ===============================
``CORRECT``         ``-(F/m)*v/v_ref``                    passes everything
``WRONG_SIGN``      ``+(F/m)*v/v_ref``                    accelerates forever
``WRONG_SCALE``     ``-2*(F/m)*v/v_ref``                  too much drag for the heat it books
==================  ====================================  ===============================

``WRONG_SIGN`` is the classic slip: a drag force written with the wrong sign.
``WRONG_SCALE`` is the subtler failure. It slows the block too fast while
crediting the damper with less heat than the block actually lost, so it breaks
the energy ledger without its speed trace ever looking unphysical. Only the
conservation ledger separates it from the correct model.

Numerical error is not model error
-----------------------------------
The energy ledger does not close to machine precision, and it should not be
expected to: ``solve_ivp`` integrates a discretized system. This example does
not hide that. It runs the correct model at four solver tolerances and shows
that the residual shrinks with every tightening, which is the same separation
of numerical error from model error that :mod:`axiomize.numerical_verification`
applies everywhere else in the engine. The falsification threshold for the
energy ledger is then set *above* the measured numerical residual at the
settings actually used, so a scientific failure is never confused with
discretization error. On the run committed here the broken models miss their ledger
by roughly 1.0e+02 and 5.9e+04 joules, which is not a tolerance question.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

# Allow ``python examples/...py`` from a plain checkout without an editable
# install, which is how a reader who has just cloned the repository runs this.
_REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from axiomize.falsification.engine import Falsifier, evaluate_falsifiers  # noqa: E402
from axiomize.general_engine import simulate_model  # noqa: E402
from axiomize.model_ir import ModelIR  # noqa: E402
from axiomize.validation.status import ValidationStatus  # noqa: E402

OUTPUT_PATH = Path(__file__).with_name("physical_plausibility_validation_output.txt")

MODEL_NAME = "sliding-block-linear-drag"
M = 1.0          # kg
V0 = 20.0        # m/s, initial speed
V_REF = 10.0     # m/s, reference speed in the drag law
F = 5.0          # N, drag force coefficient
T_END = 5.0      # s
POINTS = 101

# Closed-form speed for the correct drag law: v(t) = v0 * exp(-F t / (m v_ref)).
TAU = M * V_REF / F
INITIAL_TOTAL_ENERGY = 0.5 * M * V0 ** 2

# Tightened solver settings, so the numerical residual sits well clear of the
# physics threshold. The tolerance ladder below shows why this matters.
SOLVER: dict[str, Any] = {"backend": "scipy", "method": "DOP853",
                          "rtol": 1e-10, "atol": 1e-12}

# The energy ledger is only required to close to the residual the discretization
# itself can deliver. The broken models miss that bound by many orders of magnitude,
# so the threshold is not doing the discriminative work.
ENERGY_TOLERANCE = 1e-7

TOLERANCE_LADDER: tuple[tuple[float, float], ...] = (
    (1e-7, 1e-9), (1e-8, 1e-10), (1e-10, 1e-12), (1e-12, 1e-14),
)

_MODEL_IR: dict[str, Any] = {
    "schema_version": "1.0",
    "name": MODEL_NAME,
    "domain": "mechanics",
    "family": "ode",
    "independent_variable": "t",
    "independent_unit": "second",
    "variables": [
        {"name": "x", "unit": "m", "initial": 0.0, "bounds": [None, None]},
        {"name": "v", "unit": "m/s", "initial": V0, "bounds": [None, None]},
        {"name": "W", "unit": "J", "initial": 0.0, "bounds": [0.0, None]},
    ],
    "parameters": [
        {"name": "m", "unit": "kg", "value": M},
        {"name": "v_ref", "unit": "m/s", "value": V_REF},
        {"name": "F", "unit": "N", "value": F},
    ],
    "equations": [
        {"target": "x", "expression": "v", "kind": "derivative"},
        {"target": "W", "expression": "F*v**2/v_ref", "kind": "derivative"},
    ],
    "assumptions": [
        "block on a level surface: no slope, no rolling resistance, no contact friction",
        "linear speed-dependent drag force of magnitude F*v/v_ref",
        "W is the cumulative heat delivered to the surroundings, not a state function of v",
    ],
}

# ``(label, dv/dt)``. Every expression is dimensionally identical: F/m is m/s^2
# and v/v_ref is dimensionless, so the unit checker sees the same thing for all
# three, whatever the sign and whatever the numeric factor. That is the point.
CANDIDATES: tuple[tuple[str, str], ...] = (
    ("CORRECT", "-(F/m)*v/v_ref"),
    ("WRONG_SIGN", "+(F/m)*v/v_ref"),
    ("WRONG_SCALE", "-2*(F/m)*v/v_ref"),
)

# Each falsifier names an observable, a threshold and a direction, and is
# evaluated against values measured from an actual run, never against prose.
FALSIFIERS = (
    Falsifier(name="energy_ledger_closes", observable="energy_residual",
              threshold=ENERGY_TOLERANCE, direction="above", model_id="conservation_of_energy"),
    Falsifier(name="dissipative_force_never_accelerates", observable="speed_above_initial",
              threshold=0.0, direction="above", model_id="passivity"),
    Falsifier(name="cumulative_heat_nondecreasing", observable="heat_decrease",
              threshold=0.0, direction="above", model_id="second_law_of_thermodynamics"),
    Falsifier(name="matches_closed_form_solution", observable="closed_form_relative_error",
              threshold=1e-8, direction="above", model_id="experimental_reference"),
)

LINES: list[str] = []


def emit(text: str = "") -> None:
    LINES.append(text)
    print(text)


def build_model(accel_expression: str, solver: dict[str, Any] | None = None) -> ModelIR:
    payload = dict(_MODEL_IR)
    payload["equations"] = [*_MODEL_IR["equations"],
                            {"target": "v", "expression": accel_expression, "kind": "derivative"}]
    if solver is not None:
        payload["solver"] = solver
    return ModelIR.from_dict(payload)


def run_model(model: ModelIR) -> dict[str, Any]:
    return simulate_model(model, t_span=(0.0, T_END), points=POINTS, approve_heavy=True)


def observations(result: dict[str, Any]) -> dict[str, float]:
    """Measure the observable quantities the falsifiers are evaluated against."""
    v = result["states"]["v"]
    W = result["states"]["W"]
    total = [0.5 * M * vi ** 2 + wi for vi, wi in zip(v, W, strict=True)]
    residual = max(abs(value - INITIAL_TOTAL_ENERGY) for value in total)
    heat_decrease = max(0.0, max(-(W[i] - W[i - 1]) for i in range(1, len(W))))
    reference_error = max(abs(v[i] - V0 * math.exp(-t / TAU))
                          for i, t in enumerate(result["time"])) / V0
    return {
        "energy_residual": residual,
        "speed_above_initial": max(0.0, max(v) - V0),
        "heat_decrease": heat_decrease,
        "closed_form_relative_error": reference_error,
    }


def report_tolerance_ladder() -> None:
    """Show the energy residual is discretization error, not model error."""
    emit("-" * 78)
    emit("NUMERICAL BASELINE: the CORRECT model's energy residual vs solver tolerance")
    emit("-" * 78)
    emit("The energy ledger is a statement about physics, but it is measured through a")
    emit("discretized integrator. Tightening the tolerance must shrink the residual. The")
    emit("falsification threshold is chosen above the residual at the settings used below,")
    emit("so a discretization artefact is never reported as a scientific failure.")
    emit()
    emit(f"  {'rtol':>8} {'atol':>8} {'nfev':>7} {'energy_residual[J]':>20} "
         f"{'closed_form_err':>18}")
    ladder: list[float] = []
    for rtol, atol in TOLERANCE_LADDER:
        result = run_model(build_model("-(F/m)*v/v_ref",
                                       {"backend": "scipy", "method": "DOP853",
                                        "rtol": rtol, "atol": atol}))
        obs = observations(result)
        ladder.append(obs["energy_residual"])
        emit(f"  {rtol:8.0e} {atol:8.0e} {result['diagnostics']['nfev']:7d} "
             f"{obs['energy_residual']:20.6e} {obs['closed_form_relative_error']:18.6e}")
    emit()
    # Every magnitude printed below is measured from the ladder above, never typed in.
    emit("  The residual falls at every step: "
         + " -> ".join(f"{value:.1e}" for value in ladder) + " J.")
    emit(f"  At the settings used for the three candidates (rtol={SOLVER['rtol']:.0e},")
    emit(f"  atol={SOLVER['atol']:.0e}) the residual is {ladder[2]:.1e} J, below the energy")
    emit(f"  threshold of {ENERGY_TOLERANCE:.0e} J.")
    emit()


def run() -> int:
    emit("=" * 78)
    emit("PHYSICAL-PLAUSIBILITY VALIDATION: dimensional checks pass, three models differ")
    emit("=" * 78)
    emit(f"model          : {MODEL_NAME}")
    emit("family         : ode, integrated by scipy solve_ivp (DOP853)")
    emit(f"horizon        : t in [0, {T_END:g}] s, {POINTS} output points")
    emit(f"parameters     : m={M:g} kg, v_ref={V_REF:g} m/s, F={F:g} N")
    emit(f"initial state  : x=0 m, v={V0:g} m/s, W=0 J")
    emit(f"initial energy : 0.5*m*v0^2 = {INITIAL_TOTAL_ENERGY:g} J")
    emit(f"closed form    : v(t) = v0 * exp(-F*t/(m*v_ref)), time constant {TAU:g} s")
    emit(f"solver         : rtol={SOLVER['rtol']:.0e}, atol={SOLVER['atol']:.0e}")
    emit()

    report_tolerance_ladder()

    summary: list[tuple[str, str, str, dict[str, float]]] = []

    for label, expression in CANDIDATES:
        result = run_model(build_model(expression, SOLVER))
        validation = result.get("validation", {})
        checks = validation.get("checks", [])
        failed = [c for c in checks if c["status"] == "FAIL"]
        unit_checks = [c for c in checks
                       if c["name"].startswith(("variable_unit", "parameter_unit", "independent_unit"))]

        emit("-" * 78)
        emit(f"MODEL {label}:  dv/dt = {expression}")
        emit("-" * 78)
        emit(f"  engine status            : {result['status']}")
        emit(f"  solver                   : {result['solver']['backend']} / "
             f"{result['solver']['method']} (nfev={result['diagnostics']['nfev']})")
        emit(f"  structural checks        : {len(checks)} run, "
             f"{len(checks) - len(failed)} PASS, {len(failed)} FAIL")
        emit(f"  unit checks              : {len(unit_checks)} run, all PASS")
        emit("  Dimensional analysis is satisfied identically by all three models.")
        emit()

        v = result["states"]["v"]
        W = result["states"]["W"]
        emit(f"  {'t[s]':>6} {'v[m/s]':>14} {'W[J]':>14} {'0.5mv^2+W[J]':>16}")
        for i in (0, 20, 40, 60, 80, POINTS - 1):
            total = 0.5 * M * v[i] ** 2 + W[i]
            emit(f"  {result['time'][i]:6.1f} {v[i]:14.7f} {W[i]:14.7f} {total:16.7f}")
        emit()

        obs = observations(result)
        outcome = evaluate_falsifiers(list(FALSIFIERS), obs)
        emit("  observables measured from the run:")
        for name, value in obs.items():
            emit(f"    {name:32s} {value:.6e}")
        emit()
        emit("  falsifiers:")
        for row in outcome["results"]:
            emit(f"    {row['falsifier']:36s} threshold={row['threshold']:<10g} "
                 f"observed={row['observed']:.6e} -> {row['status']}")
        emit(f"  model_status: {outcome['model_status']}")
        emit()
        summary.append((label, result["status"], outcome["model_status"].value, obs))

    emit("=" * 78)
    emit("SUMMARY")
    emit("=" * 78)
    emit(f"{'model':<16}{'engine':<10}{'falsification':<16}"
         f"{'energy_residual[J]':>20}{'closed_form_err':>18}")
    for label, engine_status, fals_status, obs in summary:
        emit(f"{label:<16}{engine_status:<10}{fals_status:<16}"
             f"{obs['energy_residual']:>20.6e}{obs['closed_form_relative_error']:>18.6e}")
    emit()
    emit("Interpretation")
    emit("  * Structural and unit checks cannot separate the three models. F/m * v/v_ref")
    emit("    has the same dimension whatever the sign and whatever the numeric factor, so")
    emit("    every unit check passes for all three.")
    emit("  * Conservation of energy separates CORRECT from both broken models.")
    emit("  * The closed-form reference solution separates CORRECT from WRONG_SCALE even")
    emit("    though WRONG_SCALE never violates passivity. Its speed trace looks plausible;")
    emit("    it simply decays twice as fast as the drag law it declares.")
    emit("  * WRONG_SIGN trips passivity as well. The block speeds up instead of slowing,")
    emit("    passing its own initial speed with no external work done.")
    emit("  * None of these verdicts needs a human to read the numbers: each is a named")
    emit("    observable, a threshold and a direction evaluated against real output.")
    emit("=" * 78)

    # Self-check: the committed output must still describe the real behaviour.
    expected = {"CORRECT": ValidationStatus.PASS,
                "WRONG_SIGN": ValidationStatus.FAIL,
                "WRONG_SCALE": ValidationStatus.FAIL}
    problems: list[str] = []
    for label, _engine, fals_status, _obs in summary:
        want = expected[label].value
        if fals_status != want:
            problems.append(f"{label}: falsification is {fals_status}, expected {want}")
    for label, engine_status, _fals, _obs in summary:
        if engine_status != "PASS":
            problems.append(f"{label}: engine status is {engine_status}, expected PASS")
    for label, _engine, _fals, obs in summary:
        if label != "CORRECT":
            continue
        if obs["closed_form_relative_error"] > 1e-8:
            problems.append("CORRECT: closed-form error above the declared 1e-8 threshold")
        if obs["energy_residual"] > ENERGY_TOLERANCE:
            problems.append("CORRECT: energy residual above the declared threshold")
    if problems:
        emit()
        for problem in problems:
            emit(f"SELF-CHECK FAILURE: {problem}")
        return 1
    emit()
    emit("SELF-CHECK: all three models simulate and pass every structural and unit check;")
    emit("CORRECT satisfies all four falsifiers while WRONG_SIGN and WRONG_SCALE are both")
    emit("rejected. The committed output matches current engine behaviour.")
    return 0


def main() -> int:
    code = run()
    OUTPUT_PATH.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print()
    print(f"captured output written to {OUTPUT_PATH}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
