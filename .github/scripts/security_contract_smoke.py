"""Fast security-contract checks for source and workflow configuration."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHA_REF = re.compile(r"^[0-9a-f]{40}(?:\s*#.*)?$")

# ``skills/axiomize/tools`` is force-included into the wheel and provides real
# console entry points. It is therefore a runtime surface, not documentation.
RUNTIME_PYTHON_ROOTS = (
    ROOT / "src",
    ROOT / "skills" / "axiomize" / "tools",
    ROOT / "playground",
)


def _python_security_scan() -> list[str]:
    failures: list[str] = []
    seen: set[Path] = set()
    for root in RUNTIME_PYTHON_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                failures.append(f"{path.relative_to(ROOT)}: syntax error: {exc}")
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                    failures.append(f"{path.relative_to(ROOT)}:{node.lineno}: forbidden {node.func.id}()")
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "system":
                        failures.append(f"{path.relative_to(ROOT)}:{node.lineno}: forbidden os.system()")
                    if node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}:
                        for keyword in node.keywords:
                            if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                                failures.append(f"{path.relative_to(ROOT)}:{node.lineno}: subprocess shell=True")
    return failures


def _workflow_pin_scan() -> list[str]:
    failures: list[str] = []
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith("- uses:"):
                continue
            value = stripped.split(":", 1)[1].strip()
            if value.startswith("./"):
                continue
            if "@" not in value:
                failures.append(f"{path.relative_to(ROOT)}:{lineno}: action has no immutable ref")
                continue
            ref = value.rsplit("@", 1)[1]
            if not SHA_REF.fullmatch(ref):
                failures.append(f"{path.relative_to(ROOT)}:{lineno}: action is not pinned to a 40-hex commit SHA: {value}")
    return failures


def _latex_boundary_scan() -> list[str]:
    path = ROOT / "skills" / "axiomize" / "tools" / "report_to_latex.py"
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    for required in ("-no-shell-escape", "-halt-on-error", "SAFE_MATH_MACROS", "PDFLATEX_TIMEOUT_S"):
        if required not in text:
            failures.append(f"{path.relative_to(ROOT)}: missing LaTeX hardening marker {required!r}")
    return failures


def main() -> int:
    failures = [*_python_security_scan(), *_workflow_pin_scan(), *_latex_boundary_scan()]
    if failures:
        print("SECURITY CONTRACT: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("SECURITY CONTRACT: PASS")
    print("- no eval/exec/os.system/subprocess shell=True in shipped runtime surfaces")
    print("- external GitHub Actions pinned to immutable commit SHAs")
    print("- LaTeX compiler and math-macro boundary hardened")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
