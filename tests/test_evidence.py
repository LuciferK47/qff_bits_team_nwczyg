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
