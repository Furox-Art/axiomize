"""Installed CLI for the bounded scientific benchmark/stress matrix."""
from __future__ import annotations

import json


def main() -> int:
    from axiomize.scientific_stress_matrix import run_matrix
    result = run_matrix()
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
