"""Axiomize local playground (optional).

A tiny Gradio UI wrapping the bundled tools so non-CLI users can explore:
  - data quality check (csv_check)
  - parameter calibration (fit) with curve plot

Install & run:
    pip install gradio numpy scipy matplotlib pandas
    gradio app.py
Then open the printed local URL. The skill itself does NOT depend on this.
"""

import io
import sys
from pathlib import Path

import gradio as gr
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.integrate import solve_ivp
from scipy.optimize import curve_fit

TOOLS = Path(__file__).resolve().parent / "skills" / "axiomize" / "tools"
sys.path.insert(0, str(TOOLS))

from fit import fit_sir, fit_logistic  # noqa: E402


def analyze(csv_file, model):
    try:
        df = pd.read_csv(csv_file.name)
    except Exception as e:
        return None, f"CSV read failed: {e}"
    if df.shape[1] < 2:
        return None, "Need at least two columns: time, observed value."
    t = df.iloc[:, 0].to_numpy(float)
    y = df.iloc[:, 1].to_numpy(float)
    order = np.argsort(t)
    t, y = t[order], y[order]
    notes = [f"rows: {len(t)}"]

    try:
        result = fit_sir(t, y) if model == "sir" else fit_logistic(t, y)
    except Exception as e:
        return None, f"Fit failed: {e}. Try csv_check first; SIR needs N >> max(y)."

    for k, (v, err) in result["params"].items():
        notes.append(f"{k} = {v:.4g}" + (f" ± {err:.2g}" if err else ""))
    notes.append(f"RMSE = {result['rmse']:.4g}")
    d = result["diag"]
    notes.append(f"AIC {d['aic']:.1f} | BIC {d['bic']:.1f} | resid AC(1) {d['lag1_autocorr']:+.2f}")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(t, y, s=16, label="observed")
    ax.plot(t, result["fitted"], lw=2, label=f" fitted {model}")
    ax.legend(); ax.set_xlabel(df.columns[0]); ax.set_ylabel(df.columns[1])
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
    btn = gr.Button("Calibrate")
    plot_out = gr.Image(label="fit")
    text_out = gr.Textbox(label="parameters & diagnostics", lines=8)
    btn.click(analyze, inputs=[file_in, model_in], outputs=[plot_out, text_out])

if __name__ == "__main__":
    demo.launch()
