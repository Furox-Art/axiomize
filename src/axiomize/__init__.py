"""Axiomize: rigorous first-principles modeling skill pack.

Turns a vague idea into formal mathematics: sub-problem decomposition,
parameter tables with units, models from 15+ mathematical perspectives,
honest comparison, runnable validation, and falsifiable predictions.

CLI entry points installed with the package::

    axiomize-validate   deterministic/stochastic/queue model validators
    axiomize-fit        calibrate SIR / logistic models to CSV data
    axiomize-csv-check  data-quality pre-check before calibrating
    axiomize-benchmark  grade modeling reports against benchmark cases
    axiomize-to-latex   convert a modeling report to compilable LaTeX
    axiomize-sweep      parallel parameter sweeps / Monte Carlo
    axiomize-index-reports  build an index over produced reports

The skill documents (SKILL.md, perspectives/, templates/) ship inside the
``axiomize`` package for agent loaders; browse them with
``import axiomize, pathlib; pathlib.Path(axiomize.__file__).parent``.
"""

__version__ = "1.6.0"
