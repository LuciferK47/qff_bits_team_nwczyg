import json

from qtrust.classical import bench
from qtrust.params import Params


def test_run_all_end_to_end_saves_records_and_rows(tree7, tmp_path):
    prm = Params(dt=0.2); Ns = [0, 2]
    bench.run_all(tree7, prm, Ns, ["coarse"], [16], tmp_path, workers=2, budget_s=120, supervised=False)
    df, res = bench.collect(tmp_path, tree7.pid)
    assert {r["method"] for r in res} == {"pauli_prop", "mps"}
    assert all(r["error_status"] == "ok" for r in res), res
    assert set(df.Jt) == {0.0, 0.4} and {"pauli_prop", "mps"} == set(df.method)
    assert df.abs_err.max() < 5e-2                      # coarse/low-chi on 7 qubits is already near exact
    assert all("host" in r and "elapsed_s" in r for r in res)


def test_failure_is_recorded_not_hidden(tree7, tmp_path, monkeypatch):
    def boom(*a, **k): raise RuntimeError("simulated failure")
    monkeypatch.setattr(bench.mps_mod, "run", boom)
    bench.run_all(tree7, Params(), [0], [], [8], tmp_path, supervised=False)
    rec = json.loads((tmp_path / f"{tree7.pid}_mps_chi8.json").read_text())
    assert rec["error_status"] == "failed" and "simulated failure" in rec["detail"]


def test_estimates_without_exact_reference_are_kept_not_dropped(tree7, tmp_path):
    """Approximation completed at N=10 but the exact reference only exists for N<=5: N=10 rows must survive."""
    import pandas as pd
    prm = Params(); Ns = [0, 2, 10]
    cat = bench.Catalog.from_patch(tree7)
    ref, tag = bench.reference(tree7, prm, [0, 2], cat)                 # reference deliberately stops at N=2
    bench.run_all(tree7, prm, Ns, [], [16], tmp_path, ref=ref, ref_tag=tag, budget_s=120, supervised=False)
    df, res = bench.collect(tmp_path, tree7.pid)
    late = df[df.N == 10]
    assert len(late) > 0 and late.estimate.notna().all()
    assert late.reference.isna().all() and late.abs_err.isna().all()
    assert set(late.validation_status) == {"no_reference"} and set(late.reference_kind) == {"none"}
    early = df[df.N == 2]
    assert set(early.validation_status) == {"exact_reference"} and early.abs_err.notna().all()
    assert (tmp_path / f"{tree7.pid}_mps_chi16_moments.json").exists()      # raw moments saved for every time
    moments = json.loads((tmp_path / f"{tree7.pid}_mps_chi16_moments.json").read_text())
    assert "10" in moments and "0" in moments["10"]


def test_skip_done_requires_matching_hash_and_complete_status(tree7, tmp_path):
    prm = Params()
    bench.run_all(tree7, prm, [0, 2], [], [16], tmp_path, workers=1, budget_s=120, supervised=False)
    f = tmp_path / f"{tree7.pid}_mps_chi16.json"
    first = json.loads(f.read_text())
    mtime = f.stat().st_mtime_ns
    bench.run_all(tree7, prm, [0, 2], [], [16], tmp_path, workers=1, budget_s=120, supervised=False)               # identical -> skipped
    assert f.stat().st_mtime_ns == mtime
    bench.run_all(tree7, prm.with_dt(0.1), [0, 4], [], [16], tmp_path, workers=1, budget_s=120, supervised=False)  # different dt -> recomputed
    assert json.loads(f.read_text())["run_hash"] != first["run_hash"]
    rec = json.loads(f.read_text()); rec["error_status"] = "failed"; f.write_text(json.dumps(rec))
    bench.run_all(tree7, prm.with_dt(0.1), [0, 4], [], [16], tmp_path, workers=1, budget_s=120, supervised=False)  # failed -> recomputed
    assert json.loads(f.read_text())["error_status"] == "ok"


def test_supervised_run_all_records_tree_resources(tree7, tmp_path):
    prm = Params(dt=0.2)
    bench.run_all(tree7, prm, [0, 2], ["coarse"], [16], tmp_path, workers=2, budget_s=120)
    _, res = bench.collect(tmp_path, tree7.pid)
    for r in res:
        assert r["error_status"] == "ok" and r["exit_reason"] == "ok"
        assert r["peak_tree_rss_bytes"] > 50e6 and r["cpu_s"] > 0 and r["wall_s"] > 0
        assert r["physical_id"] == tree7.physical_id and r["dt"] == 0.2
    assert max(r["max_processes"] for r in res if r["method"] == "pauli_prop") >= 2


def test_reference_cache_is_reused_and_invalidated_by_parameter_change(tree7, tmp_path, monkeypatch):
    cat = bench.Catalog.from_patch(tree7)
    prm = Params(dt=0.2)
    ref1, kind = bench.reference(tree7, prm, [0, 2], cat, cache_dir=tmp_path)
    calls = []
    real = bench.exact.iter_trotter_states
    monkeypatch.setattr(bench.exact, "iter_trotter_states", lambda *a, **k: calls.append(1) or real(*a, **k))
    ref2, _ = bench.reference(tree7, prm, [0, 2], cat, cache_dir=tmp_path)                  # served from the cache
    assert not calls and ref2.keys() == ref1.keys()
    assert max(abs(ref1[N][k] - ref2[N][k]) for N in ref1 for k in ref1[N]) < 1e-15
    bench.reference(tree7, prm.with_dt(0.1), [0, 2], cat, cache_dir=tmp_path)               # different dt: recomputed
    assert calls
