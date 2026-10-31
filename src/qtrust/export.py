"""Assemble results.csv, resources.csv and metadata.json from the saved raw data (offline, no QPU, no network).

Only frozen-dt data enter the tables; exploratory dt=0.2 files stay under raw/exploratory_dt0.2 and are never mixed in.
Every table is validated by qtrust.schema before it is written."""
from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import hwdata, schema
from .classical.bench import host_info
from .params import Params, load_params

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261029
AI_DISCLOSURE = ("An AI assistant (Claude, via Claude Code) was used extensively for implementation (code, tests, scripts, draft "
                 "reports); the authors directed the changes, ran every hardware job on their own accounts and gave the "
                 "typed, hash-tied pre-hardware approval. Third-party packages: Qiskit, Qiskit Aer, qiskit-ibm-runtime, "
                 "pauli-prop (IBM), quimb, numpy, scipy, pandas, networkx, matplotlib, psutil.")


def _nan(x):
    return float("nan") if x is None else x


def _physical_ids(raw: Path) -> dict:
    out = {}
    for f in sorted((raw / "patches").glob("P*.json")):
        d = json.loads(f.read_text()); out[d["pid"]] = d["physical_id"]
    return out


def _row(**kw):
    base = {c: None for c in schema.RESULTS_COLUMNS}
    base.update(ci_low=float("nan"), ci_high=float("nan"), reference=float("nan"), execution_block="", related_job_id="", notes="")
    base.update(kw)
    return base


def results_table(raw: Path, prm: Params) -> pd.DataFrame:
    phys = _physical_ids(raw)
    rows = []
    for f in sorted((raw / "exact").glob(f"P*_trotter_kernel_dt{prm.dt}.csv")):
        for r in pd.read_csv(f).itertuples():
            rows.append(_row(graph_id=r.graph_id, physical_id=phys[r.graph_id], n=r.n, J=r.J, hx=r.hx, hz=r.hz, dt=r.dt, N=r.N,
                             t_Jt=r.Jt, observable=r.observable, site_indices=str(r.sites), method="exact_trotter_kernel",
                             approximation_setting="", estimate=r.value, reference=r.value, reference_kind="full_exact",
                             validation_status="reference", source="exact_numerics", execution_block="exact"))
    for f in sorted((raw / "reference").glob(f"P*_reference_dt{prm.dt}.json")):
        d = json.loads(f.read_text())
        if d["kind"] != "lightcone_exact":
            continue
        pid = f.name.split("_")[0]
        for N, obs in d["obs"].items():
            for kind, sites, v in obs:
                rows.append(_row(graph_id=pid, physical_id=phys[pid], n=d["meta"].get("n", 40), J=prm.J, hx=prm.hx, hz=prm.hz,
                                 dt=prm.dt, N=int(N), t_Jt=int(N) * prm.dt, observable=kind, site_indices=sites,
                                 method="exact_lightcone_kernel", approximation_setting="", estimate=v, reference=v,
                                 reference_kind="lightcone_exact", validation_status="reference", source="exact_numerics",
                                 execution_block="exact"))
    for f in sorted((raw / f"classical_dt{prm.dt}").glob("P*_*_*.csv")):
        if f.stat().st_size < 5:
            continue
        for r in pd.read_csv(f).itertuples():
            rows.append(_row(graph_id=r.graph_id, physical_id=phys[r.graph_id], n=r.n, J=prm.J, hx=prm.hx, hz=prm.hz, dt=r.dt,
                             N=r.N, t_Jt=r.Jt, observable=r.observable, site_indices=str(r.sites), method=r.method,
                             approximation_setting=r.setting, estimate=r.estimate, reference=_nan(r.reference),
                             reference_kind=r.reference_kind, validation_status=r.validation_status,
                             source="classical_approximation", execution_block=f"classical:{r.method}:{r.setting}"))
    for f in sorted((raw / f"noisy_sim_dt{prm.dt}").glob("P*_results.csv")):
        for r in pd.read_csv(f).itertuples():
            note = f"failed_reason={r.failed_reason}; n_valid={r.n_valid}/{r.B}; zne_role={r.zne_role}; " \
                   f"readout_independence_passed={r.readout_independence_passed}"
            rows.append(_row(graph_id=r.graph_id, physical_id=r.physical_id, n=r.n, J=prm.J, hx=prm.hx, hz=prm.hz, dt=r.dt, N=r.N,
                             t_Jt=r.Jt, observable=r.observable, site_indices=str(r.sites), method=r.method,
                             approximation_setting=f"{r.variant}{'|selected_model' if r.selected_model else ''}",
                             estimate=r.estimate, ci_low=_nan(r.ci_low), ci_high=_nan(r.ci_high), reference=r.reference,
                             reference_kind=r.reference_kind, validation_status=r.trust_status_simulated, source="simulated_noisy",
                             execution_block="rehearsal", notes=note))
    rows += hwdata.hardware_result_rows(raw, prm, _row)                     # real ibm_fez data, both accounts
    return pd.DataFrame(rows, columns=schema.RESULTS_COLUMNS)


def resources_table(raw: Path, prm: Params) -> pd.DataFrame:
    rows = []
    blank = {c: None for c in schema.RESOURCES_COLUMNS}
    for f in sorted((raw / f"classical_dt{prm.dt}").glob("P*_*_*.json")):
        if f.stem.endswith("_moments"):
            continue
        r = json.loads(f.read_text())
        sup = r.get("supervision") or {}
        size = (max(r["max_terms_retained"].values()) if r.get("max_terms_retained") else None) if r["method"] == "pauli_prop" else \
               (max(r["max_bond"].values()) if r.get("max_bond") else None)
        h = r.get("host", {})
        rows.append({**blank, "kind": "classical", "graph_id": r["graph_id"], "physical_id": r["physical_id"], "n": r["n"], "dt": r["dt"],
                     "method": r["method"], "setting": r["setting"], "error_status": r["error_status"],
                     "exit_reason": r.get("exit_reason") or sup.get("exit_reason") or r["error_status"],
                     "wall_s": r.get("wall_s"), "cpu_s": r.get("cpu_s"), "peak_tree_rss_bytes": r.get("peak_tree_rss_bytes"),
                     "max_processes": r.get("max_processes"), "workers": sup.get("workers"), "term_count_or_bond_dim": size,
                     "max_Jt_completed": (max(r["completed_N"]) * r["dt"]) if r.get("completed_N") else None,
                     "host_cpu": h.get("cpu"), "logical_cores": h.get("logical_cores"), "gpu": h.get("gpu"), "run_hash": r.get("run_hash")})
    phys = _physical_ids(raw)
    mdir = raw / "circuits" / f"dt{prm.dt}"
    if (mdir / "manifest_circuits.csv").exists():
        for r in pd.read_csv(mdir / "manifest_circuits.csv").itertuples():
            rows.append({**blank, "kind": "compile", "graph_id": r.patch, "physical_id": phys.get(r.patch), "dt": prm.dt, "method": "compile",
                         "setting": r.variant, "error_status": "dry_run_ok" if r.isa_ok else "isa_failed", "compiled_2q_count": r.n_2q,
                         "compiled_2q_depth": r.depth_2q, "shots": r.shots, "experiment_id": r.experiment_id})
        for job, v in json.loads((mdir / "manifest_usage.json").read_text()).items():
            rows.append({**blank, "kind": "job_estimate", "dt": prm.dt, "method": job, "error_status": "pre_submission_estimate",
                         "shots": v["executions"], "estimated_qpu_s": v["detailed_s"]})
    rows += hwdata.hardware_resource_rows(raw, phys, blank)                 # six executed jobs + 56 executed circuits
    return pd.DataFrame(rows, columns=schema.RESOURCES_COLUMNS)


def metadata(raw: Path, prm: Params) -> dict:
    pk = {}
    for name in ("qiskit", "qiskit-aer", "qiskit-ibm-runtime", "pauli-prop", "quimb", "numpy", "scipy", "pandas", "networkx", "psutil"):
        try:
            pk[name] = md.version(name)
        except md.PackageNotFoundError:
            pk[name] = None
    snap = raw / "backend_snapshots" / "fakefez_snapshot.json"
    patches = {}
    for f in sorted((raw / "patches").glob("P*.json")):
        d = json.loads(f.read_text())
        patches[d["pid"]] = dict(n=d["n"], edges=len(d["edges"]), structural_hash=d["hash"], physical_id=d["physical_id"], nodes=d["nodes"],
                                 source=d["source"], role=d.get("meta", {}).get("role", "benchmark"))
    circuits = {}
    mc = raw / "circuits" / f"dt{prm.dt}" / "manifest_circuits.csv"
    if mc.exists():
        circuits = {r.circuit: dict(qpy_sha256_16=r.qpy_sha, experiment_id=r.experiment_id, depth_2q=int(r.depth_2q)) for r in pd.read_csv(mc).itertuples()}
    from .rehearsal import INDEPENDENCE_Z_MAX, MAX_FIT_FAILURE_RATE, MODELS
    hw, ids = hwdata.hardware_metadata(raw)
    from .trust import load_policy
    return dict(
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"), frozen_dt=prm.dt,
        hamiltonian=dict(J=prm.J, hx=prm.hx, hz=prm.hz), python=sys.version.split()[0], platform=platform.platform(), host=host_info(),
        packages=pk, seeds=dict(global_seed=SEED, bootstrap_seed=SEED),
        backend=dict(
            live=(f"ibm_fez, queried live and executed on 2026-10-30/31 from two Open Plan accounts (see `hardware`)" if hw else
                  "none: no live backend was queried"),
            offline_snapshot="ibm_fez topology and noise from the FakeFez snapshot, OFFLINE, used only for pre-hardware dry runs and "
                             "the simulated rehearsal"),
        snapshot=dict(file=str(snap.relative_to(raw.parent)), sha256=hashlib.sha256(snap.read_bytes()).hexdigest(),
                      source=json.loads(snap.read_text())["source"]),
        patches=patches, circuits=circuits, policy=load_policy(),
        mitigation=dict(readout="independent asymmetric flips, structured calibration (00..0, 11..1, 2 checkerboards)",
                        zne_models=list(MODELS), zne_selection="calibration times only; held-out time evaluated separately",
                        max_fit_failure_rate=MAX_FIT_FAILURE_RATE, independence_z_max=INDEPENDENCE_Z_MAX,
                        bootstrap="joint multinomial resampling of every block incl. calibration, 2000 replicates (rehearsal)"),
        qpu=(f"executed: {hw['n_jobs']} jobs / {hw['n_executions']} circuit executions on ibm_fez, "
             f"{hw['total_reported_usage_s']:.0f} s reported usage" if hw else "none submitted"),
        job_ids=ids, hardware=hw, ai_assistance=AI_DISCLOSURE)


def build_all(raw: Path | None = None, out: Path | None = None, config: Path | None = None):
    raw = raw or ROOT / "raw"
    out = out or ROOT
    prm = load_params(config or ROOT / "configs/heavy_hex.yaml")
    res, rsc, meta = results_table(raw, prm), resources_table(raw, prm), metadata(raw, prm)
    schema.require_valid(schema.validate_results(res, prm.dt), "results.csv")
    schema.require_valid(schema.validate_resources(rsc), "resources.csv")
    schema.require_valid(schema.validate_metadata(meta), "metadata.json")
    schema.require_valid(schema.cross_check(res, rsc, meta), "results/resources/metadata consistency")
    res.to_csv(out / "results.csv", index=False)
    rsc.to_csv(out / "resources.csv", index=False)
    (out / "metadata.json").write_text(json.dumps(meta, indent=1, default=str))
    return res, rsc, meta
