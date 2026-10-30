import itertools

import numpy as np
import pytest
from qiskit import transpile
from qiskit.quantum_info import Operator

from qtrust import mitigation as mit
from qtrust.bootstrap import bootstrap, resample_counts
from qtrust.circuits import count_rzz, trotter_circuit
from qtrust.moments import kappa_partition, parity_moments
from qtrust.params import Params

N = 4
SUBS = [t for r in range(1, 5) for t in itertools.combinations(range(N), r)]


def noisy(p, e0, e1):
    """Apply independent asymmetric readout noise to a probability vector (basis index bit i = qubit i)."""
    A = np.array([[1.0]])
    for i in range(N - 1, -1, -1):                        # qubit N-1 is the most significant index bit
        A = np.kron(A, np.array([[1 - e0[i], e1[i]], [e0[i], 1 - e1[i]]]))
    return A @ p, A


def true_dist(seed=0):
    rng = np.random.default_rng(seed)
    p = rng.dirichlet(np.ones(2 ** N) * 0.4)
    k = np.arange(2 ** N)
    p = p * np.exp(1.2 * (1 - 2 * (k & 1)))
    return p / p.sum()


def test_correction_is_exact_for_independent_readout_and_cumulant():
    rng = np.random.default_rng(1)
    e0, e1 = rng.uniform(0.005, 0.05, N), rng.uniform(0.01, 0.12, N)
    p = true_dist(); pn, _ = noisy(p, e0, e1)
    pats = np.arange(2 ** N, dtype=np.uint32)
    truth = parity_moments(pats, p, SUBS)
    meas = parity_moments(pats, pn, SUBS)
    corr = mit.correct_moments(meas, e0, e1, SUBS)
    assert max(abs(corr[S] - truth[S]) for S in SUBS) < 1e-12
    assert abs(meas[(0, 1, 2, 3)] - truth[(0, 1, 2, 3)]) > 1e-3                      # raw data really is biased
    assert kappa_partition(corr, (0, 1, 2, 3)) == pytest.approx(kappa_partition(truth, (0, 1, 2, 3)), abs=1e-12)


def test_matches_explicit_assignment_matrix_inversion():
    rng = np.random.default_rng(2)
    e0, e1 = rng.uniform(0.01, 0.06, N), rng.uniform(0.01, 0.1, N)
    p = true_dist(3); pn, A = noisy(p, e0, e1)
    pats = np.arange(2 ** N, dtype=np.uint32)
    via_matrix = parity_moments(pats, np.linalg.solve(A, pn), SUBS)
    via_moments = mit.correct_moments(parity_moments(pats, pn, SUBS), e0, e1, SUBS)
    assert max(abs(via_matrix[S] - via_moments[S]) for S in SUBS) < 1e-10


def test_corrected_values_are_not_clipped():
    mu = mit.correct_moments({(0,): 1.0}, [0.1], [0.1], [(0,)])                     # 1 / 0.8
    assert mu[(0,)] == pytest.approx(1.25)


def test_assignment_rates_recovered_from_calibration_shots():
    rng = np.random.default_rng(5); n = 6
    e0, e1 = rng.uniform(0.01, 0.04, n), rng.uniform(0.02, 0.1, n)
    preps = mit.calibration_preps(n, rng)
    assert all((preps[0] + preps[1] == 1).tolist()) and all((preps[2] + preps[3] == 1).tolist())
    cal = []
    for prep in preps:
        flips = np.where(prep == 0, rng.random((8192, n)) < e0, rng.random((8192, n)) < e1)
        out = (prep ^ flips.astype(int))
        keys = ["".join(map(str, row[::-1])) for row in out]
        cal.append({k: keys.count(k) for k in set(keys)})
    g0, g1 = mit.assignment_rates(cal, preps)
    assert np.allclose(g0, e0, atol=6 * np.sqrt(e0 * (1 - e0) / 16384) + 1e-3)
    assert np.allclose(g1, e1, atol=6 * np.sqrt(e1 * (1 - e1) / 16384) + 1e-3)


def test_flip_correlation_detects_correlated_readout():
    rng = np.random.default_rng(9); n = 3; shots = 20000
    preps = [np.array([0, 0, 0]), np.array([1, 1, 1]), np.array([0, 1, 0]), np.array([1, 0, 1])]
    def run(correlated):
        cal = []
        for prep in preps:
            f = rng.random((shots, n)) < 0.03
            if correlated:
                both = rng.random(shots) < 0.04
                f[:, 0] |= both; f[:, 1] |= both
            out = prep ^ f.astype(int)
            keys = ["".join(map(str, r[::-1])) for r in out]
            cal.append({k: keys.count(k) for k in set(keys)})
        return mit.readout_flip_correlations(cal, preps, [(0, 1), (1, 2)])
    ind, cor = run(False), run(True)
    assert abs(ind[(0, 1)]) < 4 and abs(ind[(1, 2)]) < 4
    assert cor[(0, 1)] > 10 and abs(cor[(1, 2)]) < 4


@pytest.mark.parametrize("k", [1, 2])
def test_fold_preserves_unitary_and_survives_compilation(tree7, k):
    prm = Params()
    base = trotter_circuit(tree7, prm, 2, measure=False)
    folded = mit.fold_circuit(base, k)
    assert Operator(folded).equiv(Operator(base))
    assert count_rzz(folded) == (2 * k + 1) * count_rzz(base)
    out = transpile(folded, basis_gates=["rzz", "rz", "ry", "rx", "sx", "x"], optimization_level=3)
    assert count_rzz(out) == (2 * k + 1) * count_rzz(base)                         # pairs NOT cancelled


def test_unfolded_pair_without_barriers_would_cancel(tree7):
    base = trotter_circuit(tree7, Params(), 1, measure=False)
    naive = base.compose(base.inverse()).compose(base)
    out = transpile(naive, basis_gates=["rzz", "rz", "ry", "rx", "sx", "x"], optimization_level=3)
    assert count_rzz(out) < 3 * count_rzz(base)                                    # why barriers matter


def test_zne_models():
    lam = [1, 3, 5]
    assert mit.zne_extrapolate(lam, [0.8 * np.exp(-0.05 * l) for l in lam], "exp") == pytest.approx(0.8, abs=1e-9)
    assert mit.zne_extrapolate(lam, [1 + 0.1 * l + 0.01 * l * l for l in lam], "richardson") == pytest.approx(1.0, abs=1e-9)
    assert mit.zne_extrapolate(lam, [1 - 0.1 * l for l in lam], "linear") == pytest.approx(1.0, abs=1e-9)
    assert np.isnan(mit.zne_extrapolate(lam, [0.1, -0.05, 0.02], "exp"))           # refuses a sign-changing "decay"


def test_resample_preserves_shots_and_support():
    rng = np.random.default_rng(0)
    c = {"00": 700, "11": 250, "01": 50}
    r = resample_counts(c, rng)
    assert sum(r.values()) == 1000 and set(r) <= set(c)


def test_bootstrap_interval_coverage_on_synthetic_experiment():
    """95% CI of an estimator that uses two noisy blocks (data + calibration) should cover the truth ~95%."""
    rng = np.random.default_rng(11)
    p_true, e = 0.30, 0.05                                # P(true bit = 1), readout flip probability
    covered, trials = 0, 120
    for _ in range(trials):
        shots = 600
        pm = p_true * (1 - e) + (1 - p_true) * e
        data = {"run": {"1": int(rng.binomial(shots, pm)), "0": 0}, "cal": {"1": int(rng.binomial(shots, 1 - e)), "0": 0}}
        data["run"]["0"] = shots - data["run"]["1"]; data["cal"]["0"] = shots - data["cal"]["1"]
        def pipe(d):
            ev = d["cal"]["1"] / (d["cal"]["1"] + d["cal"]["0"]) if d["cal"] else 0
            m = d["run"]["1"] / (d["run"]["1"] + d["run"]["0"])
            return {"p": (m - (1 - ev)) / (2 * ev - 1)}                              # symmetric-flip correction
        bs = bootstrap(data, lambda d: pipe({k: {kk: vv for kk, vv in v.items()} for k, v in d.items()}), B=150,
                       seed=int(rng.integers(1 << 30)))
        covered += bs["p"]["lo"] <= p_true <= bs["p"]["hi"]
    assert 0.88 <= covered / trials <= 1.0


def _noisy_counts(prep, flips_fn, rng, shots=20000):
    f = flips_fn(prep, rng, shots)
    out = prep ^ f.astype(int)
    keys = ["".join(map(str, r[::-1])) for r in out]
    return {k: keys.count(k) for k in set(keys)}


def test_structured_preps_cover_all_pair_states_and_balance_each_qubit():
    from qtrust.mitigation import structured_preps
    edges = [(0, 1), (1, 2), (2, 3), (1, 4)]
    preps = structured_preps(edges, 5)
    for q in range(5):
        assert sorted(int(p[q]) for p in preps) == [0, 0, 1, 1]
    for a, b in edges:
        assert {(int(p[a]), int(p[b])) for p in preps} == {(0, 0), (1, 1), (0, 1), (1, 0)}


def test_pair_joint_correction_recovers_truth_when_readout_is_correlated():
    from qtrust.mitigation import (assignment_rates, correct_pair_joint, independence_residual,
                                   pair_assignment_matrix, structured_preps, correct_moments)
    rng = np.random.default_rng(4)
    edges = [(0, 1), (1, 2)]; n = 3

    def flips(prep, rng, shots):
        f = rng.random((shots, n)) < 0.02
        both = rng.random(shots) < 0.06                       # qubits 0 and 1 flip TOGETHER
        f[:, 0] |= both; f[:, 1] |= both
        return f

    preps = structured_preps(edges, n)
    cal = [_noisy_counts(p, flips, rng, 60000) for p in preps]
    A = pair_assignment_matrix(cal, preps, 0, 1)
    e0, e1 = assignment_rates(cal, preps)
    assert independence_residual(A, e0, e1, 0, 1) > 0.02            # the independence gate sees the correlation
    # true state: both qubits |1> (z = -1, -1): mu(0) = mu(1) = -1, mu(01) = +1
    truth = np.array([1, 1, 0])
    run = _noisy_counts(truth, flips, rng, 60000)
    joint = correct_pair_joint(run, 0, 1, A)
    assert joint[(0,)] == pytest.approx(-1.0, abs=0.02) and joint[(0, 1)] == pytest.approx(1.0, abs=0.02)
    pats, w = counts_to_patterns(run, n)
    from qtrust.moments import parity_moments
    ind = correct_moments(parity_moments(pats, w, [(0,), (1,), (0, 1)]), e0, e1, [(0,), (1,), (0, 1)])
    assert abs(ind[(0, 1)] - 1.0) > 0.05                              # independent correction is wrong here


def test_independent_readout_gives_small_residual():
    from qtrust.mitigation import assignment_rates, independence_residual, pair_assignment_matrix, structured_preps
    rng = np.random.default_rng(6); n = 3; edges = [(0, 1), (1, 2)]
    flips = lambda prep, rng, shots: rng.random((shots, n)) < np.array([0.02, 0.05, 0.03])
    preps = structured_preps(edges, n)
    cal = [_noisy_counts(p, flips, rng, 80000) for p in preps]
    A = pair_assignment_matrix(cal, preps, 0, 1); e0, e1 = assignment_rates(cal, preps)
    assert independence_residual(A, e0, e1, 0, 1) < 0.01


from qtrust.moments import counts_to_patterns  # noqa: E402
