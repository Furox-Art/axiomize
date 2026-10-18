"""Observe every JSON serialization decision on actual scientific payloads."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import pytest

from axiomize.json_safety import json_safe


class Verdict(Enum):
    PROVED = "PASS"
    UNSUPPORTED = "TOOL_UNAVAILABLE"


@dataclass(frozen=True)
class ScientificRecord:
    verdict: Verdict
    p_value: float
    sample_count: int


@pytest.mark.parametrize("value, expected", [
    (None, None), ("raw", "raw"), (True, True), (False, False), (17, 17),
    (0.5, 0.5), (float("nan"), "NaN"),
    (float("inf"), "Infinity"), (-float("inf"), "-Infinity"),
    (Verdict.PROVED, "PASS"), (Path("/tmp/model.json"), "/tmp/model.json"),
    (np.float64(2.0), 2.0), (np.float32(float("nan")), "NaN"),
    (np.int32(3), 3), (np.array([1.0, float("inf")]), [1.0, "Infinity"]),
])
def test_scalar_and_array_safety_represents_nonfinite_evidence_as_explicit_text(value, expected):
    assert json_safe(value) == expected


def test_dataclass_enum_and_nested_mapping_preserves_scientific_status():
    record = {
        Verdict.PROVED: ScientificRecord(Verdict.UNSUPPORTED, float("nan"), 3),
        "trajectory": [float("-inf"), (1, 2), frozenset((4,)), {5}],
    }
    result = json_safe(record)
    assert result["Verdict.PROVED"]["verdict"] == "TOOL_UNAVAILABLE"
    assert result["Verdict.PROVED"]["p_value"] == "NaN"
    assert result["Verdict.PROVED"]["sample_count"] == 3
    assert result["trajectory"][:2] == ["-Infinity", [1, 2]]
    assert result["trajectory"][2:] == [[4], [5]]
    wire = json.dumps(result, allow_nan=False)
    assert "NaN" in wire


class ItemOnly:
    def item(self):
        return 12


class ListOnly:
    def tolist(self):
        return [2, float("inf")]


class FailedItem:
    def item(self):
        raise TypeError("array cannot be represented as scalar")

    def tolist(self):
        return [1, 2]


class FailedList:
    def tolist(self):
        raise ValueError("invalid array projection")

    def __str__(self):
        return "unrepresentable-array"


class BothSelf:
    def item(self):
        return self

    def tolist(self):
        return self

    def __str__(self):
        return "unconverted-sentinel"


@pytest.mark.parametrize("input_value, expected", [
    (ItemOnly(), 12),
    (ListOnly(), [2, "Infinity"]),
    (FailedItem(), [1, 2]),
    (FailedList(), "unrepresentable-array"),
    (BothSelf(), "unconverted-sentinel"),
    (object(), "<object>"),
])
def test_protocol_degradation_is_explicit_not_a_fabricated_success(input_value, expected):
    converted = json_safe(input_value)
    if isinstance(input_value, object) and type(input_value) is object:
        assert converted.startswith("<object object at")
    else:
        assert converted == expected


def test_type_object_not_confused_with_record_instance():
    assert json_safe(ScientificRecord) == str(ScientificRecord)


def test_nested_output_is_valid_rfc8259_json():
    source = {
        "metrics": (np.float64(float("inf")), np.float64(float("-inf"))),
        "record": ScientificRecord(Verdict.PROVED, float("nan"), 5),
    }
    encoded = json.dumps(json_safe(source), allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["metrics"] == ["Infinity", "-Infinity"]
    assert decoded["record"] == {"verdict": "PASS", "p_value": "NaN", "sample_count": 5}
