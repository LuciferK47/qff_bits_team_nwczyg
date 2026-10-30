"""Offline dress rehearsal of the WHOLE hardware analysis chain on a noisy Aer simulation (frozen dt).

Noise = FakeFez calibration-derived Aer noise model. This is hardware-INSPIRED noise: no drift, no crosstalk. For the
``fractional`` variant the RZZ error is an ASSUMPTION (depolarising error equal to the CZ error of the same pair).
Everything produced is labelled ``simulated_noisy``; no verdict from this module is a hardware verdict
(``trust.assess`` can never return ``supported`` for source != 'hardware').

Mitigation protocol (fixed before looking at any result):
  * calibration  : four structured preparations (all-0, all-1, two checkerboards): every coupled pair sees all four
                   joint states, so independence is tested on EVERY edge.
  * ZNE model    : chosen among linear / richardson / exp using ONLY the calibration times; evaluated on a held-out
                   time that played no role in the choice. Models whose fit fails on > 5% of calibration
                   observables are disqualified. The model is never chosen per target.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import exact, mitigation as mit
from .bootstrap import bootstrap
from .circuits import trotter_circuit
from .hardware import compile_circuit
from .moments import Catalog, counts_to_patterns, parity_moments
from .params import Params
from .trust import assess, load_policy

LABEL = "simulated_noisy"
MODELS = ("linear", "richardson", "exp")
MAX_FIT_FAILURE_RATE = 0.05
INDEPENDENCE_Z_MAX = 4.0


def _raw_moments(counts, n, subsets):
    pats, w = counts_to_patterns(counts, n)
    return parity_moments(pats, w, subsets)


# ------------------------------------------------------------------ simulator
def make_sim(backend, variant: str, seed: int):
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel, depolarizing_error
    nm = NoiseModel.from_backend(backend)
    if variant == "fractional":     # ASSUMPTION: RZZ depolarising error equals the CZ error of the same pair
        for (a, b), props in backend.target["cz"].items():
            e = props.error or 0.0
            nm.add_quantum_error(depolarizing_error(min(4.0 / 3.0 * e, 15.0 / 16.0), 2), ["rzz"], [a, b])
    elif variant != "cz":
        raise ValueError(variant)
    return AerSimulator(method="density_matrix", noise_model=nm, seed_simulator=seed)


# ------------------------------------------------------------------ data collection
def collect(patch, prm: Params, backend, variant: str, Jts, zne_Jts, zne_k, shots: int, cal_shots: int, seed: int):
    sim = make_sim(backend, variant, seed)
    preps = mit.structured_preps(patch.edges, patch.n)
    comp = "cz" if variant == "cz" else "fractional"
    counter = iter(range(10 ** 6))

    def run(qc, nshots):
        c = compile_circuit(qc, patch, backend, comp)
        counts = sim.run(c.circuit, shots=nshots, seed_simulator=seed + next(counter)).result().get_counts()
        return counts, c.report

    data, reports = {"cal": [], "fwd": {}, "zne": {}}, {}
    for i, prep in enumerate(preps):
        counts, rep = run(mit.calibration_circuit(prep), cal_shots)
        data["cal"].append(counts); reports[f"cal{i}"] = rep
    for Jt in Jts:
        N = prm.steps(Jt)
        data["fwd"][N], reports[f"fwd_Jt{Jt}"] = run(trotter_circuit(patch, prm, N, measure=True), shots)
    for Jt in zne_Jts:
        N = prm.steps(Jt)
        base = trotter_circuit(patch, prm, N, measure=False)
        data["zne"][N] = {}
        for k in zne_k:
            data["zne"][N][k], reports[f"zne_Jt{Jt}_k{k}"] = run(mit.with_measurements(mit.fold_circuit(base, k)), shots)
    return data, reports, preps


# ------------------------------------------------------------------ analysis
def analyse(data: dict, patch, cat: Catalog, preps, Ns, zne_Ns, reasons: dict | None = None):
    """counts -> raw -> readout-corrected -> ZNE for every model. Flat dict keyed (method, N, (kind, sites))."""
    n, subs = patch.n, cat.subsets()
    e0, e1 = mit.assignment_rates(data["cal"], preps)
    out, corrected = {}, {}
    for N in Ns:
        raw = _raw_moments(data["fwd"][N], n, subs)
        corrected[N] = cat.evaluate(mit.correct_moments(raw, e0, e1, subs))
        for k, v in cat.evaluate(raw).items():
            out[("raw", N, k)] = v
        for k, v in corrected[N].items():
            out[("readout", N, k)] = v
    for N in zne_Ns:                                           # fold level 0 is the unfolded, readout-corrected run
        levels = {0: corrected[N]}
        for k, counts in data["zne"][N].items():
            levels[int(k)] = cat.evaluate(mit.correct_moments(_raw_moments(counts, n, subs), e0, e1, subs))
        lam = [2 * k + 1 for k in sorted(levels)]
        for key in levels[0]:
            vals = [levels[k][key] for k in sorted(levels)]
            for model in MODELS:
                fit = mit.zne_fit(lam, vals, model)
                out[(f"zne_{model}", N, key)] = fit.estimate
                if reasons is not None and not fit.finite:
                    reasons[(f"zne_{model}", N, key)] = fit.failed_reason
    return out


def select_model(point: dict, ref: dict, cal_Ns) -> tuple[str | None, dict]:
    """Pick the ZNE model on the CALIBRATION times only: lowest pooled RMSE vs exact among models whose fit failure
    rate is <= MAX_FIT_FAILURE_RATE. Returns (model | None, per-model table)."""
    table = {}
    for model in MODELS:
        errs, fails = [], 0
        keys = [k for k in point if k[0] == f"zne_{model}" and k[1] in cal_Ns]
        for k in keys:
            v = point[k]
            if np.isfinite(v):
                errs.append(v - ref[k[1]][k[2]])
            else:
                fails += 1
        table[model] = dict(rmse=float(np.sqrt(np.mean(np.square(errs)))) if errs else float("nan"),
                            failure_rate=fails / max(len(keys), 1), n=len(keys))
    ok = {m: t for m, t in table.items() if t["failure_rate"] <= MAX_FIT_FAILURE_RATE and np.isfinite(t["rmse"])}
    return (min(ok, key=lambda m: ok[m]["rmse"]) if ok else None), table


# ------------------------------------------------------------------ readout independence gate
def readout_gate(data: dict, preps, patch) -> dict:
    """z-scores of flip correlations and the pair-assignment residual for every coupled pair."""
    e0, e1 = mit.assignment_rates(data["cal"], preps)
    z = mit.readout_flip_correlations(data["cal"], preps, patch.edges)
    res = {}
    for a, b in patch.edges:
        A4 = mit.pair_assignment_matrix(data["cal"], preps, a, b)
        res[(a, b)] = None if A4 is None else mit.independence_residual(A4, e0, e1, a, b)
    worst = max(abs(v) for v in z.values())
    return dict(passed=bool(worst < INDEPENDENCE_Z_MAX), worst_abs_z=float(worst), z={f"{a}-{b}": v for (a, b), v in z.items()},
                residual={f"{a}-{b}": v for (a, b), v in res.items()}, z_max=INDEPENDENCE_Z_MAX)


def inject_pair_flips(counts: dict[str, int], a: int, b: int, q: float, rng: np.random.Generator) -> dict[str, int]:
    """Classical post-processing: with probability q per shot, flip BOTH measured bits a and b (correlated readout)."""
    out: dict[str, int] = {}
    for key, c in counts.items():
        bits = list(key.replace(" ", ""))
        n_flip = int(rng.binomial(c, q))
        flipped = bits.copy()
        for i in (a, b):                                           # bit i is the i-th character from the right
            flipped[len(bits) - 1 - i] = "1" if bits[len(bits) - 1 - i] == "0" else "0"
        out[key] = out.get(key, 0) + (c - n_flip)
        fk = "".join(flipped)
        out[fk] = out.get(fk, 0) + n_flip
    return {k: v for k, v in out.items() if v}


def correlated_readout_control(patch, backend, seed: int = 20261029, q: float = 0.05, cal_shots: int = 16384) -> dict:
    """Independent single-qubit readout errors everywhere, plus correlated flips (both bits of one edge flip together
    with probability q) injected into the sampled counts of the calibration circuits. The independence gate must trip
    on that edge only."""
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel, ReadoutError
    a, b = patch.edges[0]
    nm = NoiseModel()
    for phys in patch.nodes:
        nm.add_readout_error(ReadoutError([[0.98, 0.02], [0.02, 0.98]]), [phys])
    sim = AerSimulator(noise_model=nm, seed_simulator=seed)
    rng = np.random.default_rng(seed)
    preps = mit.structured_preps(patch.edges, patch.n)
    cal = []
    for i, prep in enumerate(preps):
        c = compile_circuit(mit.calibration_circuit(prep), patch, backend, "cz")
        counts = sim.run(c.circuit, shots=cal_shots, seed_simulator=seed + i).result().get_counts()
        cal.append(inject_pair_flips(counts, a, b, q, rng))
    gate = readout_gate({"cal": cal}, preps, patch)
    gate["injected_edge"] = f"{a}-{b}"
    gate["injected_probability"] = q
    gate["trips_on_injected_edge"] = bool(abs(gate["z"][f"{a}-{b}"]) > INDEPENDENCE_Z_MAX)
    gate["others_quiet"] = bool(all(abs(v) < INDEPENDENCE_Z_MAX for k, v in gate["z"].items() if k != f"{a}-{b}"))
    return gate


# ------------------------------------------------------------------ driver
def run_rehearsal(patch, prm: Params, backend, out_dir: Path, variant: str = "cz", Jts=(0.0, 0.4, 0.8, 1.0),
                  zne_Jts=(0.4, 0.8, 1.0), cal_Jts=(0.4, 1.0), heldout_Jt=0.8, zne_k=(1, 2), shots=16384,
                  cal_shots=4096, B=2000, seed=20261029):
    out_dir.mkdir(parents=True, exist_ok=True)
    assert heldout_Jt not in cal_Jts and heldout_Jt in zne_Jts, "held-out ZNE time must not be a calibration time"
    pol = load_policy()
    eps, min_valid = pol["tolerances_abs"]["hardware_vs_exact"], pol["bootstrap"]["min_valid_fraction"]
    cat = Catalog.from_patch(patch)
    Ns = [prm.steps(t) for t in Jts]
    zne_Ns = [prm.steps(t) for t in zne_Jts]
    cal_Ns = {prm.steps(t) for t in cal_Jts}
    held_N = prm.steps(heldout_Jt)

    data, reports, preps = collect(patch, prm, backend, variant, Jts, zne_Jts, zne_k, shots, cal_shots, seed)
    tag = f"{patch.pid}_{variant}_{LABEL}_dt{prm.dt}"
    (out_dir / f"{tag}_counts.json").write_text(json.dumps(
        dict(label=LABEL, variant=variant, dt=prm.dt, note="calibration-derived noise model; not hardware",
             assumption=("RZZ error = CZ error of the pair" if variant == "fractional" else None),
             cal=data["cal"], fwd=data["fwd"], zne=data["zne"], preps=[p.tolist() for p in preps], reports=reports,
             shots=shots, cal_shots=cal_shots, seed=seed, physical_id=patch.physical_id), default=str))

    ref = {N: cat.from_patterns(exact.all_patterns(patch.n), exact.probs(psi))
           for N, psi in exact.iter_trotter_states(patch, prm, Ns)}
    reasons: dict = {}
    point = analyse(data, patch, cat, preps, Ns, zne_Ns, reasons)
    model, table = select_model(point, ref, cal_Ns)
    gate = readout_gate(data, preps, patch)
    (out_dir / f"{tag}_selection.json").write_text(json.dumps(
        dict(selected_model=model, calibration_times_Jt=list(cal_Jts), heldout_Jt=heldout_Jt, per_model_calibration=table,
             readout_gate=gate, max_fit_failure_rate=MAX_FIT_FAILURE_RATE), indent=1))

    bs = bootstrap(data, lambda d: analyse(d, patch, cat, preps, Ns, zne_Ns), B=B, seed=seed, min_valid_fraction=min_valid)
    rows = []
    for key, v in bs.items():
        method, N, (kind, sites) = key
        r = ref[N][(kind, sites)]
        ok = v["failed_reason"] is None
        is_zne = method.startswith("zne_")
        role = ("heldout" if N == held_N else "calibration" if N in cal_Ns else "other") if is_zne else "n/a"
        a = assess(v["point"], v["lo"] - r, v["hi"] - r, r, v["lo"], v["hi"], eps, reference_kind="full_exact",
                   systematics_validated=False, source=LABEL)
        rows.append(dict(graph_id=patch.pid, physical_id=patch.physical_id, variant=variant, n=patch.n, dt=prm.dt,
                         Jt=N * prm.dt, N=N, method=method, selected_model=bool(is_zne and method == f"zne_{model}"),
                         zne_role=role, observable=kind, sites="-".join(map(str, sites)), estimate=v["point"],
                         ci_low=v["lo"], ci_high=v["hi"], se=v["se"], bootstrap_bias=v["bias"], n_valid=v["n_valid"],
                         B=v["B"], valid_fraction=v["valid_fraction"], failed_reason=reasons.get(key) or v["failed_reason"],
                         reference=r, reference_kind="full_exact", error=v["point"] - r,
                         covers_truth=(v["lo"] <= r <= v["hi"]) if ok else None, source=LABEL,
                         readout_independence_passed=gate["passed"],
                         **{f"{k}": a[k] for k in ("reference_status", "mitigation_valid", "signal_resolved",
                                                   "statistical_status", "systematics_validated")},
                         trust_status_simulated=a["final_status"]))
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / f"{tag}_results.csv", index=False)
    return df, dict(selected_model=model, table=table, gate=gate, reports=reports)
