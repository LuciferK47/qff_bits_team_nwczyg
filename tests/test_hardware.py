import numpy as np
import pytest
from qiskit.quantum_info import Statevector
from qiskit_ibm_runtime.fake_provider import FakeFez

from qtrust.circuits import trotter_circuit
from qtrust.hardware import compile_circuit, restrict_to_patch
from qtrust.params import Params


@pytest.fixture(scope="module")
def fez():
    return FakeFez()


@pytest.mark.parametrize("variant", ["fractional", "cz"])
@pytest.mark.parametrize("N", [2, 5])
def test_compiled_circuit_equals_logical_circuit_on_small_patch(patches, fez, variant, N):
    p = patches["P12"]; prm = Params()
    ideal = trotter_circuit(p, prm, N, measure=False)
    c = compile_circuit(trotter_circuit(p, prm, N, measure=True), p, fez, variant)
    assert c.report["ok"], c.report
    assert Statevector(restrict_to_patch(c.circuit, p)).equiv(Statevector(ideal))     # up to global phase


def test_fractional_uses_one_rzz_per_edge_and_valid_angles(patches, fez):
    p = patches["P18"]; prm = Params(); N = 3
    c = compile_circuit(trotter_circuit(p, prm, N), p, fez, "fractional")
    r = c.report
    assert r["n_rzz"] == N * len(p.edges) and r["n_cz"] == 0 and r["n_swap"] == 0
    assert r["invalid_rzz_angles"] == [] and r["couplings_used_subset_of_patch"]


def test_cz_variant_costs_two_cz_per_edge(patches, fez):
    p = patches["P18"]; prm = Params(); N = 3
    r = compile_circuit(trotter_circuit(p, prm, N), p, fez, "cz").report
    assert r["n_cz"] == 2 * N * len(p.edges) and r["n_swap"] == 0 and r["ok"]


def test_measurement_map_is_logical_to_physical(patches, fez):
    p = patches["P12"]
    c = compile_circuit(trotter_circuit(p, Params(), 1), p, fez, "fractional").circuit
    meas = {c.find_bit(i.clbits[0]).index: c.find_bit(i.qubits[0]).index for i in c.data if i.operation.name == "measure"}
    assert meas == {i: p.nodes[i] for i in range(p.n)}                                # clbit i <- physical nodes[i]
