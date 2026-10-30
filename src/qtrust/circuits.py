"""Second-order Trotter circuits for H = -J sum ZZ - sum (hx X + hz Z).

U_N = S(dt)^N,  S = F(dt/2) B(dt) F(dt/2),  with adjacent field halves merged.
Qiskit conventions: qubit i is bit i of the basis index (little endian); RZZ(th) = exp(-i th ZZ/2).
Logical qubit i of a patch is circuit qubit i.
"""
from __future__ import annotations

from qiskit import QuantumCircuit

from .graph import Patch
from .params import Params


def _field(qc: QuantumCircuit, tau: float, prm: Params) -> None:
    """F(tau) = exp(-i H_f tau) = exp(+i tau (hx X + hz Z)) on every qubit, exactly.

    This is the axis-angle rotation by theta = -2*omega*tau about n = (hx,0,hz)/omega, written as
    RY(beta) RZ(theta) RY(-beta) (beta = polar angle of n), so the same circuit is accepted by Aer,
    pauli-prop (Pauli rotations only) and the transpiler, with no approximation.
    """
    theta = -2.0 * prm.omega * tau
    for q in range(qc.num_qubits):
        qc.ry(-prm.beta, q)
        qc.rz(theta, q)
        qc.ry(prm.beta, q)


def _bonds(qc: QuantumCircuit, patch: Patch, prm: Params) -> None:
    """B(dt) = exp(-i H_b dt) = prod exp(+i J dt ZZ) = prod RZZ(-2 J dt); disjoint edges grouped per layer."""
    for layer in sorted(set(patch.colours.values())):
        for (a, b), c in sorted(patch.colours.items()):
            if c == layer:
                qc.rzz(-2.0 * prm.J * prm.dt, a, b)


def trotter_circuit(patch: Patch, prm: Params, N: int, measure: bool = True, barriers: bool = False) -> QuantumCircuit:
    """U_N |0...0>, optionally followed by measuring every qubit into the same-index classical bit.
    N = 0 is the identity (no gates)."""
    qc = QuantumCircuit(patch.n, patch.n if measure else 0, name=f"U_{N}_{patch.pid}")
    if N > 0:
        _field(qc, prm.dt / 2, prm)
        for k in range(N):
            if barriers:
                qc.barrier()
            _bonds(qc, patch, prm)
            if barriers:
                qc.barrier()
            _field(qc, prm.dt if k < N - 1 else prm.dt / 2, prm)
    if measure:
        qc.measure(range(patch.n), range(patch.n))
    return qc


def count_rzz(qc: QuantumCircuit) -> int:
    return qc.count_ops().get("rzz", 0)
