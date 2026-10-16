"""Solver limits must never silently truncate fractional or invalid values."""

from __future__ import annotations

import math

import pytest

from axiomize.model_ir import SolverSpec


@pytest.mark.parametrize("value", [1, 12.0, "8", 2])
def test_positive_integral_step_limits(value: object) -> None:
    assert SolverSpec.from_dict({"max_steps": value}).max_steps == int(value)


@pytest.mark.parametrize(
    "value", [True, False, 0, -1, 2.5, "3.2", math.nan, math.inf, "unbounded"]
)
def test_invalid_step_limits_fail_closed(value: object) -> None:
    with pytest.raises(ValueError, match="solver.max_steps"):
        SolverSpec.from_dict({"max_steps": value})


def test_omitted_step_limit_remains_unbounded() -> None:
    assert SolverSpec.from_dict(None).max_steps is None
