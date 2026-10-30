"""Supervised classical benchmark for one patch at the frozen dt (hard per-run wall-clock budget, tree RSS accounting).

python scripts/run_classical.py PID --budget 1200 --pauli coarse,medium,fine --chi 32,64,128,256 \
        --Ns 0,4,10,20,30,40,50 [--ref-Ns 0,4,5] [--dt 0.1]
Each (method, setting) is saved as soon as it finishes: raw/classical_dt<dt>/<pid>_<method>_<setting>.{csv,json,_moments.json}
Exact references (full or light-cone) are cached under raw/reference/ and never recomputed for identical inputs."""
import argparse
from pathlib import Path

from qtrust.classical import bench
from qtrust.params import Params
from qtrust.validate import load_patch

ap = argparse.ArgumentParser()
ap.add_argument("pid")
ap.add_argument("--budget", type=float, default=1200.0)
ap.add_argument("--pauli", default="coarse,medium,fine")
ap.add_argument("--chi", default="32,64,128,256")
ap.add_argument("--Ns", required=True)
ap.add_argument("--ref-Ns", default=None, help="times for which an exact reference is attempted (default: all Ns)")
ap.add_argument("--dt", type=float, default=None, help="default: frozen dt from qtrust.params.Params")
ap.add_argument("--workers", type=int, default=12)
a = ap.parse_args()
prm = Params() if a.dt is None else Params(dt=a.dt)
Ns = [int(n) for n in a.Ns.split(",")]
ref_Ns = [int(n) for n in a.ref_Ns.split(",")] if a.ref_Ns else None
bench.run_all(load_patch(a.pid), prm, Ns, [s for s in a.pauli.split(",") if s], [int(c) for c in a.chi.split(",") if c],
              Path(f"raw/classical_dt{prm.dt}"), workers=a.workers, budget_s=a.budget,
              ref_cache=Path("raw/reference"), ref_Ns=ref_Ns)
print("done", a.pid, flush=True)
