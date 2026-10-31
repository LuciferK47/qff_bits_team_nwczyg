"""All figures regenerate from saved data under raw/ (no network, no QPU).

Conventions: frozen-dt data live in raw/classical_dt<dt>, raw/exact (*_dt<dt>.csv), raw/noisy_sim_dt<dt>; exploratory dt=0.2 data
are never plotted next to them. Every figure carries a provenance footer. Missing references and timed-out runs are drawn
explicitly (grey band / cross), never silently shortened."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .params import load_params

ROOT = Path(__file__).resolve().parents[2]
RAW, FIG = ROOT / "raw", ROOT / "figures"
CLASSES = [("m", "single-site m_i"), ("C", "edge covariance C_ij"), ("G", "4-site raw G"), ("kappa", "4-site cumulant κ")]
COL = {"coarse": "#e41a1c", "medium": "#ff7f00", "fine": "#a65628", "chi32": "#377eb8", "chi64": "#4daf4a",
       "chi128": "#984ea3", "chi256": "#333333"}
MET = {"raw": "#999999", "readout": "#377eb8", "zne_linear": "#4daf4a", "zne_richardson": "#984ea3", "zne_exp": "#e41a1c"}


def _dt() -> float:
    return load_params(ROOT / "configs/heavy_hex.yaml").dt


def _save(fig, name, provenance: str, folder: Path | None = None):
    folder = folder or FIG                      # resolved at call time (tests redirect FIG)
    folder.mkdir(parents=True, exist_ok=True)
    fig.text(0.005, 0.005, provenance, fontsize=6.5, color="#555555", ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(folder / name, dpi=140); plt.close(fig)


def _runs(folder: Path, pid: str):
    recs = []
    for f in sorted(folder.glob(f"{pid}_*_*.json")):
        if f.stem.endswith("_moments"):
            continue
        r = json.loads(f.read_text()); csv = f.with_suffix(".csv")
        r["_df"] = pd.read_csv(csv) if csv.exists() and csv.stat().st_size > 5 else pd.DataFrame()
        recs.append(r)
    return recs


# ------------------------------------------------------------------ Trotter error (dt = 0.2 exploratory vs frozen 0.1)
def trotter_errors():
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    for f in sorted((RAW / "exact").glob("P*_trotter_error_dt0.*.csv")):
        d = pd.read_csv(f)
        if "err_dt_vs_continuous" not in d:
            continue
        dt = f.stem.split("dt")[-1]; pid = f.stem.split("_")[0]
        ax.plot(d.Jt, d.err_dt_vs_continuous, "o-" if dt == "0.1" else "s--", label=f"{pid}  J·dt={dt}" + ("  (frozen)" if dt == "0.1" else "  (exploratory)"))
    ax.axhline(0.02, c="r", ls=":", label="0.02 target"); ax.set_xlabel("Jt"); ax.set_ylabel("max |circuit − exp(−iHt)| over the catalogue")
    ax.legend(fontsize=7); ax.set_title("Trotter error of the fixed circuit (exact, separate from every other error)")
    _save(fig, "trotter_error.png", "source: exact numerics (numpy kernel vs sparse expm_multiply), FakeFez-derived patches (offline)")


# ------------------------------------------------------------------ exact + approximate trajectories for a named cluster
def trajectories(pid: str, dt: float | None = None):
    dt = dt or _dt()
    f = RAW / "exact" / f"{pid}_trotter_kernel_dt{dt}.csv"
    if not f.exists():
        return
    ex = pd.read_csv(f); patch = json.loads((RAW / "patches" / f"{pid}.json").read_text())
    cluster = patch["clusters"][0]; centre, leaves = cluster[0], cluster[1:]
    key = "-".join(map(str, sorted(cluster)))
    sel = {"m": [str(q) for q in cluster], "C": ["-".join(map(str, sorted((centre, l)))) for l in leaves], "G": [key], "kappa": [key]}
    runs = _runs(RAW / f"classical_dt{dt}", pid)
    fig, ax = plt.subplots(1, 4, figsize=(15, 3.7))
    for a, (k, title) in zip(ax, CLASSES):
        for s in sel[k]:
            e = ex[(ex.observable == k) & (ex.sites.astype(str) == s)].sort_values("Jt")
            a.plot(e.Jt, e.value, "k-", lw=1.4, alpha=.8, label="exact" if s == sel[k][0] else None)
            for r in runs:
                if r["method"] == "mps" and r["setting"] in ("chi128", "chi256", "chi64") and len(r["_df"]):
                    d = r["_df"]; d = d[(d.observable == k) & (d.sites.astype(str) == s)].sort_values("Jt")
                    a.plot(d.Jt, d.estimate, ".", color=COL[r["setting"]], ms=5, label=f"MPS {r['setting']}" if s == sel[k][0] else None)
        a.axhline(0, c="k", lw=.4); a.set_title(f"{title}\ncluster {key}", fontsize=8); a.set_xlabel("Jt")
    ax[0].legend(fontsize=6)
    _save(fig, f"trajectories_{pid}.png", f"signed values for the predeclared cluster; exact = fixed Trotter circuit at J·dt={dt}; MPS = classical approximation (offline)")


# ------------------------------------------------------------------ classical accuracy with explicit gaps
def classical_accuracy(pids=("P12", "P18", "P24", "P40"), dt: float | None = None):
    dt = dt or _dt()
    for pid in pids:
        runs = _runs(RAW / f"classical_dt{dt}", pid)
        if not runs:
            continue
        fig, ax = plt.subplots(1, 4, figsize=(15, 3.7), sharey=True)
        for a, (k, title) in zip(ax, CLASSES):
            for r in runs:
                d = r["_df"]
                if not len(d):
                    continue
                d = d[(d.observable == k) & d.abs_err.notna()]
                e = d.groupby("Jt").abs_err.max()
                if len(e):
                    a.semilogy(e.index, e.values.clip(1e-9), "o-" if r["method"] == "mps" else "s--", color=COL.get(r["setting"]), ms=3,
                               label=f"{r['method']}:{r['setting']}")
                if r["error_status"] != "ok" and r.get("completed_N"):                       # killed / limited: mark where it stopped
                    a.axvline(max(r["completed_N"]) * dt, color=COL.get(r["setting"]), lw=.6, ls=":")
            ref_t = r.get("reference_times", []) if runs else []
            allt = sorted({t for r in runs for t in (r["_df"].Jt if len(r["_df"]) else [])})
            if ref_t and allt:
                last = max(ref_t) * dt
                if allt[-1] > last:
                    a.axvspan(last, allt[-1] * 1.02, color="#dddddd", alpha=.6)
                    a.text(last, 3e-9, " no exact\n reference", fontsize=6, va="bottom")
            a.axhline(0.02, c="r", ls=":", lw=1); a.set_title(title, fontsize=9); a.set_xlabel("Jt")
        ax[0].set_ylabel("max |error| vs exact fixed circuit"); ax[-1].legend(fontsize=6, ncol=2)
        fig.suptitle(f"{pid}: classical approximation vs exact (J·dt={dt}); red = 0.02; dotted verticals = run stopped (timeout/limit)", fontsize=9)
        _save(fig, f"classical_accuracy_{pid}.png", f"source: classical approximations (MPS/Pauli) vs exact fixed circuit; reference exists only in the un-shaded range (offline)")


# ------------------------------------------------------------------ P40 predictions beyond exact reach (UNVALIDATED)
def p40_predictions(dt: float | None = None, pid: str = "P40"):
    dt = dt or _dt()
    runs = _runs(RAW / f"classical_dt{dt}", pid)
    if not runs:
        return
    fig, ax = plt.subplots(1, 4, figsize=(15, 3.7))
    summ = {"m": ("mean m_i", lambda d: d.estimate.mean()), "C": ("mean |C_ij|", lambda d: d.estimate.abs().mean()),
            "G": ("max |G|", lambda d: d.estimate.abs().max()), "kappa": ("max |κ|", lambda d: d.estimate.abs().max())}
    for a, (k, (title, f)) in zip(ax, summ.items()):
        for r in runs:
            d = r["_df"]
            if not len(d):
                continue
            g = d[d.observable == k].groupby("Jt").apply(f, include_groups=False)
            if len(g):
                a.plot(g.index, g.values, "o-" if r["method"] == "mps" else "s--", color=COL.get(r["setting"]), ms=3, label=f"{r['method']}:{r['setting']}")
        a.set_title(title, fontsize=9); a.set_xlabel("Jt")
        a.axvspan(0.5 * dt * 10, a.get_xlim()[1], color="#eeeeee", alpha=.5, zorder=0)
    ax[-1].legend(fontsize=6, ncol=2)
    fig.suptitle(f"{pid}: approximate predictions — UNVALIDATED beyond the exact light-cone reference (grey); agreement between settings is the only check", fontsize=9)
    _save(fig, f"{pid}_predictions_unvalidated.png", "source: MPS/Pauli approximations, NO exact reference in the grey range; stability across chi is empirical evidence only")


# ------------------------------------------------------------------ resources
def resources(dt: float | None = None):
    dt = dt or _dt()
    rows = []
    for pid in ("P12", "P18", "P24", "P40"):
        for r in _runs(RAW / f"classical_dt{dt}", pid):
            if r.get("wall_s"):
                rows.append(dict(pid=pid, n=r["n"], method=r["method"], setting=r["setting"], status=r["error_status"], wall_s=r["wall_s"],
                                 cpu_s=r["cpu_s"], tree_gb=r["peak_tree_rss_bytes"] / 1e9, procs=r["max_processes"]))
    d = pd.DataFrame(rows)
    if not len(d):
        return d
    d.to_csv(RAW / f"classical_dt{dt}" / "resource_summary.csv", index=False)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for (m, s), g in d.groupby(["method", "setting"]):
        ok = g[g.status == "ok"]; bad = g[g.status != "ok"]
        for a in ax:
            a.scatter(ok.wall_s if a is ax[0] else ok.cpu_s, ok.tree_gb, s=15 + 4 * ok.n, color=COL.get(s), alpha=.8, label=f"{m}:{s}")
            a.scatter(bad.wall_s if a is ax[0] else bad.cpu_s, bad.tree_gb, s=15 + 4 * bad.n, color=COL.get(s), marker="x", alpha=.9)
    ax[0].set_xlabel("wall time [s]"); ax[1].set_xlabel("aggregate CPU time over all processes [s]")
    for a in ax:
        a.set_xscale("log"); a.set_ylabel("PEAK summed RSS of the whole process tree [GB]")
    ax[0].legend(fontsize=6, ncol=2); fig.suptitle("cost of the classical methods (marker size ~ n; × = killed at the budget / limit)", fontsize=9)
    _save(fig, "classical_resources.png", f"source: supervised runs (psutil whole-process-tree sampling), host: {rows and json.loads(next(iter((RAW / f'classical_dt{dt}').glob('P12_*_*.json'))).read_text()).get('host', {}).get('cpu', '?')}")
    return d


# ------------------------------------------------------------------ simulated-noise rehearsal
def rehearsal(pid="P12", dt: float | None = None):
    dt = dt or _dt()
    for f in sorted((RAW / f"noisy_sim_dt{dt}").glob(f"{pid}_*_results.csv")):
        d = pd.read_csv(f); variant = d.variant.iloc[0]
        held = d[(d.zne_role == "heldout") | (d.method.isin(["raw", "readout"]) & d.Jt.isin(d[d.zne_role == "heldout"].Jt.unique()))]
        fig, ax = plt.subplots(1, 4, figsize=(15, 3.7), sharey=True)
        for a, (k, title) in zip(ax, CLASSES):
            g = held[held.observable == k]
            names, rm, fails = [], [], []
            for m in MET:
                x = g[g.method == m]
                if not len(x):
                    continue
                fin = x[np.isfinite(x.estimate)]
                names.append(m); rm.append(np.sqrt((fin.error ** 2).mean()) if len(fin) else np.nan); fails.append(int((~np.isfinite(x.estimate)).sum()))
            a.bar(range(len(names)), rm, color=[MET[m] for m in names])
            for i, nf in enumerate(fails):
                if nf:
                    a.text(i, 0, f"{nf} failed", rotation=90, fontsize=6, va="bottom", ha="center")
            a.set_xticks(range(len(names))); a.set_xticklabels([n.replace("zne_", "ZNE\n") for n in names], fontsize=6); a.set_title(title, fontsize=9)
        ax[0].set_ylabel("RMSE vs exact at the HELD-OUT time")
        fig.suptitle(f"{pid} [{variant}] SIMULATED-NOISE rehearsal — NOT hardware; ZNE model chosen on calibration times only", fontsize=9)
        _save(fig, f"rehearsal_{pid}_{variant}.png", "source: Aer density-matrix simulation with FakeFez-derived noise (fractional variant: RZZ error = CZ error ASSUMED)")


def exact_overview(pids=("P12", "P18", "P24"), dt: float | None = None):
    dt = dt or _dt()
    fig, a = plt.subplots(figsize=(5.4, 3.5)); any_ = False
    for pid in pids:
        f = RAW / "exact" / f"{pid}_trotter_kernel_dt{dt}.csv"
        if f.exists():
            g = pd.read_csv(f).query("observable=='M'").sort_values("Jt"); a.plot(g.Jt, g.value, "o-", label=pid); any_ = True
    if any_:
        a.axhline(0, c="k", lw=.5); a.set_xlabel("Jt"); a.set_ylabel("M(t)"); a.legend(); a.set_title("mean magnetisation, exact fixed circuit")
        _save(fig, "magnetisation.png", f"source: exact numpy kernel at J·dt={dt} (offline)")
    else:
        plt.close(fig)


# ------------------------------------------------------------------ real hardware (ibm_fez, two accounts); offline from raw/hardware
ACC = {1: "#1b7837", 2: "#762a83"}
HWNOTE = ("source: IBM ibm_fez, accounts 1 (30 Oct) and 2 (31 Oct), pre-registered manifest; exact = fixed Trotter circuit at J·dt=0.1; "
          "intervals = joint bootstrap B=2000")


def _hw():
    f = RAW / "hardware" / "hardware_results.csv"
    return pd.read_csv(f) if f.exists() else None


def hw_trajectories(pid: str = "P18"):
    h = _hw()
    if h is None:
        return
    dt = _dt(); ex = pd.read_csv(RAW / "exact" / f"{pid}_trotter_kernel_dt{dt}.csv"); patch = json.loads((RAW / "patches" / f"{pid}.json").read_text())
    cl = patch["clusters"][0]; key = "-".join(map(str, sorted(cl)))
    sel = {"M": [""], "m": [str(cl[0])], "C": ["-".join(map(str, sorted((cl[0], cl[1]))))], "G": [key], "kappa": [key]}
    fig, ax = plt.subplots(1, 5, figsize=(17, 3.8))
    for a, (k, title) in zip(ax, [("M", "mean magnetisation M")] + [(c, t) for c, t in CLASSES]):
        s_ = sel[k][0]
        e = ex[(ex.observable == k) & (ex.sites.fillna("").astype(str) == s_)].sort_values("Jt")
        a.plot(e.Jt, e.value, "k-", lw=1.3, label="exact")
        for acct in (1, 2):
            for meth, mk, off in (("raw", "o", -0.04), ("readout", "s", 0.04)):
                d = h[(h.graph_id == pid) & (h.account == acct) & (h.method == meth) & (h.observable == k) & (h.sites.fillna("").astype(str) == s_)].sort_values("Jt")
                if len(d):
                    a.errorbar(d.Jt + off + (0.02 if acct == 2 else 0), d.estimate, yerr=[d.estimate - d.ci_low, d.ci_high - d.estimate], fmt=mk, ms=3,
                               color=ACC[acct], alpha=.85 if meth == "readout" else .45, lw=.8, label=f"acct {acct} {meth}")
        a.axhline(0, c="k", lw=.4); a.set_xlabel("Jt"); a.set_title(f"{title}\n{'' if not s_ else 'sites ' + s_}", fontsize=8)
    ax[0].legend(fontsize=6, ncol=2)
    fig.suptitle(f"{pid} on ibm_fez: raw and readout-corrected estimates with 95% intervals vs the exact fixed circuit (predeclared cluster {key})", fontsize=9)
    _save(fig, f"hardware_{pid}_trajectories.png", HWNOTE)


def hw_class_error():
    f = ROOT / "reports" / "hardware_class_table.csv"
    if not f.exists():
        return
    t = pd.read_csv(f); t = t[(t.graph_id == "P18") & (t.method == "readout")]
    fig, ax = plt.subplots(1, 4, figsize=(15, 3.7), sharey=True)
    for a, (k, title) in zip(ax, CLASSES):
        for acct in (1, 2):
            g = t[(t.observable == k) & (t.account == acct)].sort_values("Jt")
            a.plot(g.Jt, g.median_abs_error, "o-", color=ACC[acct], ms=3, label=f"acct {acct}: median |error|")
            a.plot(g.Jt, g.median_ci_halfwidth, ":", color=ACC[acct], label=f"acct {acct}: median CI half-width")
        g = t[(t.observable == k) & (t.account == 1)].sort_values("Jt")
        a.plot(g.Jt, g.median_abs_reference, "k--", lw=1, label="median |exact value| (signal)")
        a.axhline(0.05, c="r", ls=":", lw=1); a.set_title(title, fontsize=9); a.set_xlabel("Jt"); a.set_yscale("symlog", linthresh=1e-3)
    ax[0].set_ylabel("absolute quantity (symlog)"); ax[0].legend(fontsize=5.5)
    fig.suptitle("P18 hardware, readout-corrected: error vs signal size vs interval width by class (red = 0.05 policy tolerance). "
                 "A class is unresolvable where its signal falls below the interval width, not necessarily where its error is large", fontsize=8.5)
    _save(fig, "hardware_class_error_vs_signal.png", HWNOTE)


def hw_zne_heldout():
    f = ROOT / "reports" / "hardware_heldout_zne.csv"
    if not f.exists():
        return
    t = pd.read_csv(f); order = ["raw", "readout", "zne_linear", "zne_exp", "zne_richardson"]
    fig, ax = plt.subplots(figsize=(7.5, 3.9)); w = .38
    for i, acct in enumerate((1, 2)):
        g = t[t.account == acct].set_index("method").reindex(order)
        xs = np.arange(len(order)) + (i - .5) * w
        ax.bar(xs, g.rmse, w, color=ACC[acct], label=f"account {acct}")
        for x, (m, r) in zip(xs, g.iterrows()):
            if r.selected:
                ax.text(x, r.rmse, "selected", rotation=90, fontsize=6, ha="center", va="bottom")
    ax.axhline(0.05, c="r", ls=":", label="pre-declared limit 0.05"); ax.set_xticks(range(len(order))); ax.set_xticklabels([o.replace("zne_", "ZNE ") for o in order])
    ax.set_ylabel("held-out RMSE vs exact\n(P18, Jt = 0.8, 45 observables)"); ax.legend(fontsize=7)
    ax.set_title("ZNE FAILED its held-out check on both accounts (selected model is worse than the raw estimate)", fontsize=9)
    _save(fig, "hardware_zne_heldout.png", HWNOTE)


def hw_drift():
    f = RAW / "hardware" / "drift_account2_vs_1.csv"
    if not f.exists():
        return
    d = pd.read_csv(f); d = d[d.method.isin(["raw", "readout"])]
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 4.4))
    for a, pid in zip(ax, ("P18", "P40")):
        g = d[d.graph_id == pid]
        a.scatter(g.estimate_1[~g.drift_flag], g.estimate_2[~g.drift_flag], s=6, c="#999999", label="|z| <= 4")
        a.scatter(g.estimate_1[g.drift_flag], g.estimate_2[g.drift_flag], s=8, c="#d95f02", label="|z| > 4 (flagged)")
        a.plot([-1, 1], [-1, 1], "k-", lw=.6); a.set_xlabel("account 1 estimate"); a.set_ylabel("account 2 estimate"); a.set_title(f"{pid} (raw and readout rows)", fontsize=9)
    ax[0].legend(fontsize=7)
    fig.suptitle(f"Window-to-window drift: {int(d.drift_flag.sum())}/{len(d)} raw/readout comparisons exceed 4 shot-noise SEs. "
                 "The comparisons share circuits and calibrations (correlated), so this is not 650 independent tests", fontsize=8.5)
    _save(fig, "hardware_drift.png", HWNOTE)


def hw_readout_z():
    f = ROOT / "reports" / "readout_independence.csv"
    if not f.exists():
        return
    t = pd.read_csv(f); t = t[t.patch == "P18"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 3.8), sharey=True)
    for a, acct in zip(ax, (1, 2)):
        g = t[t.account == acct].sort_values("abs_z", ascending=False)
        cols = ["#d95f02" if e else ACC[acct] for e in g.exceeds_prespecified_4]
        a.bar(range(len(g)), g.abs_z, color=cols)
        a.set_xticks(range(len(g))); a.set_xticklabels(g.physical_pair, rotation=90, fontsize=6)
        a.axhline(4, c="r", ls=":"); a.set_title(f"account {acct}: |z| per coupled pair (physical qubits)", fontsize=9)
    ax[0].set_ylabel("|z| of flip correlation (calibration states)")
    fig.suptitle("P18 readout independence: only physical pair 16-23 on account 2 exceeds the pre-specified |z| < 4 (mechanism not established)", fontsize=9)
    _save(fig, "hardware_readout_independence.png", HWNOTE)


def hw_resources():
    f = RAW.parent / "resources.csv"
    if not f.exists():
        return
    r = pd.read_csv(f); j = r[r.kind == "hardware_job"]; c = r[r.kind == "hardware_circuit"]
    if not len(j):
        return
    fig, ax = plt.subplots(1, 2, figsize=(12, 3.8))
    lab = [f"{s[-1]}:{m[0]}" for s, m in zip(j.setting, j.method)]
    x = np.arange(len(j)); ax[0].bar(x - .2, j.estimated_qpu_s, .4, label="estimate before submission"); ax[0].bar(x + .2, j.observed_qpu_s, .4, label="reported usage")
    ax[0].set_xticks(x); ax[0].set_xticklabels([f"acct {s[-1]}\n{m}" for s, m in zip(j.setting, j.method)], fontsize=7); ax[0].set_ylabel("QPU seconds")
    ax[0].set_title(f"six jobs: {j.observed_qpu_s.sum():.0f} s reported of the 600 s team limit", fontsize=9); ax[0].legend(fontsize=7)
    ax[1].hist(c.compiled_2q_depth, bins=range(0, 170, 10), color="#4575b4"); ax[1].axvline(100, c="orange", ls=":", label="aim 100"); ax[1].axvline(300, c="r", ls=":", label="ceiling 300")
    ax[1].set_xlabel("compiled two-qubit depth"); ax[1].set_ylabel("executed circuits"); ax[1].legend(fontsize=7)
    ax[1].set_title(f"56 executed circuits, max depth {int(c.compiled_2q_depth.max())}", fontsize=9)
    _save(fig, "hardware_resources.png", "source: resources.csv hardware_job / hardware_circuit rows (saved job usage; live-compiled QPY files)")


def hw_p40():
    h = _hw()
    if h is None:
        return
    dt = _dt(); runs = _runs(RAW / f"classical_dt{dt}", "P40")
    fig, ax = plt.subplots(1, 4, figsize=(15, 3.7))
    summ = {"m": ("mean m_i", lambda d: d.estimate.mean()), "C": ("mean |C_ij|", lambda d: d.estimate.abs().mean()),
            "G": ("max |G|", lambda d: d.estimate.abs().max()), "kappa": ("max |κ|", lambda d: d.estimate.abs().max())}
    for a, (k, (title, fn)) in zip(ax, summ.items()):
        for r in runs:
            if r["setting"] in ("chi256", "medium") and len(r["_df"]):
                g = r["_df"][r["_df"].observable == k].groupby("Jt").apply(fn, include_groups=False)
                a.plot(g.index, g.values, "-", color=COL.get(r["setting"]), lw=1, label=f"{r['method']}:{r['setting']} (approximation)")
        for acct in (1, 2):
            d = h[(h.graph_id == "P40") & (h.account == acct) & (h.method == "readout") & (h.observable == k)]
            g = d.groupby("Jt").apply(fn, include_groups=False)
            a.plot(g.index, g.values, "o", ms=4, color=ACC[acct], label=f"hardware acct {acct} readout")
        a.axvspan(0.45, a.get_xlim()[1], color="#eeeeee", alpha=.5, zorder=0); a.set_title(title, fontsize=9); a.set_xlabel("Jt")
    ax[0].legend(fontsize=6)
    fig.suptitle("P40: hardware vs classical approximations. NO exact reference beyond Jt = 0.5 (grey): disagreement there cannot say which side is right", fontsize=9)
    _save(fig, "hardware_P40_vs_classical_unvalidated.png", HWNOTE + "; approximations are unvalidated in the grey range")


def hz_reversal():
    f = RAW / "exact" / "P12_hz_reversal_dt0.1.csv"
    if not f.exists():
        return
    d = pd.read_csv(f); fig, a = plt.subplots(figsize=(5.8, 3.6))
    a.plot(d.Jt, d.M, "o-", label=f"hz = {d.hz.iloc[0]}"); a.plot(d.Jt, d.M_reversed, "s--", label=f"hz = {d.hz_reversed.iloc[0]} (reversed)")
    a.set_xlabel("Jt"); a.set_ylabel("M(t)"); a.legend(); a.axhline(0, c="k", lw=.4)
    a.set_title(f"P12, exact fixed circuit: reversing hz changes M by up to {d.contrast.abs().max():.2f}", fontsize=9)
    _save(fig, "hz_reversal_P12.png", "source: exact numpy kernel at J·dt=0.1 (offline); same J, hx, dt, only the sign of hz differs")


def cumulant_bias_fig():
    f = ROOT / "reports" / "cumulant_bias_exact.csv"
    if not f.exists():
        return
    t = pd.read_csv(f); fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    for jt, g in t.groupby("Jt"):
        ax[0].plot(g.observable, g.max_abs_bias, "o-", label=f"Jt={jt}"); ax[1].plot(g.observable, g.bootstrap_coverage, "o-", label=f"Jt={jt}")
    ax[0].set_ylabel("max |mean bias| over observables"); ax[0].set_yscale("log"); ax[1].axhline(0.95, c="r", ls=":"); ax[1].set_ylabel("coverage of 95% bootstrap interval")
    ax[1].set_ylim(0.5, 1.02); ax[0].legend(fontsize=7)
    fig.suptitle("Estimator check on the EXACT P18 distribution (16 384 shots, no noise): finite-shot bias and bootstrap coverage by class", fontsize=9)
    _save(fig, "cumulant_bias_exact.png", "source: sampling the exact fixed-circuit distribution; validates the estimator, not the device")


def hardware_figures():
    hw_trajectories("P18"); hw_class_error(); hw_zne_heldout(); hw_drift(); hw_readout_z(); hw_resources(); hw_p40()


def all_figures():
    trotter_errors(); exact_overview()
    for pid in ("P12", "P18", "P24"):
        trajectories(pid)
    classical_accuracy(); p40_predictions(); resources()
    hardware_figures(); hz_reversal(); cumulant_bias_fig()
    for pid in ("P12",):
        rehearsal(pid)


if __name__ == "__main__":
    all_figures()
