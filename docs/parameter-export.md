# Parameter table JSON export

Axiomize reports use a canonical eight-column active parameter table. You can export that table as machine-readable JSON for notebooks, validation pipelines, dashboards, or downstream agents.

```bash
axiomize export-parameters report.md --json parameters.json
```

Omit `--json` to print the JSON payload to stdout.

The exported schema is versioned:

```json
{
  "schema": "axiomize.parameter-table.v1",
  "count": 2,
  "parameters": [
    {
      "symbol": "β",
      "name": "transmission rate",
      "unit": "1/day",
      "kind": "exo",
      "range": "0.1-0.5",
      "source": "lit.",
      "sensitivity": "high",
      "models": "det, stoch"
    }
  ]
}
```

The parser only accepts the canonical active-parameter header (`Symbol`, `Name`, `Unit`, `Exo/Endo`, ...). This prevents unrelated Markdown tables in the same report from being exported accidentally.
