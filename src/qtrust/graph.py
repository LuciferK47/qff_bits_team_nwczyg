"""Device graph extraction, induced patches, edge colouring and clusters.

Offline development uses the FakeFez snapshot. Everything derived from it is labelled
``source = "FakeFez snapshot (offline, NOT live)"``; a live backend can be injected instead.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import reverse_cuthill_mckee

OFFLINE_SOURCE = "FakeFez snapshot (offline, NOT live)"


# ---------------------------------------------------------------- device snapshot
@dataclass
class DeviceSnapshot:
    name: str
    source: str
    num_qubits: int
    edges: list[tuple[int, int]]                 # undirected, sorted pairs
    cz_error: dict[tuple[int, int], float]       # worst direction per pair
    readout_error: dict[int, float]
    rep_delay: float | None = None
    meta: dict = field(default_factory=dict)

    def graph(self, cz_error_max=0.05, readout_error_max=0.08) -> nx.Graph:
        """Coupling graph with faulty qubits/couplers removed (never edges between good qubits)."""
        bad_q = {q for q, e in self.readout_error.items() if e is None or e > readout_error_max}
        G = nx.Graph()
        for (a, b) in self.edges:
            e = self.cz_error.get((a, b))
            if e is None or e > cz_error_max or a in bad_q or b in bad_q:
                continue
            G.add_edge(a, b, cz_error=e)
        for q in G.nodes:
            G.nodes[q]["readout_error"] = self.readout_error[q]
        return G

    def to_json(self) -> dict:
        return {
            "name": self.name, "source": self.source, "num_qubits": self.num_qubits,
            "edges": [list(e) for e in self.edges],
            "cz_error": {f"{a}-{b}": v for (a, b), v in self.cz_error.items()},
            "readout_error": {str(q): v for q, v in self.readout_error.items()},
            "rep_delay": self.rep_delay, "meta": self.meta,
        }

    @staticmethod
    def from_json(d: dict) -> "DeviceSnapshot":
        return DeviceSnapshot(
            d["name"], d["source"], d["num_qubits"], [tuple(e) for e in d["edges"]],
            {tuple(map(int, k.split("-"))): v for k, v in d["cz_error"].items()},
            {int(k): v for k, v in d["readout_error"].items()}, d.get("rep_delay"), d.get("meta", {}),
        )


def snapshot_from_backend(backend, name: str, source: str) -> DeviceSnapshot:
    """Build a snapshot from any BackendV2 (live or fake). Caller supplies the honest ``source`` label."""
    t = backend.target
    cz = {}
    for (a, b), props in t["cz"].items():
        key = (min(a, b), max(a, b))
        err = 1.0 if props is None or props.error is None else props.error
        cz[key] = max(cz.get(key, 0.0), err)           # worst direction
    ro = {q: (t["measure"][(q,)].error if t["measure"][(q,)].error is not None else 1.0)
          for q in range(backend.num_qubits)}
    return DeviceSnapshot(
        name, source, backend.num_qubits, sorted(cz), cz, ro,
        getattr(backend, "default_rep_delay", None),
        {"operation_names": sorted(backend.operation_names)},
    )


def load_fakefez_snapshot(cache: Path | None = None) -> DeviceSnapshot:
    if cache and cache.exists():
        return DeviceSnapshot.from_json(json.loads(cache.read_text()))
    from qiskit_ibm_runtime.fake_provider import FakeFez
    import qiskit_ibm_runtime
    snap = snapshot_from_backend(FakeFez(), "ibm_fez", OFFLINE_SOURCE)
    snap.meta["qiskit_ibm_runtime"] = qiskit_ibm_runtime.__version__
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(snap.to_json(), indent=1))
    return snap


# ---------------------------------------------------------------- graph utilities
def graph_hash(edges) -> str:
    return hashlib.sha256(json.dumps(sorted(map(list, edges))).encode()).hexdigest()[:16]


def cycle_rank(H: nx.Graph) -> int:
    return H.number_of_edges() - H.number_of_nodes() + nx.number_connected_components(H)


def star_centres(H: nx.Graph) -> list[int]:
    """Centres with exactly three neighbours in the patch (heavy-hex maximum degree is 3)."""
    return sorted(v for v in H if H.degree(v) == 3)


def edge_colouring(H: nx.Graph) -> dict[tuple[int, int], int]:
    """Proper edge colouring with Delta colours for a bipartite graph (Konig), via alternating paths.

    Heavy-hex is bipartite with maximum degree 3, so 3 layers of disjoint edges always suffice.
    """
    assert nx.is_bipartite(H), "edge colouring with Delta colours needs a bipartite graph"
    delta = max(d for _, d in H.degree)
    col: dict[frozenset, int] = {}
    at: dict[int, dict[int, int]] = {v: {} for v in H}          # at[v][colour] = neighbour

    def free(v):
        return next(c for c in range(delta) if c not in at[v])

    for (u, v) in sorted(map(tuple, map(sorted, H.edges))):
        a, b = free(u), free(v)
        if a != b:
            # flip the a/b alternating path starting at v (colour a) so that colour a is free at v
            path, x, c = [], v, a
            while c in at[x]:
                y = at[x][c]
                path.append((x, y, c))
                x, c = y, (b if c == a else a)
            for (x, y, c) in path:
                del at[x][c]; del at[y][c]; col.pop(frozenset((x, y)))
            for (x, y, c) in path:
                nc = b if c == a else a
                at[x][nc] = y; at[y][nc] = x; col[frozenset((x, y))] = nc
        col[frozenset((u, v))] = a
        at[u][a] = v; at[v][a] = u
    out = {tuple(sorted(e)): c for e, c in col.items()}
    # self-check: proper, complete
    assert len(out) == H.number_of_edges()
    for v in H:
        cs = [out[tuple(sorted((v, w)))] for w in H[v]]
        assert len(cs) == len(set(cs)), "edge colouring is not proper"
    return out


def lightcone(H: nx.Graph, sites, hops: int) -> set[int]:
    """Nodes within ``hops`` graph hops of ``sites`` (support of a Heisenberg-evolved local operator
    after ``hops`` bond layers; field layers act on-site so they do not enlarge it)."""
    seen = set(sites)
    frontier = set(sites)
    for _ in range(hops):
        frontier = {w for v in frontier for w in H[v]} - seen
        seen |= frontier
    return seen


def mps_order(H: nx.Graph) -> tuple[list[int], dict]:
    """Choose the 1D ordering (RCM vs BFS from each node) with the smallest maximum bond cut."""
    nodes = sorted(H.nodes)
    idx = {v: i for i, v in enumerate(nodes)}

    def max_cut(order):
        pos = {v: i for i, v in enumerate(order)}
        cuts = np.zeros(len(order) - 1, dtype=int)
        for a, b in H.edges:
            lo, hi = sorted((pos[a], pos[b]))
            cuts[lo:hi] += 1
        return int(cuts.max()), float(cuts.mean())

    cands = {}
    A = csr_matrix(nx.to_scipy_sparse_array(H, nodelist=nodes))
    cands["rcm"] = [nodes[i] for i in reverse_cuthill_mckee(A, symmetric_mode=True)]
    best_bfs = None
    for s in nodes:
        order = list(nx.bfs_tree(H, s))
        m = max_cut(order)
        if best_bfs is None or m < best_bfs[0]:
            best_bfs = (m, order)
    cands["bfs"] = best_bfs[1]
    cands["sorted"] = nodes
    scores = {k: max_cut(v) for k, v in cands.items()}
    best = min(scores, key=lambda k: scores[k])
    return cands[best], {"chosen": best, "max_cut_mean_cut": {k: list(v) for k, v in scores.items()}}


# ---------------------------------------------------------------- patches
@dataclass
class Patch:
    pid: str
    n: int
    nodes: list[int]                               # physical ids; logical qubit i == nodes[i]
    edges: list[tuple[int, int]]                   # logical-index pairs (i<j), ALL induced couplings
    colours: dict[tuple[int, int], int]            # logical edge -> layer
    clusters: list[list[int]]                      # four-site sets (logical idx): centre + 3 neighbours
    mps_order: list[int]                           # logical indices
    source: str
    meta: dict = field(default_factory=dict)

    def graph(self) -> nx.Graph:
        G = nx.Graph(); G.add_nodes_from(range(self.n)); G.add_edges_from(self.edges); return G

    @property
    def hash(self) -> str:
        """STRUCTURAL hash (logical edge list only). Kept for compatibility; see ``physical_id`` for identity."""
        return graph_hash(self.edges)

    @property
    def physical_id(self) -> str:
        """Identity of the physical patch: backend, data source, calibration timestamp, ordered physical qubits and
        the physical couplings. Two different device regions with the same logical shape get different ids."""
        payload = dict(backend=self.meta.get("backend"), source=self.source,
                       calibration_timestamp=self.meta.get("calibration_timestamp"), nodes=list(self.nodes),
                       edges=sorted([sorted((self.nodes[a], self.nodes[b])) for a, b in self.edges]))
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

    def to_json(self) -> dict:
        return {
            "pid": self.pid, "n": self.n, "nodes": self.nodes, "edges": [list(e) for e in self.edges],
            "colours": {f"{a}-{b}": c for (a, b), c in self.colours.items()},
            "clusters": self.clusters, "mps_order": self.mps_order, "hash": self.hash, "physical_id": self.physical_id,
            "source": self.source, "meta": copy.deepcopy(self.meta),
        }

    @staticmethod
    def from_json(d: dict) -> "Patch":
        p = Patch(d["pid"], d["n"], d["nodes"], [tuple(e) for e in d["edges"]],
                  {tuple(map(int, k.split("-"))): c for k, c in d["colours"].items()},
                  d["clusters"], d["mps_order"], d["source"], copy.deepcopy(d.get("meta", {})))
        assert p.hash == d["hash"], "patch file does not match its recorded hash"
        if "physical_id" in d:
            assert p.physical_id == d["physical_id"], "patch file does not match its recorded physical id"
        return p

    def save(self, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{self.pid}.json").write_text(json.dumps(self.to_json(), indent=1))


def pick_clusters(H: nx.Graph, k: int = 4) -> list[list[int]]:
    """Distinct four-site stars (centre + its three neighbours), spread apart (farthest-first)."""
    centres = star_centres(H)
    if not centres:
        return []
    chosen = [centres[0]]
    dist = dict(nx.all_pairs_shortest_path_length(H))
    while len(chosen) < min(k, len(centres)):
        nxt = max((c for c in centres if c not in chosen), key=lambda c: (min(dist[c][s] for s in chosen), -c))
        chosen.append(nxt)
    return [[c, *sorted(H[c])] for c in chosen]


def build_patch(pid: str, G: nx.Graph, nodes, source: str, meta: dict | None = None) -> Patch:
    """Induce the patch on ``nodes``: keep EVERY device coupling between selected qubits (incl. cycles)."""
    nodes = sorted(nodes)
    sub = G.subgraph(nodes)
    assert nx.is_connected(sub), "patch must be connected"
    lidx = {p: i for i, p in enumerate(nodes)}
    L = nx.Graph(); L.add_nodes_from(range(len(nodes)))
    L.add_edges_from((lidx[a], lidx[b]) for a, b in sub.edges)
    edges = sorted(tuple(sorted(e)) for e in L.edges)
    order, order_meta = mps_order(L)
    m = dict(meta or {})
    m.update({
        "n_edges": len(edges), "cycle_rank": cycle_rank(L), "n_stars": len(star_centres(L)),
        "degree_hist": {i: c for i, c in enumerate(nx.degree_histogram(L)) if c},
        "mean_cz_error": float(np.mean([sub[a][b]["cz_error"] for a, b in sub.edges])),
        "mean_readout_error": float(np.mean([G.nodes[p]["readout_error"] for p in nodes])),
        "mps_order_info": order_meta,
    })
    if cycle_rank(L) == 0:                       # small tree patch: needed for the level-statistics test
        m["n_automorphisms"] = automorphism_count(L)
        m["symmetry_breaking_site"] = symmetry_breaking_site(L)
    return Patch(pid, len(nodes), nodes, edges, edge_colouring(L), pick_clusters(L), order, source, m)


def _score(G: nx.Graph, nodes) -> float:
    sub = G.subgraph(nodes)
    return float(np.mean([d["cz_error"] for *_, d in sub.edges(data=True)]) +
                 np.mean([G.nodes[v]["readout_error"] for v in nodes]))


def automorphism_count(H: nx.Graph, marked: int | None = None) -> int:
    """Order of the graph automorphism group; ``marked`` optionally pins one distinguished vertex
    (used to model the PDF's symmetry-breaking recipe: scale hz on a single site)."""
    if marked is not None:
        H = H.copy()
        nx.set_node_attributes(H, {v: (v == marked) for v in H}, "mark")
        nm = lambda a, b: a["mark"] == b["mark"]
    else:
        nm = None
    return sum(1 for _ in nx.isomorphism.GraphMatcher(H, H, node_match=nm).isomorphisms_iter())


def symmetry_breaking_site(H: nx.Graph) -> int | None:
    """A site whose individual marking leaves a trivial automorphism group (None if no such site)."""
    for v in sorted(H):
        if automorphism_count(H, marked=v) == 1:
            return v
    return None


def find_tree_patch(G: nx.Graph, n: int, min_stars: int, seed: int, tries: int = 4000) -> list[int]:
    """Induced TREE on ``n`` qubits with >= ``min_stars`` full degree-3 centres, preferring the smallest
    spatial symmetry group and then the best calibration.

    On heavy-hex a tree with 3 star centres and 12 qubits always keeps a leaf-swap/mirror symmetry,
    so full asymmetry is impossible; the PDF's own recipe (hz scaled by 1.2 on one site) is used for the
    optional level-statistics test instead.
    """
    rng = random.Random(seed)
    best = None
    deg3 = [v for v in G if G.degree(v) == 3]
    seen = set()
    for _ in range(tries):
        S = {rng.choice(deg3)}
        while len(S) < n:
            front = [w for v in S for w in G[v] if w not in S and sum(x in S for x in G[w]) == 1]
            if not front:
                break
            front.sort(key=lambda w: -G.degree(w))
            S.add(front[0] if rng.random() < 0.5 else rng.choice(front))
        key = frozenset(S)
        if len(S) != n or key in seen:
            continue
        seen.add(key)
        H = G.subgraph(S)
        if cycle_rank(H) != 0 or len(star_centres(H)) < min_stars:
            continue
        rank = (automorphism_count(H), _score(G, S))
        if best is None or rank < best[0]:
            best = (rank, sorted(S))
    if best is None:
        raise RuntimeError("no tree patch with the requested number of stars found")
    return best[1]


def find_ring_patch(G: nx.Graph) -> list[int]:
    """Best 12-ring (induced cycle) plus its six outward pendants (18 qubits)."""
    best = None
    for cyc in nx.simple_cycles(G, length_bound=12):
        if len(cyc) != 12 or G.subgraph(cyc).number_of_edges() != 12:
            continue
        pend = {w for v in cyc for w in G[v] if w not in cyc}
        if len(pend) != 6:
            continue
        S = set(cyc) | pend
        if G.subgraph(S).number_of_edges() != 12 + 6:    # pendants must be genuine leaves
            continue
        sc = _score(G, S)
        if best is None or sc < best[0]:
            best = (sc, sorted(S))
    if best is None:
        raise RuntimeError("no 12-ring + 6 pendants found on this device")
    return best[1]


def grow_patch(G: nx.Graph, start, n: int, bad_edges=frozenset()) -> list[int]:
    """Greedy nested growth: prefer nodes that close cycles (most neighbours already inside), then low error.

    A node is never added if a *faulty* device coupler (``bad_edges``, absent from G) would join it to the
    patch: induced patches must keep every internal coupling, so a bad coupler means the node is unusable.
    """
    S = set(start)
    while len(S) < n:
        front = {w for v in S for w in G[v]} - S
        front = {w for w in front if not any(tuple(sorted((w, x))) in bad_edges for x in S)}
        if not front:
            raise RuntimeError(f"cannot grow patch beyond {len(S)} qubits without a faulty internal coupler")
        w = min(front, key=lambda w: (-sum(x in S for x in G[w]), G.nodes[w]["readout_error"], w))
        S.add(w)
    return sorted(S)


def build_all_patches(snap: DeviceSnapshot, seed: int = 20261029, faulty=None) -> dict[str, Patch]:
    G = snap.graph(**(faulty or {}))
    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    p12 = find_tree_patch(G, 12, 3, seed)
    p18 = find_ring_patch(G)
    bad = frozenset(tuple(sorted(e)) for e in snap.edges) - frozenset(tuple(sorted(e)) for e in G.edges)
    p24 = grow_patch(G, p18, 24, bad)
    p40 = grow_patch(G, p24, 40, bad)
    patches = {pid: build_patch(pid, G, nodes, snap.source, {"backend": snap.name})
               for pid, nodes in [("P12", p12), ("P18", p18), ("P24", p24), ("P40", p40)]}
    for p in patches.values():
        assert_all_couplings_kept(snap, p)
    return patches


def assert_all_couplings_kept(snap: DeviceSnapshot, patch: Patch) -> None:
    """Every device coupling between two selected qubits must be in the patch (open boundaries,
    cycles included). The quality filter may remove qubits but must never drop an internal coupler."""
    chosen = set(patch.nodes)
    full = {tuple(sorted(e)) for e in snap.edges if e[0] in chosen and e[1] in chosen}
    have = {tuple(sorted((patch.nodes[a], patch.nodes[b]))) for a, b in patch.edges}
    if full != have:
        raise AssertionError(f"{patch.pid}: device couplings {sorted(full ^ have)} dropped/added by filtering")


def draw_patch(patch: Patch, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    G = patch.graph()
    pos = nx.kamada_kawai_layout(G)
    pal = ["#1b9e77", "#d95f02", "#7570b3"]
    fig, ax = plt.subplots(figsize=(7, 6))
    nx.draw_networkx_edges(G, pos, ax=ax, edgelist=list(patch.colours),
                           edge_color=[pal[c] for c in patch.colours.values()], width=2.5)
    star = {s for c in patch.clusters for s in c}
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=["#fdd835" if v in star else "#cfd8dc" for v in G],
                           edgecolors="k", node_size=420)
    nx.draw_networkx_labels(G, pos, {i: str(p) for i, p in enumerate(patch.nodes)}, font_size=7, ax=ax)
    ax.set_title(f"{patch.pid}: n={patch.n}, edges={len(patch.edges)}, cycle rank={patch.meta['cycle_rank']}, "
                 f"hash={patch.hash}\nedge colour = bond layer; yellow = four-site clusters (labels: physical qubit id)\n"
                 f"{patch.source}", fontsize=8)
    ax.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- topology metrics and the compact candidate patch
def topology_metrics(H: nx.Graph, mps_cut: int | None = None) -> dict:
    """Shape descriptors used to argue what a patch can and cannot say about 2D hardness."""
    return dict(n=H.number_of_nodes(), edges=H.number_of_edges(), cycle_rank=cycle_rank(H),
                diameter=nx.diameter(H), radius=nx.radius(H), mean_degree=round(2 * H.number_of_edges() / H.number_of_nodes(), 3),
                n_stars=len(star_centres(H)), mps_max_cut=mps_cut)


def find_compact_patch(G: nx.Graph, n: int, bad_edges=frozenset(), seed: int = 20261029, tries: int = 400) -> list[int]:
    """Cycle-rich, compact induced patch of ``n`` qubits.

    Declared score (lexicographic, smaller is better): (-cycle_rank, diameter, mean CZ error). Growth from a random seed
    always adds the frontier node that closes the most cycles, then the one closest to the seed. A node joined to the
    patch by a faulty coupler is never added (induced patches must keep every internal coupling)."""
    rng = random.Random(seed)
    nodes = sorted(G.nodes)
    best = None
    for _ in range(tries):
        s = rng.choice(nodes)
        dist = nx.single_source_shortest_path_length(G, s)
        S = {s}
        while len(S) < n:
            front = {w for v in S for w in G[v]} - S
            front = {w for w in front if not any(tuple(sorted((w, x))) in bad_edges for x in S)}
            if not front:
                break
            S.add(min(front, key=lambda w: (-sum(x in S for x in G[w]), dist[w], rng.random())))
        if len(S) != n or not nx.is_connected(G.subgraph(S)):
            continue
        H = G.subgraph(S)
        score = (-cycle_rank(H), nx.diameter(H), _score(G, S))
        if best is None or score < best[0]:
            best = (score, sorted(S))
    if best is None:
        raise RuntimeError("no compact patch found")
    return best[1]
