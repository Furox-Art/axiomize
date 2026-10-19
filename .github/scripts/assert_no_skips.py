#!/usr/bin/env python3
"""Fail a real test suite when its JUnit report records skipped/xfail cases.

This gate examines every testcase, not the textual pytest footer. It must
refuse empty or corrupt reports as well as any unexecuted test. It never
relaxes source coverage or edits existing results.
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def verify_report(path: Path) -> tuple[int, str]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return 1, f"FAIL: unreadable or malformed pytest JUnit XML: {exc}"
    if root.tag not in {"testsuite", "testsuites"}:
        return 1, f"FAIL: expected a pytest JUnit testsuite, got {root.tag!r}"
    cases = root.findall(".//testcase")
    if not cases:
        return 1, "FAIL: no executed testcases in report; cannot prove zero skips"
    missing = []
    for test in cases:
        if test.find("skipped") is not None:
            missing.append("{}::{}".format(test.get("classname", ""), test.get("name", "")))
    if missing:
        return 1, f"FAIL: {len(missing)} testcases skipped/xfail out of {len(cases)}:\\n" + "\\n".join(missing)
    return 0, f"PASS: {len(cases)} executed testcases, zero skipped or xfail"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit_xml", type=Path)
    args = parser.parse_args(argv)
    status, message = verify_report(args.junit_xml)
    print(message, file=sys.stderr if status else sys.stdout)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
