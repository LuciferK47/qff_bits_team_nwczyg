"""Independent exact references.

(a) ``trotter_states``: a numpy kernel for the fixed Trotter circuit that never touches Qiskit gates.
(b) ``hamiltonian`` + ``continuous_state``: sparse H and expm_multiply for exp(-iHt)|0..0>.
Keeping (a) and (b) separate is what separates Trotter error (circuit vs exp(-iHt)) from simulation error.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import expm_multiply

from .graph import Patch
from .params import Params


def statevector_bytes(n: int) -> int:
    return 16 * 2 ** n


def _zarr(n: int) -> np.ndarray:
    """z[i, k] = +1 if bit i of basis index k is 0 else -1 (int8)."""
    k = np.arange(2 ** n, dtype=np.uint32)
    return np.stack([(1 - 2 * ((k >> i) & 1)).astype(np.int8) for i in range(n)])


def _field_matrix(tau: float, prm: Params) -> np.ndarray:
    """exp(+i tau (hx X + hz Z)) in closed form: cos(w tau) I + i sin(w tau)(hx X + hz Z)/w."""
    w = prm.omega
    X = np.array([[0, 1], [1, 0]], dtype=complex)
    Z = np.array([[1, 0], [0, -1]], dtype=complex)
    return np.cos(w * tau) * np.eye(2) + 1j * np.sin(w * tau) * (prm.hx * X + prm.hz * Z) / w


def _apply_all(psi: np.ndarray, n: int, U: np.ndarray) -> np.ndarray:
    psi = psi.reshape((2,) * n)
    for i in range(n):
        ax = n - 1 - i                                   # axis 0 is the most significant bit
        psi = np.moveaxis(np.tensordot(U, psi, axes=([1], [ax])), 0, ax)
    return np.ascontiguousarray(psi).reshape(-1)


def iter_trotter_states(patch: Patch, prm: Params, N_list):
    """Yield (N, U_N|0..0>) in increasing N from ONE pass:  psi_N = F(h) [B F(dt)]^{N-1} B F(h) |0>.
    A generator, so large patches never hold more than a couple of statevectors."""
    n = patch.n
    z = _zarr(n)
    zz = np.zeros(2 ** n, dtype=np.float64)
    for a, b in patch.edges:
        zz += (z[a] * z[b])
    bond = np.exp(1j * prm.J * prm.dt * zz)              # exp(-i H_b dt) = exp(+i J dt sum z z)
    del z, zz
    Fh, Fd = _field_matrix(prm.dt / 2, prm), _field_matrix(prm.dt, prm)
    want = sorted(set(N_list))
    psi = np.zeros(2 ** n, dtype=complex)
    psi[0] = 1.0
    if 0 in want:
        yield 0, psi
    phi = _apply_all(psi, n, Fh) * bond                  # B F(h)|0> = state after the first bond layer
    for N in range(1, want[-1] + 1):
        if N > 1:
            phi = _apply_all(phi, n, Fd) * bond
        if N in want:
            yield N, _apply_all(phi, n, Fh)


def trotter_states(patch: Patch, prm: Params, N_list) -> dict[int, np.ndarray]:
    """Dict version of :func:`iter_trotter_states` (small patches / tests)."""
    return dict(iter_trotter_states(patch, prm, N_list))


def hamiltonian(patch: Patch, prm: Params) -> sp.csr_matrix:
    """H = -J sum ZZ - sum (hx X + hz Z) as a sparse 2^n x 2^n matrix (n <= ~20)."""
    n = patch.n
    z = _zarr(n).astype(np.float64)
    diag = np.zeros(2 ** n)
    for a, b in patch.edges:
        diag -= prm.J * z[a] * z[b]
    diag -= prm.hz * z.sum(axis=0)
    idx = np.arange(2 ** n)
    H = sp.diags(diag).tocsr()
    for i in range(n):
        H = H - prm.hx * sp.csr_matrix((np.ones(2 ** n), (idx, idx ^ (1 << i))), shape=(2 ** n,) * 2)
    return H.tocsr()


def continuous_states(patch: Patch, prm: Params, times) -> dict[float, np.ndarray]:
    """exp(-iHt)|0..0> for each t via sparse expm_multiply (independent of any circuit code)."""
    H = hamiltonian(patch, prm)
    psi0 = np.zeros(2 ** patch.n, dtype=complex)
    psi0[0] = 1.0
    return {t: (psi0 if t == 0 else expm_multiply(-1j * t * H, psi0)) for t in times}


def probs(psi: np.ndarray) -> np.ndarray:
    return (psi.conj() * psi).real


def all_patterns(n: int) -> np.ndarray:
    return np.arange(2 ** n, dtype=np.uint32 if n <= 32 else np.uint64)


# ------------------------------------------------------------------ light-cone exact reference (large patches)
def subpatch(patch: Patch, nodes) -> Patch:
    """Induced sub-patch on a subset of logical qubits (re-indexed 0..k-1 in sorted order)."""
    import networkx as nx
    from .graph import edge_colouring
    nodes = sorted(nodes)
    idx = {q: i for i, q in enumerate(nodes)}
    G = nx.Graph(); G.add_nodes_from(range(len(nodes)))
    G.add_edges_from((idx[a], idx[b]) for a, b in patch.edges if a in idx and b in idx)
    edges = sorted(tuple(sorted(e)) for e in G.edges)
    return Patch(f"{patch.pid}.sub", len(nodes), [patch.nodes[q] for q in nodes], edges,
                 edge_colouring(G), [], list(range(len(nodes))), patch.source)


def lightcone_moments(patch: Patch, prm: Params, N: int, groups, max_qubits: int = 26):
    """Exact subset moments for each site group after N steps, via the backward light cone.

    A local operator spreads by at most one hop per bond layer (field layers are on-site), so after N steps it
    lives within N hops; every gate outside that cone cancels in U^dag O U. Simulating the induced sub-circuit
    on the cone is therefore EXACT, however large the full patch is.
    """
    import itertools
    from .graph import lightcone
    from .moments import parity_moments
    G = patch.graph()
    mu: dict = {(): 1.0}
    sizes = {}
    for g in groups:
        cone = lightcone(G, g, N)
        sizes[g] = len(cone)
        if len(cone) > max_qubits:
            raise MemoryError(f"light cone of {g} has {len(cone)} qubits (> {max_qubits})")
        sub = subpatch(patch, cone)
        loc = {q: i for i, q in enumerate(sorted(cone))}
        (_, psi), = exact_iter_one(sub, prm, N)
        p = probs(psi)
        pats = all_patterns(sub.n)
        for r in range(1, len(g) + 1):
            for T in itertools.combinations(g, r):
                key = tuple(sorted(T))
                if key not in mu:
                    mu[key] = parity_moments(pats, p, [tuple(sorted(loc[q] for q in T))])[tuple(sorted(loc[q] for q in T))]
    return mu, sizes


def exact_iter_one(patch: Patch, prm: Params, N: int):
    return list(iter_trotter_states(patch, prm, [N]))
