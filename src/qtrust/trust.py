"""Empirical trust classification implementing configs/trust_policy.yaml (declared before hardware data)."""
from __future__ import annotations

import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_policy(path: Path = ROOT / "configs/trust_policy.yaml") -> dict:
    return yaml.safe_load(path.read_text())


def _finite(*xs) -> bool:
    return all(x is not None and math.isfinite(x) for x in xs)


def classify(point: float | None, diff_lo: float | None, diff_hi: float | None, reference: float | None,
             hw_lo: float | None, hw_hi: float | None, eps: float, reference_validated: bool = True) -> str:
    """Status of (hardware - reference) for one observable at one (patch, time).

    point           : the corrected estimate itself (must exist)
    diff_lo/diff_hi : 95% bootstrap interval of (corrected hardware - reference)
    hw_lo/hw_hi     : 95% interval of the corrected value itself (for the signal-resolved rule)

    A non-finite point or interval means the estimator failed: the result is ``mitigation_failed`` and can never be
    ``supported`` or ``inconsistent``.
    """
    if reference is None or not math.isfinite(reference):
        return "no_reference"
    if point is None and diff_lo is None and diff_hi is None:
        return "no_hardware"
    if not _finite(point, diff_lo, diff_hi, hw_lo, hw_hi):
        return "mitigation_failed"
    if not reference_validated:
        return "inconclusive"
    if diff_hi < -eps or diff_lo > eps:
        return "inconsistent"                              # the whole interval is outside the acceptance band
    resolved = abs(reference) >= eps or not (hw_lo <= 0.0 <= hw_hi)
    if -eps <= diff_lo and diff_hi <= eps and resolved:
        return "supported"
    return "inconclusive"                                  # straddles the band edge, or the signal is not resolved


EXACT_KINDS = ("full_exact", "lightcone_exact")


def assess(point, diff_lo, diff_hi, reference, hw_lo, hw_hi, eps, *, reference_kind: str,
           systematics_validated: bool, source: str = "hardware") -> dict:
    """Multi-gate assessment. Statistical agreement is reported SEPARATELY from the other gates and ``final_status``
    is ``supported`` only if every gate passes:

      reference_status         exact | classical_stability_only | none
      mitigation_valid         point and interval are finite
      signal_resolved          |reference| >= eps, or the value's interval excludes 0
      statistical_status       classify(): supported | inconsistent | inconclusive | mitigation_failed | ...
      systematics_validated    caller-supplied: independent-readout gate passed AND the correction was validated on
                               held-out times; never True for simulated-noise rehearsals

    Rehearsal rows (source != 'hardware') can never be ``supported``: they are not hardware data.
    """
    ref_status = ("exact" if reference_kind in EXACT_KINDS else
                  "classical_stability_only" if reference_kind == "classical_stability" else "none")
    ref_value = reference if ref_status == "exact" else (None if ref_status == "none" else reference)
    stat = classify(point, diff_lo, diff_hi, ref_value, hw_lo, hw_hi, eps, reference_validated=ref_status == "exact")
    mit_ok = _finite(point, diff_lo, diff_hi, hw_lo, hw_hi)
    resolved = bool(mit_ok and reference is not None and math.isfinite(reference)
                    and (abs(reference) >= eps or not (hw_lo <= 0.0 <= hw_hi)))
    if ref_status == "none":
        final = "no_reference"
    elif ref_status == "classical_stability_only":
        final = "classical_stability_only"
    elif not mit_ok:
        final = "mitigation_failed"
    elif stat == "supported" and not (systematics_validated and source == "hardware"):
        final = "inconclusive"                               # agrees statistically, but systematics/source not validated
    else:
        final = stat
    return dict(reference_status=ref_status, mitigation_valid=bool(mit_ok), signal_resolved=resolved,
                statistical_status=stat, systematics_validated=bool(systematics_validated), source=source,
                final_status=final)
