import itertools

import numpy as np
import pytest

from qtrust.moments import Catalog, kappa_central, kappa_partition, parity_moments


def synthetic(seed=0, n=4, bias=1.5):
    rng = np.random.default_rng(seed)
    p = rng.dirichlet(np.ones(2 ** n) * 0.4)
    k = np.arange(2 ** n)
    p = p * np.exp(bias * (1 - 2 * (k & 1)))            # bias the means away from zero
    return k.astype(np.uint32), p / p.sum()


def direct_kappa(pats, p, S):
    z = {i: 1 - 2 * ((pats >> i) & 1).astype(float) for i in S}
    m = {i: float(p @ z[i]) for i in S}
    dz = {i: z[i] - m[i] for i in S}
    a, b, c, d = S
    C = lambda i, j: float(p @ (dz[i] * dz[j]))
    return float(p @ (dz[a] * dz[b] * dz[c] * dz[d])) - C(a, b) * C(c, d) - C(a, c) * C(b, d) - C(a, d) * C(b, c)


@pytest.mark.parametrize("seed", range(5))
def test_two_kappa_implementations_match_direct(seed):
    pats, p = synthetic(seed)
    S = (0, 1, 2, 3)
    mu = parity_moments(pats, p, [t for r in range(1, 5) for t in itertools.combinations(S, r)])
    ref = direct_kappa(pats, p, S)
    assert kappa_partition(mu, S) == pytest.approx(ref, abs=1e-12)
    assert kappa_central(mu, S) == pytest.approx(ref, abs=1e-12)


def test_missing_triples_would_give_wrong_cumulant():
    """Documented pitfall: G - C C ... without triple moments is NOT the connected cumulant when means != 0."""
    pats, p = synthetic(1)
    S = (0, 1, 2, 3)
    mu = parity_moments(pats, p, [t for r in range(1, 5) for t in itertools.combinations(S, r)])
    m = [mu[(i,)] for i in S]
    C = lambda i, j: mu[(i, j)] - m[i] * m[j]
    naive = mu[S] - C(0, 1) * C(2, 3) - C(0, 2) * C(1, 3) - C(0, 3) * C(1, 2)
    assert abs(naive - kappa_partition(mu, S)) > 1e-2
    assert abs(m[0]) > 0.3                               # the means really are far from zero


def test_independent_bits_have_zero_cumulants():
    n = 4; q = np.array([0.9, 0.7, 0.55, 0.8])           # P(bit = 0) per site
    k = np.arange(2 ** n, dtype=np.uint32)
    p = np.ones(2 ** n)
    for i in range(n):
        p = p * np.where((k >> i) & 1, 1 - q[i], q[i])
    mu = parity_moments(k, p, [t for r in range(1, 5) for t in itertools.combinations(range(n), r)])
    assert kappa_partition(mu, (0, 1, 2, 3)) == pytest.approx(0, abs=1e-14)
    assert mu[(0, 1)] - mu[(0,)] * mu[(1,)] == pytest.approx(0, abs=1e-14)


def test_sample_estimate_close_to_exact():
    pats, p = synthetic(3)
    S = (0, 1, 2, 3)
    rng = np.random.default_rng(7)
    shots = 4_000_000
    c = np.bincount(rng.choice(len(p), size=shots, p=p), minlength=len(p)) / shots
    subs = [t for r in range(1, 5) for t in itertools.combinations(S, r)]
    ex = kappa_partition(parity_moments(pats, p, subs), S)
    est = kappa_partition(parity_moments(pats, c, subs), S)
    assert est == pytest.approx(ex, abs=0.01)


def test_catalog_needs_all_fifteen_subsets(star4):
    cat = Catalog.from_patch(star4)
    S = cat.clusters[0]
    subs = cat.subsets()
    assert all(t in subs for r in range(1, 5) for t in itertools.combinations(S, r))
    assert len([t for t in subs if set(t) <= set(S)]) >= 15
