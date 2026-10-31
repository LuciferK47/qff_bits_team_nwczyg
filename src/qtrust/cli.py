"""Command line. Everything is offline EXCEPT live-check / submit / fetch, which contact IBM Quantum and are run by a human.

python -m qtrust.cli patches      build + save P12/P18/P24/P40 from the FakeFez snapshot (offline, NOT live)
python -m qtrust.cli manifest     compile every planned circuit, ISA checks, usage estimate -> reports/hardware_manifest.md
python -m qtrust.cli rehearsal    noisy-Aer dress rehearsal of readout correction + ZNE + bootstrap on P12
python -m qtrust.cli preregister  hash policy/config/analysis code/planned circuits -> prereg/ (then sign prereg/APPROVAL.md)
python -m qtrust.cli live-check   --account N   recompile on the live backend + all gates (no submission)
python -m qtrust.cli submit       --account N --job {1_pilot,2_forward,3_zne}   REAL QPU job; refused without signed approval
python -m qtrust.cli fetch        --account N   download counts + job.usage()
python -m qtrust.cli analyse-hardware --accounts 1,2
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .params import load_params

ROOT = Path(__file__).resolve().parents[2]


def cmd_patches(args):
    from .graph import build_all_patches, draw_patch, load_fakefez_snapshot
    snap = load_fakefez_snapshot(ROOT / "raw/backend_snapshots/fakefez_snapshot.json")
    for pid, p in build_all_patches(snap).items():
        p.save(ROOT / "raw/patches"); draw_patch(p, ROOT / f"figures/patch_{pid}.png")
        print(pid, p.n, len(p.edges), p.hash)


def cmd_manifest(args):
    from qiskit_ibm_runtime.fake_provider import FakeFez
    from .graph import OFFLINE_SOURCE
    from .manifest import build_jobs, summarize, write_markdown
    from .validate import load_patch
    prm = load_params(ROOT / "configs/heavy_hex.yaml")
    if args.dt is not None:
        prm = prm.with_dt(args.dt)
    backend = FakeFez()
    patches = {pid: load_patch(pid) for pid in ("P18", "P40")}
    outdir = ROOT / f"raw/circuits/dt{prm.dt}"; outdir.mkdir(parents=True, exist_ok=True)
    jobs = build_jobs(patches, prm, backend, outdir)               # raises ManifestGateError on any unsafe circuit
    rows, totals = summarize(jobs, backend.default_rep_delay, OFFLINE_SOURCE)
    pd.DataFrame(rows).to_csv(outdir / "manifest_circuits.csv", index=False)
    (outdir / "manifest_usage.json").write_text(json.dumps(totals, indent=1))
    write_markdown(rows, totals, prm, ROOT / "reports/hardware_manifest.md", OFFLINE_SOURCE)
    print(pd.DataFrame(rows)[["job", "circuit", "variant", "n_2q", "depth_2q", "low_headroom"]].to_string(index=False))
    print(json.dumps(totals, indent=1))


def cmd_rehearsal(args):
    from qiskit_ibm_runtime.fake_provider import FakeFez
    from .rehearsal import correlated_readout_control, run_rehearsal
    from .validate import load_patch
    prm = load_params(ROOT / "configs/heavy_hex.yaml")
    patch, backend = load_patch(args.patch), FakeFez()
    out = ROOT / f"raw/noisy_sim_dt{prm.dt}"
    out.mkdir(parents=True, exist_ok=True)
    ctl = correlated_readout_control(patch, backend)
    (out / f"{patch.pid}_correlated_readout_control.json").write_text(json.dumps(ctl, indent=1))
    print("correlated-readout control:", {k: ctl[k] for k in ("injected_edge", "trips_on_injected_edge", "others_quiet")})
    for variant in args.variants.split(","):
        df, info = run_rehearsal(patch, prm, backend, out, variant=variant, B=args.B)
        print(variant, "selected ZNE model:", info["selected_model"], "| readout gate passed:", info["gate"]["passed"])
        held = df[(df.zne_role == "heldout") | (df.method.isin(["raw", "readout"]) & (df.Jt == 0.8))]
        print(held.groupby("method").agg(rmse=("error", lambda e: (e ** 2).mean() ** 0.5),
                                         coverage=("covers_truth", "mean"), failed=("failed_reason", lambda x: x.notna().sum())))




def cmd_topology(args):
    """Add the compact candidate P40c (never replaces P40) and write the topology comparison table."""
    import networkx as nx
    from .graph import (assert_all_couplings_kept, build_patch, draw_patch, find_compact_patch, load_fakefez_snapshot,
                        topology_metrics)
    from .validate import load_patch
    snap = load_fakefez_snapshot(ROOT / "raw/backend_snapshots/fakefez_snapshot.json")
    G = snap.graph(); G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    bad = frozenset(tuple(sorted(e)) for e in snap.edges) - frozenset(tuple(sorted(e)) for e in G.edges)
    nodes = find_compact_patch(G, args.n, bad)
    p = build_patch("P40c", G, nodes, snap.source, {"backend": snap.name, "role": "candidate_compact_NOT_BENCHMARKED"})
    assert_all_couplings_kept(snap, p)
    p.save(ROOT / "raw/patches"); draw_patch(p, ROOT / "figures/patch_P40c.png")
    rows = []
    for pid in ("P12", "P18", "P24", "P40", "P40c"):
        q = load_patch(pid)
        m = topology_metrics(q.graph(), q.meta["mps_order_info"]["max_cut_mean_cut"][q.meta["mps_order_info"]["chosen"]][0])
        rows.append(dict(patch=pid, **m, mean_cz_error=round(q.meta["mean_cz_error"], 5), physical_id=q.physical_id))
    df = pd.DataFrame(rows); df.to_csv(ROOT / "reports/topology_comparison.csv", index=False)
    print(df.to_string(index=False))


def cmd_exact(args):
    """Exact fixed-circuit tables at the frozen dt (+ continuous-time comparison and Aer cross-check where affordable)."""
    from . import validate as V
    prm = load_params(ROOT / "configs/heavy_hex.yaml")
    out = ROOT / "raw/exact"; out.mkdir(parents=True, exist_ok=True)
    tag = f"dt{prm.dt}"
    for pid in args.patches.split(","):
        p = V.load_patch(pid)
        V.exact_table(p, prm).to_csv(out / f"{pid}_trotter_kernel_{tag}.csv", index=False)
        if p.n <= 18:                                   # sparse exp(-iHt) comparison and Aer state check
            V.exact_table(p, prm, source="continuous").to_csv(out / f"{pid}_continuous_{tag}.csv", index=False)
            V.trotter_error_table(p, prm, V.JT, continuous=True).to_csv(out / f"{pid}_trotter_error_{tag}.csv", index=False)
            V.aer_crosscheck(p, prm, Ns=[prm.steps(t) for t in (0.0, 0.4, 1.0, 2.0, 3.0)]).to_csv(out / f"{pid}_aer_check_{tag}.csv", index=False)
        elif args.halving:                              # P24: dt vs dt/2 with the kernel only (hours-scale)
            V.trotter_error_table(p, prm, V.JT, continuous=False).to_csv(out / f"{pid}_trotter_error_{tag}.csv", index=False)
        print("exact done", pid, flush=True)


def cmd_preregister(args):
    from .submit import preregister
    out = preregister(ROOT)
    print(f"prereg_sha {out['prereg_sha']}  ({len(out['files'])} files, {len(out['planned_circuits'])} planned circuits)")
    print("Next: both teammates read reports/hardware_manifest.md, then fill prereg/APPROVAL.md; commit or email the "
          "prereg/ folder so the timestamp is witnessed.")


def _service():
    from qiskit_ibm_runtime import QiskitRuntimeService
    return QiskitRuntimeService()                  # the account the user saved with save_account(); no token here


def cmd_live_check(args):
    from .submit import live_check
    rep = live_check(_service(), args.account)
    print(json.dumps({k: rep.get(k) for k in ("ok", "backend", "fractional_available", "any_depth_grew", "problems")}, indent=1))


def cmd_submit(args):
    """REAL QPU SUBMISSION. Refuses unless the signed pre-registration, passing live check and budget gates hold."""
    from .submit import submit_job
    rec = submit_job(_service(), args.account, args.job)
    print("submitted", args.job, rec["job_id"], f"(estimated {rec['estimated_s']:.0f} s)")


def cmd_fetch(args):
    from .submit import fetch
    print(json.dumps(fetch(_service(), args.account), indent=1))


def cmd_verify_jobs(args):
    """READ-ONLY: look the archived job ids up on IBM with your saved account and record what IBM reports."""
    from .verify import verify_jobs
    rep = verify_jobs(_service(), args.account)
    print(json.dumps({"all_verified": rep["all_verified"], **{k: {x: v.get(x) for x in ("ibm_status", "ibm_usage_s", "archived_usage_s", "found")}
                                                                for k, v in rep["jobs"].items()}}, indent=1))


def cmd_analyse_hardware(args):
    from .submit import analyse_hardware
    df = analyse_hardware(ROOT, accounts=tuple(int(a) for a in args.accounts.split(",")), B=args.B)
    print(df.groupby(["graph_id", "method", "trust_status"]).size().to_string() if len(df) else "no fetched hardware data")


def main():
    ap = argparse.ArgumentParser(prog="qtrust")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("patches").set_defaults(f=cmd_patches)
    m = sub.add_parser("manifest"); m.add_argument("--dt", type=float, default=None, help="default: frozen dt"); m.set_defaults(f=cmd_manifest)
    r = sub.add_parser("rehearsal"); r.add_argument("--patch", default="P12"); r.add_argument("--B", type=int, default=2000)
    r.add_argument("--variants", default="cz,fractional")
    r.set_defaults(f=cmd_rehearsal)
    e = sub.add_parser("exact"); e.add_argument("--patches", default="P12,P18"); e.add_argument("--halving", action="store_true"); e.set_defaults(f=cmd_exact)
    t = sub.add_parser("topology"); t.add_argument("--n", type=int, default=40); t.set_defaults(f=cmd_topology)
    sub.add_parser("preregister").set_defaults(f=cmd_preregister)
    lc = sub.add_parser("live-check"); lc.add_argument("--account", type=int, required=True); lc.set_defaults(f=cmd_live_check)
    s = sub.add_parser("submit"); s.add_argument("--account", type=int, required=True)
    s.add_argument("--job", required=True, choices=["1_pilot", "2_forward", "3_zne"]); s.set_defaults(f=cmd_submit)
    f = sub.add_parser("fetch"); f.add_argument("--account", type=int, required=True); f.set_defaults(f=cmd_fetch)
    v = sub.add_parser("verify-jobs"); v.add_argument("--account", type=int, required=True); v.set_defaults(f=cmd_verify_jobs)
    h = sub.add_parser("analyse-hardware"); h.add_argument("--accounts", default="1"); h.add_argument("--B", type=int, default=2000)
    h.set_defaults(f=cmd_analyse_hardware)
    args = ap.parse_args(); args.f(args)



if __name__ == "__main__":
    main()
