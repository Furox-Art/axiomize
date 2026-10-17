"""Physical metadata must remain finite and SI dimensions immutable."""

from __future__ import annotations

import math

import pytest

from axiomize.validation.dimensions import (
    Dimension,
    DimensionalMismatch,
    Quantity,
    check_add,
    dimension_of,
)
from axiomize.validation.status import ValidationStatus


@pytest.mark.parametrize(
    "dimensions",
    [
        {"alien": 1},
        {"L": True},
        {"M": 1.5},
        {"T": "1"},
    ],
)
def test_invalid_si_base_exponents_are_rejected(dimensions: dict) -> None:
    with pytest.raises(DimensionalMismatch, match="SI base|exponents must be integers"):
        Dimension(dimensions)


def test_dimension_vector_is_immutable_and_defensively_copied() -> None:
    source = {"L": 1}
    length = Dimension(source)
    source["T"] = 3
    assert dict(length.exponents) == {"L": 1}
    with pytest.raises(TypeError):
        length.exponents["M"] = 2  # type: ignore[index]


def test_dimensional_arithmetic_preserves_exact_si_exponents() -> None:
    length = dimension_of("metre")
    duration = dimension_of("second")
    assert (length / duration).exponents == {"L": 1, "T": -1}
    assert (length * (duration / duration)) == length
    assert Dimension({"L": 0}).is_dimensionless
    assert check_add(Quantity("a", "a", "metre"), Quantity("b", "b", "cm")).status is ValidationStatus.PASS


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "10", 10**1000])
def test_physical_quantity_rejects_nonfinite_or_non_numeric_value(value: object) -> None:
    with pytest.raises(ValueError, match="quantity value must be"):
        Quantity("length", "L", "metre", value=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("uncertainty", [-1.0, math.inf, math.nan, True, 10**1000])
def test_physical_uncertainty_must_be_finite_and_nonnegative(uncertainty: object) -> None:
    with pytest.raises(ValueError, match="uncertainty"):
        Quantity("length", "L", "metre", uncertainty=uncertainty)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bounds",
    [
        (2.0, 1.0),
        (-math.inf, 1.0),
        (0.0, math.nan),
        (False, 1.0),
        (0.0, 10**1000),
        ("0", "1"),
        [0.0, 1.0],
        (0.0,),
    ],
)
def test_physical_valid_range_must_be_finite_ordered_pair(bounds: object) -> None:
    with pytest.raises(ValueError, match="valid_range"):
        Quantity("length", "L", "metre", valid_range=bounds)  # type: ignore[arg-type]


def test_valid_scientific_quantity_preserves_range_and_uncertainty() -> None:
    quantity = Quantity(
        "length", "L", "metre", value=1.5, valid_range=(1.0, 2.0),
        uncertainty=0.01, source="direct measurement",
    )
    assert quantity.range_check().status is ValidationStatus.PASS
    assert quantity.uncertainty == 0.01
