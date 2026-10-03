# Portable scientific export

Axiomize exports its versioned Model IR without silently guessing scientific exchange schemas.

`axiomize model --action export --input-json request.json` dispatches on the `"format"`
field of the request. The measured behaviour of each format, against the installed wheel:

| Format | Status | Notes |
|---|---|---|
| `json` | `PASS` | Canonical Model IR, sorted keys |
| `python` | `PASS` | Rerunnable script that re-imports the IR |
| `yaml` / `yml` | `PASS` | Needs PyYAML; otherwise `TOOL_UNAVAILABLE` |
| `ipynb` / `notebook` / `jupyter` | `PASS` | nbformat 4 notebook, returns as `format: notebook` |
| `sbml-l3v2` | `PASS` | SBML Level 3 Version 2 Core |
| `modelica` / `modelica-3.6` / `mo` | `PASS` | Modelica 3.6 text, returns as `format: modelica-3.6` |
| `portable-bundle` / `bundle` | `PASS` | `axiomize.portable-bundle.v1`, returns as `format: portable-bundle-v1` with a SHA-256 over the canonical IR |
| `graphml` | conditional | Requires `family: network` IR with `metadata.network` |
| `causal-dot` / `dot` / `dag-dot` | conditional | Requires `family: causal` IR with identification metadata |
| `cellml-2.0` | conditional | Passes for supported units; returns `ADAPTER_REQUIRED` naming the ones it will not reinterpret |
| `sbml`, `cellml` | `ADAPTER_REQUIRED` | Unversioned aliases; callers must choose an explicit schema version |

The unversioned `sbml` and `cellml` aliases remain conservative on purpose. This avoids
silently emitting XML that only looks like a scientific standard.

SBML export preserves free-form Model IR unit declarations in an Axiomize annotation and
reports whether full libSBML validation was available. CellML export refuses unknown units
rather than reinterpreting them. A dimensionless decay model, which is what the release
smoke test uses, returns `PASS` with `standard: "CellML 2.0"`. The SIR model from the
quickstart returns `ADAPTER_REQUIRED` with `unsupported_units: ["person", "persons"]` and
the portable IR alongside, so nothing is lost: CellML has no quantity kind for a count of
people, and Axiomize declines to invent one.

Example request:

```json
{
  "model_ir": {"...": "..."},
  "format": "sbml-l3v2"
}
```

## LaTeX is not an export format

`latex`, `tex` and `pdf` are **not** in this dispatch chain. They raise
`ValueError: format must be json, python, yaml, sbml, or cellml`. LaTeX conversion takes a
written report, not a model:

```bash
axiomize-to-latex --input report.md --output report.tex
```

The same export service is available through CLI, REST, and MCP wherever the general
Model IR export operation is exposed.
