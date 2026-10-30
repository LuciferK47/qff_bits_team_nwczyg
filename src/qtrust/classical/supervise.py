"""Supervised execution of one (patch, method, setting) run.

Each run executes in its OWN child process (spawn). The parent samples the whole process tree (Pauli propagation
uses a worker pool) with psutil and records wall time, aggregate CPU time, the PEAK of the SUMMED resident memory of
all live processes and the maximum number of processes. A wall-clock budget is enforced by killing the whole tree
(a hard limit, unlike a cooperative deadline). Partial results survive the kill through per-time checkpoints.
"""
from __future__ import annotations

import os
import pickle
import subprocess
import sys
import shutil
import tempfile
import time
import traceback
from pathlib import Path

import psutil

from ..moments import Catalog
from . import mps as mps_mod
from . import pauli as pauli_mod


def child_main(spec_path: str, out_path: str) -> None:
    spec = pickle.load(open(spec_path, "rb"))
    try:
        if spec["method"] == "pauli_prop":
            res = pauli_mod.run(spec["patch"], spec["prm"], spec["Ns"], spec["pauli_setting"], workers=spec["workers"],
                                cat=spec["cat"], ckpt_dir=spec["ckpt"])
        elif spec["method"] == "mps":
            res = mps_mod.run(spec["patch"], spec["prm"], spec["Ns"], spec["chi"], cutoff=spec["cutoff"],
                              cat=spec["cat"], ckpt_path=spec["ckpt"])
        else:
            raise ValueError(spec["method"])
        out = ("ok", res)
    except BaseException as e:                                       # report, never crash silently
        out = ("error", repr(e), traceback.format_exc())
    pickle.dump(out, open(out_path, "wb"))


def _kill_tree(p: psutil.Process) -> None:
    try:
        kids = p.children(recursive=True)
    except psutil.NoSuchProcess:
        kids = []
    for k in kids + [p]:
        try:
            k.kill()
        except psutil.NoSuchProcess:
            pass


def _supervise(proc: subprocess.Popen, budget_s: float, mem_limit: float, sample_s: float):
    ps = psutil.Process(proc.pid)
    t0 = time.time()
    peak, max_procs, samples, reason = 0, 1, 0, None
    cpu: dict[int, float] = {}
    while proc.poll() is None:
        try:
            tree = [ps] + ps.children(recursive=True)
        except psutil.NoSuchProcess:
            break
        rss = 0
        for q in tree:
            try:
                rss += q.memory_info().rss
                t = q.cpu_times()
                cpu[q.pid] = t.user + t.system
            except psutil.NoSuchProcess:
                pass
        peak, max_procs, samples = max(peak, rss), max(max_procs, len(tree)), samples + 1
        if time.time() - t0 > budget_s:
            reason = "timed_out_killed"
        elif rss > mem_limit:
            reason = "memory_limited"
        if reason:
            _kill_tree(ps)
            break
        try:
            proc.wait(sample_s)
        except subprocess.TimeoutExpired:
            pass
    proc.wait()
    return dict(wall_s=time.time() - t0, cpu_s=float(sum(cpu.values())), peak_tree_rss_bytes=int(peak),
                max_processes=int(max_procs), n_samples=samples, exit_reason=reason)


def run_method(patch, prm, Ns, method: str, setting, budget_s: float, workers: int = 12, cat: Catalog | None = None,
               mem_limit_fraction: float = 0.8, sample_s: float = 0.5, cutoff: float = 1e-12, workdir: str | None = None):
    """Run one method/setting under supervision. Returns (obs, mu, stats, supervision).

    ``setting`` is a pauli_prop.PauliSetting for method 'pauli_prop' or an integer bond dimension for 'mps'.
    supervision['exit_reason'] in {'ok', 'timed_out_killed', 'memory_limited', 'failed'}.
    """
    cat = cat or Catalog.from_patch(patch)
    own = workdir is None
    work = Path(workdir or tempfile.mkdtemp(prefix="qtrust_run_"))
    work.mkdir(parents=True, exist_ok=True)
    spec_path, out_path = str(work / "spec.pkl"), str(work / "out.pkl")
    ckpt = str(work / ("ckpt" if method == "pauli_prop" else "ckpt.json"))
    spec = dict(method=method, patch=patch, prm=prm, Ns=list(Ns), workers=workers, ckpt=ckpt, cutoff=cutoff, cat=cat)
    if method == "pauli_prop":
        spec["pauli_setting"] = setting
        os.makedirs(ckpt, exist_ok=True)
    else:
        spec["chi"] = int(setting)
    pickle.dump(spec, open(spec_path, "wb"))
    # a clean interpreter running `python -m qtrust.classical.supervise`: never re-imports the caller's __main__
    proc = subprocess.Popen([sys.executable, "-m", "qtrust.classical.supervise", spec_path, out_path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    sup = _supervise(proc, budget_s, psutil.virtual_memory().total * mem_limit_fraction, sample_s)
    sup.update(budget_s=budget_s, sample_s=sample_s, workers=workers if method == "pauli_prop" else 1)

    obs = mu = stats = None
    err = proc.stderr.read() if proc.stderr else ""
    if os.path.exists(out_path):
        res = pickle.load(open(out_path, "rb"))
        if res[0] == "ok":
            obs, mu, stats = res[1]
            sup["exit_reason"] = "ok"
        else:
            sup["exit_reason"], sup["detail"] = "failed", res[1]
    if obs is None and sup["exit_reason"] in ("timed_out_killed", "memory_limited"):
        if method == "pauli_prop":
            obs, mu, stats = pauli_mod.from_checkpoints(patch, ckpt, Ns, setting, workers, sup["wall_s"], cat, budget_s)
        else:
            obs, mu, diag = mps_mod.from_checkpoint(ckpt, cat)
            stats = dict(chi=int(setting), cutoff=cutoff, elapsed_s=sup["wall_s"], budget_s=budget_s,
                         completed_N=sorted(obs), fidelity_estimate=diag["fid"],
                         error_estimate={N: 1 - f for N, f in diag["fid"].items()}, max_bond=diag["max_bond"])
        stats["timed_out"] = True
    elif obs is None:
        obs, mu, stats = {}, {}, {}
        sup["exit_reason"], sup["detail"] = "failed", (err[-2000:] or f"child exited with code {proc.returncode}")
    if sup["exit_reason"] is None:
        sup["exit_reason"] = "failed"
    if own:
        shutil.rmtree(work, ignore_errors=True)
    return obs, mu, stats, sup


if __name__ == "__main__":
    child_main(sys.argv[1], sys.argv[2])
