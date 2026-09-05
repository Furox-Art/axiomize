"""Axiomize local playground (optional).

A tiny Gradio UI wrapping the bundled calibration tools. Uploaded CSVs are
bounded and validated before pandas/SciPy processing. Tool loading never prepends
an arbitrary working directory to ``sys.path``.
"""

import importlib.util
import io
import math
from pathlib import Path

import gradio as gr
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

MAX_CSV_BYTES = 64 * 1024 * 1024
MAX_DATA_ROWS = 200_000


def _load_fit_functions():
    try:
        from axiomize.tools.fit import fit_logistic, fit_sir
        return fit_logistic, fit_sir
    except ImportError:
        pass

    here = Path(__file__).resolve()
    candidates = [here.parent.parent / "skills" / "axiomize" / "tools" / "fit.py"]
    cwd = Path.cwd().resolve()
    # A Gradio launcher may copy app.py to a temp directory. Permit a cwd
    # fallback only when it is demonstrably an Axiomize source checkout, and
    # load the exact file rather than mutating sys.path.
    if (cwd / "pyproject.toml").is_file() and (cwd / "skills" / "axiomize" / "tools" / "fit.py").is_file():
        candidates.append(cwd / "skills" / "axiomize" / "tools" / "fit.py")

    for target in candidates:
        if not target.is_file():
            continue
        spec = importlib.util.spec_from_file_location("_axiomize_playground_fit", target)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.fit_logistic, module.fit_sir
    raise RuntimeError("cannot locate Axiomize calibration tools; install axiomize or run from its repository")


fit_logistic, fit_sir = _load_fit_functions()


def _uploaded_path(csv_file):
    raw = getattr(csv_file, "name", None)
    if raw is None and isinstance(csv_file, (str, Path)):
        raw = str(csv_file)
    if not raw:
        raise ValueError("uploaded CSV has no readable file path")
    path = Path(raw)
    if not path.is_file():
        raise ValueError("uploaded CSV is not a regular file")
    if path.stat().st_size > MAX_CSV_BYTES:
        raise ValueError(f"CSV exceeds hard size limit {MAX_CSV_BYTES} bytes")
    return path


def analyze(csv_file, model, N):
    if csv_file is None:
        return None, "Upload a CSV first (time column first, value second)."
    try:
        path = _uploaded_path(csv_file)
        df = pd.read_csv(path, nrows=MAX_DATA_ROWS + 1)
    except (OSError, ValueError, UnicodeError, pd.errors.ParserError) as exc:
        return None, f"CSV read failed: {exc}"
    if len(df) > MAX_DATA_ROWS:
        return None, f"CSV exceeds hard row limit {MAX_DATA_ROWS}."
    if df.shape[1] < 2:
        return None, "Need at least two columns: time, observed value."
    try:
        t = df.iloc[:, 0].to_numpy(float)
        y = df.iloc[:, 1].to_numpy(float)
    except (TypeError, ValueError) as exc:
        return None, f"First two columns must be numeric: {exc}"
    if len(t) < 3:
        return None, "Need at least three data rows for calibration."
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):
        return None, "Time and observed values must be finite."
    if np.any(np.diff(t) <= 0):
        return None, "Time must be strictly increasing with no duplicates; run csv_check and fix the source data."
    notes = [f"rows: {len(t)}"]

    if model == "sir":
        try:
            n_float = float(N)
        except (TypeError, ValueError, OverflowError):
            return None, "SIR needs a finite positive population N (required)."
        if not math.isfinite(n_float) or n_float <= 0 or not n_float.is_integer():
            return None, "SIR needs a finite positive whole-number population N."
        n_val = int(n_float)
        if np.any(y < 0) or n_val < float(y.max()):
            return None, f"SIR needs observations in [0, N]; max observed value is {y.max():g}, N={n_val}."
    else:
        n_val = None

    try:
        result = fit_sir(t, y, N=n_val) if model == "sir" else fit_logistic(t, y)
    except (ValueError, RuntimeError, TypeError, FloatingPointError, OverflowError) as exc:
        return None, f"Fit failed: {exc}. Run csv_check and verify model assumptions."

    for key, (value, error) in result["params"].items():
        notes.append(f"{key} = {value:.4g}" + (f" ± {error:.2g}" if error else ""))
    notes.append(f"RMSE = {result['rmse']:.4g}")
    d = result["diag"]
    notes.append(f"AIC {d['aic']:.1f} | BIC {d['bic']:.1f} | resid AC(1) {d['lag1_autocorr']:+.2f}")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(t, y, s=16, label="observed")
    ax.plot(t, result["fitted"], lw=2, label=f"fitted {model}")
    ax.legend()
    ax.set_xlabel(df.columns[0])
    ax.set_ylabel(df.columns[1])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf, "\n".join(notes)


with gr.Blocks(title="Axiomize playground") as demo:
    gr.Markdown("# Axiomize playground\nCalibrate a growth/epidemic model on your CSV (time column first).")
    with gr.Row():
        file_in = gr.File(label="CSV", file_types=[".csv"])
        model_in = gr.Radio(["sir", "logistic"], value="logistic", label="model")
    with gr.Row():
        N_in = gr.Number(label="Population N (required for SIR)", value=100000, precision=0)
    btn = gr.Button("Calibrate")
    plot_out = gr.Image(label="fit")
    text_out = gr.Textbox(label="parameters & diagnostics", lines=8)
    btn.click(analyze, inputs=[file_in, model_in, N_in], outputs=[plot_out, text_out])

if __name__ == "__main__":
    demo.launch()
