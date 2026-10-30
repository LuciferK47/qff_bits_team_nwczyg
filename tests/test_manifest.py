import pytest
from qiskit import QuantumCircuit

from qtrust import manifest as M
from qtrust.hardware import Compiled
from qtrust.params import Params


def _fake_compile(report_overrides=None, measures=True, patch=None):
    def fake(qc, p, backend, variant, **kw):
        c = QuantumCircuit(max(p.nodes) + 1, p.n)
        for i in range(p.n):
            c.measure(p.nodes[i] if measures else p.nodes[(i + 1) % p.n], i)
        rep = dict(ok=True, n_cz=0, n_rzz=0, n_2q=0, n_swap=0, depth_2q=10, depth_total=12, n_gates=5, duration_s=1e-6,
                   invalid_rzz_angles=[], couplings_used_subset_of_patch=True, couplings_used=0, patch_edges=len(p.edges))
        rep.update(report_overrides or {})
        return Compiled(c, variant, rep)
    return fake


@pytest.mark.parametrize("override,msg", [(dict(ok=False), "ISA"), (dict(depth_2q=301), "ceiling")])
def test_unsafe_circuits_are_refused_not_recorded(patches, monkeypatch, override, msg):
    monkeypatch.setattr(M, "compile_circuit", _fake_compile(override))
    with pytest.raises(M.ManifestGateError, match=msg):
        M._compile("x", QuantumCircuit(1), patches["P12"], Params(), 0, None, "fractional", 10, None)


def test_wrong_measurement_map_is_refused(patches, monkeypatch):
    monkeypatch.setattr(M, "compile_circuit", _fake_compile(measures=False))
    with pytest.raises(M.ManifestGateError, match="measurement map"):
        M._compile("x", QuantumCircuit(1), patches["P12"], Params(), 0, None, "fractional", 10, None)


def test_depth_exactly_at_ceiling_is_allowed_but_headroom_is_flagged(patches, monkeypatch):
    monkeypatch.setattr(M, "compile_circuit", _fake_compile(dict(depth_2q=300)))
    item = M._compile("x", QuantumCircuit(1), patches["P12"], Params(), 0, None, "fractional", 10, None)
    rows, _ = M.summarize({"j": [item]}, 250e-6, "offline")
    assert rows[0]["within_ceiling"] and rows[0]["low_headroom"] and not rows[0]["within_aim"]


def test_experiment_id_and_markdown_written(patches, monkeypatch, tmp_path):
    monkeypatch.setattr(M, "compile_circuit", _fake_compile())
    item = M._compile("x", QuantumCircuit(1), patches["P12"], Params(), 4, None, "fractional", 10, None)
    assert len(item.experiment_id) == 16 and item.measure_map_ok
    rows, totals = M.summarize({"1_pilot": [item]}, 250e-6, "offline")
    M.write_markdown(rows, totals, Params(), tmp_path / "m.md", "offline")
    text = (tmp_path / "m.md").read_text()
    assert "DRY RUN" in text and "nothing submitted" in text and "ASSUMPTION" in text and item.qpy_sha in text
