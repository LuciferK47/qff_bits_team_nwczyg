import pytest

from qtrust.classical import mps
from qtrust.moments import Catalog
from qtrust.params import Params
from test_pauli import exact_obs


def test_mps_exact_when_bond_large(tree7, ring6):
    prm = Params(); Ns = [0, 1, 3, 5]
    for patch in (tree7, ring6):
        ref = exact_obs(patch, prm, Ns)
        obs, _, stats = mps.run(patch, prm, Ns, chi=64, cutoff=0.0)
        for N in Ns:
            for k, v in ref[N].items():
                assert obs[N][k] == pytest.approx(v, abs=1e-8), (patch.pid, N, k)
        assert all(e < 1e-9 for e in stats["error_estimate"].values())


def test_mps_non_adjacent_cycle_bond_is_applied(ring6):
    """ring6 needs a long-range bond in any 1D ordering; dropping it would change the answer."""
    prm = Params()
    ref = exact_obs(ring6, prm, [4])[4]
    obs, *_ = mps.run(ring6, prm, [4], chi=64, cutoff=0.0)
    assert max(abs(obs[4][k] - v) for k, v in ref.items()) < 1e-8


def test_mps_truncation_is_visible(ring6):
    prm = Params(); ref = exact_obs(ring6, prm, [5])[5]
    obs, _, stats = mps.run(ring6, prm, [5], chi=2, cutoff=1e-14)
    err = max(abs(obs[5][k] - v) for k, v in ref.items())
    assert err > 1e-5 and stats["error_estimate"][5] > 1e-6      # discarded weight is reported


def test_observable_error_scales_like_sqrt_of_discarded_weight(ring6):
    """quimb's error_estimate (1 - F) is a WEIGHT; observables err ~ sqrt(weight). Never report 1-F as the
    observable error."""
    prm = Params(); ref = exact_obs(ring6, prm, [5])[5]
    for cutoff in (1e-14, 1e-10, 1e-6):
        obs, _, stats = mps.run(ring6, prm, [5], chi=64, cutoff=cutoff)
        err = max(abs(obs[5][k] - v) for k, v in ref.items())
        w = max(stats["error_estimate"][5], 1e-16)
        assert err <= 20 * w ** 0.5 + 1e-12


def test_mps_budget_exhaustion_flags_timeout(ring6):
    obs, _, stats = mps.run(ring6, Params(), [0, 2, 5], chi=16, budget_s=1e-9)
    assert stats["timed_out"] and stats["completed_N"] == [0]
