import pytest

from qtrust import exact
from qtrust.moments import Catalog
from qtrust.params import Params


def _groups(p):
    cat = Catalog.from_patch(p)
    return cat, [(i,) for i in range(p.n)] + [tuple(e) for e in p.edges] + [tuple(sorted(c)) for c in cat.clusters]


def test_lightcone_equals_full_exact_small_cone():
    from qtrust.conftest_free import chain_patch
    chain = chain_patch(10); prm = Params()
    cat = Catalog(10, [tuple(e) for e in chain.edges], [(0, 1, 2, 3), (3, 4, 5, 6), (6, 7, 8, 9)])
    groups = [(i,) for i in range(10)] + [tuple(e) for e in chain.edges] + list(cat.clusters)
    mu, sizes = exact.lightcone_moments(chain, prm, 1, groups)
    full = cat.from_patterns(exact.all_patterns(10), exact.probs(exact.trotter_states(chain, prm, [1])[1]))
    lc = cat.evaluate(mu)
    assert max(sizes.values()) < chain.n                  # the test is meaningful: the cone is a strict subset
    assert max(abs(lc[k] - v) for k, v in full.items()) < 1e-12


def test_lightcone_equals_full_exact_on_device_patch(patches):
    p = patches["P18"]; prm = Params()
    cat, groups = _groups(p)
    mu, sizes = exact.lightcone_moments(p, prm, 2, groups)
    full = cat.from_patterns(exact.all_patterns(p.n), exact.probs(exact.trotter_states(p, prm, [2])[2]))
    lc = cat.evaluate(mu)
    assert max(sizes.values()) < p.n
    assert max(abs(lc[k] - v) for k, v in full.items()) < 1e-12


def test_lightcone_refuses_oversized_cones(patches):
    p = patches["P40"]; cat, groups = _groups(p)
    with pytest.raises(MemoryError):
        exact.lightcone_moments(p, Params(), 7, groups, max_qubits=26)
