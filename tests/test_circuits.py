import numpy as np
import pytest
import scipy.linalg as sl
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator, Statevector
from qiskit_aer import AerSimulator

from qtrust import exact
from qtrust.circuits import _bonds, _field, count_rzz, trotter_circuit
from qtrust.moments import Catalog, counts_to_patterns, parity_moments
from qtrust.params import Params

X = np.array([[0, 1], [1, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)
ZZ = np.diag([1, -1, -1, 1]).astype(complex)


@pytest.mark.parametrize("hx", [1.25, -1.25])
@pytest.mark.parametrize("hz", [-0.6, 0.6])
@pytest.mark.parametrize("tau", [0.05, 0.1, 0.37])
def test_field_unitary_is_exact_for_both_signs(hx, hz, tau):
    prm = Params(hx=hx, hz=hz)
    qc = QuantumCircuit(1); _field(qc, tau, prm)
    # F(tau) = exp(-i H_f tau) with H_f = -(hx X + hz Z)
    want = sl.expm(-1j * tau * (-(hx * X + hz * Z)))
    assert np.allclose(Operator(qc).data, want, atol=1e-12)
    # flipping either sign must be detected
    for bad in (Params(hx=-hx, hz=hz), Params(hx=hx, hz=-hz)):
        qb = QuantumCircuit(1); _field(qb, tau, bad)
        assert not np.allclose(Operator(qb).data, want, atol=1e-3)


def test_bond_sign_two_qubits(tiny=None):
    from conftest import tiny_patch
    p = tiny_patch(2, [(0, 1)]); prm = Params()
    qc = QuantumCircuit(2); _bonds(qc, p, prm)
    want = sl.expm(-1j * prm.dt * (-prm.J * ZZ))          # exp(-i H_b dt), H_b = -J ZZ
    assert np.allclose(Operator(qc).data, want, atol=1e-12)
    wrong = sl.expm(-1j * prm.dt * (prm.J * ZZ))
    assert not np.allclose(Operator(qc).data, wrong, atol=1e-3)


@pytest.mark.parametrize("N", [0, 1, 2, 5])
def test_circuit_matches_independent_kernel(tree7, N):
    prm = Params()
    sv = Statevector(trotter_circuit(tree7, prm, N, measure=False)).data
    ref = exact.trotter_states(tree7, prm, [N])[N]
    assert np.allclose(sv, ref, atol=1e-10)


def test_aer_matches_kernel(ring6):
    prm = Params()
    qc = trotter_circuit(ring6, prm, 4, measure=False); qc.save_statevector()
    sv = np.asarray(AerSimulator(method="statevector").run(qc).result().get_statevector())
    assert np.allclose(sv, exact.trotter_states(ring6, prm, [4])[4], atol=1e-10)


def test_merged_halves_equal_unmerged_S_power(tree7):
    prm = Params(); n = tree7.n
    z = exact._zarr(n).astype(float)
    zz = sum(z[a] * z[b] for a, b in tree7.edges)
    B = np.exp(1j * prm.J * prm.dt * zz)
    Fh = exact._field_matrix(prm.dt / 2, prm)
    psi = np.zeros(2 ** n, complex); psi[0] = 1
    for _ in range(3):                                   # S^3 with S = F(h) B F(h), no merging
        psi = exact._apply_all(exact._apply_all(psi, n, Fh) * B, n, Fh)
    assert np.allclose(psi, exact.trotter_states(tree7, prm, [3])[3], atol=1e-12)


def test_inverse_returns_initial_state(tree7):
    qc = trotter_circuit(tree7, Params(), 4, measure=False)
    both = qc.compose(qc.inverse())
    sv = Statevector(both).data
    assert abs(sv[0]) == pytest.approx(1.0, abs=1e-12)


def test_zero_steps_is_identity_and_observables(star4):
    qc = trotter_circuit(star4, Params(), 0, measure=False)
    assert qc.size() == 0
    cat = Catalog.from_patch(star4)
    p = exact.probs(exact.trotter_states(star4, Params(), [0])[0])
    obs = cat.from_patterns(exact.all_patterns(4), p)
    assert all(obs[("m", (i,))] == pytest.approx(1) for i in range(4))
    assert obs[("M", ())] == pytest.approx(1)
    assert obs[("G", (0, 1, 2, 3))] == pytest.approx(1)
    assert all(obs[("C", e)] == pytest.approx(0, abs=1e-14) for e in star4.edges)
    assert obs[("kappa", (0, 1, 2, 3))] == pytest.approx(0, abs=1e-14)


def test_bit_order_qiskit_little_endian():
    qc = QuantumCircuit(4, 4); qc.x(3); qc.measure(range(4), range(4))
    counts = AerSimulator().run(qc, shots=50).result().get_counts()
    assert list(counts) == ["1000"]                       # qubit 3 is the LEFT-most character
    pats, w = counts_to_patterns(counts, 4)
    mu = parity_moments(pats, w, [(i,) for i in range(4)])
    assert [mu[(i,)] for i in range(4)] == [1, 1, 1, -1]


def test_rzz_count_and_layers(patches):
    for p in patches.values():
        qc = trotter_circuit(p, Params(), 3, measure=False)
        assert count_rzz(qc) == 3 * len(p.edges)
        for layer in set(p.colours.values()):
            qs = [q for e, c in p.colours.items() if c == layer for q in e]
            assert len(qs) == len(set(qs))                # disjoint within a layer


def test_second_order_error_scaling(tree7):
    prm = Params(); Jt = 2.0
    ref = exact.probs(exact.continuous_states(tree7, prm, [Jt])[Jt])
    z = exact._zarr(tree7.n).astype(float)
    def merr(dt):
        pr = prm.with_dt(dt); N = pr.steps(Jt)
        p = exact.probs(exact.trotter_states(tree7, pr, [N])[N])
        return np.max(np.abs(z @ p - z @ ref))
    e1, e2 = merr(0.2), merr(0.1)
    assert e1 < 0.02 and e2 < e1 / 2.5                    # error falls ~4x when dt is halved


def test_tiny_dt_recovers_continuous_time(tree7):
    prm = Params(dt=0.01); Jt = 1.0
    a = exact.trotter_states(tree7, prm, [prm.steps(Jt)])[prm.steps(Jt)]
    b = exact.continuous_states(tree7, prm, [Jt])[Jt]
    assert np.allclose(a, b, atol=2e-4)


def test_hamiltonian_hermitian_and_norm(tree7):
    H = exact.hamiltonian(tree7, Params())
    assert abs(H - H.T.conj()).max() < 1e-14
    psi = exact.continuous_states(tree7, Params(), [3.0])[3.0]
    assert np.linalg.norm(psi) == pytest.approx(1.0, abs=1e-10)


def test_hz_reversal_changes_dynamics(tree7):
    z = exact._zarr(tree7.n).astype(float)
    def M(hz):
        pr = Params(hz=hz); N = pr.steps(2.0)
        return float((z @ exact.probs(exact.trotter_states(tree7, pr, [N])[N])).mean())
    assert abs(M(-0.6) - M(0.6)) > 0.01


def test_frozen_dt_is_consistent_between_config_and_defaults():
    from pathlib import Path
    from qtrust.params import load_params
    cfg = load_params(Path(__file__).resolve().parents[1] / "configs/heavy_hex.yaml")
    assert cfg.dt == Params().dt == 0.10
    assert Params().steps(3.0) == 30


def test_symmetry_sectors_block_diagonalise_the_hz0_floquet_unitary():
    import numpy as np
    from qtrust.conftest_free import chain_patch
    from qtrust.validate import floquet_unitary, symmetry_sector_basis
    n = 6
    U = floquet_unitary(chain_patch(n), Params(hz=0.0, dt=0.2))
    tot, eigs = 0, []
    for a in (1, -1):
        for b in (1, -1):
            B = symmetry_sector_basis(n, a, b)
            assert np.allclose(B.T @ B, np.eye(B.shape[1]), atol=1e-12)             # orthonormal
            assert np.allclose(U @ B, B @ (B.T @ U @ B), atol=1e-10)               # sector is invariant under U
            tot += B.shape[1]; eigs.append(np.linalg.eigvals(B.T @ U @ B))
    assert tot == 2 ** n
    full = np.sort(np.angle(np.linalg.eigvals(U))); sec = np.sort(np.angle(np.concatenate(eigs)))
    assert np.allclose(full, sec, atol=1e-8)                                         # union of sectors = full spectrum
