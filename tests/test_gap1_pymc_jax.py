"""GAP-1: PyMC/JAX gercek availability durumu (canli probe).

Kurulu degilse TOOL_UNAVAILABLE beklenir ve sahte sonuc uretilmemeli;
kuruluysa gercek fit yolu calismali. Tum iddialar canli
``importlib.util.find_spec`` ile karsilastirilir, hardcode False yok.
"""

from __future__ import annotations

import importlib.util

import pytest


def _spec_present(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def test_pymc_probe_matches_reality():
    from axiomize.bayesian.pymc_tool import PyMCTool

    meta = PyMCTool.availability()
    assert meta.available == _spec_present("pymc")
    if meta.available:
        assert isinstance(meta.version, str) and meta.version
    else:
        assert isinstance(meta.reason, str) and meta.reason


def test_pymc_execute_never_fakes():
    from axiomize.bayesian.pymc_tool import PyMCTool

    tool = PyMCTool()
    # Girdi dogrulama availability'den once calisir.
    with pytest.raises(ValueError):
        tool.execute({})
    if not _spec_present("pymc"):
        with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
            tool.execute({"model": "normal-mean"})
    else:
        # Kuruluysa TOOL_UNAVAILABLE denmemeli, veri verilmeden de
        # uydurulmamali: y yoksa acik ValueError.
        with pytest.raises(ValueError):
            tool.execute({"model": "normal-mean"})
        out = tool.execute({"model": "normal-mean", "y": [1.0, 2.0, 3.0],
                            "draws": 200, "tune": 200, "seed": 0})
        assert isinstance(out, dict)
        assert "posterior_mean" in out


def test_pymc_real_fit_when_installed():
    if not _spec_present("pymc"):
        pytest.skip("pymc kurulu degil; TOOL_UNAVAILABLE yolu gecerli")
    import numpy as np

    from axiomize.bayesian.pymc_tool import PyMCTool

    tool = PyMCTool()
    assert PyMCTool.availability().available is True
    rng = np.random.default_rng(7)
    y = rng.normal(5.0, 1.0, size=50)
    out = tool.execute({"model": "normal-mean", "y": y.tolist(),
                        "sigma": 1.0, "draws": 300, "tune": 300, "seed": 0})
    assert out["model"] == "normal-mean"
    assert abs(out["posterior_mean"] - 5.0) < 0.3
    lo, hi = out["ci95"]
    assert lo < 5.0 < hi
    assert out["status"] in ("PASS", "WARNING")
    if isinstance(out["r_hat"], float):
        assert out["r_hat"] < 1.05


def test_jax_real_grad_when_installed():
    if not _spec_present("jax"):
        pytest.skip("jax kurulu degil; capabilities False yolu gecerli")
    import jax

    grad = jax.grad(lambda x: x ** 2 + 2 * x)
    assert float(grad(3.0)) == pytest.approx(8.0)


def test_jax_capabilities_honest():
    from axiomize.capabilities import get_capabilities

    caps = get_capabilities()
    assert caps["automatic_differentiation"] == _spec_present("jax")
    assert caps["bayesian_inference"] == _spec_present("pymc")
    assert caps["bayesian_builtin_mh"] is True
    torch_present = _spec_present("torch")
    assert caps["gpu"] == (torch_present or _spec_present("jax"))


def test_router_no_fake_success_without_pymc_jax():
    from axiomize.routing.router import classify

    decision = classify({"signals": ["bayesian"]})
    d = decision.to_dict()
    if not _spec_present("pymc"):
        assert "pymc" not in d["primary_tools"]
        assert any("pymc:TOOL_UNAVAILABLE" in a for a in d["alternatives"])
        assert d["status"] in ("TOOL_UNAVAILABLE", "WARNING")
    # Router jax basarisi iddia etmemeli (jax kurali yok, PASS sahte olurdu).
    assert not (d["status"] == "PASS" and "pymc" in d["primary_tools"]
                and not _spec_present("pymc"))


def test_builtin_mh_fallback_works():
    import numpy as np

    from axiomize.bayesian.mh import normal_mean_posterior

    rng = np.random.default_rng(1)
    y = rng.normal(5.0, 1.0, size=50)
    post = normal_mean_posterior(y, sigma=1.0, n_samples=4000,
                                 burn=1000, seed=0)
    assert abs(post["mean"] - 5.0) < 0.25
    lo, hi = post["ci95"]
    assert lo < 5.0 < hi
