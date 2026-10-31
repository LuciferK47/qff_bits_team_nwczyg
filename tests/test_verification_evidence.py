"""Supplementary ledger for the post-execution IBM verification records, estimator health and documentation pointers.

The original evidence ledger (68 rows) is frozen and must stay unchanged; the verification files are covered by a second ledger."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HW = ROOT / "raw" / "hardware"
pytestmark = pytest.mark.skipif(not (HW / "account2" / "jobs.json").exists(), reason="hardware evidence not present")


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_original_ledger_is_unchanged_and_supplement_matches():
    orig = list(csv.DictReader((ROOT / "reports" / "evidence_hashes.csv").open()))
    assert len(orig) == 68 and all(_sha(ROOT / r["path"]) == r["sha256"] for r in orig)
    sup = list(csv.DictReader((ROOT / "reports" / "job_verification_hashes.csv").open()))
    assert sorted(r["path"] for r in sup) == [f"raw/hardware/account{a}/job_verification.json" for a in (1, 2)]
    for r in sup:
        assert _sha(ROOT / r["path"]) == r["sha256"] and (ROOT / r["path"]).stat().st_size == int(r["bytes"])


def test_every_account_file_is_in_one_of_the_two_ledgers():
    listed = {r["path"] for n in ("evidence_hashes", "job_verification_hashes")
              for r in csv.DictReader((ROOT / "reports" / f"{n}.csv").open())}
    on_disk = {p.relative_to(ROOT).as_posix() for a in (1, 2) for p in (HW / f"account{a}").rglob("*") if p.is_file()}
    assert on_disk <= listed, sorted(on_disk - listed)


def test_verification_records_match_the_archive():
    for a in (1, 2):
        d = HW / f"account{a}"
        jobs = json.loads((d / "jobs.json").read_text())
        ver = json.loads((d / "job_verification.json").read_text())
        assert ver["all_verified"] and set(ver["jobs"]) == set(jobs) and len(jobs) == 3
        for name, rec in jobs.items():
            v = ver["jobs"][name]
            usage = json.loads((d / f"{name}_results.json").read_text())["usage_s"]
            assert (v["job_id"], v["ibm_status"], v["ibm_backend"], v["ibm_usage_s"]) == (rec["job_id"], "DONE", "ibm_fez", usage)


def test_no_nonfinite_estimate_is_supported_or_inconsistent_and_health_counts():
    from qtrust import hwanalysis as H
    hw = pd.read_csv(HW / "hardware_results.csv")
    bad = ~np.isfinite(hw.estimate)
    assert bad.sum() == 69 and not hw[bad].trust_status.isin(["supported", "inconsistent"]).any()
    assert hw[bad].trust_status.value_counts().to_dict() == {"mitigation_failed": 37, "no_reference": 32}
    assert (hw[bad].failed_reason == "sign_change").all() and (hw[bad].method == "zne_exp").all()
    h = H.estimator_health(ROOT)
    assert h.n_rows.sum() == 99 and h[~h.finite_estimate].n_rows.sum() == 69
    assert h[h.finite_estimate].groupby("trust_status").n_rows.sum().to_dict() == {"mitigation_failed": 18, "no_reference": 12}


def test_reproducibility_doc_points_to_a_current_clean_room_log():
    import re
    doc = (ROOT / "reports" / "REPRODUCIBILITY.md").read_text()
    m = re.search(r"latest clean-room log is `(logs/verify_release\d*\.log)`", doc)
    assert m, "REPRODUCIBILITY.md must name the latest clean-room log"
    log = (ROOT / m.group(1)).read_text()
    assert "15108 rows" in log and "exit=0" in log
