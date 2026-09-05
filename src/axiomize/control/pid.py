"""Feedback-control analysis (PHASE 6).

Closed-loop step response of a plant under PID control, with bounded input
polynomials and explicit settling/overshoot metrics.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.limits import MAX_CONTROL_DIMENSION, MAX_POINTS, bounded_int

_MAX_TIME_HORIZON = 1e9


def _finite(value: Any, *, name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


def _poly(values: Any, *, name: str, allow_all_zero: bool) -> np.ndarray:
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a numeric 1D coefficient array") from exc
    if arr.ndim != 1 or arr.size == 0 or arr.size > MAX_CONTROL_DIMENSION:
        raise ValueError(f"{name} must contain 1..{MAX_CONTROL_DIMENSION} coefficients")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} coefficients must be finite")
    if not allow_all_zero and np.all(arr == 0):
        raise ValueError(f"{name} cannot be the zero polynomial")
    return arr


def closed_loop_step(kp: float, ki: float, kd: float,
                     plant_num: list[float], plant_den: list[float],
                     t_end: float = 20.0, n: int = 2000) -> dict[str, Any]:
    import control as ct

    kp = _finite(kp, name="kp")
    ki = _finite(ki, name="ki")
    kd = _finite(kd, name="kd")
    numerator = _poly(plant_num, name="plant_num", allow_all_zero=True)
    denominator = _poly(plant_den, name="plant_den", allow_all_zero=False)
    t_end = _finite(t_end, name="t_end")
    if t_end <= 0 or t_end > _MAX_TIME_HORIZON:
        raise ValueError(f"t_end must be in (0, {_MAX_TIME_HORIZON:g}]")
    n = bounded_int(n, name="control output points", minimum=2, maximum=MAX_POINTS)

    plant = ct.tf(numerator.tolist(), denominator.tolist())
    pid = ct.tf([kd, kp, ki], [1.0, 0.0])
    loop = ct.feedback(ct.series(pid, plant), 1)
    t = np.linspace(0, t_end, n)
    resp = ct.step_response(loop, t)
    y = np.asarray(resp.y, dtype=float).ravel()
    if y.size != n or not np.all(np.isfinite(y)):
        raise RuntimeError("control step response is malformed or non-finite")
    final = float(y[-1])
    peak = float(y.max())
    overshoot = max(0.0, peak - 1.0) if abs(final) > 1e-9 else 0.0
    band = 0.02
    settling: float | None = 0.0
    for i in range(n - 1, -1, -1):
        if abs(y[i] - 1.0) > band:
            settling = float(t[min(i + 1, n - 1)]) if i + 1 < n else None
            break
    settled = abs(final - 1.0) <= band
    if not settled:
        settling = None
    return {
        "final": final,
        "overshoot": float(overshoot),
        "settling_time": settling,
        "settled": bool(settled),
        "points": n,
    }
