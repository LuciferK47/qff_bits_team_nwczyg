"""Post-hoc hardware analyses reproduce the numbers quoted in the reports; none of them touches a frozen verdict."""
from pathlib import Path

import pandas as pd
import pytest

from qtrust import hwanalysis as H

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (REPO / "raw/hardware/account2/jobs.json").exists(), reason="hardware evidence not present")


@pytest.fixture(scope="module")
def pairs():
    return H.readout_diagnostic(REPO)[0]


def test_account2_p18_readout_failure_is_physical_pair_16_23(pairs):
    w = pairs[(pairs.account == 2) & (pairs.patch == "P18")].iloc[0]
    assert (w.logical_pair, w.physical_pair) == ("0-4", "16-23") and w.z_pooled == pytest.approx(6.6605, abs=1e-3)
    assert w.exceeds_prespecified_4 and w.p_bonferroni < 1e-6
    assert w.z_prep_all0 > 8 and abs(w.z_prep_all1) < 1                      # the excess sits in the |0...0> calibration only
    others = pairs[(pairs.account == 2) & (pairs.patch == "P18")].iloc[1:]
    assert not others.exceeds_prespecified_4.any()


def test_account1_and_p40_stay_below_the_prespecified_limit(pairs):
    assert pairs[(pairs.account == 1) & (pairs.patch == "P18")].abs_z.max() == pytest.approx(3.0048, abs=1e-3)
    assert pairs[pairs.patch == "P40"].abs_z.max() < 4 and not pairs[(pairs.account == 1)].exceeds_prespecified_4.any()


def test_heldout_zne_numbers_and_negative_result():
    t = H.heldout_table(REPO).set_index(["account", "method"]).rmse
    exp = {(1, "raw"): 0.09395, (1, "readout"): 0.09168, (1, "zne_linear"): 0.11757, (1, "zne_exp"): 0.09451, (1, "zne_richardson"): 0.19143,
           (2, "raw"): 0.07722, (2, "readout"): 0.08483, (2, "zne_linear"): 0.09551, (2, "zne_exp"): 0.10711, (2, "zne_richardson"): 0.08344}
    for k, v in exp.items():
        assert t[k] == pytest.approx(v, abs=2e-5)
    full = H.heldout_table(REPO)
    sel = full[full.selected]
    assert set(sel.method) == {"zne_linear"} and not sel.passes_predeclared_limit.any()
    for a in (1, 2):
        assert t[(a, "zne_linear")] > t[(a, "raw")]                              # selected ZNE is worse than raw on both accounts
    assert (full.n_observables == 45).all()


def test_class_table_is_consistent_with_the_frozen_rows():
    t = H.class_table(REPO)
    h = pd.read_csv(REPO / "raw/hardware/hardware_results.csv")
    h = h[h.method.isin(["raw", "readout"]) & (h.reference_kind != "none")]
    assert t.n.sum() == len(h) and t.n_supported.sum() == (h.trust_status == "supported").sum()
    assert (t.n_within_tolerance <= t.n).all() and (t.tolerance == 0.05).all()


def test_drift_cases_include_the_jt0_p40_qubit_and_flag_counts_match():
    cases, summ = H.drift_cases(REPO)
    d = pd.read_csv(REPO / "raw/hardware/drift_account2_vs_1.csv")
    assert summ.n_flagged.sum() == int(d[(d.se_1 > 0) & (d.se_2 > 0)].drift_flag.sum())
    assert len(d) == 2115 and int(d.drift_flag.sum()) == 650
    assert cases.iloc[0].N == 0 and cases.iloc[0].graph_id == "P40"            # identity circuit: not an entangling-gate effect


def test_hz_reversal_changes_M_strongly_on_the_exact_p12_circuit():
    from qtrust import validate as V
    from qtrust.params import load_params
    prm = load_params(REPO / "configs/heavy_hex.yaml")
    t = V.hz_reversal_table(V.load_patch("P12", REPO / "raw/patches"), prm)
    assert t.iloc[0].contrast == pytest.approx(0, abs=1e-12) and t.contrast.abs().max() > 0.5
    saved = pd.read_csv(REPO / "raw/exact/P12_hz_reversal_dt0.1.csv")
    assert saved.M.values == pytest.approx(t.M.values, abs=1e-9)
