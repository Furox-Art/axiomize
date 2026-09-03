"""Executable falsification criteria (PHASE 5).

A falsifier is not prose: it names an observable, a threshold and a
direction, and evaluates to PASS/FAIL against real observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from axiomize.validation.status import ValidationStatus


@dataclass
class Falsifier:
    name: str
    observable: str
    threshold: float
    direction: str = "above"
    model_id: str = ""

    def evaluate(self, value: float) -> dict[str, Any]:
        triggered = value > self.threshold if self.direction == "above" else value < self.threshold
        return {
            "falsifier": self.name,
            "observable": self.observable,
            "observed": value,
            "threshold": self.threshold,
            "triggered": triggered,
            "status": ValidationStatus.FAIL if triggered else ValidationStatus.PASS,
        }


def evaluate_falsifiers(falsifiers: list[Falsifier],
                        observations: dict[str, float]) -> dict[str, Any]:
    results = [f.evaluate(observations[f.observable])
               for f in falsifiers if f.observable in observations]
    failed = [r for r in results if r["status"] == ValidationStatus.FAIL]
    missing = [f.observable for f in falsifiers if f.observable not in observations]
    return {"results": results,
            "model_status": ValidationStatus.FAIL if failed else ValidationStatus.PASS,
            "untested": missing}
