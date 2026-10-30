"""Step 2 validation: exact curves, Trotter-error tables, Aer cross-check, level statistics."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import exact
from .graph import Patch
from .moments import Catalog
from .params import Params

ROOT = Path(__file__).resolve().parents[2]
JT = [0.0, 0.4, 1.0, 2.0, 3.0, 4.0, 5.0]


def load_patch(pid: str, folder: Path = ROOT / "raw/patches") -> Patch:
    return Patch.from_json(json.loads((folder / f"{pid}.json").read_text()))


def label(key: tuple) -> tuple[str, str]:
    return key[0], "-".join(map(str, key[1]))


def observables_over_time(patch: Patch, prm: Params, Jt_list, source: str = "kernel", cat: Catalog | None = None):
    """{Jt: {observable key: value}} for the fixed Trotter circuit (source='kernel') or exp(-iHt) ('continuous')."""
    cat = cat or Catalog.from_patch(patch)
    pats = exact.all_patterns(patch.n)
    out = {}
    if source == "kernel":
        Ns = [prm.steps(t) for t in Jt_list]
        back = {prm.steps(t): t for t in Jt_list}
        for N, psi in exact.iter_trotter_states(patch, prm, Ns):
            out[back[N]] = cat.from_patterns(pats, exact.probs(psi))
    else:
        for t in Jt_list:
            psi = exact.continuous_states(patch, prm, [t])[t]
            out[t] = cat.from_patterns(pats, exact.probs(psi))
    return out


def max_abs_diff(a: dict, b: dict) -> tuple[float, tuple]:
    worst = max(a, key=lambda k: abs(a[k] - b[k]))
    return abs(a[worst] - b[worst]), worst


def exact_table(patch: Patch, prm: Params, Jt_list=JT, source="kernel") -> pd.DataFrame:
    rows = []
    for t, obs in observables_over_time(patch, prm, Jt_list, source).items():
        for key, v in obs.items():
            kind, sites = label(key)
            rows.append(dict(graph_id=patch.pid, n=patch.n, J=prm.J, hx=prm.hx, hz=prm.hz, dt=prm.dt,
                             N=prm.steps(t), Jt=t, observable=kind, sites=sites, method=f"exact_{source}",
                             value=v))
    return pd.DataFrame(rows)


def trotter_error_table(patch: Patch, prm: Params, Jt_list, continuous: bool) -> pd.DataFrame:
    """Separates (C) ideal circuit vs exp(-iHt) [needs sparse H, n<=~20] from circuit(dt) vs circuit(dt/2)."""
    half = prm.with_dt(prm.dt / 2)
    ts = [t for t in Jt_list if t > 0]
    A = observables_over_time(patch, prm, ts)
    B = observables_over_time(patch, half, ts)
    C = observables_over_time(patch, prm, ts, "continuous") if continuous else None
    D = observables_over_time(patch, half, ts, "continuous") if continuous else None
    rows = []
    for t in ts:
        e_half, w_half = max_abs_diff(A[t], B[t])
        row = dict(graph_id=patch.pid, n=patch.n, Jt=t, dt=prm.dt, err_dt_vs_dthalf=e_half,
                   worst_dt_vs_dthalf="/".join(label(w_half)))
        if continuous:
            e1, w1 = max_abs_diff(A[t], C[t]); e2, w2 = max_abs_diff(B[t], D[t])
            row.update(err_dt_vs_continuous=e1, worst_dt="/".join(label(w1)),
                       err_dthalf_vs_continuous=e2, worst_dthalf="/".join(label(w2)))
        rows.append(row)
    return pd.DataFrame(rows)


def aer_crosscheck(patch: Patch, prm: Params, Ns=(0, 2, 5, 10, 15)) -> pd.DataFrame:
    """Aer statevector of the actual Qiskit circuit vs the independent numpy kernel (state-level)."""
    from qiskit_aer import AerSimulator
    from .circuits import trotter_circuit
    sim = AerSimulator(method="statevector")
    ref = dict(exact.iter_trotter_states(patch, prm, Ns))
    rows = []
    for N in Ns:
        qc = trotter_circuit(patch, prm, N, measure=False); qc.save_statevector()
        sv = np.asarray(sim.run(qc).result().get_statevector())
        rows.append(dict(graph_id=patch.pid, N=N, Jt=N * prm.dt, max_amp_diff=float(np.abs(sv - ref[N]).max())))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ level statistics (optional item 4)
def _site_field(tau: float, prm: Params, hz_scale: float) -> np.ndarray:
    return exact._field_matrix(tau, prm.__class__(prm.J, prm.hx, prm.hz * hz_scale, prm.dt))


def floquet_unitary(patch: Patch, prm: Params, scale_site: int | None = None, scale: float = 1.2) -> np.ndarray:
    """Dense single-step unitary S = F(dt/2) B F(dt/2) (2^n x 2^n), optionally with hz scaled on one site."""
    n = patch.n
    z = exact._zarr(n).astype(float)
    zz = sum(z[a] * z[b] for a, b in patch.edges) if patch.edges else np.zeros(2 ** n)
    bond = np.exp(1j * prm.J * prm.dt * zz)
    del z
    mats = [_site_field(prm.dt / 2, prm, scale if i == scale_site else 1.0) for i in range(n)]
    F = np.array([[1.0 + 0j]])
    for i in range(n - 1, -1, -1):                       # qubit n-1 is the most significant index bit
        F = np.kron(F, mats[i])
    return F @ (bond[:, None] * F)


def mean_gap_ratio(U: np.ndarray) -> float:
    ph = np.sort(np.angle(np.linalg.eigvals(U)))
    gaps = np.diff(np.concatenate([ph, [ph[0] + 2 * np.pi]]))        # include the wrap-around gap
    gaps = gaps[gaps > 1e-9]                                         # drop exact degeneracies
    s1, s2 = gaps, np.roll(gaps, -1)
    return float(np.mean(np.minimum(s1, s2) / np.maximum(s1, s2)))


def level_statistics(p12: Patch, prm: Params) -> pd.DataFrame:
    from .graph import star_centres  # noqa: F401  (kept for clarity of provenance)
    from .conftest_free import chain_patch
    site = p12.meta.get("symmetry_breaking_site")
    cases = [
        ("P12 tree, table params, hz x1.2 on site %s" % site, p12, prm, site),
        ("12-site chain, hz=0 (integrable control)", chain_patch(12), prm.with_hz(0.0), None),
        ("12-site chain, table params, hz x1.2 on end site", chain_patch(12), prm, 0),
    ]
    rows = []
    for name, patch, pr, s in cases:
        t0 = time.time()
        rows.append(dict(case=name, n=patch.n, mean_r=mean_gap_ratio(floquet_unitary(patch, pr, s)),
                         seconds=round(time.time() - t0, 1), poisson=0.386, goe=0.530))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ symmetry-resolved level statistics (diagnosis)
def gap_ratio_detail(eigvals: np.ndarray, tol: float = 1e-9) -> dict:
    """<r> of the consecutive quasi-energy gaps (circular), reporting how many exact degeneracies were dropped."""
    ph = np.sort(np.angle(eigvals))
    gaps = np.diff(np.concatenate([ph, [ph[0] + 2 * np.pi]]))
    kept = gaps[gaps > tol]
    r = np.minimum(kept, np.roll(kept, -1)) / np.maximum(kept, np.roll(kept, -1))
    return dict(n_levels=len(ph), n_degenerate_gaps=int((gaps <= tol).sum()), mean_r=float(r.mean()))


def symmetry_sector_basis(n: int, parity_sign: int, mirror_sign: int):
    """Orthonormal basis (dense 2^n x dim) of the sector with prod-X parity eigenvalue ``parity_sign`` and chain-mirror
    eigenvalue ``mirror_sign``. Built from orbits of the group {1, P, R, PR} on computational basis states."""
    N = 2 ** n
    k = np.arange(N)
    P = k ^ (N - 1)
    R = np.zeros(N, dtype=np.int64)
    for i in range(n):
        R |= ((k >> i) & 1) << (n - 1 - i)
    PR = P[R]
    chi = (1, parity_sign, mirror_sign, parity_sign * mirror_sign)
    seen = np.zeros(N, bool)
    cols = []
    for s in range(N):
        if seen[s]:
            continue
        v: dict[int, int] = {}
        for g, c in zip((np.arange(N), P, R, PR), chi):
            t = int(g[s]); v[t] = v.get(t, 0) + c
            seen[t] = True
        v = {t: c for t, c in v.items() if c != 0}
        if v:
            cols.append(v)
    B = np.zeros((N, len(cols)))
    for j, v in enumerate(cols):
        for t, c in v.items():
            B[t, j] = c
    return B / np.linalg.norm(B, axis=0)


def level_statistics_diagnosis(prm: Params, n: int = 12) -> pd.DataFrame:
    """hz = 0 chain: full-spectrum <r> versus <r> inside each (parity, mirror) symmetry sector, plus degeneracy counts."""
    from .conftest_free import chain_patch
    patch = chain_patch(n)
    pr = prm.with_hz(0.0)
    U = floquet_unitary(patch, pr)
    rows = [dict(case="hz=0 chain, full spectrum", sector="all", dim=2 ** n, **gap_ratio_detail(np.linalg.eigvals(U)))]
    for a in (+1, -1):
        for b in (+1, -1):
            B = symmetry_sector_basis(n, a, b)
            Us = B.T @ U @ B
            rows.append(dict(case="hz=0 chain, symmetry sector", sector=f"parity={a:+d},mirror={b:+d}", dim=B.shape[1],
                             commutator_norm=float(np.linalg.norm(U @ B - B @ Us)), **gap_ratio_detail(np.linalg.eigvals(Us))))
    return pd.DataFrame(rows)
