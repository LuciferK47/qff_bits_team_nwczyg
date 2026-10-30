import numpy as np
import pytest

from qtrust import rehearsal as R


def _synthetic(held_bias=0.0, exp_nan_rate=0.0, n_keys=40):
    """Point estimates for three ZNE models at calibration N=4,10 and held-out N=8. linear is best on calibration."""
    rng = np.random.default_rng(0)
    ref = {N: {("m", (i,)): float(rng.uniform(-1, 1)) for i in range(n_keys)} for N in (4, 8, 10)}
    point = {}
    for N in (4, 8, 10):
        for i in range(n_keys):
            key = ("m", (i,)); t = ref[N][key]
            point[("zne_linear", N, key)] = t + 0.01 + (held_bias if N == 8 else 0.0)
            point[("zne_richardson", N, key)] = t + 0.05
            nan = rng.random() < exp_nan_rate
            point[("zne_exp", N, key)] = float("nan") if nan else t + 0.03
    return point, ref


def test_model_selection_uses_only_calibration_times():
    point, ref = _synthetic()
    m1, _ = R.select_model(point, ref, {4, 10})
    point2, _ = _synthetic(held_bias=5.0)                     # wreck the held-out time only
    m2, _ = R.select_model(point2, ref, {4, 10})
    assert m1 == m2 == "linear"


def test_model_with_frequent_fit_failures_is_disqualified():
    point, ref = _synthetic(exp_nan_rate=0.5)
    for k in point:                                            # make exp the best fit where it exists
        if k[0] == "zne_exp" and np.isfinite(point[k]):
            point[k] = ref[k[1]][k[2]]
    m, table = R.select_model(point, ref, {4, 10})
    assert table["exp"]["failure_rate"] > R.MAX_FIT_FAILURE_RATE and m != "exp"


def test_no_model_qualifies_returns_none():
    point = {("zne_exp", 4, ("m", (0,))): float("nan"), ("zne_linear", 4, ("m", (0,))): float("nan"),
             ("zne_richardson", 4, ("m", (0,))): float("nan")}
    m, _ = R.select_model(point, {4: {("m", (0,)): 0.1}}, {4})
    assert m is None


def test_correlated_readout_control_trips_only_on_injected_edge(patches):
    from qiskit_ibm_runtime.fake_provider import FakeFez
    ctl = R.correlated_readout_control(patches["P12"], FakeFez())
    assert ctl["trips_on_injected_edge"] and ctl["others_quiet"] and not ctl["passed"]


def test_rehearsal_smoke_end_to_end_small(patches, tmp_path):
    """Tiny but complete run: collect -> select (calibration times only) -> bootstrap -> multi-gate trust."""
    from qiskit_ibm_runtime.fake_provider import FakeFez
    from qtrust.params import Params
    df, info = R.run_rehearsal(patches["P12"], Params(dt=0.1), FakeFez(), tmp_path, variant="cz", Jts=(0.0, 0.1, 0.2, 0.4),
                               zne_Jts=(0.1, 0.2, 0.4), cal_Jts=(0.1, 0.4), heldout_Jt=0.2, zne_k=(1, 2),
                               shots=2048, cal_shots=1024, B=12)
    assert set(df.source) == {R.LABEL} and "supported" not in set(df.trust_status_simulated)      # never a hardware verdict
    assert {"raw", "readout", "zne_linear", "zne_richardson", "zne_exp"} <= set(df.method)
    assert set(df[df.zne_role == "heldout"].Jt) == {0.2} and 0.2 not in set(df[df.zne_role == "calibration"].Jt)
    assert info["selected_model"] in R.MODELS or info["selected_model"] is None
    bad = df[~np.isfinite(df.estimate)]
    assert set(bad.trust_status_simulated) <= {"mitigation_failed", "no_reference"}
    assert df.valid_fraction.between(0, 1).all() and (df.B == 12).all()


def test_inject_pair_flips_preserves_shots_and_flips_both_bits():
    rng = np.random.default_rng(0)
    out = R.inject_pair_flips({"0000": 10000}, 0, 2, 0.3, rng)
    assert sum(out.values()) == 10000 and set(out) == {"0000", "0101"}          # bits 0 and 2 flip together
    assert abs(out["0101"] / 10000 - 0.3) < 0.02
    assert R.inject_pair_flips({"0000": 100}, 0, 2, 0.0, rng) == {"0000": 100}
