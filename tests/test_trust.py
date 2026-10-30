import math

import pandas as pd
import pytest

from qtrust.bootstrap import bootstrap
from qtrust.mitigation import zne_fit
from qtrust.trust import classify, load_policy
from pathlib import Path

EPS = 0.05
NAN = float("nan")


def test_policy_declared_before_hardware_data():
    pol = load_policy()
    assert pol["hardware_data_seen_when_declared"] is False
    assert pol["tolerances_abs"]["hardware_vs_exact"] == EPS
    assert pol["tolerances_abs"]["trotter_dt_halving"] == 0.02
    assert pol["bootstrap"]["min_valid_fraction"] == 0.99


def test_supported_requires_whole_interval_inside_band_and_resolved_signal():
    assert classify(0.41, -0.02, 0.03, 0.40, 0.38, 0.45, EPS) == "supported"


def test_inconsistent_when_interval_entirely_outside_band():
    assert classify(0.5, 0.08, 0.15, 0.40, 0.5, 0.6, EPS) == "inconsistent"
    assert classify(0.3, -0.20, -0.06, 0.40, 0.2, 0.34, EPS) == "inconsistent"


def test_inconclusive_when_interval_straddles_band_edge():
    assert classify(0.45, 0.01, 0.09, 0.40, 0.4, 0.5, EPS) == "inconclusive"


def test_near_zero_cumulant_is_not_called_supported_without_a_resolved_signal():
    assert classify(0.01, -0.03, 0.04, 0.01, -0.02, 0.05, EPS) == "inconclusive"
    assert classify(0.02, -0.03, 0.04, 0.01, 0.005, 0.05, EPS) == "supported"


def test_missing_inputs_and_unvalidated_reference():
    assert classify(None, None, None, None, None, None, EPS) == "no_reference"
    assert classify(None, None, None, 0.3, None, None, EPS) == "no_hardware"
    assert classify(0.3, -0.01, 0.01, 0.3, 0.29, 0.31, EPS, reference_validated=False) == "inconclusive"


@pytest.mark.parametrize("point,lo,hi,hwlo,hwhi", [
    (NAN, -0.01, 0.01, 0.0, 0.0), (0.3, NAN, 0.01, 0.2, 0.4), (0.3, -0.01, NAN, 0.2, 0.4),
    (0.3, -0.01, 0.01, NAN, 0.4), (float("inf"), -0.01, 0.01, 0.2, 0.4)])
def test_non_finite_estimator_is_mitigation_failed_never_supported_or_inconsistent(point, lo, hi, hwlo, hwhi):
    assert classify(point, lo, hi, 0.3, hwlo, hwhi, EPS) == "mitigation_failed"


def test_nan_point_with_an_interval_that_looks_inconsistent_is_still_failed():
    assert classify(NAN, 0.2, 0.3, 0.3, 0.5, 0.6, EPS) == "mitigation_failed"


def test_archived_rehearsal_rows_with_nan_estimates_are_all_rejected():
    """The 7 archived P12 rows whose exponential-ZNE estimate is NaN (2 were wrongly 'supported')."""
    root = Path(__file__).resolve().parents[1]
    f = next(iter(sorted(root.glob("raw/**/P12_simulated_noisy_results.csv"))))
    d = pd.read_csv(f)
    bad = d[~d.estimate.apply(math.isfinite)]
    assert len(bad) == 7
    for _, r in bad.iterrows():
        st = classify(r.estimate, r.ci_low - r.reference, r.ci_high - r.reference, r.reference, r.ci_low, r.ci_high, EPS)
        assert st == "mitigation_failed"


def test_bootstrap_refuses_interval_for_nonfinite_point_and_low_valid_fraction():
    data = {"a": {"0": 50, "1": 50}}
    def pipe(d):
        n1 = d["a"].get("1", 0)
        return {("nan_point",): float("nan"), ("sometimes_nan",): 1.0 if n1 % 2 == 0 else float("nan"), ("ok",): n1 / 100}
    out = bootstrap(data, pipe, B=60, seed=1)
    assert out[("nan_point",)]["failed_reason"] == "non_finite_point" and math.isnan(out[("nan_point",)]["lo"])
    assert out[("sometimes_nan",)]["failed_reason"] == "insufficient_finite_bootstrap"
    assert out[("ok",)]["failed_reason"] is None and out[("ok",)]["n_valid"] == 60


def test_bootstrap_all_replicates_invalid_does_not_crash():
    out = bootstrap({"a": {"0": 5, "1": 5}}, lambda d: {("x",): 1.0 if d["a"].get("1", 0) == 5 else float("nan")}, B=40, seed=3)
    assert out[("x",)]["n_valid"] < 40 and math.isnan(out[("x",)]["hi"]) or out[("x",)]["failed_reason"] is None


def test_zne_fit_reports_failure_reason_and_diagnostics():
    bad = zne_fit([1, 3, 5], [0.1, -0.05, 0.02], "exp")
    assert not bad.finite and bad.failed_reason == "sign_change" and math.isnan(bad.estimate)
    good = zne_fit([1, 3, 5], [0.8, 0.7, 0.6], "linear")
    assert good.finite and good.cond > 1 and good.residual < 1e-12


from qtrust.trust import assess  # noqa: E402


def _a(**kw):
    base = dict(point=0.41, diff_lo=-0.02, diff_hi=0.03, reference=0.40, hw_lo=0.38, hw_hi=0.45, eps=EPS,
                reference_kind="full_exact", systematics_validated=True, source="hardware")
    base.update(kw)
    return assess(**base)


def test_supported_only_when_every_gate_passes():
    assert _a()["final_status"] == "supported"
    assert _a(systematics_validated=False)["final_status"] == "inconclusive"
    assert _a(systematics_validated=False)["statistical_status"] == "supported"        # reported separately
    assert _a(source="simulated_noisy")["final_status"] == "inconclusive"              # rehearsal is never 'supported'


def test_reference_status_gates_the_verdict():
    assert _a(reference_kind="none", reference=float("nan"))["final_status"] == "no_reference"
    r = _a(reference_kind="classical_stability")
    assert r["final_status"] == "classical_stability_only" and r["reference_status"] == "classical_stability_only"
    assert _a(reference_kind="lightcone_exact")["final_status"] == "supported"


def test_failed_mitigation_overrides_everything_for_exact_references():
    r = _a(point=float("nan"), diff_lo=float("nan"), diff_hi=float("nan"), hw_lo=float("nan"), hw_hi=float("nan"))
    assert r["final_status"] == "mitigation_failed" and not r["mitigation_valid"]


def test_signal_resolved_is_its_own_column():
    r = _a(reference=0.01, hw_lo=-0.02, hw_hi=0.05, diff_lo=-0.03, diff_hi=0.04)
    assert not r["signal_resolved"] and r["final_status"] == "inconclusive"
