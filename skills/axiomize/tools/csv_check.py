"""Axiomize CSV quality pre-check.

Run BEFORE calibrating (fit.py): surfaces the data problems that silently
corrupt parameter fits - gaps, duplicates, non-monotonic time, extreme
outliers, low variance.
"""

import argparse
import csv
import math
import os
import sys

import numpy as np

MAX_CSV_BYTES = 64 * 1024 * 1024
MAX_DATA_ROWS = 200_000


def load(path, tcol, vcol):
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise SystemExit(f"error: cannot stat {path}: {exc}") from exc
    if size > MAX_CSV_BYTES:
        raise SystemExit(f"error: {path} exceeds hard CSV size limit {MAX_CSV_BYTES} bytes")

    try:
        fh = open(path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise SystemExit(f"error: cannot open {path}: {exc}") from exc
    with fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise SystemExit(f"error: {path} is empty") from exc
        if tcol is None:
            raise SystemExit(
                f"error: --time-col is required. Header is {header}. Pass an explicit column name."
            )
        if tcol not in header:
            raise SystemExit(f"error: time column '{tcol}' not found in header: {header}")
        ti = header.index(tcol)
        if vcol is None:
            raise SystemExit(
                f"error: --value-col is required. Header is {header}. Pass an explicit column name."
            )
        if vcol not in header:
            raise SystemExit(f"error: value column '{vcol}' not found in header: {header}")
        vi = header.index(vcol)

        t_values = []
        y_values = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) <= max(ti, vi):
                continue
            if len(t_values) >= MAX_DATA_ROWS:
                raise SystemExit(f"error: {path} exceeds hard row limit {MAX_DATA_ROWS}")
            try:
                t_value = float(row[ti])
                y_value = float(row[vi])
            except ValueError as exc:
                raise SystemExit(
                    f"error: row {row_number}: cannot parse '{row[ti]}', '{row[vi]}' as numbers"
                ) from exc
            if not math.isfinite(t_value) or not math.isfinite(y_value):
                raise SystemExit(f"error: row {row_number}: time/value must be finite")
            t_values.append(t_value)
            y_values.append(y_value)

    if not t_values:
        raise SystemExit(f"error: {path} has no parseable data rows")
    return header[ti], header[vi], np.asarray(t_values, dtype=float), np.asarray(y_values, dtype=float)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True)
    p.add_argument("--time-col", required=True, help="name of the time column (required)")
    p.add_argument("--value-col", required=True, help="name of the value column (required)")
    p.add_argument("--z-outlier", type=float, default=4.0, help="positive modified-z threshold for outliers")
    args = p.parse_args()
    if not math.isfinite(args.z_outlier) or args.z_outlier <= 0:
        p.error("--z-outlier must be finite and > 0")

    tname, vname, t, y = load(args.data, args.time_col, args.value_col)
    print(f"=== CSV check: {args.data} ({tname}, {vname}) ===")
    checks = {}
    checks["time_monotonic_increasing"] = bool(len(t) < 2 or np.all(t[:-1] <= t[1:]))
    if not checks["time_monotonic_increasing"]:
        bad = int(np.sum(np.diff(t) < 0))
        print(f"FAIL: time column not sorted ({bad} backward step(s)); fix the source data")

    checks["no_duplicate_times"] = bool(len(np.unique(t)) == len(t))
    checks["enough_points(n>=10)"] = bool(len(t) >= 10)
    gaps = np.diff(t)
    max_gap = float(gaps.max()) if len(gaps) else 0.0
    positive_gaps = gaps[gaps > 0]
    median_gap = float(np.median(positive_gaps)) if len(positive_gaps) else 0.0
    checks["no_gap_gt_3x_median"] = bool(median_gap == 0 or max_gap <= 3 * median_gap)

    med = np.median(y)
    mad = np.median(np.abs(y - med))
    if mad == 0.0:
        mz = np.zeros_like(y)
    else:
        mz = 0.6745 * (y - med) / mad
    outliers = int(np.sum(np.abs(mz) > args.z_outlier))
    checks[f"no_outliers(mod-z>{args.z_outlier})"] = outliers == 0
    if outliers:
        print(f"WARNING: {outliers} extreme value(s) - inspect or clean before calibrating")
    checks["value_variance_not_degenerate"] = bool(np.std(y) > 1e-9)
    checks["nonnegative_values"] = bool(np.all(y >= 0))

    print(f"points: {len(t)}, span {t[0]:.4g}..{t[-1]:.4g}, max gap {max_gap:.4g}")
    print(f"outliers flagged: {outliers} (indices {[int(i) for i in np.where(np.abs(mz)>args.z_outlier)[0]]})")
    ok = True
    for key, value in checks.items():
        print(f"{key:34s} {'PASS' if value else 'FAIL'}")
        ok = ok and value
    print("\nRESULT:", "PASS - safe to calibrate" if ok else "FAIL - clean data before fitting")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
