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
