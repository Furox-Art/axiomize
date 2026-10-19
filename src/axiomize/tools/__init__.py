"""Standalone modeling tools shipped with axiomize.

Each module is importable (``axiomize.tools.validate``) and also runs as a
script; the package exposes them as the ``axiomize-*`` console commands.
"""


# Wheel builds force-include the standalone skill tools into this package.
# Editable source checkouts do not: expose the same trusted, repository-owned
# modules so normal public CLI/benchmark imports work outside pytest conftest.
from pathlib import Path as _Path

_root = _Path(__file__).resolve().parents[3]
_skill_tools = _root / "skills" / "axiomize" / "tools"
_package_paths = globals().get("__path__")
if (
    (_root / "src" / "axiomize" / "tools" / "__init__.py").resolve() == _Path(__file__).resolve()
    and _skill_tools.is_dir()
    and _package_paths is not None
    and str(_skill_tools) not in _package_paths
):
    _package_paths.append(str(_skill_tools))
