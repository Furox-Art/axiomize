"""Feedback-control analysis (PHASE 6).

Closed-loop step response of a plant under PID control, with
settling/overshoot metrics instead of eyeballing a plot.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def closed_loop_step(kp: float, ki: float, kd: float,
                     plant_num: list[float], plant_den: list[float],
                     t_end: float = 20.0, n: int = 2000) -> dict[str, Any]:
    import control as ct

    plant = ct.tf(plant_num, plant_den)
    pid = ct.tf([kd, kp, ki], [1.0, 0.0])
    loop = ct.feedback(ct.series(pid, plant), 1)
    t = np.linspace(0, t_end, n)
    resp = ct.step_response(loop, t)
    y = np.asarray(resp.y).ravel()
    final = float(y[-1])
    peak = float(y.max())
    overshoot = max(0.0, (peak - 1.0)) if abs(final) > 1e-9 else 0.0
    band = 0.02
    settling: float | None = None
    for i in range(n - 1, -1, -1):
        if abs(y[i] - 1.0) > band:
            settling = float(t[min(i + 1, n - 1)])
            break
    settled = abs(final - 1.0) <= band
    return {"final": final, "overshoot": overshoot,
            "settling_time": settling, "settled": settled}
