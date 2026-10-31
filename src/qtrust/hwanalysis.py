"""Post-hoc analyses of the saved hardware data (offline, read-only on raw/hardware).

EXPLORATORY / DESCRIPTIVE ONLY: nothing here changes a frozen ``trust_status``, ``readout_independence_passed`` or any
pre-registered threshold. Outputs go to reports/ (small CSVs a judge can open)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
HW = ROOT / "raw" / "hardware"


def _two_sided_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


# ------------------------------------------------------------------ 1. readout independence, per physical pair
def readout_diagnostic(root: Path = ROOT) -> tuple[pd.DataFrame, pd.DataFrame]:
    from . import mitigation as mit
    from .params import load_params
    from .rehearsal import readout_gate
    from .submit import assemble
    from .validate import load_patch
    prm = load_params(root / "configs/heavy_hex.yaml")
    pair_rows, qubit_rows = [], []
    for a in (1, 2):
        lc = json.loads((root / "raw/hardware" / f"account{a}" / "live_check.json").read_text())
        for pid in ("P18", "P40"):
            patch = load_patch(pid, root / "raw/patches")
            data = assemble(root, a, pid, prm)
            nodes = lc[f"{pid}_physical_nodes"]
            preps = mit.structured_preps(patch.edges, patch.n)
            gate = readout_gate(data, preps, patch)
            e0, e1 = mit.assignment_rates(data["cal"], preps)
            for q in range(patch.n):
                qubit_rows.append(dict(account=a, patch=pid, logical=q, physical=nodes[q], e0=float(e0[q]), e1=float(e1[q])))
            n_edges = len(patch.edges)
            for (u, v) in patch.edges:
                z = gate["z"][f"{u}-{v}"]
                per_prep = []
                for counts, prep in zip(data["cal"], preps):
                    per_prep.append(mit.readout_flip_correlations([counts], [prep], [(u, v)])[(u, v)])
                p = _two_sided_p(z)
                pair_rows.append(dict(
                    account=a, patch=pid, logical_pair=f"{u}-{v}", physical_pair=f"{nodes[u]}-{nodes[v]}", z_pooled=z,
                    z_prep_all0=per_prep[0], z_prep_all1=per_prep[1], z_prep_checker_a=per_prep[2], z_prep_checker_b=per_prep[3],
                    abs_z=abs(z), p_two_sided=p, p_bonferroni=min(1.0, p * n_edges), n_edges_tested=n_edges,
                    residual_pair_vs_product=gate["residual"][f"{u}-{v}"], exceeds_prespecified_4=abs(z) >= gate["z_max"]))
    pairs = pd.DataFrame(pair_rows).sort_values(["account", "patch", "abs_z"], ascending=[True, True, False])
    qubits = pd.DataFrame(qubit_rows)
    return pairs, qubits


# ------------------------------------------------------------------ 2. per-class table (accuracy vs signal vs resolution)
def class_table(root: Path = ROOT) -> pd.DataFrame:
    """Per patch / account / method / time / class. The verdict fractions are shown next to a verdict-free agreement rate
    (|estimate - exact| <= the 0.05 policy tolerance) so that systematics gates and drift demotions do not masquerade
    as a class effect."""
    from .trust import load_policy
    eps = load_policy(root / "configs/trust_policy.yaml")["tolerances_abs"]["hardware_vs_exact"]
    h = pd.read_csv(root / "raw/hardware/hardware_results.csv")
    h = h[h.method.isin(["raw", "readout"]) & (h.reference_kind != "none")].copy()
    h["err"] = (h.estimate - h.reference).abs()
    h["half_ci"] = (h.ci_high - h.ci_low) / 2
    h["abs_ref"] = h.reference.abs()
    h["agree"] = h.err <= eps
    h["zero_ok"] = h.abs_ref <= eps                    # a predictor that always says 0 would also be "within tolerance" here

    def agg(g):
        return pd.Series(dict(
            n=len(g), median_abs_reference=g.abs_ref.median(), median_abs_error=g.err.median(), max_abs_error=g.err.max(),
            median_ci_halfwidth=g.half_ci.median(), n_signal_resolved=int(g.signal_resolved.sum()),
            n_within_tolerance=int(g.agree.sum()), n_zero_predictor_within_tolerance=int(g.zero_ok.sum()), n_supported=int((g.trust_status == "supported").sum()),
            n_inconsistent=int((g.trust_status == "inconsistent").sum()), n_inconclusive=int((g.trust_status == "inconclusive").sum())))
    t = h.groupby(["graph_id", "account", "method", "Jt", "observable"]).apply(agg, include_groups=False).reset_index()
    t["tolerance"] = eps
    return t


# ------------------------------------------------------------------ 3. held-out ZNE
def heldout_table(root: Path = ROOT) -> pd.DataFrame:
    """P18, held-out Jt = 0.8, every catalogue observable (all of m_i, M, edge C_ij and the cluster G/kappa)."""
    h = pd.read_csv(root / "raw/hardware/hardware_results.csv")
    h = h[(h.graph_id == "P18") & (h.Jt.round(6) == 0.8) & (h.reference_kind != "none")].copy()
    rows = []
    for (acct, method), g in h.groupby(["account", "method"]):
        fin = g[np.isfinite(g.estimate)]
        e = fin.estimate - fin.reference
        rows.append(dict(account=acct, method=method, selected=bool(g.selected_model.any()), n_observables=len(g), n_finite=len(fin),
                         rmse=float(np.sqrt(np.mean(e ** 2))), mean_signed_error=float(e.mean()), max_abs_error=float(e.abs().max()),
                         limit=0.05, passes_predeclared_limit=bool(np.sqrt(np.mean(e ** 2)) <= 0.05),
                         predicate="P18, Jt=0.8, all catalogue observables (m, M, C, G, kappa), exact reference exists"))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 4. drift case studies
def drift_cases(root: Path = ROOT, top: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_csv(root / "raw/hardware/drift_account2_vs_1.csv")
    d = d[(d.se_1 > 0) & (d.se_2 > 0)].copy()
    d["abs_diff"] = (d.estimate_1 - d.estimate_2).abs()
    cases = d[d.method.isin(["raw", "readout"])].sort_values("drift_z", key=np.abs, ascending=False).head(top)
    summary = d.assign(flag=d.drift_flag).groupby(["graph_id", "method", "observable"]).agg(
        n=("flag", "size"), n_flagged=("flag", "sum"), median_abs_diff=("abs_diff", "median"), median_abs_z=("drift_z", lambda s: s.abs().median())
    ).reset_index()
    return cases, summary


# ------------------------------------------------------------------ 5. cumulant estimator on the exact case
def cumulant_bias(root: Path = ROOT, pid: str = "P18", Jts=(0.4, 0.8, 1.0), shots: int = 16384, reps: int = 200,
                  boot: int = 100, boot_reps: int = 30, seed: int = 20261031) -> pd.DataFrame:
    """Sample the exact fixed-circuit distribution with the hardware shot count and apply the pipeline's raw-moment estimator
    (no noise, no mitigation): measures finite-shot bias and variance of G and kappa (and m, C for comparison) and the coverage of
    the percentile bootstrap used for the intervals. It validates the estimator, not the device."""
    from . import exact
    from .bootstrap import resample_counts
    from .moments import Catalog, counts_to_patterns, parity_moments
    from .params import load_params
    from .validate import load_patch
    prm = load_params(root / "configs/heavy_hex.yaml")
    patch = load_patch(pid, root / "raw/patches")
    cat = Catalog.from_patch(patch); subs = cat.subsets(); n = patch.n
    rng = np.random.default_rng(seed)
    pats_all = exact.all_patterns(n)
    rows = []
    for Jt in Jts:
        N = prm.steps(Jt)
        p = exact.probs(exact.trotter_states(patch, prm, [N])[N])
        truth = cat.from_patterns(pats_all, p)
        support = np.flatnonzero(p > 1e-12)
        ests = {k: [] for k in truth}
        cover = {k: 0 for k in truth}
        for r in range(reps):
            draw = rng.multinomial(shots, p[support] / p[support].sum())
            counts = {format(int(support[i]), f"0{n}b"): int(c) for i, c in enumerate(draw) if c}
            pats, w = counts_to_patterns(counts, n)
            est = cat.evaluate(parity_moments(pats, w, subs))
            for k, v in est.items():
                ests[k].append(v)
            if r < boot_reps:
                reps_b = {k: [] for k in est}
                for _ in range(boot):
                    pb, wb = counts_to_patterns(resample_counts(counts, rng), n)
                    for k, v in cat.evaluate(parity_moments(pb, wb, subs)).items():
                        reps_b[k].append(v)
                for k in est:
                    lo, hi = np.percentile(reps_b[k], [2.5, 97.5])
                    cover[k] += int(lo <= truth[k] <= hi)
        for cls in ("m", "M", "C", "G", "kappa"):
            keys = [k for k in truth if k[0] == cls]
            bias = np.array([np.mean(ests[k]) - truth[k] for k in keys])
            sd = np.array([np.std(ests[k], ddof=1) for k in keys])
            rows.append(dict(patch=pid, Jt=Jt, observable=cls, n_observables=len(keys), shots=shots, reps=reps,
                             median_abs_truth=float(np.median([abs(truth[k]) for k in keys])), mean_bias=float(bias.mean()),
                             max_abs_bias=float(np.abs(bias).max()), median_sd=float(np.median(sd)),
                             bootstrap_coverage=float(np.mean([cover[k] / boot_reps for k in keys])), boot=boot, boot_reps=boot_reps))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ driver
def estimator_health(root: Path = ROOT) -> pd.DataFrame:
    """Read-only tally of estimator failures in the frozen hardware table.

    "Reference missing" (no validated reference) and "estimator failed" (non-finite estimate or failed interval) are
    independent axes; the frozen trust_status keeps whichever the policy's precedence picked."""
    hw = pd.read_csv(root / "raw" / "hardware" / "hardware_results.csv")
    hw["finite_estimate"] = np.isfinite(hw["estimate"])
    hw["finite_interval"] = np.isfinite(hw["ci_low"]) & np.isfinite(hw["ci_high"])
    hw["failed_reason"] = hw["failed_reason"].fillna("none")
    keys = ["account", "graph_id", "method", "reference_kind", "finite_estimate", "finite_interval", "failed_reason",
            "mitigation_valid", "trust_status"]
    out = hw.groupby(keys, dropna=False).size().reset_index(name="n_rows")
    return out[(~out.finite_estimate) | (~out.finite_interval) | (out.failed_reason != "none")].reset_index(drop=True)


def run_all(root: Path = ROOT, with_bias: bool = True) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    out["estimator_health"] = estimator_health(root)
    pairs, qubits = readout_diagnostic(root)
    out["readout_independence"], out["readout_qubit_rates"] = pairs, qubits
    out["hardware_class_table"] = class_table(root)
    out["hardware_heldout_zne"] = heldout_table(root)
    cases, summ = drift_cases(root)
    out["hardware_drift_cases"], out["hardware_drift_summary"] = cases, summ
    if with_bias:
        out["cumulant_bias_exact"] = cumulant_bias(root)
    reports = root / "reports"
    for name, df in out.items():
        df.to_csv(reports / f"{name}.csv", index=False)
    return out


if __name__ == "__main__":
    run_all()
