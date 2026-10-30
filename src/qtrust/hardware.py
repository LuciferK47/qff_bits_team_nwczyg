"""Hardware compilation, ISA safety checks and QPU-usage estimation. NOTHING here submits a job.

Offline we compile against the FakeFez target. FakeFez exposes only CZ, so the *fractional* variant adds an
RZZ(theta) (0 < theta <= pi/2) with the CZ calibration as an ASSUMED duration/error; this is recorded in the
manifest and must be re-checked against the live backend (use_fractional_gates=True) before submission.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.circuit.library import RXGate, RZZGate
from qiskit.transpiler import InstructionProperties, PassManager
from qiskit.transpiler.passes import Optimize1qGatesDecomposition
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime.transpiler.passes.basis import FoldRzzAngle

from .graph import Patch

PI2 = math.pi / 2
OFFLINE_FRACTIONAL_NOTE = ("fractional RZZ/RX added to the FakeFez target with CZ/SX calibration as an ASSUMPTION "
                           "(offline, not live); verify with service.backend(name, use_fractional_gates=True)")


def fractional_target(backend):
    """Copy of the backend target with RZZ(theta) on every coupled pair (and RX) added.

    A live backend opened with use_fractional_gates=True already carries rzz/rx: its real target is used unchanged
    (nothing is assumed); only the offline FakeFez target gets the assumed gates."""
    tgt = copy.deepcopy(backend.target)
    names = set(tgt.operation_names)
    if "cz" in names and "rzz" not in names:
        cz = backend.target["cz"]
        tgt.add_instruction(RZZGate(Parameter("theta")),
                            {pair: InstructionProperties(duration=p.duration, error=p.error) for pair, p in cz.items()})
    if "sx" in names and "rx" not in names:
        sx = backend.target["sx"]
        tgt.add_instruction(RXGate(Parameter("theta")),
                            {q: InstructionProperties(duration=p.duration, error=p.error) for q, p in sx.items()})
    return tgt


@dataclass
class Compiled:
    circuit: QuantumCircuit
    variant: str                       # 'fractional' | 'cz'
    report: dict


def compile_circuit(qc: QuantumCircuit, patch: Patch, backend, variant: str, seed: int = 20261029,
                    optimization_level: int = 2) -> Compiled:
    """Compile onto the physical qubits of ``patch`` (logical i -> patch.nodes[i]) and run the ISA checks."""
    if variant == "fractional":
        target = fractional_target(backend)
    elif variant == "cz":
        target = backend.target
    else:
        raise ValueError(variant)
    pm = generate_preset_pass_manager(optimization_level=optimization_level, target=target,
                                      initial_layout=list(patch.nodes), seed_transpiler=seed)
    out = pm.run(qc)
    if variant == "fractional":      # fold angles into (0, pi/2] with X conjugations, then merge the 1q gates
        out = PassManager([FoldRzzAngle(), Optimize1qGatesDecomposition(target=target)]).run(out)
    return Compiled(out, variant, check_compiled(out, patch, target))


def check_compiled(circ: QuantumCircuit, patch: Patch, target) -> dict:
    """Hard checks; ``ok`` is False if any invariant fails. Counts are reported, never assumed."""
    phys_edges = {tuple(sorted((patch.nodes[a], patch.nodes[b]))) for a, b in patch.edges}
    ops = circ.count_ops()
    used, bad_angles, n_swap = set(), [], ops.get("swap", 0)
    for inst in circ.data:
        if inst.operation.num_qubits == 2 and inst.operation.name not in ("barrier",):
            qs = tuple(sorted(circ.find_bit(q).index for q in inst.qubits))
            used.add(qs)
        if inst.operation.name == "rzz":
            a = float(inst.operation.params[0])
            if not (-1e-12 < a <= PI2 + 1e-12):
                bad_angles.append(a)
    n_cz, n_rzz = ops.get("cz", 0), ops.get("rzz", 0)
    return dict(
        ok=bool(not bad_angles and used <= phys_edges and n_swap == 0),
        n_cz=n_cz, n_rzz=n_rzz, n_2q=n_cz + n_rzz, n_swap=n_swap,
        depth_2q=circ.depth(lambda i: i.operation.num_qubits == 2),
        depth_total=circ.depth(), n_gates=sum(ops.values()),
        duration_s=float(circ.estimate_duration(target)) if circ.num_qubits else 0.0,
        invalid_rzz_angles=bad_angles, couplings_used_subset_of_patch=bool(used <= phys_edges),
        couplings_used=len(used), patch_edges=len(phys_edges),
    )


def restrict_to_patch(circ: QuantumCircuit, patch: Patch) -> QuantumCircuit:
    """Re-express a compiled device-wide circuit on the n patch qubits (for state-equivalence checks)."""
    idx = {p: i for i, p in enumerate(patch.nodes)}
    out = QuantumCircuit(patch.n)
    out.global_phase = circ.global_phase
    for inst in circ.data:
        if inst.operation.name in ("measure", "barrier", "delay"):
            continue
        out.append(inst.operation, [idx[circ.find_bit(q).index] for q in inst.qubits])
    return out


def usage_estimate(circuits: list[Compiled], shots: list[int], rep_delay: float, per_job_overhead: float = 2.0) -> dict:
    """QPU seconds for ONE job: overhead + sum over circuits of (duration + rep_delay) * shots.
    Also returns IBM's quick rule (2 s + 0.35 ms per execution) and the PDF planning rate (0.5 ms/shot)."""
    execs = int(sum(shots))
    detailed = per_job_overhead + sum((c.report["duration_s"] + rep_delay) * s for c, s in zip(circuits, shots))
    return dict(executions=execs, detailed_s=detailed, ibm_quick_rule_s=2.0 + 0.00035 * execs, pdf_rate_s=0.0005 * execs)
