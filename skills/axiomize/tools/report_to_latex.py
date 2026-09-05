"""Axiomize report-to-LaTeX converter.

Converts the standardized modeling report format into a conservative LaTeX
subset. User math is filtered through an allow-list of ordinary mathematical
control sequences before it reaches TeX. PDF compilation disables shell escape,
halts on the first error and is time-bounded.
"""

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

MAX_MARKDOWN_BYTES = 64 * 1024 * 1024
PDFLATEX_TIMEOUT_S = 60

PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[a4paper, margin=2.4cm]{geometry}
\usepackage{amsmath, amssymb}
\usepackage{booktabs}
\usepackage{array}
\usepackage{enumitem}
\setlistdepth{9}
\usepackage[hidelinks]{hyperref}
\usepackage{parskip}
\setlength{\tabcolsep}{4pt}
\begin{document}
"""
POSTAMBLE = "\n\\end{document}\n"

SUBSCRIPTS = {chr(0x2080 + i): f"$_{{{i}}}$" for i in range(10)}
SUBSCRIPTS.update({"\u208a": "$_{+}$", "\u208b": "$_{-}$", "\u209c": "$_{t}$",
                   "\u2090": "$_{a}$", "\u2091": "$_{e}$", "\u2095": "$_{h}$"})
SUPERS = {**{chr(0x2070 + i): f"$^{i}$" for i in [0, 4, 5, 6, 7, 8, 9]},
          "\u00b9": "$^1$", "\u00b2": "$^2$", "\u00b3": "$^3$",
          "\u1d40": "$^{T}$", "\u1d4f": "$^{k}$", "\u207f": "$^{n}$"}
CIRCLED = {chr(0x2460 + i): f"({i + 1})" for i in range(10)}
DOUBLE_STRUCK = {"\u2124": r"$\mathbb{Z}$", "\u2115": r"$\mathbb{N}$",
                 "\u211d": r"$\mathbb{R}$", "\u211a": r"$\mathbb{Q}$"}
MATH_EXTRA = {
    **DOUBLE_STRUCK,
    "\u2200": r"$\forall$", "\u222b": r"$\int$", "\u2282": r"$\subset$",
    "\u2286": r"$\subseteq$", "\u2283": r"$\supset$", "\u222a": r"$\cup$",
    "\u2229": r"$\cap$", "\u230a": r"$\lfloor$", "\u230b": r"$\rfloor$",
    "\u2308": r"$\lceil$", "\u2309": r"$\rceil$", "\u27fa": r"$\iff$",
    "\u2194": r"$\leftrightarrow$", "\u21a6": r"$\mapsto$", "\u22c5": r"$\cdot$",
    "\u2218": r"$\circ$", "\u2245": r"$\cong$", "\u223c": r"$\sim$",
    "\u2207": r"$\nabla$", "\u2202": r"$\partial$", "\u26a0": "(!)",
}
TRANSLIT = {
    **SUBSCRIPTS, **SUPERS, **CIRCLED, **MATH_EXTRA,
    "\u00b2": "$^2$", "\u00b3": "$^3$", "\u2070": "$^0$", "\u2074": "$^4$",
    "\u2075": "$^5$", "\u207a": "$^+$", "\u207b": "$^-$",
    "\u03b1": r"$\alpha$", "\u03b2": r"$\beta$", "\u03b3": r"$\gamma$",
    "\u03b4": r"$\delta$", "\u03bb": r"$\lambda$", "\u03bc": r"$\mu$",
    "\u03c1": r"$\rho$", "\u03c3": r"$\sigma$", "\u03c4": r"$\tau$",
    "\u03ba": r"$\kappa$", "\u03c0": r"$\pi$", "\u03b7": r"$\eta$",
    "\u03b5": r"$\varepsilon$", "\u03a3": r"$\Sigma$", "\u03a0": r"$\Pi$",
    "\u0394": r"$\Delta$", "\u03c9": r"$\omega$", "\u03b8": r"$\theta$",
    "\u2192": r"$\to$", "\u21d2": r"$\Rightarrow$", "\u27f6": r"$\longrightarrow$",
    "\u27f7": r"$\longleftrightarrow$", "\u2264": r"$\leq$", "\u2265": r"$\geq$",
    "\u2260": r"$\neq$", "\u2248": r"$\approx$", "\u2208": r"$\in$",
    "\u2209": r"$\notin$", "\u221d": r"$\propto$", "\u00d7": r"$\times$",
    "\u00f7": r"$\div$", "\u221a": r"$\sqrt{\ }$", "\u221e": r"$\infty$",
    "\u2211": r"$\sum$", "\u226a": r"$\ll$", "\u226b": r"$\gg$",
    "\u2212": "-", "\u2013": "--", "\u2014": "---", "\u00b7": r"$\cdot$",
    "\u27e8": r"$\langle$", "\u27e9": r"$\rangle$", "\u2032": "'",
    "\u2026": "\\ldots{}", "\u2261": r"$\equiv$", "\u00b1": r"$\pm$",
    "\u2713": "yes", "\u2717": "no", "\u27f9": r"$\Longrightarrow$",
    "\u21d4": r"$\Leftrightarrow$", "\u2190": r"$\leftarrow$",
}


def _bare(rep):
    if rep.startswith("$") and rep.endswith("$") and len(rep) > 1:
        return rep[1:-1]
    return r"\text{" + rep + "}"


TRANSLIT_MATH = {k: _bare(v) for k, v in TRANSLIT.items()}

# Alphabetic control sequences permitted in user-supplied math. Structural TeX
# primitives (input, include, csname, def, write, catcode, begin/end, usepackage,
# etc.) are intentionally absent. Unknown commands are neutralized rather than
# passed through.
SAFE_MATH_MACROS = frozenset({
    # Greek / common symbols
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta", "vartheta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "varpi", "rho", "varrho", "sigma", "tau",
    "upsilon", "phi", "varphi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi",
    "Sigma", "Upsilon", "Phi", "Psi", "Omega",
    # Operators / functions
    "frac", "sqrt", "sum", "prod", "int", "iint", "iiint", "oint", "lim", "sup", "inf", "min", "max",
    "log", "ln", "exp", "sin", "cos", "tan", "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh",
    "det", "gcd", "Pr", "arg", "deg", "dim", "ker", "hom",
    # Relations / sets / arrows
    "le", "leq", "ge", "geq", "neq", "approx", "sim", "simeq", "cong", "equiv", "propto", "ll", "gg",
    "in", "notin", "subset", "subseteq", "supset", "supseteq", "cup", "cap", "setminus", "emptyset",
    "to", "rightarrow", "leftarrow", "leftrightarrow", "Rightarrow", "Leftarrow", "Leftrightarrow",
    "longrightarrow", "longleftarrow", "longleftrightarrow", "Longrightarrow", "Longleftarrow", "mapsto", "iff",
    # Delimiters / accents / formatting needed for ordinary math
    "left", "right", "langle", "rangle", "lfloor", "rfloor", "lceil", "rceil", "vert", "Vert",
    "overline", "underline", "hat", "widehat", "bar", "vec", "dot", "ddot", "tilde", "widetilde",
    "mathrm", "mathbf", "mathit", "mathsf", "mathtt", "mathcal", "mathbb", "operatorname",
    # Miscellaneous
    "partial", "nabla", "infty", "forall", "exists", "neg", "land", "lor", "cdot", "times", "div",
    "pm", "mp", "circ", "ldots", "cdots", "vdots", "ddots", "quad", "qquad", "hbar", "ell",
})

DANGEROUS_MACROS = frozenset({
    "input", "include", "includeonly", "write", "openout", "openin", "closeout", "closein", "read",
    "immediate", "catcode", "def", "gdef", "edef", "xdef", "directlua", "luadirect", "luaexec",
    "special", "write18", "inputlineno", "scantokens", "csname", "endcsname", "usepackage", "documentclass",
    "newcommand", "renewcommand", "newenvironment", "begin", "end",
})


def esc_map(text, dropped):
    out = []
    for ch in text:
        if ch == "\\": out.append(r"\textbackslash{}")
        elif ch == "&": out.append(r"\&")
        elif ch == "%": out.append(r"\%")
        elif ch == "#": out.append(r"\#")
        elif ch == "_": out.append(r"\_")
        elif ch == "$": out.append(r"\$")
        elif ch == "^": out.append(r"\textasciicircum{}")
        elif ch == "~": out.append(r"\textasciitilde{}")
        elif ch == "{": out.append(r"\{")
        elif ch == "}": out.append(r"\}")
        elif ord(ch) < 128: out.append(ch)
        elif ch in TRANSLIT: out.append(TRANSLIT[ch])
        else:
            name = unicodedata.name(ch, "")
            if "GREEK SMALL LETTER " in name: out.append(f"${name.rsplit(' ', 1)[-1].lower()}$")
            elif "GREEK CAPITAL LETTER " in name: out.append(f"${name.rsplit(' ', 1)[-1].capitalize()}$")
            elif "COMBINING" in name: dropped.add(f"U+{ord(ch):04X} {name}")
            elif "LETTER" in name: out.append(ch)
            else:
                decomposed = unicodedata.normalize("NFKD", ch)
                if all(ord(c) < 128 for c in decomposed): out.append(decomposed)
                else: dropped.add(f"U+{ord(ch):04X} {name or ch!r}")
    return "".join(out)


def sanitize_math(text, dropped):
    out = []
    for ch in text:
        if ord(ch) < 128: out.append(ch)
        elif ch in TRANSLIT_MATH: out.append(TRANSLIT_MATH[ch])
        else:
            name = unicodedata.name(ch, "")
            if "GREEK SMALL LETTER " in name: out.append(name.rsplit(" ", 1)[-1].lower())
            elif "GREEK CAPITAL LETTER " in name: out.append(name.rsplit(" ", 1)[-1])
            else: dropped.add(f"U+{ord(ch):04X} {name or ch!r}")
    return "".join(out)


def neutralize_text_macros(math_latex):
    # User math cannot request arbitrary text-mode TeX. Preserve the contents.
    return math_latex.replace(r"\text{", "{")


def neutralize_dangerous_macros(latex, dropped=None):
    """Backward-compatible deny-list helper used by existing callers/tests."""
    if dropped is None:
        dropped = set()

    def repl(match):
        name = match.group(1)
        if name.lower() in DANGEROUS_MACROS:
            dropped.add(f"blocked \\{name}")
            return f"[blocked-{name}]"
        return match.group(0)

    return re.sub(r"\\([A-Za-z]+)", repl, latex)


def neutralize_math_macros(latex, dropped=None):
    """Allow only ordinary math macros; neutralize every other alphabetic macro."""
    if dropped is None:
        dropped = set()

    def repl(match):
        name = match.group(1)
        if name in SAFE_MATH_MACROS:
            return match.group(0)
        dropped.add(f"blocked \\{name}")
        # No backslash is emitted, so following braces are only math grouping.
        return f"\u005bblocked-{name}\u005d"

    return re.sub(r"\\([A-Za-z]+)", repl, latex)


def safe_math(text, dropped):
    sanitized = neutralize_text_macros(sanitize_math(text, dropped))
    # Keep the old deny-list as defense in depth, then enforce the allow-list.
    sanitized = neutralize_dangerous_macros(sanitized, dropped)
    return neutralize_math_macros(sanitized, dropped)


def inline(text, dropped):
    spans = []

    def stash(latex):
        spans.append(latex)
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"\$\$(.+?)\$\$", lambda m: stash("\\[" + safe_math(m.group(1), dropped) + "\\]"), text, flags=re.S)
    text = re.sub(r"\$(?![\d,])((?:[^$\n\\]|\\.)+?)\$", lambda m: stash("$" + safe_math(m.group(1), dropped) + "$"), text)
    text = esc_map(text, dropped)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"`([^`]+)`", r"\\texttt{\1}", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)
    return text


def flush_table(rows, dropped):
    if not rows:
        return []
    cols = max(len(r) for r in rows)
    body = [r for r in rows if not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", "".join(r))]
    out = ["\\begin{tabular}{" + "l" * cols + "}", "\\toprule"]
    for j, row in enumerate(body):
        cells = [inline(c.strip(), dropped) for c in row] + [""] * (cols - len(row))
        out.append(" & ".join(cells) + " \\\\")
        if j == 0:
            out.append("\\midrule")
    out += ["\\bottomrule", "\\end{tabular}"]
    return out


def convert(md_text):
    if not isinstance(md_text, str):
        raise ValueError("markdown input must be text")
    if len(md_text.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        raise ValueError(f"markdown input exceeds hard limit of {MAX_MARKDOWN_BYTES} bytes")
    dropped = set()
    lines = md_text.splitlines()
    out = [PREAMBLE]
    table_buf = []
    code_state = None
    code_buf = []
    display_buf = None
    list_stack = []

    def close_lists(to_depth=0):
        while len(list_stack) > to_depth:
            out.append(f"\\end{{{list_stack.pop()}}}")

    def handle_list(indent, ordered, text_line):
        env = "enumerate" if ordered else "itemize"
        depth = min(indent // 2, 8)
        close_lists(depth + 1)
        if len(list_stack) == depth + 1 and list_stack[-1] != env:
            close_lists(depth)
        if len(list_stack) <= depth:
            while len(list_stack) <= depth:
                list_stack.append(env)
                out.append(f"\\begin{{{env}}}")
        out.append("  \\item " + inline(text_line, dropped))

    for raw in lines:
        stripped = raw.strip()
        if display_buf is not None:
            if stripped == "$$":
                out.append("\\[" + safe_math(" ".join(display_buf), dropped) + "\\]")
                display_buf = None
            else:
                display_buf.append(stripped)
            continue
        if stripped == "$$":
            close_lists(); out.extend(flush_table(table_buf, dropped)); table_buf = []; display_buf = []
            continue
        if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
            inner = stripped[2:-2].strip()
            close_lists(); out.extend(flush_table(table_buf, dropped)); table_buf = []
            out.append("\\[" + safe_math(inner, dropped) + "\\]")
            continue
        if stripped.startswith("```"):
            if code_state:
                if code_state == "mermaid": out += ["%" + line for line in code_buf]
                else: out += ["\\begin{verbatim}"] + code_buf + ["\\end{verbatim}"]
                code_state, code_buf = None, []
            else:
                close_lists(); code_state = stripped[3:].strip() or "text"; code_buf = []
            continue
        if code_state:
            code_buf.append(esc_map(raw, dropped))
            continue
        is_row = stripped.startswith("|") and stripped.count("|") >= 2
        if not is_row and table_buf:
            out.extend(flush_table(table_buf, dropped)); table_buf = []
        if is_row:
            table_buf.append(stripped.strip("|").split("|")); continue
        indent = len(raw) - len(raw.lstrip())
        if re.match(r"^-\s+", stripped):
            handle_list(indent, False, re.sub(r"^-\s+", "", stripped)); continue
        mnum = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if mnum:
            handle_list(indent, True, mnum.group(2)); continue
        close_lists()
        if not stripped: continue
        if stripped == "---":
            out.append("\\medskip\\hrule\\medskip"); continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            cmd = {1: "\\section*{", 2: "\\subsection*{", 3: "\\subsubsection*{", 4: "\\paragraph*{"}[len(heading.group(1))]
            out.append(cmd + inline(heading.group(2).strip(), dropped) + "}"); continue
        out.append(inline(stripped, dropped) + "\\\\")

    out.extend(flush_table(table_buf, dropped))
    if display_buf is not None:
        out.append("\\[" + safe_math(" ".join(display_buf), dropped) + "\\]")
        print("warning: unclosed $$ block at end of input - auto-closed")
    close_lists(); out.append(POSTAMBLE)
    tex = "\n".join(out)
    if dropped:
        print("note: dropped or blocked input:", ", ".join(sorted(dropped)))
    return tex


def selftest():
    root = Path(__file__).resolve().parents[3]
    sample = root / "examples" / "epidemic-sir.md"
    if not sample.exists():
        print("selftest skipped: example not found"); return 0
    tex = convert(sample.read_text(encoding="utf-8"))
    needed = ["\\section*", "\\begin{tabular}", "\\begin{verbatim}", "$_{0}$", "\\textbf", "\\begin{itemize}"]
    missing = [item for item in needed if item not in tex]
    print(f"converted {sample.name}: {len(tex.splitlines())} lines of LaTeX")
    for item in needed:
        print(f"contains {item:22s} {'PASS' if item in tex else 'FAIL'}")
    return 0 if not missing else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", help="report markdown file")
    parser.add_argument("--output", help="destination .tex file")
    parser.add_argument("--pdf", action="store_true", help="also compile with pdflatex (if installed)")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        sys.exit(selftest())
    if not args.input or not args.output:
        parser.error("--input and --output are required unless --selftest")
    src = Path(args.input)
    if src.stat().st_size > MAX_MARKDOWN_BYTES:
        raise ValueError(f"markdown input exceeds hard limit of {MAX_MARKDOWN_BYTES} bytes")
    tex = convert(src.read_text(encoding="utf-8"))
    dst = Path(args.output)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(tex, encoding="utf-8")
    print(f"wrote {dst} ({len(tex.splitlines())} lines)")

    if args.pdf:
        try:
            subprocess.run(["pdflatex", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=True, timeout=15, shell=False)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print("pdflatex not found or unusable - skipping PDF step"); return
        command = [
            "pdflatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", dst.name,
        ]
        try:
            for _ in range(2):
                completed = subprocess.run(command, cwd=str(dst.parent), capture_output=True, text=True,
                                           timeout=PDFLATEX_TIMEOUT_S, shell=False, check=False)
                if completed.returncode != 0:
                    print("PDF compilation failed - inspect the .log next to the .tex")
                    return
        except subprocess.TimeoutExpired:
            print(f"PDF compilation timed out after {PDFLATEX_TIMEOUT_S}s")
            return
        pdf = dst.with_suffix(".pdf")
        print(("PDF ready -> " + str(pdf)) if pdf.exists() else "PDF compilation failed - inspect the .log next to the .tex")


if __name__ == "__main__":
    main()
