"""Regression tests for the three audited hardening fixes.

These lock in behaviour that must not be silently reverted by a refactor:

* the npm entry point must stay syntactically valid and forward the CLI exit
  status (``index.js``);
* the bounded expression parser must not be defeated by a *nested* constant
  exponent, and must refuse constant-only expansion above the hard ceilings
  (``safe_expression``);
* run-bundle import must keep every member inside the destination directory
  (``runs.bundle``).

Each hostile case is paired with a legitimate neighbour so a fix cannot pass by
simply rejecting more.
"""

from __future__ import annotations

import ast
import io
import os
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path

import pytest
import sympy as sp
from axiomize.limits import (
    MAX_ABS_CONSTANT_EXPONENT,
    MAX_BINOMIAL_ARGUMENT,
    MAX_FACTORIAL_ARGUMENT,
    MAX_INTEGER_FOLD_BITS,
)
from axiomize.runs.bundle import (
    MAX_BUNDLE_MEMBERS,
    MAX_BUNDLE_UNCOMPRESSED_BYTES,
    export_run,
    import_run,
)
from axiomize.safe_expression import (
    _fold_integer_constant,
    sympy_expression,
    validate_expression,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# Ceilings for "this must be fast" assertions. The hostile payloads are
# rejected by a bounds check, so they cost microseconds; a generous bound still
# catches a regression that reintroduces unbounded evaluation without making the
# suite flaky on a slow CI worker.
HOSTILE_TIME_BUDGET_S = 5.0


# ---------------------------------------------------------------------------
# 1. npm entry point
# ---------------------------------------------------------------------------


def _node_available() -> bool:
    return shutil.which("node") is not None


def test_npm_entrypoint_is_syntactically_valid() -> None:
    """``index.js`` must parse; the shipped version had a syntax error."""
    entry = REPO_ROOT / "index.js"
    assert entry.is_file(), "index.js is missing from the repository"
    source = entry.read_text(encoding="utf-8")
    # The truncated arrow body that shipped to npm, as a cheap non-parser guard.
    assert "=;" not in source, "index.js still contains the truncated '=> ;' arrow body"
    assert "=>" in source, "index.js must contain a complete arrow function"
    assert "proc.on('close'" in source or 'proc.on("close"' in source, \
        "index.js must handle the child's close event and forward its exit code"


def test_npm_bin_wrapper_delegates_to_the_entrypoint() -> None:
    wrapper = REPO_ROOT / "bin" / "axiomize.js"
    assert wrapper.is_file()
    source = wrapper.read_text(encoding="utf-8")
    assert "../index.js" in source
    assert "=;" not in source


def test_npm_entrypoint_forwards_the_cli_module() -> None:
    source = (REPO_ROOT / "index.js").read_text(encoding="utf-8")
    assert "axiomize.cli" in source, \
        "index.js must invoke the module that owns main() (axiomize.cli)"


@pytest.mark.skipif(not _node_available(), reason="node is not installed")
def test_npm_entrypoint_passes_node_syntax_check(tmp_path: Path) -> None:
    for name in ("index.js", "bin/axiomize.js"):
        result = subprocess.run(
            ["node", "--check", str(REPO_ROOT / name)],
            capture_output=True, text=True, timeout=60, shell=False, check=False,
        )
        assert result.returncode == 0, (
            f"node --check {name} failed:\n{result.stdout}\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# 2. bounded expression parser: nested constant powers
# ---------------------------------------------------------------------------

# The audited denial of service: ten characters that every gate accepted and
# that SymPy never returned from, because the exponent 10**9 was not a literal
# and therefore skipped the MAX_ABS_CONSTANT_EXPONENT ceiling.
NESTED_POW_PAYLOADS = [
    "9**(10**9)",
    "(10**10)**(10**10)",
    "9**(2**10)",
    "9**(2**10)*x",
    "x**(10**9)",
    "9**(10**9) + 1",
    "2**(3**(4**5))",
    "9**(-(10**9))",
]


@pytest.mark.parametrize("payload", NESTED_POW_PAYLOADS)
def test_nested_constant_exponent_is_rejected(payload: str) -> None:
    started = time.perf_counter()
    with pytest.raises(ValueError, match="exponent|folded-constant"):
        validate_expression(payload, allowed_names={"x"})
    assert time.perf_counter() - started < HOSTILE_TIME_BUDGET_S, (
        f"rejecting {payload!r} must be a bounds check, not a slow evaluation"
    )


def test_flattened_constant_exponent_is_still_rejected() -> None:
    """The original ceiling must keep working (no back-compat regression)."""
    with pytest.raises(ValueError, match="exponent magnitude"):
        validate_expression("9**1000000000", allowed_names={"x"})
    with pytest.raises(ValueError, match="exponent magnitude"):
        validate_expression("9**2000", allowed_names={"x"})


@pytest.mark.parametrize(
    "expression",
    [
        "2**1000",
        "10**64",
        "x**2",
        "x**(1/2)",
        "2.5**(1/3)",
        "x**x",
        "(x + 1)**3",
        "sqrt(x**2) + exp(-x)",
    ],
)
def test_legitimate_expressions_still_validate(expression: str) -> None:
    assert validate_expression(expression, allowed_names={"x"}) is not None


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("2 + 3", 5),
        ("2 ** 10", 1024),
        ("7 % 3", 1),
        ("factorial(5)", 120),
        ("binomial(20, 10)", 184756),
        ("product(2, 10)", 3628800),
        ("x", None),
        ("2**(-3)", None),
    ],
)
def test_constant_folder_folds_allowlisted_integers(expression: str, expected: int | None) -> None:
    folded = _fold_integer_constant(ast.parse(expression, mode="eval").body)
    assert folded == expected


def test_factorial_argument_is_allowlisted() -> None:
    assert _fold_integer_constant(ast.parse(f"factorial({MAX_FACTORIAL_ARGUMENT})", mode="eval").body) is not None
    with pytest.raises(ValueError, match="factorial argument"):
        _fold_integer_constant(
            ast.parse(f"factorial({MAX_FACTORIAL_ARGUMENT + 1})", mode="eval").body
        )


def test_binomial_arguments_are_allowlisted() -> None:
    with pytest.raises(ValueError, match="binomial arguments"):
        _fold_integer_constant(
            ast.parse(f"binomial({MAX_BINOMIAL_ARGUMENT + 1}, 5)", mode="eval").body
        )


def test_product_range_is_allowlisted() -> None:
    with pytest.raises(ValueError, match="product range"):
        _fold_integer_constant(ast.parse("product(1, 100000)", mode="eval").body)


def test_oversized_constant_product_is_rejected() -> None:
    """Many individually-legal terms must not multiply into one huge integer."""
    expression = "*".join(["9**1000"] * 20)
    with pytest.raises(ValueError, match="folded-constant"):
        validate_expression(expression, allowed_names={"x"})


def test_folded_constant_ceiling_is_enforced() -> None:
    huge = 2 ** (MAX_INTEGER_FOLD_BITS + 1)
    with pytest.raises(ValueError, match="folded-constant|integer literal"):
        validate_expression(str(huge), allowed_names={"x"})


def test_nested_pow_is_rejected_before_reaching_sympy() -> None:
    """The whole point: the parser refuses the payload SymPy would hang on."""
    started = time.perf_counter()
    with pytest.raises(ValueError):
        sympy_expression("9**(10**9)", {"x": sp.Symbol("x", real=True)})
    elapsed = time.perf_counter() - started
    assert elapsed < HOSTILE_TIME_BUDGET_S, (
        f"sympy_expression must fail fast, took {elapsed:.2f}s "
        f"(ceiling {HOSTILE_TIME_BUDGET_S}s)"
    )


def test_exponent_ceiling_is_configured_and_enforced() -> None:
    """Guard against someone raising the ceiling without adding a real bound."""
    assert MAX_ABS_CONSTANT_EXPONENT == 1000.0
    validate_expression(f"2**{int(MAX_ABS_CONSTANT_EXPONENT)}", allowed_names={"x"})


# ---------------------------------------------------------------------------
# 3. run-bundle import path traversal
# ---------------------------------------------------------------------------


def _zip(path: Path, members: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members:
            archive.writestr(name, data)


def _tar(path: Path, members: list[tuple[str, bytes]], mode: str = "w") -> None:
    with tarfile.open(path, mode) as archive:
        for name, data in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def test_export_import_round_trip_still_works(tmp_path: Path) -> None:
    source = tmp_path / "run_source"
    (source / "nested").mkdir(parents=True)
    (source / "run.json").write_text('{"run_format_version": 1}', encoding="utf-8")
    (source / "nested" / "detail.txt").write_text("hello", encoding="utf-8")

    bundle = export_run(source, tmp_path / "bundle.zip")
    destination = import_run(bundle, tmp_path / "imported")

    assert isinstance(destination, Path)
    assert destination == tmp_path / "imported"
    assert (destination / "run.json").read_text(encoding="utf-8") == '{"run_format_version": 1}'
    assert (destination / "nested" / "detail.txt").read_text(encoding="utf-8") == "hello"


@pytest.mark.parametrize(
    "member_name",
    [
        "../escape.txt",
        "../../escape.txt",
        "../../../../../../../../../../tmp/escape.txt",
        "a/../../escape.txt",
    ],
)
def test_zip_parent_traversal_is_rejected(tmp_path: Path, member_name: str) -> None:
    bundle = tmp_path / "evil.zip"
    _zip(bundle, [(member_name, b"pwned"), ("run.json", b"{}")])
    with pytest.raises(ValueError, match="unsafe archive member"):
        import_run(bundle, tmp_path / "dest")
    assert not list(tmp_path.glob("*escape*"))


def test_zip_absolute_member_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "absolute-escape.txt"
    bundle = tmp_path / "evil.zip"
    _zip(bundle, [(str(target).replace("\\", "/"), b"pwned")])
    with pytest.raises(ValueError, match="unsafe archive member"):
        import_run(bundle, tmp_path / "dest")
    assert not target.exists()


def test_zip_drive_letter_member_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "evil.zip"
    _zip(bundle, [("C:/Windows/System32/evil.dll", b"pwned")])
    with pytest.raises(ValueError, match="unsafe archive member"):
        import_run(bundle, tmp_path / "dest")


def test_zip_backslash_member_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "evil.zip"
    _zip(bundle, [("..\\escape.txt", b"pwned")])
    with pytest.raises(ValueError, match="unsafe archive member"):
        import_run(bundle, tmp_path / "dest")


def test_tar_absolute_member_is_rejected(tmp_path: Path) -> None:
    """The audited escape: a tar member named with an absolute host path."""
    escape = tmp_path / "PWNED.txt"
    bundle = tmp_path / "evil.tar"
    _tar(bundle, [(str(escape), b"tar-traversal-pwned"), ("run.json", b"{}")])
    with pytest.raises(ValueError, match="unsafe archive member"):
        import_run(bundle, tmp_path / "dest")
    assert not escape.exists()
    assert not (tmp_path / "dest" / "run.json").exists()


def test_tar_parent_traversal_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "evil.tar"
    _tar(bundle, [("../../PWNED.txt", b"pwned")])
    with pytest.raises(ValueError, match="unsafe archive member"):
        import_run(bundle, tmp_path / "dest")
    assert not (tmp_path.parent / "PWNED.txt").exists()


def test_tar_symlink_member_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "symlink.tar"
    with tarfile.open(bundle, "w") as archive:
        info = tarfile.TarInfo(name="passwd-link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(ValueError, match="symlink or hardlink"):
        import_run(bundle, tmp_path / "dest")


def test_tar_hardlink_member_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "hardlink.tar"
    with tarfile.open(bundle, "w") as archive:
        info = tarfile.TarInfo(name="run-link")
        info.type = tarfile.LNKTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(ValueError, match="symlink or hardlink"):
        import_run(bundle, tmp_path / "dest")


def test_tar_device_member_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "device.tar"
    with tarfile.open(bundle, "w") as archive:
        info = tarfile.TarInfo(name="dev-node")
        info.type = tarfile.CHRTYPE
        info.devmajor, info.devminor = 1, 3
        archive.addfile(info)
    with pytest.raises(ValueError, match="special member"):
        import_run(bundle, tmp_path / "dest")


def test_zip_symlink_member_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "symlink.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0xA1FF << 16  # S_IFLNK
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(ValueError, match="symlink member"):
        import_run(bundle, tmp_path / "dest")


def test_rejection_does_not_partially_extract(tmp_path: Path) -> None:
    """A hostile member anywhere in the manifest must abort the whole import."""
    bundle = tmp_path / "mixed.tar"
    _tar(bundle, [
        ("good1.json", b"{}"),
        ("good2.json", b"{}"),
        ("../../escape.txt", b"pwned"),
    ])
    destination = tmp_path / "dest"
    with pytest.raises(ValueError, match="unsafe archive member"):
        import_run(bundle, destination)
    leaked = sorted(p.name for p in destination.rglob("*")) if destination.exists() else []
    assert leaked == [], f"bundle was partially extracted: {leaked}"


@pytest.mark.parametrize(
    "suffix,mode",
    [(".tar.gz", "w:gz"), (".tgz", "w:gz"), (".tar.bz2", "w:bz2"), (".tar.xz", "w:xz")],
)
def test_compressed_tar_round_trip_still_works(tmp_path: Path, suffix: str, mode: str) -> None:
    bundle = tmp_path / f"bundle{suffix}"
    _tar(bundle, [("run.json", b'{"ok":1}'), ("a/b/c/deep.txt", b"deep")], mode)
    destination = import_run(bundle, tmp_path / f"dest{suffix.replace('.', '_')}")
    assert (destination / "run.json").read_text(encoding="utf-8") == '{"ok":1}'
    assert (destination / "a" / "b" / "c" / "deep.txt").read_text(encoding="utf-8") == "deep"


def test_tar_directory_members_are_supported(tmp_path: Path) -> None:
    bundle = tmp_path / "dirs.tar"
    with tarfile.open(bundle, "w") as archive:
        info = tarfile.TarInfo(name="onlydir/")
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        archive.addfile(info)
        child = tarfile.TarInfo(name="onlydir/file.txt")
        child.size = 4
        archive.addfile(child, io.BytesIO(b"data"))
    destination = import_run(bundle, tmp_path / "dest")
    assert (destination / "onlydir" / "file.txt").read_text(encoding="utf-8") == "data"


def test_expansion_bomb_is_rejected(tmp_path: Path) -> None:
    """A small archive that expands past the hard byte ceiling must not unpack."""
    declared = MAX_BUNDLE_UNCOMPRESSED_BYTES + (1 << 20)
    bundle = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big.bin", b"\x00" * declared)
    with zipfile.ZipFile(bundle) as archive:
        assert sum(e.file_size for e in archive.infolist()) == declared
    destination = tmp_path / "dest"
    with pytest.raises(ValueError, match="expands beyond the hard limit"):
        import_run(bundle, destination)
    assert not (destination / "big.bin").exists()


def test_member_count_ceiling_is_enforced(tmp_path: Path) -> None:
    bundle = tmp_path / "many.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        for index in range(MAX_BUNDLE_MEMBERS + 1):
            archive.writestr(f"f{index:05d}.txt", b"x")
    destination = tmp_path / "dest"
    with pytest.raises(ValueError, match="hard member limit"):
        import_run(bundle, destination)
    assert not list(destination.rglob("*"))


def test_legitimate_bundle_under_the_ceilings_still_imports(tmp_path: Path) -> None:
    bundle = tmp_path / "ok.zip"
    payload = b"x" * (1024 * 1024)
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.bin", payload)
        archive.writestr("run.json", b'{"ok":true}')
    destination = import_run(bundle, tmp_path / "dest")
    assert (destination / "data.bin").stat().st_size == len(payload)
    assert (destination / "run.json").exists()


def test_unsupported_bundle_format_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.rar"
    bundle.write_bytes(b"not an archive")
    with pytest.raises(ValueError, match="unsupported bundle format"):
        import_run(bundle, tmp_path / "dest")


def test_missing_bundle_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        import_run(tmp_path / "nope.zip", tmp_path / "dest")


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink creation needs privileges on Windows")
def test_nested_symlink_escape_is_rejected(tmp_path: Path) -> None:
    """A pre-existing symlink inside the destination must not be followed out."""
    destination = tmp_path / "dest"
    destination.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (destination / "link").symlink_to(outside, target_is_directory=True)

    bundle = tmp_path / "evil.zip"
    _zip(bundle, [("link/escape.txt", b"pwned")])
    with pytest.raises(ValueError):
        import_run(bundle, destination)
    assert not (outside / "escape.txt").exists()
