"""One- to four-site moments and cumulants from a weighted set of bit patterns.

Pattern bit i (value 1<<i) is the measured bit of logical qubit i, z_i = (-1)^{b_i}.
The SAME code path serves exact probabilities (patterns = arange(2^n)), Aer counts and hardware counts.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

Subset = tuple[int, ...]


def counts_to_patterns(counts: dict[str, int], n: int) -> tuple[np.ndarray, np.ndarray]:
    """Qiskit count keys are 'b_{n-1} ... b_0' (rightmost = classical bit 0 = logical qubit 0)."""
    dtype = np.uint32 if n <= 32 else np.uint64
    pats = np.array([int(k.replace(" ", ""), 2) for k in counts], dtype=dtype)
    w = np.array(list(counts.values()), dtype=float)
    return pats, w / w.sum()


def parity_moments(patterns: np.ndarray, weights: np.ndarray, subsets) -> dict[Subset, float]:
    """mu(S) = sum_k w_k prod_{i in S} z_i(k); weights need not be non-negative (quasi-probabilities)."""
    out: dict[Subset, float] = {}
    for S in subsets:
        S = tuple(sorted(S))
        if not S:
            out[S] = float(weights.sum())
            continue
        mask = patterns.dtype.type(sum(1 << i for i in S))
        parity = np.bitwise_count(patterns & mask) & 1
        out[S] = float(np.dot(weights, 1.0 - 2.0 * parity))
    return out


def kappa_partition(mu: dict[Subset, float], S: Subset) -> float:
    """Fourth joint cumulant from raw moments (needs all 15 non-empty subsets, incl. the 4 triples)."""
    a, b, c, d = sorted(S)
    m = lambda *x: mu[tuple(sorted(x))]
    k = m(a, b, c, d)
    k -= m(a) * m(b, c, d) + m(b) * m(a, c, d) + m(c) * m(a, b, d) + m(d) * m(a, b, c)
    k -= m(a, b) * m(c, d) + m(a, c) * m(b, d) + m(a, d) * m(b, c)
    k += 2 * (m(a) * m(b) * m(c, d) + m(a) * m(c) * m(b, d) + m(a) * m(d) * m(b, c)
              + m(b) * m(c) * m(a, d) + m(b) * m(d) * m(a, c) + m(c) * m(d) * m(a, b))
    k -= 6 * m(a) * m(b) * m(c) * m(d)
    return k


def kappa_central(mu: dict[Subset, float], S: Subset) -> float:
    """The problem statement's definition: <prod dz> - C_ij C_kl - C_ik C_jl - C_il C_jk."""
    S = tuple(sorted(S))
    a, b, c, d = S
    m = {i: mu[(i,)] for i in S}
    central = 0.0
    for r in range(5):
        for T in itertools.combinations(S, r):
            rest = [i for i in S if i not in T]
            central += (-1) ** len(rest) * (mu[T] if T else 1.0) * np.prod([m[i] for i in rest])
    C = lambda i, j: mu[tuple(sorted((i, j)))] - m[i] * m[j]
    return float(central - C(a, b) * C(c, d) - C(a, c) * C(b, d) - C(a, d) * C(b, c))


@dataclass
class Catalog:
    """Observables fixed BEFORE looking at any hardware data: all m_i, all edge C_ij, >=3 four-site G/kappa."""
    n: int
    edges: list[tuple[int, int]]
    clusters: list[Subset]                       # sorted logical four-site sets

    @staticmethod
    def from_patch(patch) -> "Catalog":
        return Catalog(patch.n, [tuple(e) for e in patch.edges], [tuple(sorted(c)) for c in patch.clusters])

    def subsets(self) -> set[Subset]:
        out: set[Subset] = {(i,) for i in range(self.n)} | {tuple(sorted(e)) for e in self.edges}
        for c in self.clusters:
            for r in range(1, 5):
                out |= set(itertools.combinations(c, r))
        return out

    def evaluate(self, mu: dict[Subset, float]) -> dict[tuple, float]:
        """Observable label -> value. Labels: ('m',(i,)), ('M',()), ('C',(i,j)), ('G',S4), ('kappa',S4)."""
        out: dict[tuple, float] = {}
        for i in range(self.n):
            out[("m", (i,))] = mu[(i,)]
        out[("M", ())] = float(np.mean([mu[(i,)] for i in range(self.n)]))
        for (i, j) in self.edges:
            out[("C", (i, j))] = mu[(i, j)] - mu[(i,)] * mu[(j,)]
        for c in self.clusters:
            out[("G", c)] = mu[c]
            out[("kappa", c)] = kappa_partition(mu, c)
        return out

    def from_patterns(self, patterns, weights) -> dict[tuple, float]:
        return self.evaluate(parity_moments(patterns, weights, self.subsets()))
