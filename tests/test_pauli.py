import numpy as np
import pytest

from qtrust import exact
from qtrust.classical import pauli
from qtrust.moments import Catalog
from qtrust.params import Params


def exact_obs(patch, prm, Ns):
    cat = Catalog.from_patch(patch)
    return {N: cat.from_patterns(exact.all_patterns(patch.n), exact.probs(psi))
            for N, psi in exact.iter_trotter_states(patch, prm, Ns)}


def test_untruncated_pauli_propagation_is_exact_on_small_tree(tree7):
    prm = Params(); Ns = [0, 1, 2, 4]
    ref = exact_obs(tree7, prm, Ns)
    huge = pauli.PauliSetting("exact", 10 ** 7, 0.0)
    obs, _, stats = pauli.run(tree7, prm, Ns, huge, workers=2)
    for N in Ns:
        for k, v in ref[N].items():
            assert obs[N][k] == pytest.approx(v, abs=1e-9), (N, k)
    assert not any(stats["cap_hit"].values())


def test_truncation_reports_loss_and_degrades_gracefully(tree7):
    prm = Params(); Ns = [4]
    ref = exact_obs(tree7, prm, Ns)[4]
    tight = pauli.PauliSetting("tight", 8, 1e-2)
    obs, _, stats = pauli.run(tree7, prm, Ns, tight, workers=2)
    assert stats["max_truncated_l1"][4] > 0 and stats["cap_hit"][4]
    err = max(abs(obs[4][k] - v) for k, v in ref.items())
    assert err > 1e-6                                     # truncation is visible, not silently exact


def test_z_string_ordering_matches_qiskit_little_endian():
    op = pauli.z_string(4, (3,))
    assert op.paulis[0].to_label() == "ZIII"


def test_budget_exhaustion_returns_only_completed_times_and_flags_timeout(tree7):
    prm = Params()
    obs, _, stats = pauli.run(tree7, prm, [0, 2, 5], pauli.PauliSetting("t", 10 ** 6, 0.0), workers=2, budget_s=0.0)
    assert stats["timed_out"] and stats["completed_N"] == [0] and list(obs) == [0]
