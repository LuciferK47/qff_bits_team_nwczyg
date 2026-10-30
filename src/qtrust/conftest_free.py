"""Tiny helper patches (chains) used by validation controls; not device patches."""
import networkx as nx

from .graph import Patch, edge_colouring


def chain_patch(n: int) -> Patch:
    G = nx.path_graph(n)
    edges = sorted(tuple(sorted(e)) for e in G.edges)
    return Patch(f"chain{n}", n, list(range(n)), edges, edge_colouring(G), [], list(range(n)), "synthetic chain")
