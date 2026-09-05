"""Run the installed-wheel scientific stress matrix and fail on any regression."""
from __future__ import annotations

import json
import sys

from axiomize.model_ir import ModelFamily
from axiomize.scientific_stress import run_stress_matrix


def main()->int:
    result=run_stress_matrix()
    print(json.dumps(result,indent=2,sort_keys=True))
    expected={family.value for family in ModelFamily}
    covered=set(result.get("families_covered",[]))
    if covered!=expected:
        print(f"family coverage mismatch: missing={sorted(expected-covered)} extra={sorted(covered-expected)}",file=sys.stderr)
        return 1
    return 0 if result.get("status")=="PASS" else 1

if __name__=="__main__":raise SystemExit(main())
