"""Axiomize: adaptive rigorous first-principles modeling skill pack.

Turns a vague idea into multiple formal mathematical candidates, clarifies
missing mechanisms, compares models honestly, validates with scientific tools,
quantifies uncertainty and sensitivity, produces testable hypotheses and keeps
runs reproducible while extra agent/provider consumption remains user-controlled.

CLI entry points installed with the package::

    axiomize            adaptive intake + scientific engine CLI
    axiomize-validate   deterministic/stochastic/queue model validators
    axiomize-fit        calibrate SIR / logistic models to CSV data
    axiomize-csv-check  data-quality pre-check before calibrating
    axiomize-benchmark  grade modeling reports against benchmark cases
    axiomize-to-latex   convert a modeling report to compilable LaTeX
    axiomize-sweep      parallel parameter sweeps / Monte Carlo
    axiomize-index-reports  build an index over produced reports

The skill documents (SKILL.md, adaptive-workflow.md, perspectives/, templates/)
ship inside the ``axiomize`` package for agent loaders.
"""

__version__ = "1.11.1"

# Initialize the public engine once. This installs the hardened parser/resource
# hooks into the legacy ``general_engine_core`` module before any caller can
# resolve ``axiomize.general_engine_core`` directly.
from axiomize import general_engine as _general_engine  # noqa: E402,F401
from axiomize.runtime_guard import install_general_engine_guards as _install_runtime_guards  # noqa: E402

_install_runtime_guards(_general_engine)
del _install_runtime_guards
