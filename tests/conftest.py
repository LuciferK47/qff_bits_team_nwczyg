from pathlib import Path

import networkx as nx
import pytest

from qtrust.graph import Patch, edge_colouring, load_fakefez_snapshot, build_all_patches, pick_clusters

ROOT = Path(__file__).resolve().parents[1]


def tiny_patch(n, edges, pid="T") -> Patch:
    G = nx.Graph(); G.add_nodes_from(range(n)); G.add_edges_from(edges)
    edges = sorted(tuple(sorted(e)) for e in G.edges)
    return Patch(pid, n, list(range(n)), edges, edge_colouring(G), pick_clusters(G), list(range(n)), "test")


@pytest.fixture(scope="session")
def star4():
    return tiny_patch(4, [(0, 1), (0, 2), (0, 3)], "star4")


@pytest.fixture(scope="session")
def tree7():
    # centre 0 with arms; two stars (0 and 1) -> exercises cumulants on a non-trivial graph
    return tiny_patch(7, [(0, 1), (0, 2), (0, 3), (1, 4), (1, 5), (5, 6)], "tree7")


@pytest.fixture(scope="session")
def ring6():
    return tiny_patch(6, [(i, (i + 1) % 6) for i in range(6)], "ring6")


@pytest.fixture(scope="session")
def snapshot():
    return load_fakefez_snapshot(ROOT / "raw/backend_snapshots/fakefez_snapshot.json")


@pytest.fixture(scope="session")
def patches(snapshot):
    return build_all_patches(snapshot)
