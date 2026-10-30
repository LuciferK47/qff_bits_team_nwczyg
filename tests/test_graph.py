import networkx as nx
import pytest

from qtrust.graph import (Patch, assert_all_couplings_kept, cycle_rank, edge_colouring, lightcone,
                          star_centres)


def test_expected_patch_sizes(patches):
    assert {k: p.n for k, p in patches.items()} == {"P12": 12, "P18": 18, "P24": 24, "P40": 40}


def test_every_device_coupling_between_selected_qubits_is_kept(snapshot, patches):
    for p in patches.values():
        assert_all_couplings_kept(snapshot, p)             # includes cycle-closing couplings


def test_cycles_preserved_and_connected(patches):
    assert cycle_rank(patches["P12"].graph()) == 0
    assert cycle_rank(patches["P18"].graph()) >= 1         # the 12-ring is kept
    assert cycle_rank(patches["P40"].graph()) >= cycle_rank(patches["P18"].graph())
    for p in patches.values():
        assert nx.is_connected(p.graph())


def test_nested_patches(patches):
    assert set(patches["P18"].nodes) <= set(patches["P24"].nodes) <= set(patches["P40"].nodes)


def test_edge_colouring_proper_complete_three_layers(patches):
    for p in patches.values():
        G = p.graph()
        assert set(p.colours) == {tuple(sorted(e)) for e in G.edges}      # every edge used exactly once
        assert len(set(p.colours.values())) <= 3
        for v in G:
            cs = [p.colours[tuple(sorted((v, w)))] for w in G[v]]
            assert len(cs) == len(set(cs))


def test_clusters_are_stars_with_real_couplings(patches):
    for pid, p in patches.items():
        G = p.graph()
        assert len(p.clusters) >= 3
        assert len({tuple(sorted(c)) for c in p.clusters}) == len(p.clusters)
        for c in p.clusters:
            centre, *leaves = c
            assert len(leaves) == 3 and all(G.has_edge(centre, l) for l in leaves)


def test_patch_json_round_trip_and_hash(patches, tmp_path):
    for p in patches.values():
        p.save(tmp_path)
        q = Patch.from_json(__import__("json").loads((tmp_path / f"{p.pid}.json").read_text()))
        assert q.edges == p.edges and q.hash == p.hash


def test_lightcone_radius():
    G = nx.path_graph(10)
    assert lightcone(G, [5], 0) == {5}
    assert lightcone(G, [5], 2) == {3, 4, 5, 6, 7}


def test_no_faulty_qubits_or_couplers_used(snapshot, patches):
    for p in patches.values():
        for q in p.nodes:
            assert snapshot.readout_error[q] <= 0.08
        for a, b in p.edges:
            e = snapshot.cz_error[tuple(sorted((p.nodes[a], p.nodes[b])))]
            assert e <= 0.05


def test_physical_id_distinguishes_patches_with_identical_logical_structure():
    from conftest import tiny_patch
    a = tiny_patch(4, [(0, 1), (0, 2), (0, 3)], "a")
    b = tiny_patch(4, [(0, 1), (0, 2), (0, 3)], "b")
    b.nodes = [10, 11, 12, 13]                             # same logical edges, different physical qubits
    assert a.hash == b.hash and a.physical_id != b.physical_id


def test_physical_id_depends_on_source_and_calibration(patches):
    p = patches["P18"]
    q = Patch.from_json(p.to_json())
    q.source = "live backend"
    assert q.physical_id != p.physical_id
    q = Patch.from_json(p.to_json()); q.meta["calibration_timestamp"] = "2026-10-30T00:00:00"
    assert q.physical_id != p.physical_id


def test_saved_patch_files_carry_a_verified_physical_id(patches, tmp_path):
    import json
    for p in patches.values():
        p.save(tmp_path)
        d = json.loads((tmp_path / f"{p.pid}.json").read_text())
        assert d["physical_id"] == p.physical_id
        d["nodes"][0] += 1                                  # tamper with the physical qubits
        import pytest
        with pytest.raises(AssertionError):
            Patch.from_json(d)


def test_experiment_id_changes_with_dt_and_n(patches):
    from qtrust.ids import experiment_id
    from qtrust.params import Params
    p = patches["P12"]
    base = experiment_id(p, Params(dt=0.1), 10)
    assert base != experiment_id(p, Params(dt=0.2), 10) and base != experiment_id(p, Params(dt=0.1), 20)
    assert base == experiment_id(p, Params(dt=0.1), 10)


def test_compact_candidate_is_valid_and_more_compact_than_p40(snapshot, patches):
    from qtrust.graph import build_patch, find_compact_patch, topology_metrics
    G = snapshot.graph(); G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    bad = frozenset(tuple(sorted(e)) for e in snapshot.edges) - frozenset(tuple(sorted(e)) for e in G.edges)
    nodes = find_compact_patch(G, 40, bad, tries=60)
    p = build_patch("P40c", G, nodes, snapshot.source, {"backend": snapshot.name})
    assert_all_couplings_kept(snapshot, p) and p.n == 40 and nx.is_connected(p.graph())
    a, b = topology_metrics(p.graph()), topology_metrics(patches["P40"].graph())
    assert a["cycle_rank"] >= b["cycle_rank"] and a["diameter"] < b["diameter"]


def test_p40_is_documented_as_elongated(patches):
    from qtrust.graph import topology_metrics
    m = topology_metrics(patches["P40"].graph())
    assert (m["n"], m["edges"], m["cycle_rank"], m["diameter"]) == (40, 41, 2, 22)
