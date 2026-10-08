"""Browser audit of old versus corrected CanvasXpress sensitivity Bar shapes.

Uses the real, pinned CanvasXpress JavaScript bundle checked out by the
dedicated GitHub Actions job. It reports both render attempts and saves a
side-by-side screenshot. No vendor runtime is committed to this repository.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from axiomize.visualization.canvasxpress_export import chart_definition, sensitivity_chart

ROOT = Path(__file__).resolve().parents[1]


def _page_html(old: dict, fixed: dict, library_root: str) -> str:
    old_data = json.dumps({"y": old["y"], "z": old.get("z")}, allow_nan=False)
    fixed_data = json.dumps({"y": fixed["y"]}, allow_nan=False)
    old_config = json.dumps(old["config"], allow_nan=False)
    fixed_config = json.dumps(fixed["config"], allow_nan=False)
    # All embedded JSON is produced from constant numeric fixtures, not from
    # user-supplied HTML. Paths to the vendor bundle are repo-relative.
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CanvasXpress sensitivity: layout comparison</title>
<link rel="stylesheet" href="{library_root}/canvasXpress.css">
<style>
body {{ font: 16px system-ui, sans-serif; margin: 22px; }}
h1 {{ font-size: 22px; }}
.row {{ display: flex; gap: 16px; align-items: flex-start; }}
.panel {{ width: 730px; }}
canvas {{ border: 1px solid #bdbdbd; }}
code, pre {{ font-size: 12px; white-space: pre-wrap; }}
</style>
<script src="{library_root}/canvasXpress.min.js"></script>
</head>
<body>
<h1>Identical signed sensitivity data, two CanvasXpress layouts</h1>
<p>All three input values are identical. Parameters: enzyme=0.21, gamma=-0.44, beta=0.82.</p>
<div class="row">
<div class="panel"><h2>Old: parameter variables, one sample</h2>
<canvas id="old" width="710" height="590"></canvas></div>
<div class="panel"><h2>Fixed: one variable, parameter samples</h2>
<canvas id="fixed" width="710" height="590"></canvas></div>
</div>
<pre id="report">pending</pre>
<script>
(function () {{
  const specs = [
    {{ id: "old", data: {old_data}, config: {old_config} }},
    {{ id: "fixed", data: {fixed_data}, config: {fixed_config} }}
  ];
  const results = {{}};
  for (const spec of specs) {{
    try {{
      if (typeof CanvasXpress !== "function") {{
        throw new Error("CanvasXpress JavaScript failed to load");
      }}
      const instance = new CanvasXpress(spec.id, spec.data, spec.config);
      results[spec.id] = {{ initialized: Boolean(instance), error: null }};
    }} catch (error) {{
      results[spec.id] = {{ initialized: false, error: String(error) }};
    }}
  }}
  setTimeout(function () {{
    for (const spec of specs) {{
      try {{
        const canvas = document.getElementById(spec.id);
        const rgba = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
        let ink = 0;
        for (let i = 0; i < rgba.length; i += 40) {{
          // Ignore background white or transparent pixels.
          if (rgba[i + 3] > 0 && (rgba[i] < 220 || rgba[i + 1] < 220 || rgba[i + 2] < 220)) {{
            ink++;
          }}
        }}
        results[spec.id].sampled_ink_pixels = ink;
        results[spec.id].rendered = results[spec.id].initialized && ink > 100;
      }} catch (error) {{
        results[spec.id].rendered = false;
        results[spec.id].error = String(error);
      }}
    }}
    window.__auditResult = results;
    document.getElementById("report").textContent = JSON.stringify(results, null, 2);
  }}, 1500);
}})();
</script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-root", type=Path, default=ROOT / "external" / "canvasxpress-js" / "src")
    parser.add_argument("--output", type=Path, default=ROOT / "browser-audit")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    assert (args.vendor_root / "canvasXpress.min.js").is_file(), "pinned CanvasXpress bundle is missing"
    args.output.mkdir(parents=True, exist_ok=True)
    scores = {"beta": 0.82, "gamma": -0.44, "enzyme": 0.21}
    ranked = ["enzyme", "gamma", "beta"]
    values = [scores[name] for name in ranked]
    config = {
        "graphType": "Bar",
        "graphOrientation": "horizontal",
        "xAxisTitle": "Sensitivity score",
        "showDataValues": True,
        "title": "Signed sensitivity scores",
    }
    old = chart_definition(
        vars=ranked, smps=["sensitivity"], data=[[v] for v in values],
        variable_annotations={"parameter": ranked}, config=config,
    )
    fixed = sensitivity_chart(scores, config={"showDataValues": True, "title": "Signed sensitivity scores"})
    assert fixed["y"] == {"vars": ["Sensitivity"], "smps": ranked, "data": [values]}
    library_relative = Path("..") / args.vendor_root.relative_to(ROOT)
    html_path = args.output / "comparison.html"
    html_path.write_text(
        _page_html(old, fixed, library_relative.as_posix()), encoding="utf-8"
    )
    browser_path = shutil.which("google-chrome") or shutil.which("chromium")
    if browser_path is None:
        raise RuntimeError("Google Chrome or Chromium is required for the browser audit")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_path, headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": 1530, "height": 890}, device_scale_factor=1)
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=30000)
            page.wait_for_function("window.__auditResult !== undefined", timeout=30000)
            result = page.evaluate("window.__auditResult")
            page.screenshot(path=str(args.output / "comparison.png"), full_page=True)
        finally:
            browser.close()
    report = {"layout": {"old": old["y"], "fixed": fixed["y"]}, "render": result, "page_errors": errors}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not result["fixed"].get("rendered"):
        raise SystemExit("FAIL: corrected CanvasXpress chart did not render with actual vendor library")
    print("PASS: corrected sensitivity layout renders with the pinned CanvasXpress JavaScript library")
    print("Side-by-side screenshot and machine-readable report saved under browser-audit/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
