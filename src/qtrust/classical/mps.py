"""Matrix-product-state simulation of the fixed Trotter circuit with quimb ``CircuitMPS``.

Every device coupling is applied (non-adjacent ones by swap+split in the chosen 1D ordering); no edge is
dropped. All moments are read from exact small-subset marginals of the (truncated) MPS, renormalised, with
the discarded weight reported through quimb's fidelity estimate.
"""
from __future__ import annotations

import itertools
import json
import os
import time

import numpy as np
import quimb.tensor as qtn

from ..graph import Patch
from ..moments import Catalog, parity_moments
from ..params import Params


def _apply_field(circ, pos, n, tau, prm):
    theta = -2.0 * prm.omega * tau
    for q in range(n):
        circ.apply_gate("RY", -prm.beta, pos[q])
        circ.apply_gate("RZ", theta, pos[q])
        circ.apply_gate("RY", prm.beta, pos[q])


def _apply_bonds(circ, pos, patch, prm):
    for layer in sorted(set(patch.colours.values())):
        for (a, b), c in sorted(patch.colours.items()):
            if c == layer:
                circ.apply_gate("RZZ", -2.0 * prm.J * prm.dt, pos[a], pos[b])


def _group_moments(circ, pos, group):
    """All non-empty subset moments inside ``group`` (logical qubits) from one k-site marginal."""
    k = len(group)
    p = np.asarray(circ.compute_marginal(tuple(pos[q] for q in group)), dtype=float).reshape(-1)
    norm = p.sum()
    p = p / norm
    f = np.arange(2 ** k)
    pats = np.zeros(2 ** k, dtype=np.uint64)
    for j in range(k):                                    # marginal axis j (C order) <-> group[j]
        pats |= (((f >> (k - 1 - j)) & 1).astype(np.uint64)) << np.uint64(j)
    out = {}
    for r in range(1, k + 1):
        for T in itertools.combinations(range(k), r):
            out[tuple(sorted(group[j] for j in T))] = parity_moments(pats, p, [T])[tuple(sorted(T))]
    return out, float(norm)


def _key(S) -> str:
    return "-".join(map(str, S))


def from_checkpoint(path, cat: Catalog):
    """(obs, mu, diagnostics) of the times a (killed) run completed, from its checkpoint file."""
    if not os.path.exists(path):
        return {}, {}, dict(fid={}, max_bond={})
    d = json.load(open(path))
    mu = {int(N): {tuple(int(x) for x in k.split("-")) if k else (): v for k, v in m.items()} for N, m in d["mu"].items()}
    return ({N: cat.evaluate(m) for N, m in mu.items()}, mu,
            dict(fid={int(k): v for k, v in d["fid"].items()}, max_bond={int(k): v for k, v in d["max_bond"].items()}))


def run(patch: Patch, prm: Params, Ns, chi: int, cutoff: float = 1e-10, cat: Catalog | None = None,
        budget_s: float | None = None, ckpt_path: str | None = None):
    """Returns (observables {N: {label: value}}, moments {N: ...}, stats).

    psi_N = F(h) [B F(dt)]^{N-1} B F(h)|0>: the circuit keeps evolving without the final field half; for each
    recorded N that half is applied to a COPY, so quimb's discarded-weight tracking is never reset.
    """
    cat = cat or Catalog.from_patch(patch)
    n = patch.n
    pos = {q: i for i, q in enumerate(patch.mps_order)}
    Ns = sorted(set(Ns))
    t0 = time.time()
    circ = qtn.CircuitMPS(n, max_bond=chi, cutoff=cutoff)
    groups = [(q,) for q in range(n)] + [tuple(e) for e in patch.edges] + [tuple(sorted(c)) for c in cat.clusters]
    obs, mus, fid, maxbond, norms = {}, {}, {}, {}, {}

    def record(N, c):
        mu: dict = {(): 1.0}
        worst = 1.0
        for g in groups:
            m, nm = _group_moments(c, pos, g)
            worst = min(worst, nm)
            for S, v in m.items():
                mu.setdefault(S, v)
        mus[N], obs[N] = mu, cat.evaluate(mu)
        fid[N], maxbond[N], norms[N] = float(c.fidelity_estimate()), int(c.psi.max_bond()), worst
        if ckpt_path:                                            # cumulative checkpoint (survives a hard kill)
            tmp = f"{ckpt_path}.tmp"
            json.dump(dict(mu={str(n_): {_key(S): v for S, v in m.items()} for n_, m in mus.items()}, fid=fid,
                           max_bond=maxbond), open(tmp, "w"))
            os.replace(tmp, ckpt_path)

    if 0 in Ns:
        record(0, circ)
    timed_out = False
    if Ns[-1] > 0:
        _apply_field(circ, pos, n, prm.dt / 2, prm)
        for k in range(1, Ns[-1] + 1):
            if budget_s is not None and time.time() - t0 > budget_s:
                timed_out = True                                   # resource limit: keep the times already done
                break
            _apply_bonds(circ, pos, patch, prm)
            if k in Ns:
                c2 = circ.copy()
                _apply_field(c2, pos, n, prm.dt / 2, prm)
                record(k, c2)
            if k < Ns[-1]:
                _apply_field(circ, pos, n, prm.dt, prm)
    stats = dict(chi=chi, cutoff=cutoff, order=patch.meta.get("mps_order_info", {}).get("chosen", "given"), elapsed_s=time.time() - t0,
                 timed_out=timed_out, budget_s=budget_s, completed_N=sorted(obs),
                 fidelity_estimate=fid, error_estimate={N: 1 - f for N, f in fid.items()},
                 max_bond=maxbond, min_marginal_norm=norms)
    return obs, mus, stats
