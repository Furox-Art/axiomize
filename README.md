# Axiomize  
  
Current package line: **1.12.3**  
  
![License](https://img.shields.io/badge/license-MIT-blue)  
![Python](https://img.shields.io/badge/python-3.10%2B-informational)  
![CI](https://github.com/Furox-Art/axiomize/actions/workflows/ci.yml/badge.svg)  
[![PyPI](https://img.shields.io/pypi/v/axiomize)](https://pypi.org/project/axiomize/)  
[![npm](https://img.shields.io/npm/v/axiomize)](https://www.npmjs.com/package/axiomize)  
[![Downloads](https://img.shields.io/pypi/dm/axiomize)](https://pypi.org/project/axiomize/)  
  
I got tired of scientific models that live in Jupyter notebooks and die there.  
  
You know the pattern: someone writes a beautiful simulation, it works on their machine, they graduate or change jobs, and six months later nobody can run it. The dependencies are broken, the data is missing, and the "documentation" is a 47-cell notebook with no explanation.  
  
Axiomize is my attempt to fix that. It forces you to write models as explicit, versioned, testable code-not as exploratory spaghetti. Every assumption is written down. Every parameter has units. Every result can be reproduced by someone else, on a different machine, years later.  
  
## Quick Start

```bash
pip install axiomize
```

```python
from axiomize import Model

m = Model.from_yaml("seir_model.yaml")   # explicit, versioned model IR
m.fit(observed_data, uncertainty=True)   # calibrated, with CIs
m.validate(holdout=validation_set)       # pass/fail against held-out data
m.export("v1.2.0/")                     # reproducible provenance bundle
```

CLI, REST, and MCP surfaces included: `axiomize serve`, `axiomize fit`, `axiomize validate`. Also on npm: `npm i axiomize`.

## What it actually does  
  
- Turns vague ideas into explicit mathematical models with real constraints  
- Validates dimensional consistency (no more adding meters to seconds)  
- Runs sensitivity analysis so you know which parameters actually matter  
- Exports to LaTeX, PDF, and portable formats that don't require Python  
- Keeps a full audit trail so you can prove what you did and why  
  
## Common modeling use cases

- Turn a vague scientific idea into an explicit **mathematical model** with assumptions and constraints.
- Perform **parameter estimation, calibration, sensitivity analysis, and uncertainty quantification**.
- Compare alternative model families and document why one formulation was selected.
- Build reproducible **causal inference, Bayesian inference, finite-element, and dynamical-system** workflows.
- Produce auditable model artifacts for research, engineering, and scientific review.

## Quick start  
  
```bash  
pip install axiomize  
# or  
npx axiomize  
```  
  
## Why I built this  
  
I was reviewing a paper last year and the authors claimed their model predicted some chemical reaction yield within 2%. I spent three days trying to reproduce it. The code was a mess of global variables, the data wasn't available, and when I finally got it running, the answer was off by 40%.  
  
That shouldn't be normal. Science should be checkable.  
  
## License  
  
MIT. Use it, break it, fix it. 

