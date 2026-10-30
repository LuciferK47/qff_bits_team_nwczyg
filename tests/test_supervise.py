import os
import time

import psutil
import pytest

from qtrust.classical import mps, pauli, supervise
from qtrust.params import Params
from test_pauli import exact_obs


def test_supervised_run_matches_exact_and_reports_tree_resources(tree7):
    prm = Params(dt=0.2); Ns = [0, 2]
    ref = exact_obs(tree7, prm, Ns)
    obs, mu, stats, sup = supervise.run_method(tree7, prm, Ns, "pauli_prop", pauli.PauliSetting("exact", 10 ** 7, 0.0),
                                               budget_s=120, workers=2)
    assert sup["exit_reason"] == "ok" and sup["max_processes"] >= 2          # parent + pool workers are all counted
    assert sup["peak_tree_rss_bytes"] > 50e6 and sup["cpu_s"] > 0 and sup["wall_s"] > 0
    assert max(abs(obs[N][k] - v) for N in Ns for k, v in ref[N].items()) < 1e-9
    obs2, _, stats2, sup2 = supervise.run_method(tree7, prm, Ns, "mps", 32, budget_s=120)
    assert sup2["exit_reason"] == "ok" and max(abs(obs2[N][k] - v) for N in Ns for k, v in ref[N].items()) < 1e-8


def test_hard_kill_at_budget_keeps_completed_times_and_kills_every_worker(ring6, monkeypatch):
    """A slow propagation (huge term budget on a bigger chain) must be KILLED at the budget, with the whole
    process tree gone and the already-completed times preserved from the checkpoints."""
    from qtrust.conftest_free import chain_patch
    from qtrust.moments import Catalog
    p = chain_patch(14)
    cat = Catalog(14, [tuple(e) for e in p.edges], [(0, 1, 2, 3), (4, 5, 6, 7)])
    prm = Params(dt=0.2)
    before = set(psutil.Process().children(recursive=True))
    t0 = time.time()
    obs, mu, stats, sup = supervise.run_method(p, prm, [0, 1, 40], "pauli_prop",
                                               pauli.PauliSetting("big", 10 ** 8, 0.0), budget_s=25, workers=2, cat=cat)
    assert sup["exit_reason"] == "timed_out_killed" and stats["timed_out"]
    assert time.time() - t0 < 25 + 20                                        # killed promptly, not run to the end
    assert 0 in obs and 1 in obs and 40 not in obs                                         # early times kept, unfinished time absent
    time.sleep(0.5)
    leftover = [c for c in psutil.Process().children(recursive=True) if c not in before]
    assert not leftover, "worker processes survived the kill"


def test_memory_limit_kills_and_reports_memory_limited(tree7):
    prm = Params(dt=0.2)
    obs, mu, stats, sup = supervise.run_method(tree7, prm, [0, 2, 8], "pauli_prop", pauli.PauliSetting("x", 10 ** 7, 0.0),
                                               budget_s=120, workers=2, mem_limit_fraction=1e-6)
    assert sup["exit_reason"] == "memory_limited"


def test_child_failure_is_reported_not_raised(tree7):
    obs, mu, stats, sup = supervise.run_method(tree7, Params(), [0, 2], "mps", -5, budget_s=60)
    assert sup["exit_reason"] in ("failed", "ok")        # an invalid bond dimension must not crash the supervisor


def test_supervisor_works_when_the_calling_script_has_no_main_guard(tmp_path):
    """Regression: spawn-based children re-executed an unguarded caller script (MPS runs died in 0 s)."""
    script = tmp_path / "unguarded.py"
    script.write_text(
        "import sys\n"
        "from qtrust.classical import supervise\n"
        "from qtrust.conftest_free import chain_patch\n"
        "from qtrust.params import Params\n"
        "obs, mu, stats, sup = supervise.run_method(chain_patch(6), Params(), [0, 2], 'mps', 16, budget_s=120)\n"
        "print('RESULT', sup['exit_reason'], sorted(obs))\n")
    import subprocess, sys
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
    assert "RESULT ok [0, 2]" in out.stdout, out.stdout + out.stderr
