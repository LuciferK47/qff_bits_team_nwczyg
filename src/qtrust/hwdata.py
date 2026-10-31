"""Turn the archived hardware evidence under raw/hardware into rows for results.csv / resources.csv and the metadata block.

Read-only: nothing under raw/hardware is modified. Everything here works offline from saved files (counts, live-check records,
compiled QPY files, hardware_results.csv). If raw/hardware is absent the functions return empty results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = "ibm_fez"
TWOQ = ("rzz", "cz")


def hw_dir(raw: Path) -> Path:
    return raw / "hardware"


def accounts(raw: Path) -> list[int]:
    d = hw_dir(raw)
    return sorted(int(p.name[7:]) for p in d.glob("account[0-9]*") if (p / "jobs.json").exists()) if d.exists() else []


def has_hardware(raw: Path) -> bool:
    return bool(accounts(raw))


def _load(p: Path):
    return json.loads(p.read_text())


def label_jobs(raw: Path, account: int) -> dict[str, tuple[str, str]]:
    """label -> (job name, IBM job id) for one account."""
    out = {}
    for name, rec in _load(hw_dir(raw) / f"account{account}" / "jobs.json").items():
        for lbl in rec["labels"]:
            out[lbl] = (name, rec["job_id"])
    return out


def _contributing(label_map: dict, pid: str, Jt: float, method: str) -> list[str]:
    """Labels whose counts feed an estimate: the structured calibrations, the forward run and (ZNE) the folded runs."""
    want = [l for l in label_map if l.startswith(f"{pid}_cal")]
    want.append(f"{pid}_Jt{Jt:.1f}_fractional")
    if method.startswith("zne_"):
        want += [f"{pid}_Jt{Jt:.1f}_fold1", f"{pid}_Jt{Jt:.1f}_fold2"]
    return [l for l in want if l in label_map]


# ------------------------------------------------------------------ results.csv rows
def hardware_result_rows(raw: Path, prm, make_row) -> list[dict]:
    src = hw_dir(raw) / "hardware_results.csv"
    if not src.exists():
        return []
    df = pd.read_csv(src)
    maps = {a: label_jobs(raw, a) for a in accounts(raw)}
    rows = []
    for i, r in enumerate(df.itertuples()):
        lm = maps[int(r.account)]
        jobs = sorted({lm[l][1] for l in _contributing(lm, r.graph_id, r.Jt, r.method)})
        sel = bool(r.selected_model)
        notes = (f"account={int(r.account)}; se={r.se:.6g}; n_valid={int(r.n_valid)}/{int(r.B)}; failed_reason={r.failed_reason}; "
                 f"selected_model={sel}; readout_independence_passed={bool(r.readout_independence_passed)}; "
                 f"zne_heldout_validated={bool(r.zne_heldout_validated)}; reference_status={r.reference_status}; "
                 f"mitigation_valid={bool(r.mitigation_valid)}; signal_resolved={bool(r.signal_resolved)}; "
                 f"statistical_status={r.statistical_status}; systematics_validated={bool(r.systematics_validated)}; "
                 f"drift_flag={bool(getattr(r, 'drift_flag', False))}; source_row={i}")
        sites = "" if pd.isna(r.sites) else str(r.sites)
        rows.append(make_row(
            graph_id=r.graph_id, physical_id=r.physical_id, n=int(r.n), J=prm.J, hx=prm.hx, hz=prm.hz, dt=r.dt, N=int(r.N),
            t_Jt=r.Jt, observable=r.observable, site_indices=sites, method=r.method,
            approximation_setting=f"account{int(r.account)}" + ("|selected_model" if sel else ""),
            estimate=r.estimate, ci_low=r.ci_low, ci_high=r.ci_high, reference=r.reference, reference_kind=r.reference_kind,
            validation_status=r.trust_status, source="hardware", execution_block=f"{BACKEND}:account{int(r.account)}",
            related_job_id=";".join(jobs), notes=notes))
    return rows


# ------------------------------------------------------------------ resources.csv rows
def count_2q(qpy_file: Path) -> int:
    from qiskit import qpy
    with open(qpy_file, "rb") as f:
        circ = qpy.load(f)[0]
    ops = circ.count_ops()
    return int(sum(ops.get(g, 0) for g in TWOQ))


def qpy_sha16(qpy_file: Path) -> str:
    return hashlib.sha256(qpy_file.read_bytes()).hexdigest()[:16]


def hardware_resource_rows(raw: Path, phys: dict, blank: dict) -> list[dict]:
    rows = []
    for a in accounts(raw):
        d = hw_dir(raw) / f"account{a}"
        jobs = _load(d / "jobs.json"); lc = _load(d / "live_check.json")
        meta = {m["label"]: m for ms in lc["jobs"].values() for m in ms}
        for name, rec in jobs.items():
            res = _load(d / f"{name}_results.json")
            shots = int(sum(sum(c.values()) for c in res["counts"].values()))
            rows.append({**blank, "kind": "hardware_job", "dt": None, "method": name, "setting": f"account{a}", "error_status": "completed",
                         "exit_reason": "completed", "shots": shots, "estimated_qpu_s": rec["estimated_s"],
                         "observed_qpu_s": res["usage_s"], "job_id": rec["job_id"], "host_cpu": f"IBM {BACKEND} (QPU)"})
        for name, rec in jobs.items():
            for lbl in rec["labels"]:
                m = meta[lbl]; q = d / "circuits" / f"{lbl}.qpy"
                rows.append({**blank, "kind": "hardware_circuit", "graph_id": m["patch"], "physical_id": phys.get(m["patch"]), "method": m["variant"],
                             "setting": f"account{a}:{lbl}", "error_status": "executed", "compiled_2q_count": count_2q(q),
                             "compiled_2q_depth": m["depth_2q"], "shots": m["shots"], "job_id": rec["job_id"],
                             "run_hash": qpy_sha16(q), "experiment_id": m["experiment_id"], "host_cpu": f"IBM {BACKEND} (QPU)"})
    return rows


# ------------------------------------------------------------------ metadata
def verification_state(raw: Path) -> dict:
    """What has been checked against IBM's own records: only the job_verification.json files the account owners create."""
    out = {}
    for a in accounts(raw):
        f = hw_dir(raw) / f"account{a}" / "job_verification.json"
        out[f"account{a}"] = ("verified against IBM records" if f.exists() and _load(f).get("all_verified")
                              else "verification file present but NOT all jobs verified" if f.exists()
                              else "not externally verified (run `qtrust verify-jobs`)")
    return out


def hardware_metadata(raw: Path) -> dict | None:
    accts = accounts(raw)
    if not accts:
        return None, []
    out, total_s, total_shots, ids = {}, 0.0, 0, []
    for a in accts:
        d = hw_dir(raw) / f"account{a}"
        jobs = _load(d / "jobs.json"); lc = _load(d / "live_check.json")
        meta = {m["label"]: m for ms in lc["jobs"].values() for m in ms}
        jrec = {}
        for name, rec in jobs.items():
            res = _load(d / f"{name}_results.json")
            shots = int(sum(sum(c.values()) for c in res["counts"].values()))
            total_s += res["usage_s"]; total_shots += shots; ids.append(rec["job_id"])
            jrec[name] = dict(job_id=rec["job_id"], submitted_utc=rec["submitted_utc"], fetched_utc=res["fetched_utc"],
                              prereg_sha=rec["prereg_sha"], estimated_s=rec["estimated_s"], reported_usage_s=res["usage_s"], shots=shots,
                              executions=len(rec["labels"]), labels=rec["labels"],
                              qpy_sha256_16={l: meta[l]["qpy_sha"] for l in rec["labels"]})
        out[f"account{a}"] = dict(
            live_check=dict(checked_utc=lc["checked_utc"], backend=lc["backend"], num_qubits=lc["num_qubits"],
                            fractional_available=lc["fractional_available"], backend_rep_delay_s=lc["backend_rep_delay"],
                            any_depth_grew=lc["any_depth_grew"], P18_physical_nodes=lc["P18_physical_nodes"],
                            P40_physical_nodes=lc["P40_physical_nodes"]),
            jobs=jrec)
    return dict(
        backend=BACKEND, accounts=out, n_jobs=len(ids), n_executions=sum(v["executions"] for a in out.values() for v in a["jobs"].values()),
        total_shots=total_shots, total_reported_usage_s=total_s, team_limit_s=600,
        prereg_sha=next(iter(out.values()))["jobs"]["1_pilot"]["prereg_sha"],
        sampler="SamplerV2 in Batch mode; gate and measurement twirling off; dynamical decoupling off; no PEA/PEC "
                "(fractional gates); manual global-fold ZNE at 1x/3x/5x; asymmetric readout correction from 4 structured calibrations",
        timestamps_source="saved job records (submitted/fetched); IBM-side timestamps appear only after `qtrust verify-jobs`",
        verification=verification_state(raw),
        note="Job ids and usage are the values saved by `qtrust fetch`; independent confirmation against IBM's service is recorded "
             "separately by `qtrust verify-jobs` and is not implied by this file."), ids
