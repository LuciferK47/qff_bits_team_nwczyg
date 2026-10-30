"""Identifiers that make every result traceable to the exact physical patch and fixed circuit it came from."""
from __future__ import annotations

import hashlib
import json

from .graph import Patch
from .params import Params


def experiment_id(patch: Patch, prm: Params, N: int, circuit_sha: str | None = None) -> str:
    """Target of a comparison: physical patch + Hamiltonian parameters + dt + N (+ compiled/ideal circuit hash)."""
    payload = dict(physical_id=patch.physical_id, J=prm.J, hx=prm.hx, hz=prm.hz, dt=prm.dt, N=int(N),
                   circuit_sha=circuit_sha)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
