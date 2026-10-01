"""Test-suite import bootstrap for Axiomize.

Every test module in ``tests/`` imports the package under test. Historically each
file did its own ``sys.path.insert(0, REPO / "src")``, which made the suite
collection-order dependent: running a single test file in a fresh interpreter
raised ``ModuleNotFoundError: No module named 'axiomize'`` for the 20 modules
that did not carry the hack. That is a false failure, not a product defect.

Two import roots are registered here, once, for the whole session:

``src``
    The package source tree. When the CI jobs install the distribution first
    (``pip install -e ".[dev]"``) this entry is redundant but harmless, and it
    keeps ``pytest tests/`` working for a contributor who has not installed
    anything yet.

``skills/axiomize/tools``
    The standalone skill tools. These are force-included into the wheel as
    ``axiomize/tools/*``, which means an *editable* install does not expose
    them. ``tests/test_tools.py`` and ``tests/test_benchmark_suite.py`` import
    them under their flat module names (``validate``, ``csv_check``, ``fit``,
    ``report_to_latex``), so the directory has to be importable directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Inserted in reverse priority order; the last insert wins the index-0 slot.
for _source_root in (REPO_ROOT / "src", REPO_ROOT / "skills" / "axiomize" / "tools"):
    _entry = str(_source_root)
    if _source_root.is_dir() and _entry not in sys.path:
        sys.path.insert(0, _entry)
