"""Data transformations and scientific-run differences remain fully auditable."""
from __future__ import annotations

import numpy as np
import pytest

from axiomize.data import quality
from axiomize.runs.compare import _changed_mapping, _load_manifest, compare_run_directories, compare_run_states
from axiomize.runs.state import RunState


@pytest.mark.parametrize("times, values, fragment", [
    ("garbled", [1, 2], "must be numeric"),
    ([0, 1], ["invalid", "row"], "must be numeric"),
    ([[0, 1]], [[1, 2]], "one-dimensional"),
    ([0, 1, 2], [1, 2], "same length"),
    ([0], [1], "observation count"),
    ([0, 1], [1, 2], None),
])
def test_real_numeric_input_validation(times, values, fragment):
    if fragment is None:
        assert quality.clean_numeric_xy(times, values).cleaned_t == [0, 1]
    else:
        with pytest.raises(ValueError, match=fragment):
            quality.clean_numeric_xy(times, values)


def test_nonfinite_values_are_audited_not_silently_dropped():
    actual = quality.clean_numeric_xy(
        [0, 1, 2, 3], [1, float("nan"), 3, 4]
    )
    assert actual.cleaned_t == [0, 2, 3]
    assert actual.cleaned_y == [1, 3, 4]
    assert actual.audit[0]["operation"] == "drop_nonfinite_rows"
    assert actual.audit[0]["rows"] == [1]
    assert actual.material_change is True
    assert actual.to_dict()["warnings"]


def test_nonfinite_refusal_preserves_unmodified_data():
    with pytest.raises(ValueError, match="non-finite observations"):
        quality.clean_numeric_xy(
            [0, 1, 2], [1, float("nan"), 3], drop_nonfinite=False
        )
    with pytest.raises(ValueError, match="fewer than two finite"):
        quality.clean_numeric_xy([0, 1, 2], [1, float("nan"), float("inf")])


@pytest.mark.parametrize("policy, expected", [
    ("mean", [2.0, 5.0]),
    ("first", [1.0, 5.0]),
])
def test_duplicate_policy_is_visible_and_reproducible(policy, expected):
    result = quality.clean_numeric_xy([0, 0, 1], [1, 3, 5], duplicate_policy=policy)
    assert result.cleaned_t == [0, 1]
    assert result.cleaned_y == expected
    assert result.audit[0]["operation"] == "merge_duplicate_times"
    assert result.audit[0]["policy"] == policy


def test_duplicate_error_is_not_hidden_by_sorting():
    with pytest.raises(ValueError, match="duplicate time"):
        quality.clean_numeric_xy([1, 0, 1], [1, 2, 3], duplicate_policy="error")


def test_no_sort_preserves_first_occurrence_order_of_duplicate_groups():
    result = quality.clean_numeric_xy(
        [2, 1, 2, 1, 3], [10, 20, 30, 40, 50],
        sort_time=False, duplicate_policy="mean",
    )
    assert result.cleaned_t == [2, 1, 3]
    assert result.cleaned_y == [20, 30, 50]
    assert result.audit[0]["order_policy"] == "first_occurrence"


def test_explicit_time_sort_records_exact_transformation():
    result = quality.clean_numeric_xy([2, 0, 1], [4, 0, 2])
    assert result.cleaned_t == [0, 1, 2]
    assert result.cleaned_y == [0, 2, 4]
    assert result.audit[0]["operation"] == "sort_by_time"


def test_statistical_outlier_is_retained_not_fabricated_away():
    result = quality.clean_numeric_xy(
        list(range(9)), [1, 2, 3, 4, 5, 6, 7, 8, 500]
    )
    assert result.cleaned_y[-1] == 500
    assert any("outliers retained" in warning for warning in result.warnings)


def test_robust_outlier_detection_refuses_short_or_constant_series():
    assert quality._robust_outlier_indices(np.asarray([1, 2, 100])) == []
    assert quality._robust_outlier_indices(np.asarray([3, 3, 3, 3, 3])) == []


def test_validation_rejects_unknown_duplicate_policy():
    with pytest.raises(ValueError, match="duplicate_policy"):
        quality.clean_numeric_xy([0, 1], [1, 2], duplicate_policy="arbitrary")


def test_run_comparison_is_exact_on_identical_state():
    before = RunState(parameters={"k": 0.5}, results={"x": [1.0, 0.5]})
    report = compare_run_states(before, before)
    assert report["same_input_hash"]
    assert report["same_results"]
    assert report["differences"] == {}
    assert report["likely_reasons"] == ["no recorded reproducibility difference detected"]


def test_parameter_and_environment_changes_are_separate_causes():
    a = RunState(parameters={"k": 0.5}, results={"x": 1.0})
    b = RunState(parameters={"k": 0.8}, results={"x": 0.6})
    report = compare_run_states(
        a, b, before_manifest={"tool_versions": {"scipy": "1.0"}},
        after_manifest={"tool_versions": {"scipy": "2.0"}},
    )
    assert not report["same_input_hash"]
    assert not report["same_results"]
    assert report["differences"]["parameters"]["k"] == {"before": 0.5, "after": 0.8}
    assert report["differences"]["tool_versions"]["scipy"] == {"before": "1.0", "after": "2.0"}
    assert "model parameters changed" in report["likely_reasons"]
    assert "software/tool versions changed" in report["likely_reasons"]


def test_same_recorded_inputs_with_different_results_is_flagged_as_unexplained():
    a = RunState(parameters={"k": 0.5}, results={"x": 1.0})
    b = RunState(parameters={"k": 0.5}, results={"x": 0.6})
    report = compare_run_states(a, b)
    assert report["same_input_hash"]
    assert not report["same_results"]
    assert "results" in report["differences"]
    assert any("randomness" in reason for reason in report["likely_reasons"])


def test_all_changed_inputs_are_explicit_and_not_collapsed_to_single_reason():
    a = RunState()
    b = RunState(
        solver_settings={"rtol": 1e-7},
        workflow_policy={"allow_heavy": False},
        datasets=["real.csv"],
        data_transformations=[{"operation": "sort"}],
        assumptions=["conditional independence"],
        selected_model="model-B",
        equations=["x=2"],
    )
    result = compare_run_states(a, b)
    fields = {
        "solver_settings", "workflow_policy", "datasets", "data_transformations",
        "assumptions", "selected_model", "equations",
    }
    assert fields.issubset(result["differences"])
    assert len(result["likely_reasons"]) >= len(fields)


def test_missing_and_nonobject_manifests_do_not_invent_versions(tmp_path):
    assert _load_manifest(tmp_path) == {}
    (tmp_path / "manifest.json").write_text("[1,2]")
    assert _load_manifest(tmp_path) == {}


def test_real_saved_run_directories_detect_different_inputs(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    RunState(parameters={"k": 0.5}, results={"x": 1.0}).save(first)
    RunState(parameters={"k": 0.8}, results={"x": 0.8}).save(second)
    result = compare_run_directories(first, second)
    assert result["differences"]["parameters"]["k"] == {"before": 0.5, "after": 0.8}
    assert result["same_input_hash"] is False


def test_mapping_comparison_does_not_drop_additions_or_removals():
    assert _changed_mapping({"a": 1, "b": 2}, {"b": 2, "c": 3}) == {
        "a": {"before": 1, "after": None},
        "c": {"before": None, "after": 3},
    }


class LazyNumericIterable:
    def __iter__(self):
        yield 0.0
        yield 1.0


class DeclaredHugeArray:
    def __len__(self):
        return quality.MAX_ARRAY_ITEMS + 1


def test_lenless_measurement_iterable_is_accepted_by_precheck():
    quality._precheck_length(LazyNumericIterable(), name="time")


def test_oversized_declared_observation_is_rejected_before_allocation():
    with pytest.raises(ValueError, match="exceeds hard observation limit"):
        quality._precheck_length(DeclaredHugeArray(), name="time")


def test_zero_mean_signal_does_not_create_unjustified_relative_shift():
    result = quality.clean_numeric_xy([0.0, 1.0], [-1.0, 1.0])
    assert result.material_change is False
    assert result.audit[-1]["relative_mean_shift"] == 0.0
