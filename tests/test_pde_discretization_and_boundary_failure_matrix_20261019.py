"""Direct method-of-lines PDE tests with physical boundary and failure checks."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from axiomize import advanced_family_engine as native
from axiomize.model_ir import ModelFamily, ModelIR
from axiomize.scientific_stress import _models


def pde(config=None, equation=None):
    payload = _models()[ModelFamily.PDE].to_dict()
    values = payload["metadata"]["pde"]
    if config is not None:
        values.update(config)
    if equation is not None:
        payload["equations"] = [{"target": "u", "expression": equation, "kind": "derivative"}]
    return ModelIR.from_dict(payload)


def simulate(m):
    return native._simulate_pde(m, t_span=(0.0, 0.2), points=7,
                                parameter_overrides=None, seed=15)


def test_true_native_pde_solver_preserves_grid_shape_and_finiteness():
    result = simulate(pde())
    assert result["status"] == "PASS"
    values = np.asarray(result["states"]["u"])
    assert values.shape == (7, 10)
    assert np.isfinite(values).all()
    assert result["diagnostics"]["finite"] is True
    assert result["solver"]["spatial_method"] == "method_of_lines"


def test_diffusion_with_spatially_constant_profile_has_no_artificial_gradient():
    model = pde(config={"initial_profiles": {"u": [3.0] * 10},
                        "diffusion": {"u": 0.3}}, equation="0")
    result = simulate(model)
    assert result["status"] == "PASS"
    np.testing.assert_allclose(result["states"]["u"][-1], np.full(10, 3.0), atol=1e-6)


@pytest.mark.parametrize("profile", [
    {"u": "1+x"},
    {"u": [float(i) for i in range(10)]},
])
def test_spatial_initial_profile_is_evaluated_on_actual_grid(profile):
    result = simulate(pde(config={
        "initial_profiles": profile, "diffusion": 0.0,
        "advection": 0.0,
    }, equation="0"))
    assert result["status"] == "PASS"
    expected = 1.0 + np.linspace(0, 1, 10) if isinstance(profile["u"], str) else np.arange(10)
    np.testing.assert_allclose(result["states"]["u"][0], expected)


@pytest.mark.parametrize("config", [
    {"diffusion": 0.3, "advection": 0.2},
    {"diffusion": "k", "advection": {"u": "k"}},
    {"diffusion": {"u": 0.4}, "advection": {"u": 0.2}},
])
def test_real_advection_and_diffusion_are_independently_supported(config):
    result = simulate(pde(config=config))
    assert result["status"] == "PASS", result
    assert np.isfinite(result["states"]["u"]).all()


@pytest.mark.parametrize("side", ["left", "right"])
def test_dirichlet_boundary_stays_fixed_at_declared_physical_value(side):
    model = pde(config={
        "diffusion": 0.3, "initial_profiles": {"u": "1+x"},
        "boundary_conditions": {
            "u": {side: {"type": "dirichlet", "value": 5.0}}
        },
    }, equation="0")
    result = simulate(model)
    assert result["status"] == "PASS"
    index = 0 if side == "left" else -1
    assert np.asarray(result["states"]["u"])[:, index] == pytest.approx(np.full(7, 5.0))


def test_periodic_boundary_with_advection_is_finite_and_preserves_constant_field():
    cfg = {"initial_profiles": {"u": [2.0] * 10}, "diffusion": 0.3,
           "advection": 0.4,
           "boundary_conditions": {
               "u": {"left": {"type": "periodic"}, "right": {"type": "periodic"}}
           }}
    result = simulate(pde(config=cfg, equation="0"))
    assert result["status"] == "PASS"
    np.testing.assert_allclose(np.asarray(result["states"]["u"]), 2.0, atol=1e-6)


@pytest.mark.parametrize("bad, fragment", [
    ({"grid_points": 4}, "grid_points must be"),
    ({"grid_points": 4097}, "grid_points must be"),
    ({"space_span": "bad"}, "space_span must"),
    ({"space_span": [1, 0]}, "finite and increasing"),
    ({"space_span": [0, float("inf")]}, "finite and increasing"),
    ({"initial_profiles": []}, "initial_profiles must be an object"),
    ({"initial_profiles": {"u": [1.0, 2.0]}}, "grid length"),
    ({"diffusion": []}, "diffusion must"),
    ({"advection": []}, "advection must"),
])
def test_unphysical_or_unbounded_pde_discretization_is_rejected(bad,fragment):
    with pytest.raises(ValueError,match=fragment):
        simulate(pde(config=bad))


def test_time_reversal_is_not_accepted_for_forward_pde_solver():
    with pytest.raises(ValueError,match="t_span must be increasing"):
        native._simulate_pde(pde(),t_span=(1.0,0.0),points=7,
                             parameter_overrides=None,seed=15)


@pytest.mark.parametrize("mode",["refused","nonfinite","exception"])
def test_failed_native_solver_does_not_forge_pde_pass(monkeypatch,mode):
    import scipy.integrate

    def broken(*args, **kwargs):
        if mode == "exception":
            raise RuntimeError("backend refused input")
        if mode == "nonfinite":
            return SimpleNamespace(success=True,message="non-finite",y=np.array([[np.nan]]))
        return SimpleNamespace(success=False,message="native convergence refused",y=np.array([[1.0]]))

    monkeypatch.setattr(scipy.integrate,"solve_ivp",broken)
    result = simulate(pde())
    assert result["status"] == "FAIL"
    assert result["stage"] == "pde_solve"
    assert len(result["solver_attempts"]) == 3


def test_pde_solver_tries_stiff_alternative_after_first_refusal(monkeypatch):
    import scipy.integrate

    actual=scipy.integrate.solve_ivp
    seen=[]

    def override(*args, **kwargs):
        seen.append(kwargs["method"])
        if kwargs["method"] == "BDF":
            return SimpleNamespace(success=False,message="nonconvergent",y=np.array([[1.0]]))
        return actual(*args,**kwargs)

    monkeypatch.setattr(scipy.integrate,"solve_ivp",override)
    result=simulate(pde())
    assert result["status"] == "PASS"
    assert seen[:2] == ["BDF","Radau"]
    assert result["solver"]["method"] == "Radau"
