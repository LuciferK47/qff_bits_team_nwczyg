"""Approval-gated hardware path: pre-registration, live check, submit, fetch, analyse.

This is the ONLY module that can talk to IBM Quantum, and nothing calls it automatically. A human runs
``python -m qtrust.cli <preregister|live-check|submit|fetch|analyse-hardware>``. ``submit`` refuses unless
  * prereg/prereg.json still matches the files on disk (policy, configs, analysis code, planned circuits), and
  * prereg/APPROVAL.md carries that exact sha, two different approver names and a date, and
  * the same account has a passing live check, and the pilot job (1_pilot) is fetched before any other job, and
  * the job fits in the account's remaining usage budget.
Credentials are never read or written here: ``QiskitRuntimeService()`` uses the account the user saved themselves.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BACKEND = "ibm_fez"
ACCOUNT_CAP_S = 420.0           # of the 600 s monthly allocation; the rest is headroom
PLACEHOLDER = "<"
CODE_FILES = ("src/qtrust/rehearsal.py", "src/qtrust/mitigation.py", "src/qtrust/trust.py", "src/qtrust/bootstrap.py",
              "src/qtrust/manifest.py", "src/qtrust/hardware.py", "src/qtrust/submit.py")
CONFIG_FILES = ("configs/trust_policy.yaml", "configs/heavy_hex.yaml")
DEPTH_GROWTH_FLAG = 1.2         # live compile deeper than 1.2x the dry-run manifest is reported


class ApprovalError(RuntimeError):
    """A submission gate failed. Nothing was sent."""


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ pre-registration
def _manifest_dir(root: Path, dtv: float) -> Path:
    return root / f"raw/circuits/dt{dtv}"


def prereg_files(root: Path, dtv: float) -> dict[str, str]:
    """{relative path: sha256} for everything the analysis and the plan depend on."""
    md = _manifest_dir(root, dtv)
    paths = [root / p for p in CONFIG_FILES + CODE_FILES]
    paths += [md / "manifest_circuits.csv", md / "manifest_usage.json"] + sorted(md.glob("*.qpy"))
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise ApprovalError(f"cannot pre-register, missing: {missing[:5]}; run `qtrust manifest` first")
    return {str(p.relative_to(root)): _sha(p.read_bytes()) for p in paths}


def prereg_sha(files: dict[str, str]) -> str:
    return _sha(json.dumps(files, sort_keys=True).encode())[:32]


APPROVAL_TEMPLATE = """# Pre-hardware approval (REQUIRED before any QPU job)

This file is checked by `qtrust submit`. Fill every field below with plain text and no angle brackets; both
teammates must have read reports/hardware_manifest.md and configs/trust_policy.yaml. Editing any pre-registered file
afterwards changes the sha and invalidates this approval.

prereg_sha: {sha}
approved_by_1: <full name of teammate 1>
approved_by_2: <full name of teammate 2>
date: <YYYY-MM-DD>
"""


def preregister(root: Path = ROOT, dtv: float | None = None) -> dict:
    from .params import load_params
    dtv = dtv if dtv is not None else load_params(root / "configs/heavy_hex.yaml").dt
    files = prereg_files(root, dtv)
    sha = prereg_sha(files)
    md = _manifest_dir(root, dtv)
    planned = pd.read_csv(md / "manifest_circuits.csv")[["job", "circuit", "variant", "shots", "qpy_sha"]].to_dict("records")
    out = dict(prereg_sha=sha, created_utc=_utc(), dt=dtv, backend=BACKEND, files=files, planned_circuits=planned,
               note=("dry-run compilation on the FakeFez snapshot with ASSUMED fractional-gate timing; live circuits are "
                     "recompiled by `live-check` and their shas recorded then"))
    d = root / "prereg"; d.mkdir(exist_ok=True)
    (d / "prereg.json").write_text(json.dumps(out, indent=1))
    if not (d / "APPROVAL.md").exists():
        (d / "APPROVAL.md").write_text(APPROVAL_TEMPLATE.format(sha=sha))
    return out


def _parse_approval(text: str) -> dict:
    kv = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            kv[k.strip()] = v.strip()
    return kv


def verify_approval(root: Path = ROOT) -> str:
    """Return the verified pre-registration sha or raise ApprovalError."""
    pj, ap = root / "prereg/prereg.json", root / "prereg/APPROVAL.md"
    if not pj.exists() or not ap.exists():
        raise ApprovalError("prereg/prereg.json and prereg/APPROVAL.md are required: run `qtrust preregister`, then sign")
    stored = json.loads(pj.read_text())
    current = prereg_sha(prereg_files(root, stored["dt"]))
    if current != stored["prereg_sha"]:
        raise ApprovalError("a pre-registered file changed after pre-registration; re-run `qtrust preregister` and re-approve")
    kv = _parse_approval(ap.read_text())
    if kv.get("prereg_sha") != current:
        raise ApprovalError("APPROVAL.md does not carry the current prereg_sha")
    names = [kv.get("approved_by_1", ""), kv.get("approved_by_2", "")]
    if any((not n) or PLACEHOLDER in n for n in names) or names[0].casefold() == names[1].casefold():
        raise ApprovalError("APPROVAL.md needs two different, filled-in approver names")
    if not kv.get("date") or PLACEHOLDER in kv["date"]:
        raise ApprovalError("APPROVAL.md needs a date")
    return current


# ------------------------------------------------------------------ per-account storage
def acct_dir(root: Path, account: int) -> Path:
    d = root / f"raw/hardware/account{account}"; d.mkdir(parents=True, exist_ok=True)
    return d


def _jobs(root, account) -> dict:
    p = acct_dir(root, account) / "jobs.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _results(root, account, job) -> dict | None:
    p = acct_dir(root, account) / f"{job}_results.json"
    return json.loads(p.read_text()) if p.exists() else None


def spent_seconds(root: Path, account: int) -> float:
    return float(sum((_results(root, account, j) or {}).get("usage_s") or 0.0 for j in _jobs(root, account)))


def estimate_seconds(root: Path, account: int, job: str, dtv: float) -> float:
    """Conservative usage estimate for a job: the PDF 0.5 ms/shot rate, or the detailed model rescaled by the pilot's
    measured usage once the pilot has been fetched."""
    usage = json.loads((_manifest_dir(root, dtv) / "manifest_usage.json").read_text())
    pilot = _results(root, account, "1_pilot")
    if pilot and pilot.get("usage_s"):
        return float(usage[job]["detailed_s"] * pilot["usage_s"] / usage["1_pilot"]["detailed_s"])
    return float(usage[job]["pdf_rate_s"])


# ------------------------------------------------------------------ live check (no submission)
def _cz_error(cz, a: int, b: int):
    props = cz.get((a, b)) or cz.get((b, a))
    return None if props is None else props.error



def live_check(service, account: int, root: Path = ROOT, backend_name: str = BACKEND) -> dict:
    """Recompile every planned circuit on the LIVE target, re-run every gate, store the circuits that submit will send."""
    from qiskit import qpy
    from .manifest import ManifestGateError, build_jobs
    from .params import load_params
    from .validate import load_patch
    prm = load_params(root / "configs/heavy_hex.yaml")
    report = dict(account=account, backend=backend_name, checked_utc=_utc(), ok=False, problems=[])
    try:
        backend = service.backend(backend_name, use_fractional_gates=True)
    except TypeError:
        backend = service.backend(backend_name)
    ops = set(backend.target.operation_names)
    report.update(num_qubits=backend.target.num_qubits, operation_names=sorted(ops))
    report["fractional_available"] = bool("rzz" in ops)
    if not report["fractional_available"]:
        report["problems"].append("live target has no rzz: fractional gates unavailable on this instance; the manifest must "
                                  "be re-planned as CZ-only and re-pre-registered (not done automatically)")
    patches = {pid: load_patch(pid) for pid in ("P18", "P40")}
    cz_pairs = {tuple(sorted(p)) for p in backend.target["cz"]} if "cz" in ops else set()
    for pid, p in patches.items():
        missing = [(p.nodes[a], p.nodes[b]) for a, b in p.edges if tuple(sorted((p.nodes[a], p.nodes[b]))) not in cz_pairs]
        if missing:
            report["problems"].append(f"{pid}: couplings absent from the live target: {missing}")
        report[f"{pid}_physical_nodes"] = list(p.nodes)
        report[f"{pid}_cz_error"] = {f"{p.nodes[a]}-{p.nodes[b]}": _cz_error(backend.target["cz"], p.nodes[a], p.nodes[b])
                                     for a, b in p.edges} if cz_pairs else {}
    if report["problems"]:
        return _save_live(root, account, report)
    try:
        jobs = build_jobs(patches, prm, backend, None)
    except ManifestGateError as e:
        report["problems"].append(f"gate: {e}")
        return _save_live(root, account, report)
    dry = pd.read_csv(_manifest_dir(root, prm.dt) / "manifest_circuits.csv").set_index("circuit")
    cdir = acct_dir(root, account) / "circuits"; cdir.mkdir(exist_ok=True)
    out_jobs, diffs = {}, []
    for name, items in jobs.items():
        out_jobs[name] = []
        for it in items:
            buf = io.BytesIO(); qpy.dump(it.compiled.circuit, buf)
            sha = _sha(buf.getvalue())[:16]
            (cdir / f"{it.label}.qpy").write_bytes(buf.getvalue())
            d0 = int(dry.loc[it.label, "depth_2q"]) if it.label in dry.index else None
            d1 = it.compiled.report["depth_2q"]
            diffs.append(dict(circuit=it.label, dry_depth_2q=d0, live_depth_2q=d1, qpy_sha_live=sha,
                              depth_grew=bool(d0 and d1 > DEPTH_GROWTH_FLAG * d0)))
            out_jobs[name].append(dict(label=it.label, shots=it.shots, qpy_sha=sha, depth_2q=d1,
                                       experiment_id=it.experiment_id, patch=it.patch, variant=it.variant))
    report.update(jobs=out_jobs, depth_diffs=diffs, any_depth_grew=any(d["depth_grew"] for d in diffs),
                  ok=True, backend_rep_delay=getattr(backend, "default_rep_delay", None))
    return _save_live(root, account, report)


def _save_live(root, account, report):
    (acct_dir(root, account) / "live_check.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# ------------------------------------------------------------------ submit / fetch
def _make_sampler(backend):
    """Batch-mode SamplerV2, no twirling / PEA (incompatible with fractional gates), no dynamical decoupling
    (identical to the rehearsal). Returns (sampler, closer)."""
    from qiskit_ibm_runtime import Batch, SamplerV2
    batch = Batch(backend=backend)
    sampler = SamplerV2(mode=batch)
    sampler.options.dynamical_decoupling.enable = False
    sampler.options.twirling.enable_gates = False
    sampler.options.twirling.enable_measure = False
    return sampler, batch.close


def submit_job(service, account: int, job: str, root: Path = ROOT, sampler_factory=None, backend_name: str = BACKEND) -> dict:
    from qiskit import qpy
    from .params import load_params
    sha = verify_approval(root)
    live = acct_dir(root, account) / "live_check.json"
    if not live.exists() or not json.loads(live.read_text()).get("ok"):
        raise ApprovalError(f"account {account}: no passing live check; run `qtrust live-check --account {account}`")
    lc = json.loads(live.read_text())
    if job not in lc["jobs"]:
        raise ApprovalError(f"unknown job {job}")
    if job in _jobs(root, account):
        raise ApprovalError(f"{job} was already submitted on account {account}; refusing to spend budget twice")
    if job != "1_pilot" and not (_results(root, account, "1_pilot") or {}).get("usage_s"):
        raise ApprovalError("the pilot (1_pilot) must be submitted AND fetched (with usage) before any other job")
    dtv = load_params(root / "configs/heavy_hex.yaml").dt
    est, spent = estimate_seconds(root, account, job, dtv), spent_seconds(root, account)
    if spent + est > ACCOUNT_CAP_S:
        raise ApprovalError(f"{job}: spent {spent:.0f} s + estimated {est:.0f} s exceeds the {ACCOUNT_CAP_S:.0f} s cap")
    cdir = acct_dir(root, account) / "circuits"
    circs, pubs_meta = [], []
    for it in lc["jobs"][job]:
        raw = (cdir / f"{it['label']}.qpy").read_bytes()
        if _sha(raw)[:16] != it["qpy_sha"]:
            raise ApprovalError(f"{it['label']}: stored circuit does not match its live-check sha")
        circs.append(qpy.load(io.BytesIO(raw))[0]); pubs_meta.append(it)
    try:
        backend = service.backend(backend_name, use_fractional_gates=True)
    except TypeError:
        backend = service.backend(backend_name)
    sampler, close = (sampler_factory or _make_sampler)(backend)
    run = sampler.run([(c, None, m["shots"]) for c, m in zip(circs, pubs_meta)])
    rec = dict(job_id=run.job_id(), submitted_utc=_utc(), prereg_sha=sha, estimated_s=est,
               labels=[m["label"] for m in pubs_meta], backend=backend_name)
    jobs = _jobs(root, account); jobs[job] = rec
    (acct_dir(root, account) / "jobs.json").write_text(json.dumps(jobs, indent=1))      # recorded before anything else
    close()
    return rec


def _counts_of(pub_result) -> dict[str, int]:
    return dict(next(iter(pub_result.data.values())).get_counts())


def fetch(service, account: int, root: Path = ROOT) -> dict:
    status = {}
    for job, rec in _jobs(root, account).items():
        if _results(root, account, job):
            status[job] = "fetched"; continue
        run = service.job(rec["job_id"])
        st = str(getattr(run.status(), "name", run.status()))
        if st.upper() != "DONE":
            status[job] = st; continue
        res = run.result()
        try:
            usage = float(run.usage())
        except Exception:                                             # older runtime: metrics()
            usage = float(run.metrics().get("usage", {}).get("quantum_seconds"))
        out = dict(job_id=rec["job_id"], backend=rec["backend"], usage_s=usage, fetched_utc=_utc(),
                   counts={lbl: _counts_of(res[i]) for i, lbl in enumerate(rec["labels"])})
        (acct_dir(root, account) / f"{job}_results.json").write_text(json.dumps(out))
        status[job] = f"fetched ({usage:.1f} s)"
    return status


# ------------------------------------------------------------------ analysis of fetched hardware data
def assemble(root: Path, account: int, pid: str, prm) -> dict | None:
    """{'cal': [counts...], 'fwd': {N: counts}, 'zne': {N: {k: counts}}} for patch ``pid`` from fetched results."""
    cal: dict[int, dict] = {}; fwd: dict[int, dict] = {}; zne: dict[int, dict] = {}
    for job in _jobs(root, account):
        r = _results(root, account, job)
        for lbl, counts in (r or {}).get("counts", {}).items():
            parts = lbl.split("_")
            if parts[0] != pid:
                continue
            if parts[1].startswith("cal"):
                cal[int(parts[1][3:])] = counts
            else:
                N = prm.steps(float(parts[1][2:]))
                if parts[2].startswith("fold"):
                    zne.setdefault(N, {})[int(parts[2][4:])] = counts
                elif parts[2] == "fractional":                       # the cz twin is only for the compilation comparison
                    fwd[N] = counts
    if not cal or not fwd:
        return None
    return dict(cal=[cal[i] for i in sorted(cal)], fwd=fwd, zne={N: zne[N] for N in zne})


def drift_table(a: pd.DataFrame, b: pd.DataFrame, z_max: float = 4.0) -> pd.DataFrame:
    """Account 2 vs account 1 on the identical frozen manifest: z = (e1 - e2) / sqrt(se1^2 + se2^2) per observable."""
    key = ["graph_id", "N", "method", "observable", "sites"]
    m = a.merge(b, on=key, suffixes=("_1", "_2"))
    se = np.sqrt(m.se_1 ** 2 + m.se_2 ** 2)
    m["drift_z"] = (m.estimate_1 - m.estimate_2) / se.where(se > 0)
    m["drift_flag"] = m.drift_z.abs() > z_max
    return m[key + ["estimate_1", "estimate_2", "se_1", "se_2", "drift_z", "drift_flag"]]


def analyse_hardware(root: Path = ROOT, accounts=(1,), B: int = 2000, seed: int = 20261029) -> pd.DataFrame:
    """Same pipeline as the rehearsal on fetched hardware counts. ``source='hardware'``; a row can only be ``supported`` if
    the readout-independence gate passed, the held-out ZNE check passed and (with two accounts) there is no drift."""
    from . import exact, mitigation as mit
    from .bootstrap import bootstrap
    from .classical.bench import reference
    from .moments import Catalog
    from .params import load_params
    from .rehearsal import analyse, readout_gate, select_model
    from .trust import assess, load_policy
    from .validate import load_patch
    prm = load_params(root / "configs/heavy_hex.yaml")
    pol = load_policy(root / "configs/trust_policy.yaml")
    eps, min_valid = pol["tolerances_abs"]["hardware_vs_exact"], pol["bootstrap"]["min_valid_fraction"]
    sysp = pol.get("systematics", {})
    drift_zmax, held_rmse_max = sysp.get("drift_z_max", 4.0), sysp.get("heldout_rmse_max", eps)
    cal_Ns, held_N = {prm.steps(0.4), prm.steps(1.0)}, prm.steps(0.8)
    rows = []
    for account in accounts:
        for pid in ("P18", "P40"):
            patch = load_patch(pid)
            data = assemble(root, account, pid, prm)
            if data is None:
                continue
            cat = Catalog.from_patch(patch)
            preps = mit.structured_preps(patch.edges, patch.n)
            Ns, zne_Ns = sorted(data["fwd"]), sorted(data["zne"])
            ref, kind = reference(patch, prm, Ns, cat, cache_dir=root / "raw/reference")
            gate = readout_gate(data, preps, patch)
            reasons: dict = {}
            point = analyse(data, patch, cat, preps, Ns, zne_Ns, reasons)
            model, table, heldout_ok = None, {}, False
            if pid == "P18" and cal_Ns <= set(ref) and held_N in ref:
                model, table = select_model(point, ref, cal_Ns)
                errs = [point[(f"zne_{model}", held_N, k)] - v for k, v in ref[held_N].items()
                        if model and np.isfinite(point.get((f"zne_{model}", held_N, k), np.nan))]
                heldout_ok = bool(model and errs and float(np.sqrt(np.mean(np.square(errs)))) <= held_rmse_max)
            bs = bootstrap(data, lambda d: analyse(d, patch, cat, preps, Ns, zne_Ns), B=B, seed=seed, min_valid_fraction=min_valid)
            for key, v in bs.items():
                method, N, (kind_, sites) = key
                has = N in ref
                r = ref[N][(kind_, sites)] if has else float("nan")
                is_zne = method.startswith("zne_")
                sys_ok = bool(gate["passed"] and (heldout_ok if is_zne else True))
                a = assess(v["point"], v["lo"] - r, v["hi"] - r, r if has else None, v["lo"], v["hi"], eps,
                           reference_kind=kind if has else "none", systematics_validated=sys_ok, source="hardware")
                rows.append(dict(account=account, graph_id=pid, physical_id=patch.physical_id, n=patch.n, dt=prm.dt, N=N,
                                 Jt=N * prm.dt, method=method, selected_model=bool(is_zne and method == f"zne_{model}"),
                                 observable=kind_, sites="-".join(map(str, sites)), estimate=v["point"], ci_low=v["lo"],
                                 ci_high=v["hi"], se=v["se"], n_valid=v["n_valid"], B=v["B"], valid_fraction=v["valid_fraction"],
                                 failed_reason=reasons.get(key) or v["failed_reason"], reference=r, reference_kind=kind if has else "none",
                                 readout_independence_passed=gate["passed"], zne_heldout_validated=heldout_ok, source="hardware",
                                 **{k: a[k] for k in ("reference_status", "mitigation_valid", "signal_resolved",
                                                      "statistical_status", "systematics_validated")},
                                 trust_status=a["final_status"]))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if {1, 2} <= set(df.account):                                    # cross-account drift gates the verdict
        dr = drift_table(df[df.account == 1], df[df.account == 2], drift_zmax)
        flagged = dr[dr.drift_flag][["graph_id", "N", "method", "observable", "sites"]].assign(_drift=True)
        df = df.merge(flagged, on=["graph_id", "N", "method", "observable", "sites"], how="left")
        df["drift_flag"] = df.pop("_drift").fillna(False).astype(bool)
        demote = df.drift_flag & (df.trust_status == "supported")
        df.loc[demote, ["trust_status", "systematics_validated"]] = ["inconclusive", False]
        out = root / "raw/hardware"; dr.to_csv(out / "drift_account2_vs_1.csv", index=False)
    out = root / "raw/hardware"; out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "hardware_results.csv", index=False)
    return df
