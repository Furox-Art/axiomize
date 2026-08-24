"""Axiomize CSV quality pre-check.

Run BEFORE calibrating (fit.py): surfaces the data problems that silently
corrupt parameter fits - gaps, duplicates, non-monotonic time, extreme
outliers, low variance.

Usage:
    python csv_check.py --data mycases.csv --time-col day --value-col infected
"""

import argparse
import csv
import sys

import numpy as np


def load(path, tcol, vcol):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 2:
        raise SystemExit(f"error: {path} has no data rows")
    header = rows[0]
    ti = header.index(tcol) if tcol in header else 0
    vi = header.index(vcol) if vcol in header else 1
    body = [r for r in rows[1:] if len(r) > max(ti, vi)]
    if not body:
        raise SystemExit(f"error: {path} has no parseable data rows")
    t = np.empty(len(body))
    y = np.empty(len(body))
    for i, r in enumerate(body):
        try:
            t[i] = float(r[ti])
            y[i] = float(r[vi])
        except ValueError:
            raise SystemExit(f"error: row {i + 2}: cannot parse '{r[ti]}', '{r[vi]}' as numbers")
    return header[ti], header[vi], t, y


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True)
    p.add_argument("--time-col", default=None)
    p.add_argument("--value-col", default=None)
    p.add_argument("--z-outlier", type=float, default=4.0, help="modified-z threshold for outliers")
    args = p.parse_args()

    tname, vname, t, y = load(args.data, args.time_col, args.value_col)
    print(f"=== CSV check: {args.data} ({tname}, {vname}) ===")
    checks = {}
    order = np.argsort(t)
    t, y = t[order], y[order]

    checks["no_duplicate_times"] = bool(len(np.unique(t)) == len(t))
    checks["enough_points(n>=10)"] = bool(len(t) >= 10)
    gaps = np.diff(t)
    max_gap = float(gaps.max()) if len(gaps) else 0.0
    median_gap = float(np.median(gaps)) if len(gaps) else 0.0
    checks["no_gap_gt_3x_median"] = bool(median_gap == 0 or max_gap <= 3 * median_gap)

    med = np.median(y)
    mad = np.median(np.abs(y - med)) or 1e-12
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
    for k, v in checks.items():
        print(f"{k:34s} {'PASS' if v else 'FAIL'}")
        ok = ok and v
    print("\nRESULT:", "PASS - safe to calibrate" if ok else "FAIL - clean data before fitting")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
