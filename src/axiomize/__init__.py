"""Axiomize: rigorous, reproducible scientific modeling engine and agent skill pack."""

__version__ = "1.12.2"

# Initialize compatibility/security hooks before callers can import submodules.
from axiomize import general_engine as _general_engine  # noqa: E402,F401
from axiomize import advanced_family_engine as _advanced_family_engine  # noqa: E402
from axiomize.portable_export_compat import install_notebook_schema_alias as _install_notebook_schema_alias  # noqa: E402
from axiomize.runtime_guard import install_general_engine_guards as _install_runtime_guards  # noqa: E402
from axiomize.v120_runtime import install as _install_v120  # noqa: E402

_install_runtime_guards(_general_engine)
_install_notebook_schema_alias()
_advanced_family_engine._compile_expression = _general_engine._compile_expression_hardened
_install_v120(_general_engine, _advanced_family_engine)

del _install_runtime_guards, _install_notebook_schema_alias, _install_v120, _advanced_family_engine