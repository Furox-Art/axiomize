"""Parse Axiomize active-parameter Markdown tables into stable JSON data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_COLUMNS = (
    "symbol",
    "name",
    "unit",
    "kind",
    "range",
    "source",
    "sensitivity",
    "models",
)


def _split_row(line: str) -> list[str]:
    text = line.strip()
    if not text.startswith("|"):
        return []
    return [cell.strip() for cell in text.strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(cell and set(cell) <= {"-", ":", " "} for cell in cells)


def parse_parameter_table(markdown: str) -> dict[str, Any]:
    """Return the first active parameter table found in an Axiomize report.

    The parser intentionally keys off the canonical eight-column header so it
    does not accidentally export comparison or excluded-parameter tables.
    """

    lines = markdown.splitlines()
    header_index: int | None = None
    for idx, line in enumerate(lines):
        cells = _split_row(line)
        lowered = [c.lower() for c in cells]
        if len(cells) == 8 and lowered[:4] == ["symbol", "name", "unit", "exo/endo"]:
            header_index = idx
            break

    if header_index is None:
        raise ValueError("active parameter table not found")

    rows: list[dict[str, str]] = []
    started = False
    for line in lines[header_index + 1 :]:
        cells = _split_row(line)
        if not cells:
            if started:
                break
            continue
        if _is_separator(cells):
            continue
        if len(cells) != 8:
            if started:
                break
            continue
        started = True
        rows.append(dict(zip(_COLUMNS, cells, strict=True)))

    if not rows:
        raise ValueError("active parameter table is empty")

    return {
        "schema": "axiomize.parameter-table.v1",
        "parameters": rows,
        "count": len(rows),
    }


def export_parameter_table(source: str | Path, destination: str | Path) -> dict[str, Any]:
    """Parse a Markdown report and write its parameter table as JSON."""

    import json

    src = Path(source)
    dst = Path(destination)
    payload = parse_parameter_table(src.read_text(encoding="utf-8"))
    dst.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
