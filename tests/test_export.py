import json

import pandas as pd
import pytest

from qtrust import export, schema
from qtrust.params import Params


def _mini_raw(tmp_path, patches):
    raw = tmp_path / "raw"
    (raw / "patches").mkdir(parents=True); (raw / "exact").mkdir(); (raw / "classical_dt0.1").mkdir(); (raw / "reference").mkdir()
    (raw / "backend_snapshots").mkdir()
    for p in patches.values():
        p.save(raw / "patches")
    (raw / "backend_snapshots/fakefez_snapshot.json").write_text(json.dumps({"source": "FakeFez snapshot (offline, NOT live)"}))
    prm = Params()
    pd.DataFrame([dict(graph_id="P12", n=12, J=1, hx=1.25, hz=-0.6, dt=0.1, N=4, Jt=0.4, observable="m", sites="3",
                       method="exact_trotter_kernel", value=0.62)]).to_csv(raw / "exact/P12_trotter_kernel_dt0.1.csv", index=False)
    rows = [dict(graph_id="P12", n=12, dt=0.1, N=4, Jt=0.4, method="mps", setting="chi64", observable="m", sites="3", estimate=0.62,
                 reference=0.62, abs_err=0.0, reference_kind="full_exact", validation_status="exact_reference"),
            dict(graph_id="P12", n=12, dt=0.1, N=10, Jt=1.0, method="mps", setting="chi64", observable="m", sites="3", estimate=0.1,
                 reference=float("nan"), abs_err=float("nan"), reference_kind="none", validation_status="no_reference")]
    pd.DataFrame(rows).to_csv(raw / "classical_dt0.1/P12_mps_chi64.csv", index=False)
    (raw / "classical_dt0.1/P12_mps_chi64.json").write_text(json.dumps(dict(
        graph_id="P12", physical_id=patches["P12"].physical_id, n=12, dt=0.1, method="mps", setting="chi64", error_status="ok",
        exit_reason="ok", wall_s=2.0, cpu_s=2.0, peak_tree_rss_bytes=3e8, max_processes=1, completed_N=[0, 4, 10], max_bond={"4": 12, "10": 48}, reference_times=[0, 4],
        host=dict(cpu="x", logical_cores=12, gpu="none"), supervision=dict(workers=1, exit_reason="ok"), run_hash="abc")))
    return raw


def test_build_all_from_saved_data_is_valid_and_keeps_unreferenced_rows(patches, tmp_path):
    raw = _mini_raw(tmp_path, {"P12": patches["P12"]})
    out = tmp_path / "out"; out.mkdir()
    res, rsc, meta = export.build_all(raw, out)
    assert set(res.source) == {"exact_numerics", "classical_approximation"}
    late = res[(res.method == "mps") & (res.N == 10)]
    assert len(late) == 1 and late.validation_status.iloc[0] == "no_reference" and late.reference_kind.iloc[0] == "none"
    assert rsc.loc[0, "term_count_or_bond_dim"] == 48 and rsc.loc[0, "max_Jt_completed"] == pytest.approx(1.0)
    assert meta["qpu"] == "none submitted" and meta["job_ids"] == [] and meta["frozen_dt"] == 0.1
    assert meta["patches"]["P12"]["physical_id"] == patches["P12"].physical_id
    for name in ("results.csv", "resources.csv", "metadata.json"):
        assert (out / name).exists()
    assert pd.read_csv(out / "results.csv").shape[0] == len(res)


def test_build_all_refuses_data_from_a_different_dt(patches, tmp_path):
    raw = _mini_raw(tmp_path, {"P12": patches["P12"]})
    bad = pd.read_csv(raw / "classical_dt0.1/P12_mps_chi64.csv"); bad["dt"] = 0.2
    bad.to_csv(raw / "classical_dt0.1/P12_mps_chi64.csv", index=False)
    with pytest.raises(schema.SchemaError, match="frozen dt"):
        export.build_all(raw, tmp_path)


# ------------------------------------------------------------------ hardware integration (real saved ibm_fez evidence)
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parents[1]
_HW = pytest.mark.skipif(not (_REPO / "raw/hardware/account2/jobs.json").exists(), reason="hardware evidence not present")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("hwout")
    res, rsc, meta = export.build_all(_REPO / "raw", out)
    return res, rsc, meta


@_HW
def test_every_hardware_analysis_row_is_in_results_csv_and_nothing_else_changed(built):
    res, _, _ = built
    src = pd.read_csv(_REPO / "raw/hardware/hardware_results.csv")
    hw = res[res.source == "hardware"].reset_index(drop=True)
    assert len(src) == len(hw) == 4230 and set(hw.approximation_setting.str[:8]) == {"account1", "account2"}
    assert (hw.validation_status.values == src.trust_status.values).all()                 # frozen verdicts preserved
    assert (hw.t_Jt.values == pytest.approx(src.Jt.values)) and (hw.N.values == src.N.values).all()
    est_ok = (hw.estimate.values == src.estimate.values) | (hw.estimate.isna().values & src.estimate.isna().values)
    assert est_ok.all()
    assert not ((hw.validation_status == "supported") & (hw.reference_kind == "none")).any()
    assert len(res) == 10878 + 4230
    assert not hw.duplicated(["graph_id", "N", "method", "observable", "site_indices", "approximation_setting"]).any()


@_HW
def test_resources_have_the_six_jobs_with_estimate_and_observed_usage(built):
    _, rsc, meta = built
    hj = rsc[rsc.kind == "hardware_job"]
    assert len(hj) == 6 and hj.observed_qpu_s.sum() == 202 and hj.shots.sum() == 720_896
    assert set(hj.job_id) == set(meta["job_ids"]) and hj.estimated_qpu_s.notna().all()
    hc = rsc[rsc.kind == "hardware_circuit"]
    assert len(hc) == 56 and hc.compiled_2q_depth.max() <= 150 and (hc.shots.isin([4096, 16384])).all()
    assert (rsc.error_status == "dry_run_not_submitted").sum() == 0


@_HW
def test_metadata_no_longer_claims_that_nothing_ran(built):
    _, _, meta = built
    assert meta["qpu"].startswith("executed") and len(meta["job_ids"]) == 6
    assert "none submitted" not in json.dumps(meta) and meta["hardware"]["n_executions"] == 56
    assert meta["hardware"]["total_reported_usage_s"] == 202 and meta["hardware"]["prereg_sha"].startswith("5360308738")
    assert "NOT LIVE" not in json.dumps(meta["backend"]["live"]) and "OFFLINE" in meta["backend"]["offline_snapshot"]
    assert all("not externally verified" in v or "verified" in v for v in meta["hardware"]["verification"].values())


@_HW
def test_qpy_files_match_live_check_hashes_and_folds_scale_the_two_qubit_count(built):
    from qtrust import hwdata
    for a in (1, 2):
        d = _REPO / f"raw/hardware/account{a}"
        lc = json.loads((d / "live_check.json").read_text())
        for ms in lc["jobs"].values():
            for m in ms:
                assert hwdata.qpy_sha16(d / "circuits" / f"{m['label']}.qpy") == m["qpy_sha"]
        base = hwdata.count_2q(d / "circuits/P18_Jt0.4_fractional.qpy")
        assert hwdata.count_2q(d / "circuits/P18_Jt0.4_fold1.qpy") == 3 * base
        assert hwdata.count_2q(d / "circuits/P18_Jt0.4_fold2.qpy") == 5 * base


@_HW
def test_cross_check_catches_contradictory_exports(built):
    res, rsc, meta = built
    assert schema.cross_check(res, rsc, meta) == [] and schema.validate_metadata(meta) == []
    bad = dict(meta, qpu="none submitted")
    assert any("none submitted" in p for p in schema.validate_metadata(bad))
    assert schema.cross_check(res[res.source != "hardware"], rsc, meta)                   # hardware vanished from results.csv
    assert schema.cross_check(res, rsc[rsc.kind != "hardware_job"], meta)                 # usage rows vanished
    assert schema.cross_check(res, rsc, dict(meta, job_ids=[]))


@_HW
def test_export_is_deterministic_in_its_scientific_columns(built, tmp_path):
    res, rsc, _ = built
    res2, rsc2, _ = export.build_all(_REPO / "raw", tmp_path)
    pd.testing.assert_frame_equal(res, res2); pd.testing.assert_frame_equal(rsc, rsc2)


def test_nonfinite_hardware_estimates_need_a_reason_and_never_get_a_verdict():
    import math
    row = dict(graph_id="P18", physical_id="d8d2727881dd5868", n=18, J=1, hx=1.25, hz=-0.6, dt=0.1, N=4, t_Jt=0.4, observable="m",
               site_indices="1", method="zne_exp", approximation_setting="account1", estimate=float("nan"), ci_low=float("nan"),
               ci_high=float("nan"), reference=0.1, reference_kind="full_exact", validation_status="supported", source="hardware",
               execution_block="x", related_job_id="j", notes="failed_reason=sign_change")
    df = pd.DataFrame([row], columns=schema.RESULTS_COLUMNS)
    assert any("non-finite" in p for p in schema.validate_results(df, 0.1))
    df.loc[0, "validation_status"] = "mitigation_failed"
    assert schema.validate_results(df, 0.1) == []
    df.loc[0, "notes"] = "failed_reason=nan"
    assert any("failure reason" in p for p in schema.validate_results(df, 0.1))
