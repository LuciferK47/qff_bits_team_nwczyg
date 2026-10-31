"""Frozen hardware evidence: raw counts, QPY files, job records and the signed pre-registration must never change.

The fixture constants below describe the two executed runs (6 jobs, 56 circuit executions); they live in the test only."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREREG_SHA = "5360308738170cc5410562cb971a3050"
HW = ROOT / "raw" / "hardware"


def _have_hardware():
    return (HW / "account1" / "jobs.json").exists() and (HW / "account2" / "jobs.json").exists()


pytestmark = pytest.mark.skipif(not _have_hardware(), reason="hardware evidence not present")


def test_every_frozen_file_matches_its_recorded_hash():
    rows = list(csv.DictReader((ROOT / "reports" / "evidence_hashes.csv").open()))
    assert len(rows) >= 60
    bad = []
    for r in rows:
        p = ROOT / r["path"]
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            bad.append(r["path"])
    assert not bad, f"frozen evidence changed or missing: {bad[:5]}"


def test_signed_preregistration_is_still_valid():
    from qtrust.submit import verify_approval
    assert verify_approval(ROOT) == PREREG_SHA


def test_six_jobs_56_executions_720896_shots_202_seconds():
    jobs = shots = 0
    labels = 0
    usage = 0.0
    for acct in (1, 2):
        d = HW / f"account{acct}"
        recs = json.loads((d / "jobs.json").read_text())
        assert len(recs) == 3
        for name, rec in recs.items():
            res = json.loads((d / f"{name}_results.json").read_text())
            assert res["job_id"] == rec["job_id"] and res["backend"] == "ibm_fez"
            assert set(res["counts"]) == set(rec["labels"])
            assert rec["prereg_sha"] == PREREG_SHA
            jobs += 1; labels += len(rec["labels"]); usage += res["usage_s"]
            shots += sum(sum(c.values()) for c in res["counts"].values())
    assert (jobs, labels, shots, usage) == (6, 56, 720_896, 202.0)
    assert usage < 600


def test_verify_jobs_is_read_only_and_flags_mismatch(tmp_path):
    import shutil
    from types import SimpleNamespace
    from qtrust import verify
    root = tmp_path
    shutil.copytree(HW / "account1", root / "raw/hardware/account1", ignore=shutil.ignore_patterns("circuits"))
    recs = json.loads((root / "raw/hardware/account1/jobs.json").read_text())
    use = {r["job_id"]: json.loads((root / f"raw/hardware/account1/{n}_results.json").read_text())["usage_s"] for n, r in recs.items()}

    class Svc:
        def __init__(self, shift=0.0): self.shift = shift
        def job(self, jid):
            return SimpleNamespace(status=lambda: SimpleNamespace(name="DONE"), usage=lambda: use[jid] + self.shift,
                                   backend=lambda: SimpleNamespace(name="ibm_fez"), metrics=lambda: {"timestamps": {"finished": "t"}})
    before = {p.name: p.read_bytes() for p in (root / "raw/hardware/account1").glob("*_results.json")}
    ok = verify.verify_jobs(Svc(), 1, root)
    assert ok["all_verified"] and (root / "raw/hardware/account1/job_verification.json").exists()
    assert before == {p.name: p.read_bytes() for p in (root / "raw/hardware/account1").glob("*_results.json")}
    assert not verify.verify_jobs(Svc(shift=5.0), 1, root)["all_verified"]
    assert "token" not in (root / "raw/hardware/account1/job_verification.json").read_text().lower()
