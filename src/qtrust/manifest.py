"""Hardware job manifest (DRY RUN). Compiles every planned circuit offline, enforces the safety gates, estimates QPU usage
per job and writes reports/hardware_manifest.md. Submitting is a separate, approval-gated step that does not exist here.

Gates (build_jobs raises ``ManifestGateError`` instead of recording a bad circuit):
  * every compiled circuit passes the ISA checks (valid RZZ angles, only the patch's couplings, no SWAPs)
  * the measurement map is exactly clbit i <- physical qubit patch.nodes[i]
  * compiled two-qubit depth <= CEILING (300); depth above HEADROOM (250) is flagged ``low_headroom`` and needs an
    explicit written justification before it may be submitted.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from qiskit import qpy

from . import mitigation as mit
from .circuits import trotter_circuit
from .hardware import OFFLINE_FRACTIONAL_NOTE, Compiled, compile_circuit, usage_estimate
from .ids import experiment_id
from .params import Params

CAL_SHOTS, SHOTS = 4096, 16384
CEILING, AIM, HEADROOM = 300, 100, 250


class ManifestGateError(RuntimeError):
    """A planned circuit violates a hard submission gate."""


@dataclass
class Item:
    label: str
    patch: str
    variant: str
    shots: int
    compiled: Compiled
    qpy_sha: str
    experiment_id: str
    measure_map_ok: bool


def _measure_map_ok(c: Compiled, patch) -> bool:
    circ = c.circuit
    got = {circ.find_bit(i.clbits[0]).index: circ.find_bit(i.qubits[0]).index for i in circ.data if i.operation.name == "measure"}
    return got == {i: patch.nodes[i] for i in range(patch.n)}


def _compile(label, qc, patch, prm, N, backend, variant, shots, outdir: Path | None):
    c = compile_circuit(qc, patch, backend, variant)
    buf = io.BytesIO(); qpy.dump(c.circuit, buf)
    sha = hashlib.sha256(buf.getvalue()).hexdigest()[:16]
    if outdir:
        (outdir / f"{label}.qpy").write_bytes(buf.getvalue())
    item = Item(label, patch.pid, variant, shots, c, sha, experiment_id(patch, prm, N, sha), _measure_map_ok(c, patch))
    if not c.report["ok"]:
        raise ManifestGateError(f"{label}: ISA check failed: {c.report}")
    if not item.measure_map_ok:
        raise ManifestGateError(f"{label}: measurement map is not clbit i <- physical nodes[i]")
    if c.report["depth_2q"] > CEILING:
        raise ManifestGateError(f"{label}: compiled two-qubit depth {c.report['depth_2q']} exceeds the ceiling {CEILING}")
    return item


def build_jobs(patches, prm: Params, backend, outdir: Path | None = None, seed: int = 20261029):
    """Planned jobs at the frozen dt: pilot, forward, ZNE (shallow validated times only)."""
    P18, P40 = patches["P18"], patches["P40"]
    steps = prm.steps
    cal = lambda p: [_compile(f"{p.pid}_cal{i}", mit.calibration_circuit(pr), p, prm, -1, backend, "cz", CAL_SHOTS, outdir)
                     for i, pr in enumerate(mit.structured_preps(p.edges, p.n))]
    fwd = lambda p, Jt, v="fractional": _compile(f"{p.pid}_Jt{Jt}_{v}", trotter_circuit(p, prm, steps(Jt)), p, prm, steps(Jt),
                                                  backend, v, SHOTS, outdir)
    zne = lambda p, Jt, k: _compile(f"{p.pid}_Jt{Jt}_fold{k}", mit.with_measurements(mit.fold_circuit(
        trotter_circuit(p, prm, steps(Jt), measure=False), k)), p, prm, steps(Jt), backend, "fractional", SHOTS, outdir)
    return {
        "1_pilot": cal(P18) + [fwd(P18, 0.0), fwd(P18, 0.4), fwd(P18, 0.4, "cz")],
        # P18 Jt=0.8 is the unfolded (fold level 0) run that the held-out ZNE time needs
        "2_forward": [fwd(P18, t) for t in (0.8, 1.0, 2.0, 3.0)] + cal(P40) + [fwd(P40, t) for t in (0.0, 0.4, 1.0, 2.0, 3.0)],
        # calibration times 0.4 and 1.0, held-out 0.8 (same protocol as the rehearsal); P40 only at Jt=1.0
        "3_zne": [zne(P18, t, k) for t in (0.4, 0.8, 1.0) for k in (1, 2)] + [zne(P40, 1.0, k) for k in (1, 2)],
    }


def summarize(jobs: dict[str, list[Item]], rep_delay: float, snapshot_source: str):
    rows, totals = [], {}
    for name, items in jobs.items():
        est = usage_estimate([i.compiled for i in items], [i.shots for i in items], rep_delay)
        totals[name] = est
        for i in items:
            r = i.compiled.report
            rows.append(dict(job=name, circuit=i.label, patch=i.patch, variant=i.variant, shots=i.shots, n_2q=r["n_2q"],
                             n_cz=r["n_cz"], n_rzz=r["n_rzz"], depth_2q=r["depth_2q"], duration_us=round(r["duration_s"] * 1e6, 1),
                             isa_ok=r["ok"], measure_map_ok=i.measure_map_ok, within_aim=r["depth_2q"] <= AIM,
                             within_ceiling=r["depth_2q"] <= CEILING, low_headroom=r["depth_2q"] > HEADROOM,
                             experiment_id=i.experiment_id, qpy_sha=i.qpy_sha, snapshot_source=snapshot_source,
                             fractional_gate_basis="ASSUMED (offline)" if i.variant == "fractional" else "native cz"))
    return rows, totals


def _md_table(rows, cols) -> str:
    head = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    return head + "\n".join("| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows)


def write_markdown(rows, totals, prm: Params, path: Path, snapshot_source: str):
    lines = [
        "# Hardware manifest — DRY RUN (nothing submitted)", "",
        f"* frozen J*dt = **{prm.dt}**, shots {SHOTS} per forward/ZNE circuit, {CAL_SHOTS} per calibration circuit",
        f"* data source: **{snapshot_source}** — not a live backend", f"* {OFFLINE_FRACTIONAL_NOTE}",
        f"* gates enforced at build time: ISA valid, measurement map, compiled 2q depth <= {CEILING} "
        f"(flag > {HEADROOM}, aim <= {AIM})", "",
        "## QPU usage estimates (seconds; estimates only, replaced by `job.usage()` after the pilot)", "",
        "| job | executions | detailed model | IBM quick rule | PDF 0.5 ms/shot |", "|---|---:|---:|---:|---:|"]
    for k, v in totals.items():
        lines.append(f"| {k} | {v['executions']} | {v['detailed_s']:.1f} | {v['ibm_quick_rule_s']:.1f} | {v['pdf_rate_s']:.1f} |")
    lines += ["", f"Total (detailed / PDF-rate): {sum(v['detailed_s'] for v in totals.values()):.0f} s / "
                  f"{sum(v['pdf_rate_s'] for v in totals.values()):.0f} s of a 600 s allocation (cap 420 s).", "",
              "## Circuits", "", _md_table(rows, ["job", "circuit", "variant", "shots", "n_2q", "depth_2q", "duration_us", "isa_ok",
                                                  "measure_map_ok", "low_headroom", "qpy_sha"]), "",
              "## Before any submission (NOT done)", "",
              "1. Each teammate saves their own Open Plan credentials with `QiskitRuntimeService.save_account`; never in code or logs.",
              "2. `qtrust live-check --account N`: `service.backend('ibm_fez', use_fractional_gates=True)`; recompile every "
              "circuit on the LIVE target, compare depths with this table, re-run all gates (stops if rzz is unavailable).",
              "3. `qtrust preregister`, then BOTH teammates sign `prereg/APPROVAL.md` (names, date, current sha). The organisers "
              "said the mentor reviews after the answer is screened, so this signed pre-registration replaces a pre-hardware mentor review.",
              "4. Pilot job only (`qtrust submit --job 1_pilot`: P18 calibration + Jt 0, 0.4 in both compilations); `qtrust fetch`; "
              "the measured `job.usage()` rescales every later estimate; then 2_forward and 3_zne.",
              "5. Account 2 repeats the identical frozen manifest in a later calibration window (drift check)."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
