"""Backward-compatible metadata normalization for portable exports.

The notebook exporter originally exposed ``metadata.axiomize.schema_version``.
A later internal rename to ``model_ir_schema_version`` is more descriptive but
must not break the installed export contract. Keep both keys until a deliberate
major-version migration can remove the alias.
"""

from __future__ import annotations

from typing import Any


def install_notebook_schema_alias() -> None:
    from axiomize import standards_export

    current = standards_export.export_notebook
    if getattr(current, "__axiomize_schema_alias__", False):
        return

    def export_notebook(model: Any) -> dict[str, Any]:
        out = current(model)
        notebook = out.get("notebook")
        if isinstance(notebook, dict):
            metadata = notebook.setdefault("metadata", {})
            if isinstance(metadata, dict):
                axiomize_meta = metadata.setdefault("axiomize", {})
                if isinstance(axiomize_meta, dict):
                    version = axiomize_meta.get("model_ir_schema_version", getattr(model, "schema_version", None))
                    if version is not None:
                        axiomize_meta.setdefault("schema_version", version)
            # ``content`` must describe exactly the same notebook object.
            import json

            out["content"] = json.dumps(notebook, indent=2)
        return out

    export_notebook.__axiomize_schema_alias__ = True  # type: ignore[attr-defined]
    standards_export.export_notebook = export_notebook
