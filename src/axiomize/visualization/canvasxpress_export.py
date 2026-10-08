"""CanvasXpress chart-definition export.

CanvasXpress consumes a JSON document with a ``data`` object and a ``config``
object. This module builds those documents from the same numeric results the
rest of Axiomize already produces, so an interactive chart can never be built
from a number that is not also recorded in the run.

Two properties are deliberate:

*No silent invention.*  Every value that reaches a chart definition passes
through the same finite/shape checks the simulation path uses. A NaN, a
ragged matrix or a mismatched annotation length raises instead of producing a
chart that silently drops rows.

*Charts carry their own provenance.*  A chart definition is only as trustworthy
as the run behind it. :func:`attach_run_record` binds the input hash, the
recorded computation results, the validation outcome and the tool versions into
the definition, under a reserved ``axiomize`` key, so a chart can be audited
without the conversation that produced it.

The Matplotlib helpers in :mod:`axiomize.visualization.plots` are untouched.
This module is additive: it emits JSON, and does not depend on a browser, a
JavaScript runtime or any optional visualization backend being installed.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from axiomize.json_safety import json_safe

# Reserved key carrying Axiomize provenance inside a chart definition. CanvasXpress
# ignores unknown top-level keys, so this cannot collide with its own schema.
PROVENANCE_KEY = "axiomize"

# Name of the MCP tool this module is written to serve. Recording it here keeps
# the wiring contract explicit and testable rather than implied by a later commit.
MCP_TOOL_NAME = "model_visualize"

_MAX_VARS = 500
_MAX_SMPS = 200_000
_MAX_ANNOTATION_ENTRIES = 500


def _finite(value: Any, *, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite; CanvasXpress cannot render it and it "
                         "would otherwise be silently dropped from the chart")
    return number


def _matrix(rows: Sequence[Sequence[Any]], *, name: str,
            n_vars: int | None = None, n_smps: int | None = None) -> list[list[float]]:
    if not rows:
        raise ValueError(f"{name} must contain at least one row")
    if len(rows) > _MAX_VARS:
        raise ValueError(f"{name} declares more than the hard variable limit of {_MAX_VARS}")
    widths = {len(row) for row in rows}
    if len(widths) != 1:
        raise ValueError(f"{name} rows must all have the same length; found {sorted(widths)}")
    if not widths or next(iter(widths)) == 0:
        raise ValueError(f"{name} must contain at least one column")
    if next(iter(widths)) > _MAX_SMPS:
        raise ValueError(f"{name} has more than the hard sample limit of {_MAX_SMPS} columns")
    if n_vars is not None and len(rows) != n_vars:
        raise ValueError(f"{name} must have exactly {n_vars} rows; got {len(rows)}")
    if n_smps is not None and next(iter(widths)) != n_smps:
        raise ValueError(f"{name} must have exactly {n_smps} columns; got {next(iter(widths))}")
    return [[_finite(value, name=f"{name}[{i}][{j}]") for j, value in enumerate(row)]
            for i, row in enumerate(rows)]


def _annotations(axis: str, payload: Mapping[str, Sequence[Any]], *,
                 n_smps: int) -> dict[str, list[Any]]:
    """Validate a CanvasXpress ``x`` (sample) or ``z`` (variable) annotation block."""
    if len(payload) > _MAX_ANNOTATION_ENTRIES:
        raise ValueError(f"{axis} declares more than the hard annotation limit of {_MAX_ANNOTATION_ENTRIES}")
    out: dict[str, list[Any]] = {}
    for key, values in payload.items():
        if not str(key).strip():
            raise ValueError(f"{axis} annotation keys must be non-empty")
        items = list(values)
        if len(items) != n_smps:
            raise ValueError(
                f"{axis} annotation {str(key)!r} has {len(items)} entries but the data "
                f"declares {n_smps}; CanvasXpress would misalign every sample"
            )
        out[str(key)] = [json_safe(value) for value in items]
    return out


def chart_definition(
    vars: Sequence[str],
    smps: Sequence[str],
    data: Sequence[Sequence[float]],
    config: Mapping[str, Any] | None = None,
    *,
    sample_annotations: Mapping[str, Sequence[Any]] | None = None,
    variable_annotations: Mapping[str, Sequence[Any]] | None = None,
    title: str = "",
) -> dict[str, Any]:
    """Build a complete CanvasXpress definition from a dense matrix.

    ``data`` is indexed ``[variable][sample]``, matching the CanvasXpress ``y``
    block. Annotations map onto samples (``x``) and variables (``z``).
    """
    var_names = [str(name) for name in vars]
    smp_names = [str(name) for name in smps]
    if len(set(var_names)) != len(var_names):
        raise ValueError("variable names must be unique")
    if len(set(smp_names)) != len(smp_names):
        raise ValueError("sample names must be unique")
    matrix = _matrix(list(data), name="data", n_vars=len(var_names), n_smps=len(smp_names))

    payload: dict[str, Any] = {
        "y": {"vars": var_names, "smps": smp_names, "data": matrix},
    }
    if sample_annotations:
        payload["x"] = _annotations("x", sample_annotations, n_smps=len(smp_names))
    if variable_annotations:
        payload["z"] = _annotations("z", variable_annotations, n_smps=len(var_names))

    settings: dict[str, Any] = dict(config or {})
    if title:
        settings.setdefault("title", title)
    payload["config"] = settings
    return payload


def sensitivity_chart(scores: Mapping[str, float], *,
                      title: str = "Parameter sensitivity",
                      config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Ranked horizontal bar chart of sensitivity indices.

    The companion Matplotlib helper is ``plot_sensitivity``; this emits the same
    ranking as an interactive CanvasXpress bar chart instead of a PNG. Each
    parameter is one variable with one sample, so the ranking is preserved
    regardless of the chart's orientation.
    """
    if not scores:
        raise ValueError("scores must not be empty")
    ranked = sorted(((str(k), _finite(v, name=f"scores.{k}")) for k, v in scores.items()),
                    key=lambda item: abs(item[1]))
    names = [name for name, _ in ranked]
    values = [value for _, value in ranked]
    settings = {
        "graphType": "Bar",
        "graphOrientation": "horizontal",
        "xAxis": ["Sensitivity score"],
        "colorScheme": "Basic",
        "showDataValues": False,
        **(dict(config or {})),
    }
    return chart_definition(vars=names, smps=["sensitivity"],
                            data=[[value] for value in values],
                            config=settings, title=title,
                            variable_annotations={"parameter": names})


def trajectory_chart(time: Sequence[float], series: Mapping[str, Sequence[float]], *,
                     independent_label: str = "t",
                     title: str = "State trajectory",
                     config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Multi-series line chart of simulated state trajectories."""
    if not series:
        raise ValueError("series must not be empty")
    t = [_finite(value, name=f"time[{i}]") for i, value in enumerate(time)]
    n = len(t)
    if n < 2:
        raise ValueError("a trajectory needs at least two time points")
    names = list(series)
    data = [[_finite(v, name=f"series.{name}[{j}]") for j, v in enumerate(series[name])]
            for name in names]
    if any(len(row) != n for row in data):
        raise ValueError(f"every series must have exactly {n} samples, matching the time axis")
    smps = [f"{value:g}" for value in t]
    settings = {
        "graphType": "Line",
        "xAxis": [independent_label],
        "yAxis": ["state value"],
        "lineType": "line",
        "smpOverlays": None,
        **(dict(config or {})),
    }
    # ``smpOverlays`` is meaningless for a line chart; drop it if a caller passed it.
    settings.pop("smpOverlays", None)
    return chart_definition(vars=names, smps=smps, data=data,
                            config=settings, title=title,
                            sample_annotations={independent_label: t})


def response_surface_chart(x: Sequence[float], y: Sequence[float], z: Sequence[Sequence[float]],
                           *, xlabel: str = "x", ylabel: str = "y", zlabel: str = "response",
                           title: str = "Response surface",
                           config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Heatmap of a 2D response surface ``z[i][j]`` over ``y[i]`` by ``x[j]``.

    Row/column orientation matches the Matplotlib ``plot_surface_3d`` helper, so
    the same arrays drive both backends.
    """
    xs = [_finite(value, name=f"x[{i}]") for i, value in enumerate(x)]
    ys = [_finite(value, name=f"y[{i}]") for i, value in enumerate(y)]
    matrix = _matrix(list(z), name="z", n_vars=len(ys), n_smps=len(xs))
    settings = {
        "graphType": "Heatmap",
        "colorScheme": "RdYlBu",
        "showSampleNames": True,
        "smpLabelRotate": 45,
        "smpTitle": xlabel,
        "varTitle": ylabel,
        "legendTitle": zlabel,
        **(dict(config or {})),
    }
    return chart_definition(vars=[f"{value:g}" for value in ys],
                            smps=[f"{value:g}" for value in xs],
                            data=matrix, config=settings, title=title,
                            sample_annotations={xlabel: xs},
                            variable_annotations={ylabel: ys})


def response_surface_3d_chart(x: Sequence[float], y: Sequence[float], z: Sequence[Sequence[float]],
                              *, xlabel: str = "x", ylabel: str = "y", zlabel: str = "response",
                              title: str = "Response surface",
                              config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Scatter3D point cloud of the same surface data, for interactive rotation."""
    xs = [_finite(value, name=f"x[{i}]") for i, value in enumerate(x)]
    ys = [_finite(value, name=f"y[{i}]") for i, value in enumerate(y)]
    matrix = _matrix(list(z), name="z", n_vars=len(ys), n_smps=len(xs))
    col_x: list[float] = []
    col_y: list[float] = []
    col_z: list[float] = []
    for i, yi in enumerate(ys):
        for j, xj in enumerate(xs):
            col_x.append(xj)
            col_y.append(yi)
            col_z.append(matrix[i][j])
    settings = {
        "graphType": "Scatter3D",
        "xAxis": [xlabel],
        "yAxis": [ylabel],
        "zAxis": [zlabel],
        **(dict(config or {})),
    }
    return chart_definition(vars=[xlabel, ylabel, zlabel],
                            smps=[f"p{i}" for i in range(len(col_x))],
                            data=[col_x, col_y, col_z],
                            config=settings, title=title)


def dependency_chart(nodes: Iterable[str], edges: Sequence[Sequence[str]], *,
                     title: str = "Model dependency graph",
                     config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Directed variable/mechanism dependency graph.

    Edge lists are encoded as a weighted adjacency matrix, which is the shape
    CanvasXpress's ``Network`` graph consumes.
    """
    node_names = [str(node) for node in nodes]
    if not node_names:
        raise ValueError("nodes must not be empty")
    if len(set(node_names)) != len(node_names):
        raise ValueError("node names must be unique")
    index = {name: i for i, name in enumerate(node_names)}
    n = len(node_names)
    adjacency = [[0.0] * n for _ in range(n)]
    for edge in edges:
        if not isinstance(edge, Sequence) or len(edge) < 2:
            raise ValueError("each edge must be a [source, target] pair")
        source, target = str(edge[0]), str(edge[1])
        for endpoint in (source, target):
            if endpoint not in index:
                raise ValueError(f"edge references undeclared node: {endpoint!r}")
        adjacency[index[source]][index[target]] = 1.0
    settings = {
        "graphType": "Network",
        "networkLayoutAlgorithm": "force",
        "showSampleNames": True,
        **(dict(config or {})),
    }
    return chart_definition(vars=node_names, smps=node_names, data=adjacency,
                            config=settings, title=title)


def attach_run_record(definition: dict[str, Any], run: Any) -> dict[str, Any]:
    """Bind run provenance into a chart definition under the reserved key.

    ``run`` is any object exposing ``input_hash()``, ``manifest()`` and the
    ``RunState`` result fields (``results``, ``validation_results``,
    ``assumptions``, ``solver_settings``, ``equations``, ``selected_model``).
    Returns a new definition; the input is not mutated.
    """
    if not isinstance(definition, dict):
        raise ValueError("definition must be a CanvasXpress definition object")
    manifest = dict(run.manifest())
    provenance: dict[str, Any] = {
        "run_input_sha256": str(run.input_hash()),
        "axiomize_version": manifest.get("axiomize_version"),
        "tool_versions": manifest.get("tool_versions", {}),
        "solver_settings": manifest.get("solver_settings", {}),
        "recorded_results": json_safe(getattr(run, "results", {})),
        "validation_results": json_safe(getattr(run, "validation_results", {})),
        "model_assumptions": [str(item) for item in getattr(run, "assumptions", [])],
        "selected_model": str(getattr(run, "selected_model", "")),
        "equations": [str(item) for item in getattr(run, "equations", [])],
        "served_by_mcp_tool": MCP_TOOL_NAME,
    }
    payload = dict(definition)
    existing = payload.get(PROVENANCE_KEY)
    if isinstance(existing, dict):
        merged = dict(existing)
        merged.update(provenance)
        payload[PROVENANCE_KEY] = merged
    else:
        payload[PROVENANCE_KEY] = provenance
    return payload


def export_chart(definition: dict[str, Any], path: str | Path) -> Path:
    """Write a chart definition to disk as UTF-8 JSON with sorted keys."""
    import json

    if not isinstance(definition, dict):
        raise ValueError("definition must be a CanvasXpress definition object")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(json_safe(definition), indent=2, sort_keys=True)
    target.write_text(text + "\n", encoding="utf-8")
    return target
