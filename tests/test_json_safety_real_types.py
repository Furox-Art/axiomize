"""JSON wire conversions preserve scientific status and reject nonstandard numeric literals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import pytest

from axiomize.json_safety import json_safe


class Status(Enum):
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"


@dataclass
class Evidence:
    status: Status
    values: list[float]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (True, True),
        (False, False),
        (0, 0),
        ("reported", "reported"),
        (float("nan"), "NaN"),
        (float("inf"), "Infinity"),
        (-float("inf"), "-Infinity"),
        (1.25, 1.25),
        (Status.FAIL, "FAIL"),
        (Path("/tmp/file.txt"), "/tmp/file.txt"),
    ],
)
def test_json_safe_serializes_standard_numbers_and_explicit_nonfinite_sentinels(value, expected):
    assert json_safe(value) == expected
    json.dumps(json_safe(value), allow_nan=False)


def test_nested_multidimensional_numpy_remains_structured_not_stringified():
    array = np.asarray([[1.0, 2.0], [3.0, float("nan")]], dtype=float)
    result = json_safe({"measurements": array, "counter": np.int64(5)})
    assert result == {"measurements": [[1.0, 2.0], [3.0, "NaN"]], "counter": 5}
    json.dumps(result, allow_nan=False)


def test_dataclass_evidence_remains_machine_readable_and_preserves_failure():
    result = json_safe(Evidence(status=Status.UNVERIFIED, values=[2.0, float("inf")]))
    assert result == {"status": "UNVERIFIED", "values": [2.0, "Infinity"]}
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("collection", [[], (), set(), frozenset()])
def test_iterable_collections_can_be_encoded_as_valid_json(collection):
    assert json_safe(collection) == []


def test_mapping_keys_are_explicitly_converted_to_json_strings():
    assert json_safe({7: Status.FAIL, True: None}) == {"7": "FAIL", "True": None}


def test_non_serializable_unknown_objects_report_an_explicit_string():
    class NoJson:
        def __str__(self):
            return "external-proxy"

    assert json_safe(NoJson()) == "external-proxy"


def test_numpy_boolean_and_float_scalars_are_never_left_as_nonstandard_types():
    converted = json_safe({"x": np.float64(float("nan")), "ok": np.bool_(False)})
    assert converted == {"x": "NaN", "ok": False}
    json.dumps(converted, allow_nan=False)


@pytest.mark.parametrize("numeric", [np.float32(float("inf")), np.float64(float("-inf"))])
def test_numpy_nonfinite_values_emit_explicit_sentinels(numeric):
    assert json_safe(numeric) in {"Infinity", "-Infinity"}
