"""Portable run bundles (PHASE 9).

A run directory zips into a single file that another machine or agent
can import and inspect - no chat context required.

Import is hardened: every archive member is resolved against the destination
directory and rejected before extraction if it would land outside it. Absolute
member names, ``..`` traversal, and symlink/hardlink members are refused, so an
attacker-supplied bundle cannot write anywhere else on the host.
"""

from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

# Bound the work a single import can request, the same way every other Axiomize
# entry point bounds its input, so a hostile archive cannot exhaust memory or
# disk before its members are even inspected.
MAX_BUNDLE_MEMBERS = 20_000
MAX_BUNDLE_UNCOMPRESSED_BYTES = 64 * 1024 * 1024


def export_run(run_dir: str | Path, bundle_path: str | Path) -> Path:
    bundle = Path(bundle_path)
    if bundle.suffix != ".zip":
        raise ValueError("bundle path must end in .zip")
    base = str(bundle.with_suffix(""))
    shutil.make_archive(base, "zip", root_dir=str(Path(run_dir).resolve()))
    return bundle


def _reject(reason: str, name: str) -> ValueError:
    return ValueError(f"unsafe archive member {name!r}: {reason}")


def _safe_member_name(name: str) -> PurePosixPath:
    """Validate one archive member name and return it as a relative path.

    Rejects absolute paths, Windows drive letters and UNC prefixes, and any
    ``..`` component. Returns a :class:`PurePosixPath` so the traversal check is
    identical on every platform regardless of how the archive spelled the path.
    """
    if not name or name in {".", "./"}:
        raise _reject("empty name", name)
    if "\x00" in name:
        raise _reject("NUL byte in name", name)
    # ``PurePosixPath`` would happily keep a leading separator; reject first.
    # A backslash is a separator on Windows and an ordinary character on POSIX,
    # so refuse it as well and handle the common prefixes in one comparison.
    if name.startswith(("/", "\\", "//")):
        raise _reject("absolute path", name)
    if len(name) >= 2 and name[1] == ":":
        raise _reject("drive-letter path", name)
    if "\\" in name:
        raise _reject("backslash separator", name)

    parts = [part for part in name.split("/") if part not in ("", ".")]
    if not parts:
        raise _reject("empty name", name)
    if any(part == ".." for part in parts):
        raise _reject("parent-directory traversal", name)
    return PurePosixPath(*parts)


def _resolve_member(dest_root: Path, name: str) -> Path:
    """Resolve ``name`` under ``dest_root`` or raise if it escapes the root."""
    relative = _safe_member_name(name)
    target = (dest_root / Path(*relative.parts)).resolve()
    try:
        target.relative_to(dest_root)
    except ValueError as exc:
        raise _reject("resolves outside the destination directory", name) from exc
    return target


def _check_member_budget(count: int, total_bytes: int) -> None:
    if count > MAX_BUNDLE_MEMBERS:
        raise ValueError(
            f"bundle declares more than the hard member limit of {MAX_BUNDLE_MEMBERS}"
        )
    if total_bytes > MAX_BUNDLE_UNCOMPRESSED_BYTES:
        raise ValueError(
            "bundle expands beyond the hard limit of "
            f"{MAX_BUNDLE_UNCOMPRESSED_BYTES} bytes"
        )


def _import_zip(bundle: Path, dest_root: Path) -> None:
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.infolist()
        _check_member_budget(len(entries), sum(e.file_size for e in entries))
        # Validate the whole manifest before writing anything, so a hostile
        # bundle cannot be half-extracted before the bad member is noticed.
        plan: list[tuple[zipfile.ZipInfo, Path]] = []
        for entry in entries:
            mode = (entry.external_attr >> 16) & 0xF000
            if mode == 0xA000:
                raise _reject("symlink member", entry.filename)
            target = _resolve_member(dest_root, entry.filename)
            plan.append((entry, target))
        for entry, target in plan:
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink, length=1024 * 1024)


def _import_tar(bundle: Path, dest_root: Path) -> None:
    with tarfile.open(bundle) as archive:
        members = archive.getmembers()
        _check_member_budget(len(members), sum(m.size for m in members))
        plan: list[tuple[tarfile.TarInfo, Path]] = []
        for member in members:
            if member.issym() or member.islnk():
                raise _reject("symlink or hardlink member", member.name)
            if not (member.isfile() or member.isdir()):
                raise _reject("device, FIFO or other special member", member.name)
            target = _resolve_member(dest_root, member.name)
            plan.append((member, target))
        for member, target in plan:
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise _reject("unreadable member", member.name)
            with source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink, length=1024 * 1024)


def import_run(bundle_path: str | Path, dest_dir: str | Path) -> Path:
    """Extract a run bundle, keeping every member inside ``dest_dir``.

    Supports the same archive types :func:`shutil.unpack_archive` accepted
    (``.zip``, ``.tar`` and the compressed tar variants). Unknown extensions are
    rejected rather than guessed at.
    """
    bundle = Path(bundle_path)
    if not bundle.is_file():
        raise ValueError(f"bundle {bundle.name!r} does not exist")
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    dest_root = dest.resolve()

    suffixes = [suffix.lower() for suffix in bundle.suffixes]
    if ".zip" in suffixes:
        _import_zip(bundle, dest_root)
    elif suffixes and suffixes[-1] in {".tar", ".gz", ".tgz", ".bz2", ".tbz", ".xz", ".txz"}:
        _import_tar(bundle, dest_root)
    else:
        raise ValueError(
            f"unsupported bundle format for {bundle.name!r}; expected .zip, .tar or a compressed tar"
        )
    return dest
