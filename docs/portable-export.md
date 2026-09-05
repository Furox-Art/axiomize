# Portable scientific export

Axiomize exports its versioned Model IR without silently guessing scientific exchange schemas.

Supported portable formats:

- `json` — canonical Model IR JSON.
- `python` — rerunnable Python script.
- `yaml` — YAML when PyYAML is installed.
- `ipynb` / `notebook` — nbformat 4 rerunnable notebook JSON.
- `sbml-l3v2` — conservative ODE/algebraic export to SBML Level 3 Version 2 Core XML.
- `cellml-2.0` — conservative ODE/algebraic export to CellML 2.0 XML for supported units.

The unversioned `sbml` and `cellml` aliases remain conservative and return `ADAPTER_REQUIRED`; callers must choose an explicit schema version. This avoids silently emitting XML that only looks like a scientific standard.

SBML export preserves free-form Model IR unit declarations in an Axiomize annotation and reports whether full libSBML validation was available. CellML export refuses unknown units rather than reinterpreting them.

Example request through the existing general-model interface:

```json
{
  "model_ir": {"...": "..."},
  "format": "sbml-l3v2"
}
```

The same export service is available through CLI, REST, and MCP wherever the general Model IR export operation is exposed.
