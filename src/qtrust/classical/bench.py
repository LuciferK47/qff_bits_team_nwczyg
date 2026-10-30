"""Accuracy / runtime / memory benchmark of the classical methods against exact references."""
from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import os
import platform
from pathlib import Path

import numpy as np
import pandas as pd

from .. import exact
from ..moments import Catalog
from ..params import Params
from . import mps as mps_mod
from . import pauli as pauli_mod


def host_info() -> dict:
    cpu = "unknown"
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except Exception:
        pass
    return dict(cpu=cpu, logical_cores=os.cpu_count(), gpu="none used", platform=platform.platform(),
                python=platform.python_version())


def _ref_path(cache_dir: Path, patch, prm: Params) -> Path:
    return cache_dir / f"{patch.pid}_reference_dt{prm.dt}.json"


def _ref_meta(patch, prm: Params) -> dict:
    return dict(physical_id=patch.physical_id, J=prm.J, hx=prm.hx, hz=prm.hz, dt=prm.dt)


def _ref_load(path: Path, meta: dict):
    if not path.exists():
        return {}
    d = json.loads(path.read_text())
    if d.get("meta") != meta:                       # different patch/parameters: never reuse
        return {}
    return {int(N): {(k, tuple(int(x) for x in s.split("-")) if s else ()): v for k, s, v in rows}
            for N, rows in d["obs"].items()}, d.get("kind", {})


def reference(patch, prm: Params, Ns, cat: Catalog, full_max_n: int = 24, cache_dir: Path | None = None,
              max_qubits: int = 26):
    """({N: {label: value}}, kind) with kind 'full_exact' (n <= full_max_n) or 'lightcone_exact' (only the times whose
    light cone fits in ``max_qubits``). With ``cache_dir`` every finished time is stored immediately and reused."""
    kind = "full_exact" if patch.n <= full_max_n else "lightcone_exact"
    cached: dict = {}
    path = _ref_path(cache_dir, patch, prm) if cache_dir else None
    meta = _ref_meta(patch, prm)
    if path:
        loaded = _ref_load(path, meta)
        cached = loaded[0] if loaded else {}

    def store():
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(dict(meta=meta, kind=kind, obs={
                str(N): [[k, "-".join(map(str, s)), v] for (k, s), v in o.items()] for N, o in cached.items()})))

    todo = [N for N in sorted(set(Ns)) if N not in cached]
    if todo and patch.n <= full_max_n:
        pats = exact.all_patterns(patch.n)
        for N, psi in exact.iter_trotter_states(patch, prm, todo):
            cached[N] = cat.from_patterns(pats, exact.probs(psi)); store()
    elif todo:
        groups = [(q,) for q in range(patch.n)] + [tuple(e) for e in patch.edges] + [tuple(sorted(c)) for c in cat.clusters]
        for N in todo:
            try:
                mu, _ = exact.lightcone_moments(patch, prm, N, groups, max_qubits=max_qubits)
            except MemoryError:
                continue                            # light cone too big at this time: no exact reference there
            cached[N] = cat.evaluate(mu); store()
    return {N: cached[N] for N in sorted(set(Ns)) if N in cached}, kind


def compare(patch, prm, obs, ref, method, setting, ref_kind: str = "none") -> pd.DataFrame:
    """One row per completed (N, observable). Times WITHOUT an exact reference are kept, with
    reference/abs_err = NaN, reference_kind = 'none' and validation_status = 'no_reference'."""
    rows = []
    for N, o in obs.items():
        has_ref = N in ref
        for key, est in o.items():
            r = ref[N][key] if has_ref else float("nan")
            rows.append(dict(graph_id=patch.pid, n=patch.n, dt=prm.dt, N=N, Jt=N * prm.J * prm.dt, method=method,
                             setting=setting, observable=key[0], sites="-".join(map(str, key[1])), estimate=est,
                             reference=r, abs_err=abs(est - r) if has_ref else float("nan"),
                             reference_kind=ref_kind if has_ref else "none",
                             validation_status="exact_reference" if has_ref else "no_reference"))
    return pd.DataFrame(rows)


def run_hash(patch, prm: Params, Ns, method: str, setting: str, budget_s) -> str:
    """Content hash of everything that determines a run's result; used to decide whether a saved run is reusable."""
    versions = {}
    for pkg in ("qiskit", "quimb", "pauli-prop", "numpy", "scipy"):
        try:
            versions[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            versions[pkg] = None
    payload = dict(nodes=list(patch.nodes), edges=[list(e) for e in patch.edges], J=prm.J, hx=prm.hx, hz=prm.hz,
                   dt=prm.dt, Ns=sorted(set(Ns)), method=method, setting=str(setting), budget_s=budget_s,
                   versions=versions)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _reusable(path: Path, rhash: str) -> bool:
    """A saved record suppresses recomputation only if it is complete (ok/timed_out) AND from identical inputs."""
    if not path.exists():
        return False
    try:
        rec = json.loads(path.read_text())
    except json.JSONDecodeError:
        return False
    return rec.get("run_hash") == rhash and rec.get("error_status") in ("ok", "timed_out", "memory_limited")


def class_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Max abs error per observable class (m, M, C, G, kappa) per method/setting/time."""
    g = df.groupby(["graph_id", "method", "setting", "Jt", "observable"]).abs_err.max().unstack("observable")
    return g.round(5)


def _save(out: Path, pid: str, method: str, setting: str, df: pd.DataFrame, res: dict, moments=None):
    tag = f"{pid}_{method}_{setting}"
    df.to_csv(out / f"{tag}.csv", index=False)
    if moments is not None:                       # raw parity moments, independent of reference availability
        (out / f"{tag}_moments.json").write_text(json.dumps(
            {str(N): {"-".join(map(str, S)) or "empty": v for S, v in m.items()} for N, m in moments.items()}))
    (out / f"{tag}.json").write_text(json.dumps(res, indent=1, default=str))


def run_all(patch, prm: Params, Ns, pauli_settings, mps_chis, out: Path, workers: int = 12, ref=None, ref_tag=None,
            budget_s: float | None = None, skip_done: bool = True, supervised: bool = True,
            ref_cache: Path | None = None, ref_Ns=None):
    """Run every (method, setting); each one is saved the moment it finishes, failures included.

    ``supervised`` (default) runs each setting in its own process under a HARD wall-clock budget with whole-process-
    tree memory/CPU accounting (``classical.supervise``). Only the *computation* sits inside the try/except; building
    and saving the record is outside it, so a bookkeeping bug can never be mislabelled as a failed simulation.
    ``ref_Ns`` (default: Ns) are the times for which an exact reference is attempted.
    """
    from . import supervise
    out.mkdir(parents=True, exist_ok=True)
    cat = Catalog.from_patch(patch)
    if ref is None:
        ref, ref_tag = reference(patch, prm, ref_Ns if ref_Ns is not None else Ns, cat, cache_dir=ref_cache)
    base = dict(graph_id=patch.pid, physical_id=patch.physical_id, n=patch.n, dt=prm.dt, J=prm.J, hx=prm.hx, hz=prm.hz,
                reference=ref_tag, reference_times=sorted(ref), host=host_info())
    for method, settings in (("pauli_prop", pauli_settings), ("mps", mps_chis)):
        for st_name in settings:
            name = st_name if method == "pauli_prop" else f"chi{st_name}"
            rhash = run_hash(patch, prm, Ns, method, name, budget_s)
            if skip_done and _reusable(out / f"{patch.pid}_{method}_{name}.json", rhash):
                continue
            obs = st = mu = sup = failure = None
            try:
                setting = pauli_mod.SETTINGS[st_name] if method == "pauli_prop" else int(st_name)
                if supervised:
                    obs, mu, st, sup = supervise.run_method(patch, prm, Ns, method, setting, budget_s or 1200.0,
                                                            workers=workers, cat=cat)
                elif method == "pauli_prop":
                    obs, mu, st = pauli_mod.run(patch, prm, Ns, setting, workers=workers, cat=cat, budget_s=budget_s)
                else:
                    obs, mu, st = mps_mod.run(patch, prm, list(Ns), setting, cutoff=1e-12, cat=cat, budget_s=budget_s)
            except MemoryError as e:
                failure = ("memory_limited", repr(e))
            except Exception as e:
                failure = ("failed", repr(e))
            if failure is None and sup is not None and sup["exit_reason"] in ("failed",):
                failure = ("failed", sup.get("detail", "child process failed"))
            if failure:
                rec = {**base, "method": method, "setting": name, "run_hash": rhash, "error_status": failure[0],
                       "detail": failure[1], **({"supervision": sup} if sup else {})}
                _save(out, patch.pid, method, name, pd.DataFrame(), rec)
                continue
            status = ("timed_out" if (sup and sup["exit_reason"] == "timed_out_killed") or st.get("timed_out") else
                      "memory_limited" if sup and sup["exit_reason"] == "memory_limited" else "ok")
            rec = {**base, **st, "method": method, "setting": name, "run_hash": rhash, "error_status": status,
                   **({"supervision": sup, "wall_s": sup["wall_s"], "cpu_s": sup["cpu_s"],
                       "peak_tree_rss_bytes": sup["peak_tree_rss_bytes"], "max_processes": sup["max_processes"],
                       "exit_reason": sup["exit_reason"]} if sup else {})}
            _save(out, patch.pid, method, name, compare(patch, prm, obs, ref, method, name, ref_tag), rec, mu)


def collect(out: Path, pid: str):
    """(all error rows, list of resource records) for one patch from the incrementally saved files."""
    frames = [pd.read_csv(f) for f in sorted(out.glob(f"{pid}_*_*.csv")) if f.stat().st_size > 5]
    res = [json.loads(f.read_text()) for f in sorted(out.glob(f"{pid}_*_*.json")) if not f.stem.endswith("_moments")]
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), res
