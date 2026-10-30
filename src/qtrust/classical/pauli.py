"""Pauli propagation (pauli-prop, Rust) of Z-string observables through the fixed Trotter circuit.

Heisenberg recursion: U_N = U_{N-1} S  =>  O_N = U_N^dag O U_N = S^dag O_{N-1} S, so ONE pass over N gives
every requested time. Expectation in |0..0> is the sum of coefficients of the terms with no X/Y part.
Observables are independent, so they are spread over a process pool (pauli-prop is single threaded).
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np
from pauli_prop import propagate_through_circuit
from qiskit.quantum_info import SparsePauliOp

from ..circuits import trotter_circuit
from ..graph import Patch
from ..moments import Catalog, Subset
from ..params import Params


@dataclass(frozen=True)
class PauliSetting:
    name: str
    max_terms: int
    atol: float


SETTINGS = {
    "coarse": PauliSetting("coarse", 2 ** 12, 1e-3),
    "medium": PauliSetting("medium", 2 ** 15, 1e-4),
    "fine": PauliSetting("fine", 2 ** 18, 1e-5),
}


def z_string(n: int, S: Subset) -> SparsePauliOp:
    label = ["I"] * n
    for i in S:
        label[n - 1 - i] = "Z"                       # Qiskit labels are little endian (rightmost = qubit 0)
    return SparsePauliOp("".join(label))


def expect_zero(op: SparsePauliOp) -> float:
    """<0..0| op |0..0>: only terms made of I and Z survive."""
    return float(op.coeffs[~op.paulis.x.any(axis=1)].sum().real)


def _ckpt_name(S) -> str:
    return "-".join(map(str, S)) or "empty"


def _write_atomic(path: str, payload: dict) -> None:
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, path)


def _slice(args):
    """Advance EVERY observable of this worker's slice through the same step before going one step deeper, so an
    interrupted run always has the earliest times complete for all observables (not some observables complete to
    late times and others never started)."""
    patch, prm, subsets, N_max, outs, max_terms, atol, deadline, ckpt_dir = args
    step = trotter_circuit(patch, prm, 1, measure=False)             # S = F(h) B F(h)
    state = {S: z_string(patch.n, S) for S in subsets}
    lost = {S: 0.0 for S in subsets}
    res = {S: ({}, {}, {}) for S in subsets}

    def record(S, N, op):
        vals, terms, trunc = res[S]
        vals[N], terms[N], trunc[N] = expect_zero(op), len(op), lost[S]
        if ckpt_dir:                                                  # per-time checkpoint (survives a hard kill)
            _write_atomic(os.path.join(ckpt_dir, _ckpt_name(S) + ".json"), dict(vals=vals, terms=terms, trunc=trunc))

    if 0 in outs:
        for S in subsets:
            record(S, 0, state[S])
    for N in range(1, N_max + 1):
        for S in subsets:
            if time.time() > deadline:                               # soft deadline (unsupervised use)
                return [(S2, *res[S2]) for S2 in subsets]
            state[S], tn = propagate_through_circuit(state[S], step, max_terms, atol, frame="h")
            lost[S] += float(tn)
            if N in outs:
                record(S, N, state[S])
    return [(S, *res[S]) for S in subsets]


def _slices(subsets, workers: int):
    """Deal subsets round-robin, largest first, so every worker gets a similar mix of cheap and expensive ones."""
    ordered = sorted(subsets, key=lambda S: (-len(S), S))
    return [ordered[i::workers] for i in range(workers) if ordered[i::workers]]


def assemble(patch: Patch, cat: Catalog, subsets, per: dict, Ns, setting: PauliSetting, workers: int, elapsed: float,
             budget_s=None):
    """(obs, mu, stats) from per-subset (vals, terms, trunc); only times where EVERY subset finished are kept."""
    Ns = sorted(set(Ns))
    done = [N for N in Ns if all(S in per and N in per[S][0] for S in subsets)]
    mu = {N: {**{S: per[S][0][N] for S in subsets}, (): 1.0} for N in done}
    obs = {N: cat.evaluate(m) for N, m in mu.items()}
    stats = dict(
        setting=setting.name, max_terms=setting.max_terms, atol=setting.atol, workers=workers,
        elapsed_s=elapsed, budget_s=budget_s, timed_out=len(done) < len(Ns), completed_N=done,
        max_terms_retained={N: int(max(per[S][1][N] for S in subsets)) for N in done},
        mean_terms_retained={N: float(np.mean([per[S][1][N] for S in subsets])) for N in done},
        max_truncated_l1={N: float(max(per[S][2][N] for S in subsets)) for N in done},
        cap_hit={N: bool(max(per[S][1][N] for S in subsets) >= setting.max_terms) for N in done},
    )
    return obs, mu, stats


def from_checkpoints(patch: Patch, ckpt_dir, Ns, setting: PauliSetting, workers: int, elapsed: float,
                     cat: Catalog | None = None, budget_s=None):
    """Rebuild partial results after a hard kill from the per-subset checkpoint files."""
    cat = cat or Catalog.from_patch(patch)
    subsets = sorted(cat.subsets())
    per = {}
    for S in subsets:
        f = os.path.join(ckpt_dir, _ckpt_name(S) + ".json")
        if os.path.exists(f):
            try:
                d = json.load(open(f))
            except json.JSONDecodeError:
                continue
            per[S] = ({int(k): v for k, v in d["vals"].items()}, {int(k): v for k, v in d["terms"].items()},
                      {int(k): v for k, v in d["trunc"].items()})
    return assemble(patch, cat, subsets, per, Ns, setting, workers, elapsed, budget_s)


def run(patch: Patch, prm: Params, Ns, setting: PauliSetting, subsets=None, workers: int = 12,
        cat: Catalog | None = None, budget_s: float | None = None, ckpt_dir: str | None = None):
    """Returns (observables {N: {label: value}}, moments {N: {subset: value}}, stats dict).

    ``budget_s`` is a SOFT deadline (workers stop between steps). Hard limits and memory accounting are done by
    ``classical.supervise``, which also passes ``ckpt_dir`` so a killed run keeps the times it completed.
    """
    cat = cat or Catalog.from_patch(patch)
    subsets = sorted(subsets if subsets is not None else cat.subsets())
    Ns = sorted(set(Ns))
    t0 = time.time()
    deadline = t0 + budget_s if budget_s is not None else float("inf")
    if ckpt_dir:
        os.makedirs(ckpt_dir, exist_ok=True)
    jobs = [(patch, prm, sl, Ns[-1], set(Ns), setting.max_terms, setting.atol, deadline, ckpt_dir)
            for sl in _slices(subsets, workers)]
    per = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for out in ex.map(_slice, jobs):
            for S, vals, tm, tr in out:
                per[S] = (vals, tm, tr)
    return assemble(patch, cat, subsets, per, Ns, setting, workers, time.time() - t0, budget_s)
