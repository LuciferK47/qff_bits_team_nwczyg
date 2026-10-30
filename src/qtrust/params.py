"""Hamiltonian / Trotter parameters (heavy-hex benchmark family from the problem statement)."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Params:
    J: float = 1.0
    hx: float = 1.25
    hz: float = -0.60
    dt: float = 0.10            # J*dt with J = 1 (hbar = 1); FROZEN at 0.10 (configs/heavy_hex.yaml: dt_rationale)

    @property
    def omega(self) -> float:
        return math.hypot(self.hx, self.hz)

    @property
    def beta(self) -> float:
        """Polar angle of the field axis (hx, 0, hz)/omega measured from +z."""
        return math.atan2(self.hx, self.hz)

    def steps(self, Jt: float) -> int:
        N = round(Jt / (self.J * self.dt))
        if abs(N * self.J * self.dt - Jt) > 1e-9:
            raise ValueError(f"Jt={Jt} is not an integer number of steps of J*dt={self.J * self.dt}")
        return N

    def with_hz(self, hz: float) -> "Params":
        return replace(self, hz=hz)

    def with_dt(self, dt: float) -> "Params":
        return replace(self, dt=dt)


def load_params(path: str | Path = "configs/heavy_hex.yaml") -> Params:
    c = yaml.safe_load(Path(path).read_text())
    return Params(J=c["J"], hx=c["hx"], hz=c["hz"], dt=c["dt"])
