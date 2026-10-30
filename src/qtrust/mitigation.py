"""Readout calibration/correction and manual zero-noise extrapolation (global folding).

Readout model: independent asymmetric flips per qubit, e0 = P(read 1 | true 0), e1 = P(read 0 | true 1).
For z = +/-1 this gives E[z_meas | z] = alpha + gamma z with alpha = e1 - e0, gamma = 1 - e0 - e1, so for any
subset S:  m(S) = sum_{T subset S} prod_{S\\T} alpha  prod_T gamma  mu(T)   -- triangular, solved exactly.
Corrected values are NEVER clipped (they may leave [-1, 1]).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from qiskit import QuantumCircuit

from .moments import Subset, counts_to_patterns


# ------------------------------------------------------------------ readout calibration
def calibration_preps(n: int, rng: np.random.Generator) -> list[np.ndarray]:
    """Four preparations r1, ~r1, r2, ~r2: every qubit is prepared 0 twice and 1 twice (not circular with t=0)."""
    r1, r2 = rng.integers(0, 2, n), rng.integers(0, 2, n)
    return [r1, 1 - r1, r2, 1 - r2]


def calibration_circuit(prep: np.ndarray) -> QuantumCircuit:
    qc = QuantumCircuit(len(prep), len(prep))
    for q, b in enumerate(prep):
        if b:
            qc.x(q)
    qc.measure(range(len(prep)), range(len(prep)))
    return qc


def _bits(counts: dict[str, int], n: int):
    pats, w = counts_to_patterns(counts, n)
    tot = sum(counts.values())
    return pats, w * tot, tot


def assignment_rates(cal: list[dict[str, int]], preps: list[np.ndarray]):
    """Per-qubit (e0, e1) pooled over the calibration circuits."""
    n = len(preps[0])
    n0 = np.zeros(n); f0 = np.zeros(n); n1 = np.zeros(n); f1 = np.zeros(n)
    for counts, prep in zip(cal, preps):
        pats, w, _ = _bits(counts, n)
        for q in range(n):
            read1 = float(w[((pats >> q) & 1) == 1].sum())
            tot = float(w.sum())
            if prep[q] == 0:
                n0[q] += tot; f0[q] += read1
            else:
                n1[q] += tot; f1[q] += tot - read1
    return f0 / n0, f1 / n1


def correct_moments(mu_meas: dict[Subset, float], e0, e1, subsets) -> dict[Subset, float]:
    """Corrected parity moments for every subset in ``subsets`` (each subset's own subsets must be present)."""
    alpha, gamma = np.asarray(e1) - np.asarray(e0), 1.0 - np.asarray(e0) - np.asarray(e1)
    mu: dict[Subset, float] = {(): 1.0}
    for S in sorted(subsets, key=lambda s: (len(s), s)):
        if not S:
            continue
        acc = mu_meas[S]
        for r in range(len(S)):
            for T in itertools.combinations(S, r):
                rest = [i for i in S if i not in T]
                acc -= np.prod([alpha[i] for i in rest]) * np.prod([gamma[i] for i in T]) * mu[T]
        mu[S] = acc / np.prod([gamma[i] for i in S])
    return mu


def readout_flip_correlations(cal: list[dict[str, int]], preps: list[np.ndarray], edges):
    """z-scores of the correlation between flip indicators of coupled qubits within each calibration circuit.
    Independent readout errors predict values ~ N(0,1); large |z| flags correlated readout."""
    n = len(preps[0])
    out = {}
    for (a, b) in edges:
        num = den = 0.0
        zs = []
        for counts, prep in zip(cal, preps):
            pats, w, tot = _bits(counts, n)
            fa = (((pats >> a) & 1) != prep[a]).astype(float)
            fb = (((pats >> b) & 1) != prep[b]).astype(float)
            p = w / tot
            ma, mb = p @ fa, p @ fb
            cov = p @ (fa * fb) - ma * mb
            var = max(ma * (1 - ma) * mb * (1 - mb), 1e-12) / tot
            zs.append(cov / np.sqrt(var))
        out[(a, b)] = float(np.sum(zs) / np.sqrt(len(zs)))
    return out


# ------------------------------------------------------------------ zero-noise extrapolation (manual folding)
def fold_circuit(qc: QuantumCircuit, k: int) -> QuantumCircuit:
    """U (U^dag U)^k with barriers so the compiler cannot cancel the inserted pairs. ``qc`` has no measurements.
    Noise factor is 2k+1 (global folding scales every gate, not only two-qubit ones)."""
    out = qc.copy()
    inv = qc.inverse()
    for _ in range(k):
        out.barrier()
        out.compose(inv, inplace=True)
        out.barrier()
        out.compose(qc, inplace=True)
    return out


def with_measurements(qc: QuantumCircuit) -> QuantumCircuit:
    """Append 'measure every qubit i into classical bit i' (same convention as ``trotter_circuit``)."""
    out = QuantumCircuit(qc.num_qubits, qc.num_qubits, name=qc.name)
    out.compose(qc, inplace=True)
    out.measure(range(qc.num_qubits), range(qc.num_qubits))
    return out


@dataclass(frozen=True)
class FitResult:
    """Outcome of one zero-noise extrapolation. ``finite`` False means NO estimate exists (never clip or guess)."""
    estimate: float
    finite: bool
    model: str
    failed_reason: str | None = None        # 'sign_change' | 'invalid_fit' | None
    residual: float = float("nan")          # RMS residual of the fit at the measured noise factors
    cond: float = float("nan")              # condition number of the design matrix


def zne_fit(factors, values, model: str = "linear") -> FitResult:
    """Extrapolate to noise factor 0. ``richardson`` = exact polynomial through all points; ``exp`` = A exp(-B x).

    ``exp`` needs a sign-definite decay; if the observable changes sign across the folds there is no valid fit and
    a failed FitResult is returned instead of fitting logs of absolute values.
    """
    x, y = np.asarray(factors, float), np.asarray(values, float)
    if model not in ("linear", "richardson", "exp"):
        raise ValueError(model)
    if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
        return FitResult(float("nan"), False, model, "invalid_fit")
    if model == "exp":
        if not (np.all(y > 0) or np.all(y < 0)):
            return FitResult(float("nan"), False, model, "sign_change")
        sgn = np.sign(y[0])
        A = np.vander(x, 2)
        b, a = np.polyfit(x, np.log(np.abs(y)), 1)
        est = float(sgn * np.exp(a))
        res = float(np.sqrt(np.mean((sgn * np.exp(a + b * x) - y) ** 2)))
    else:
        deg = 1 if model == "linear" else len(x) - 1
        A = np.vander(x, deg + 1)
        coef = np.polyfit(x, y, deg)
        est = float(np.polyval(coef, 0.0))
        res = float(np.sqrt(np.mean((np.polyval(coef, x) - y) ** 2)))
    cond = float(np.linalg.cond(A))
    if not np.isfinite(est):
        return FitResult(float("nan"), False, model, "invalid_fit", res, cond)
    return FitResult(est, True, model, None, res, cond)


def zne_extrapolate(factors, values, model: str = "linear") -> float:
    """Float view of :func:`zne_fit` (NaN when no valid fit exists)."""
    return zne_fit(factors, values, model).estimate


# ------------------------------------------------------------------ structured calibration + pair-joint readout
def structured_preps(edges, n: int) -> list[np.ndarray]:
    """Four preparations 00..0, 11..1 and the two checkerboards of the graph's bipartition.

    Every qubit is prepared 0 twice and 1 twice (same per-qubit statistics as random preps), and EVERY coupled pair
    sees all four joint states (00, 11, 01, 10), so independence can be tested on each edge and a 4x4 pair
    assignment matrix can be estimated. Needs a bipartite graph (heavy-hex is)."""
    import networkx as nx
    G = nx.Graph(); G.add_nodes_from(range(n)); G.add_edges_from(edges)
    side = nx.bipartite.color(G)                                   # raises if the graph is not bipartite
    s = np.array([side[i] for i in range(n)])
    return [np.zeros(n, int), np.ones(n, int), s.copy(), 1 - s]


def pair_assignment_matrix(cal: list[dict[str, int]], preps: list[np.ndarray], a: int, b: int):
    """4x4 matrix A[r, s] = P(read state r | prepared state s), state index = 2*bit_a + bit_b, pooled over the
    calibration circuits that prepared state s on (a, b). None if some joint state was never prepared."""
    n = len(preps[0])
    num, den = np.zeros((4, 4)), np.zeros(4)
    for counts, prep in zip(cal, preps):
        s = 2 * int(prep[a]) + int(prep[b])
        for key, c in counts.items():
            bits = key.replace(" ", "")[::-1]                       # bits[i] = classical bit i
            r = 2 * int(bits[a]) + int(bits[b])
            num[r, s] += c
        den[s] += sum(counts.values())
    if np.any(den == 0):
        return None
    return num / den


def independence_residual(A4: np.ndarray, e0, e1, a: int, b: int) -> float:
    """Max |A_pair - A_a (x) A_b| entry: how far the measured pair assignment is from the product of the
    single-qubit assignments (0 for independent readout)."""
    def single(i):
        return np.array([[1 - e0[i], e1[i]], [e0[i], 1 - e1[i]]])
    return float(np.abs(A4 - np.kron(single(a), single(b))).max())


def correct_pair_joint(counts: dict[str, int], a: int, b: int, A4: np.ndarray) -> dict:
    """Readout-corrected moments mu(a), mu(b), mu(a,b) by inverting the joint 4x4 pair assignment matrix (valid also
    when readout errors of the two qubits are correlated). Not clipped."""
    p = np.zeros(4)
    for key, c in counts.items():
        bits = key.replace(" ", "")[::-1]
        p[2 * int(bits[a]) + int(bits[b])] += c
    p = np.linalg.solve(A4, p / p.sum())
    za, zb = np.array([1, 1, -1, -1.0]), np.array([1, -1, 1, -1.0])    # z of qubit a / b for state index 2*ba+bb
    return {(a,): float(p @ za), (b,): float(p @ zb), (min(a, b), max(a, b)): float(p @ (za * zb))}
