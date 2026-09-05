"""Run the package-native scientific stress matrix against the installed wheel."""
from __future__ import annotations

import json

from axiomize.scientific_stress_matrix import run_matrix


def main() -> int:
    result = run_matrix()
    print(json.dumps(result, indent=2, allow_nan=False))
    if result["status"] != "PASS":
        raise SystemExit("scientific benchmark/stress matrix failed")
    if result.get("family_coverage") != {"passed": 14, "total": 14}:
        raise SystemExit(f"incomplete Model IR family benchmark coverage: {result.get('family_coverage')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
