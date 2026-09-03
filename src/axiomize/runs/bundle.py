"""Portable run bundles (PHASE 9).

A run directory zips into a single file that another machine or agent
can import and inspect - no chat context required.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def export_run(run_dir: str | Path, bundle_path: str | Path) -> Path:
    bundle = Path(bundle_path)
    if bundle.suffix != ".zip":
        raise ValueError("bundle path must end in .zip")
    base = str(bundle.with_suffix(""))
    shutil.make_archive(base, "zip", root_dir=str(Path(run_dir).resolve()))
    return bundle


def import_run(bundle_path: str | Path, dest_dir: str | Path) -> Path:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(str(bundle_path), str(dest))
    return dest
