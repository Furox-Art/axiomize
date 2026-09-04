"""Dimensional analysis: mandatory unit-consistency layer (PHASE 1).

Every physical quantity carries an explicit dimension vector over the SI
base dimensions. Adding or subtracting quantities with different
dimensions raises :class:`DimensionalMismatch` instead of silently
producing a meaningless number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from axiomize.validation.status import ValidationStatus

_BASES = ("L", "M", "T", "I", "Theta", "N", "J")

# unit name -> dimension vector (scale factors are irrelevant for dimensional checks)
_UNIT_TABLE: dict[str, dict[str, int]] = {
    "metre": {"L": 1},
    "meter": {"L": 1},
    "m": {"L": 1},
    "centimeter": {"L": 1},
    "cm": {"L": 1},
    "millimeter": {"L": 1},
    "mm": {"L": 1},
    "kilometer": {"L": 1},
    "km": {"L": 1},
    "litre": {"L": 3},
    "liter": {"L": 3},
    "L": {"L": 3},
    "m^2": {"L": 2},
    "m2": {"L": 2},
    "m^3": {"L": 3},
    "m3": {"L": 3},
    "kilogram": {"M": 1},
    "kg": {"M": 1},
    "gram": {"M": 1},
    "g": {"M": 1},
    "second": {"T": 1},
    "s": {"T": 1},
    "minute": {"T": 1},
    "min": {"T": 1},
    "day": {"T": 1},
    "hour": {"T": 1},
    "h": {"T": 1},
    "year": {"T": 1},
    "yr": {"T": 1},
    "ampere": {"I": 1},
    "A": {"I": 1},
    "kelvin": {"Theta": 1},
    "K": {"Theta": 1},
    "mole": {"N": 1},
    "mol": {"N": 1},
    "candela": {"J": 1},
    "hertz": {"T": -1},
    "Hz": {"T": -1},
    "newton": {"L": 1, "M": 1, "T": -2},
    "N": {"L": 1, "M": 1, "T": -2},
    "joule": {"L": 2, "M": 1, "T": -2},
    "J": {"L": 2, "M": 1, "T": -2},
    "watt": {"L": 2, "M": 1, "T": -3},
    "W": {"L": 2, "M": 1, "T": -3},
    "pascal": {"L": -1, "M": 1, "T": -2},
    "Pa": {"L": -1, "M": 1, "T": -2},
    "volt": {"L": 2, "M": 1, "T": -3, "I": -1},
    "V": {"L": 2, "M": 1, "T": -3, "I": -1},
    "coulomb": {"T": 1, "I": 1},
    "C": {"T": 1, "I": 1},
    "persons": {"N": 1},
    "person": {"N": 1},
    "cells": {"N": 1},
    "molecules": {"N": 1},
    "1/day": {"T": -1},
    "1/second": {"T": -1},
    "1/s": {"T": -1},
    "1/min": {"T": -1},
    "1/hour": {"T": -1},
    "1/h": {"T": -1},
    "1/year": {"T": -1},
    "per_day": {"T": -1},
    "m/s": {"L": 1, "T": -1},
    "m/s^2": {"L": 1, "T": -2},
    "m/s2": {"L": 1, "T": -2},
    "kg/m^3": {"M": 1, "L": -3},
    "kg/m3": {"M": 1, "L": -3},
    "mol/m^3": {"N": 1, "L": -3},
    "mol/m3": {"N": 1, "L": -3},
    "mol/L": {"N": 1, "L": -3},
    "mmol/L": {"N": 1, "L": -3},
    "umol/L": {"N": 1, "L": -3},
    "M": {"N": 1, "L": -3},
    "dimensionless": {},
    "1": {},
}


class DimensionalMismatch(ValueError):
    """Raised when an operation combines dimensionally incompatible quantities."""


@dataclass(frozen=True)
class Dimension:
    """Sparse dimension vector over SI base dimensions."""

    exponents: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cleaned = {k: v for k, v in self.exponents.items() if v != 0}
        object.__setattr__(self, "exponents", cleaned)

    def __mul__(self, other: "Dimension") -> "Dimension":
        merged = dict(self.exponents)
        for key, value in other.exponents.items():
            merged[key] = merged.get(key, 0) + value
        return Dimension(merged)

    def __truediv__(self, other: "Dimension") -> "Dimension":
        merged = dict(self.exponents)
        for key, value in other.exponents.items():
            merged[key] = merged.get(key, 0) - value
        return Dimension(merged)

    @property
    def is_dimensionless(self) -> bool:
        return not self.exponents


def dimension_of(unit: str) -> Dimension:
    """Look up the dimension vector for a unit name.

    An empty unit string is rejected: dimensionless must be declared
    explicitly as ``"dimensionless"``, never forgotten.
    """
    if not unit:
        raise DimensionalMismatch(
            "empty unit: mark deliberately dimensionless quantities "
            "as 'dimensionless' instead of omitting the unit"
        )
    try:
        return Dimension(_UNIT_TABLE[unit])
    except KeyError:
        raise DimensionalMismatch(f"unknown unit: {unit!r}") from None


@dataclass
class Quantity:
    """A physical variable with unit, dimension and provenance metadata."""

    name: str
    symbol: str
    unit: str
    value: float | None = None
    valid_range: tuple[float, float] | None = None
    source: str = "UNKNOWN"
    uncertainty: float | None = None
    provenance: str = "UNKNOWN"
    dimension: Dimension = field(init=False)

    def __post_init__(self) -> None:
        self.dimension = dimension_of(self.unit)

    @dataclass
    class _Check:
        status: ValidationStatus
        detail: str

    def range_check(self) -> _Check:
        if self.valid_range is None or self.value is None:
            return self._Check(ValidationStatus.INCONCLUSIVE, "no range or value to check")
        low, high = self.valid_range
        if low <= self.value <= high:
            return self._Check(ValidationStatus.PASS, f"{self.value} within [{low}, {high}]")
        return self._Check(
            ValidationStatus.FAIL, f"{self.value} outside [{low}, {high}]"
        )


@dataclass
class DimCheck:
    status: ValidationStatus
    detail: str


def check_add(left: Quantity, right: Quantity) -> DimCheck:
    """Adding/subtracting requires identical dimensions (e.g. metre + second fails)."""
    if left.dimension != right.dimension:
        raise DimensionalMismatch(
            f"cannot add {left.symbol} [{left.unit}] to {right.symbol} [{right.unit}]: "
            f"{dict(left.dimension.exponents)} != {dict(right.dimension.exponents)}"
        )
    return DimCheck(ValidationStatus.PASS, f"{left.symbol} + {right.symbol}: dimensions match")


def check_mul(left: Quantity, right: Quantity) -> tuple[Dimension, DimCheck]:
    return left.dimension * right.dimension, DimCheck(
        ValidationStatus.PASS, f"{left.symbol} * {right.symbol}: dimensions combined"
    )
