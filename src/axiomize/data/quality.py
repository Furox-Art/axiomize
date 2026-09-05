"""Conservative numeric-data cleaning with a complete audit trail.

Axiomize never silently drops or rewrites observations. This helper performs
only structural cleaning that can be explained exactly: non-finite rows,
ordering, and duplicate time coordinates. Statistical outliers are flagged but
not deleted automatically because they may be real scientific signal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from axiomize.limits import MAX_ARRAY_ITEMS


@dataclass
class DataCleaningResult:
    original_t: list[float]
    original_y: list[float]
    cleaned_t: list[float]
    cleaned_y: list[float]
    audit: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    material_change: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _robust_outlier_indices(values: np.ndarray, threshold: float = 6.0) -> list[int]:
    if len(values) < 5:
        return []
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad == 0.0:
        return []
    robust_z = 0.67448975 * (values - median) / mad
    return [int(i) for i in np.flatnonzero(np.abs(robust_z) > threshold)]


def _precheck_length(values: Any, *, name: str) -> None:
    try:
        size = len(values)
    except TypeError:
        return
    if size > MAX_ARRAY_ITEMS:
        raise ValueError(f"{name} exceeds hard observation limit {MAX_ARRAY_ITEMS}")


def clean_numeric_xy(t: Any, y: Any, *, drop_nonfinite: bool = True,
                     sort_time: bool = True, duplicate_policy: str = "mean") -> DataCleaningResult:
    """Clean paired numeric observations without hiding transformations.

    ``duplicate_policy`` may be ``mean``, ``first`` or ``error``. Outliers are
    reported in ``warnings`` and are deliberately retained. When ``sort_time``
    is false, duplicate merging preserves the first-occurrence order exactly.
    """
    _precheck_length(t, name="t")
    _precheck_length(y, name="y")
    try:
        t_arr = np.asarray(t, dtype=float)
        y_arr = np.asarray(y, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("t and y must be numeric") from exc
    if t_arr.ndim != 1 or y_arr.ndim != 1:
        raise ValueError("t and y must be one-dimensional")
    if len(t_arr) != len(y_arr):
        raise ValueError("t and y must have the same length")
    if len(t_arr) < 2 or len(t_arr) > MAX_ARRAY_ITEMS:
        raise ValueError(f"observation count must be between 2 and {MAX_ARRAY_ITEMS}")
    if duplicate_policy not in {"mean", "first", "error"}:
        raise ValueError("duplicate_policy must be mean, first, or error")

    original_t = [float(v) for v in t_arr]
    original_y = [float(v) for v in y_arr]
    audit: list[dict[str, Any]] = []
    warnings: list[str] = []

    finite_mask = np.isfinite(t_arr) & np.isfinite(y_arr)
    bad_indices = [int(i) for i in np.flatnonzero(~finite_mask)]
    if bad_indices:
        if not drop_nonfinite:
            raise ValueError(f"non-finite observations at rows {bad_indices[:100]}")
        audit.append({
            "operation": "drop_nonfinite_rows",
            "rows": bad_indices[:1000],
            "count": len(bad_indices),
            "rows_truncated": len(bad_indices) > 1000,
            "reason": "time/value must be finite for numerical fitting",
        })
        t_arr = t_arr[finite_mask]
        y_arr = y_arr[finite_mask]

    if len(t_arr) < 2:
        raise ValueError("fewer than two finite observations remain after cleaning")

    if sort_time and np.any(np.diff(t_arr) < 0):
        order = np.argsort(t_arr, kind="stable")
        t_arr = t_arr[order]
        y_arr = y_arr[order]
        audit.append({"operation": "sort_by_time", "reason": "time coordinate was not monotonic"})

    unique, first_indices, counts = np.unique(
        t_arr,
        return_index=True,
        return_counts=True,
    )
    duplicate_mask = counts > 1
    duplicate_times = unique[duplicate_mask]
    if len(duplicate_times):
        if duplicate_policy == "error":
            raise ValueError(f"duplicate time coordinates: {duplicate_times[:100].tolist()}")

        # np.unique sorts its output. That is desired after an explicit time
        # sort, but it would silently reorder data when sort_time=False. In that
        # mode restore first-occurrence order before merging duplicate groups.
        if sort_time:
            merge_times = unique
        else:
            merge_times = unique[np.argsort(first_indices, kind="stable")]

        new_t: list[float] = []
        new_y: list[float] = []
        duplicate_records: list[dict[str, Any]] = []
        for time_value in merge_times:
            idx = np.flatnonzero(t_arr == time_value)
            vals = y_arr[idx]
            value = float(np.mean(vals)) if duplicate_policy == "mean" else float(vals[0])
            new_t.append(float(time_value))
            new_y.append(value)
            if len(idx) > 1 and len(duplicate_records) < 1000:
                duplicate_records.append({
                    "time": float(time_value),
                    "rows_merged": int(len(idx)),
                    "original_values": [float(v) for v in vals[:100]],
                    "original_values_truncated": len(vals) > 100,
                    "cleaned_value": value,
                })
        t_arr = np.asarray(new_t, dtype=float)
        y_arr = np.asarray(new_y, dtype=float)
        audit.append({
            "operation": "merge_duplicate_times",
            "policy": duplicate_policy,
            "duplicates": duplicate_records,
            "duplicate_groups": int(len(duplicate_times)),
            "duplicates_truncated": len(duplicate_times) > 1000,
            "order_policy": "sorted_time" if sort_time else "first_occurrence",
        })

    outliers = _robust_outlier_indices(y_arr)
    if outliers:
        shown = ", ".join(str(i) for i in outliers[:100])
        suffix = " ..." if len(outliers) > 100 else ""
        warnings.append(f"possible robust-MAD outliers retained at cleaned rows {shown}{suffix}")

    changed_rows = len(original_t) - len(t_arr)
    changed_fraction = abs(changed_rows) / max(len(original_t), 1)
    finite_original_y = np.asarray([v for v in original_y if np.isfinite(v)], dtype=float)
    original_mean = float(np.mean(finite_original_y)) if len(finite_original_y) else float("nan")
    cleaned_mean = float(np.mean(y_arr))
    mean_shift = 0.0
    if np.isfinite(original_mean) and abs(original_mean) > 1e-12:
        mean_shift = abs(cleaned_mean - original_mean) / abs(original_mean)
    material_change = bool(changed_fraction > 0.05 or mean_shift > 0.05)
    if material_change:
        warnings.append("cleaning materially changed the dataset; compare model results on original and cleaned data")

    audit.append({
        "operation": "cleaning_summary",
        "n_original": len(original_t),
        "n_cleaned": len(t_arr),
        "row_count_change_fraction": changed_fraction,
        "relative_mean_shift": mean_shift,
        "material_change": material_change,
    })
    return DataCleaningResult(
        original_t=original_t,
        original_y=original_y,
        cleaned_t=[float(v) for v in t_arr],
        cleaned_y=[float(v) for v in y_arr],
        audit=audit,
        warnings=warnings,
        material_change=material_change,
    )
