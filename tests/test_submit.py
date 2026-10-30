"""The approval-gated hardware path, exercised with a fake service/sampler. Nothing here contacts IBM Quantum."""
import io
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from qiskit import QuantumCircuit, qpy

from qtrust import submit as S
from qtrust.params import Params

REAL = Path(__file__).resolve().parents[1]
DT = 0.1


def _sha16(b):
    return S._sha(b)[:16]


@pytest.fixture()
def root(tmp_path):
    for rel in S.CONFIG_FILES + S.CODE_FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL / rel, tmp_path / rel)
    md = tmp_path / f"raw/circuits/dt{DT}"; md.mkdir(parents=True)
    qc = QuantumCircuit(2); qc.h(0); qc.cx(0, 1); qc.measure_all()
    buf = io.BytesIO(); qpy.dump(qc, buf)
    (md / "x.qpy").write_bytes(buf.getvalue())
    pd.DataFrame([dict(job="1_pilot", circuit="P18_cal0", variant="cz", shots=100, qpy_sha="aa", depth_2q=1)]).to_csv(
        md / "manifest_circuits.csv", index=False)
    usage = {j: dict(executions=100, detailed_s=10.0, ibm_quick_rule_s=12.0, pdf_rate_s=20.0)
             for j in ("1_pilot", "2_forward", "3_zne")}
    (md / "manifest_usage.json").write_text(json.dumps(usage))
    return tmp_path


def sign(root, a="Ada Lovelace", b="Alan Turing"):
    sha = S.preregister(root, DT)["prereg_sha"]
    (root / "prereg/APPROVAL.md").write_text(S.APPROVAL_TEMPLATE.format(sha=sha).replace(
        "<full name of teammate 1>", a).replace("<full name of teammate 2>", b).replace("<YYYY-MM-DD>", "2026-10-31"))
    return sha


def live_ok(root, account=1, shots=100):
    cd = S.acct_dir(root, account) / "circuits"; cd.mkdir(exist_ok=True)
    qc = QuantumCircuit(2); qc.h(0); qc.measure_all()
    buf = io.BytesIO(); qpy.dump(qc, buf); raw = buf.getvalue()
    jobs = {}
    for j in ("1_pilot", "2_forward", "3_zne"):
        (cd / f"{j}_c.qpy").write_bytes(raw)
        jobs[j] = [dict(label=f"{j}_c", shots=shots, qpy_sha=_sha16(raw), depth_2q=1)]
    (S.acct_dir(root, account) / "live_check.json").write_text(json.dumps(dict(ok=True, jobs=jobs)))


class FakeRun:
    def __init__(self, jid): self._id = jid
    def job_id(self): return self._id


class FakeSampler:
    def __init__(self): self.pubs = None
    def run(self, pubs):
        self.pubs = pubs; return FakeRun("job-123")


def factory(sampler):
    return lambda backend: (sampler, lambda: None)


class FakeService:
    def backend(self, name, use_fractional_gates=False): return SimpleNamespace(name=name)
    def job(self, jid):
        pub = SimpleNamespace(data=SimpleNamespace(values=lambda: [SimpleNamespace(get_counts=lambda: {"00": 60, "11": 40})]))
        return SimpleNamespace(status=lambda: SimpleNamespace(name="DONE"), result=lambda: [pub], usage=lambda: 7.5)


# ------------------------------------------------------------------ approval gate
def test_unsigned_template_is_refused(root):
    S.preregister(root, DT)
    with pytest.raises(S.ApprovalError, match="two different"):
        S.verify_approval(root)


def test_missing_preregistration_is_refused(root):
    with pytest.raises(S.ApprovalError, match="required"):
        S.verify_approval(root)


def test_signed_approval_passes_and_sha_is_stable(root):
    sha = sign(root)
    assert S.verify_approval(root) == sha
    assert S.preregister(root, DT)["prereg_sha"] == sha


def test_same_name_twice_is_refused(root):
    sign(root, "Ada", "ada")
    with pytest.raises(S.ApprovalError, match="two different"):
        S.verify_approval(root)


def test_editing_the_policy_after_preregistration_invalidates_it(root):
    sign(root)
    p = root / "configs/trust_policy.yaml"
    p.write_text(p.read_text() + "\n# tweak after seeing data\n")
    with pytest.raises(S.ApprovalError, match="changed after"):
        S.verify_approval(root)


def test_approval_for_a_different_sha_is_refused(root):
    sign(root)
    ap = root / "prereg/APPROVAL.md"
    ap.write_text(ap.read_text().replace("prereg_sha: ", "prereg_sha: 0000"))
    with pytest.raises(S.ApprovalError, match="current prereg_sha"):
        S.verify_approval(root)


# ------------------------------------------------------------------ submit gates
def test_submit_refused_without_approval(root):
    live_ok(root)
    with pytest.raises(S.ApprovalError):
        S.submit_job(FakeService(), 1, "1_pilot", root, factory(FakeSampler()))


def test_submit_refused_without_live_check(root):
    sign(root)
    with pytest.raises(S.ApprovalError, match="live check"):
        S.submit_job(FakeService(), 1, "1_pilot", root, factory(FakeSampler()))


def test_pilot_goes_first_and_records_job_id_before_close(root):
    sign(root); live_ok(root)
    with pytest.raises(S.ApprovalError, match="pilot"):
        S.submit_job(FakeService(), 1, "2_forward", root, factory(FakeSampler()))
    sampler = FakeSampler()
    rec = S.submit_job(FakeService(), 1, "1_pilot", root, factory(sampler))
    assert rec["job_id"] == "job-123" and sampler.pubs[0][2] == 100               # per-pub shots
    assert json.loads((S.acct_dir(root, 1) / "jobs.json").read_text())["1_pilot"]["job_id"] == "job-123"
    with pytest.raises(S.ApprovalError, match="already submitted"):
        S.submit_job(FakeService(), 1, "1_pilot", root, factory(FakeSampler()))


def test_tampered_circuit_is_refused(root):
    sign(root); live_ok(root)
    (S.acct_dir(root, 1) / "circuits/1_pilot_c.qpy").write_bytes(b"not the checked circuit")
    with pytest.raises(S.ApprovalError, match="does not match"):
        S.submit_job(FakeService(), 1, "1_pilot", root, factory(FakeSampler()))


def test_budget_cap_blocks_a_job_and_pilot_usage_rescales_the_estimate(root):
    sign(root); live_ok(root)
    S.submit_job(FakeService(), 1, "1_pilot", root, factory(FakeSampler()))
    assert S.fetch(FakeService(), 1, root)["1_pilot"].startswith("fetched")
    assert S.spent_seconds(root, 1) == 7.5
    assert S.estimate_seconds(root, 1, "2_forward", DT) == pytest.approx(10.0 * 7.5 / 10.0)      # detailed x measured/modelled
    r = S._results(root, 1, "1_pilot"); r["usage_s"] = S.ACCOUNT_CAP_S - 1.0
    (S.acct_dir(root, 1) / "1_pilot_results.json").write_text(json.dumps(r))
    with pytest.raises(S.ApprovalError, match="cap"):
        S.submit_job(FakeService(), 1, "2_forward", root, factory(FakeSampler()))


def test_fetch_waits_for_unfinished_jobs(root):
    sign(root); live_ok(root)
    S.submit_job(FakeService(), 1, "1_pilot", root, factory(FakeSampler()))
    svc = FakeService(); svc.job = lambda jid: SimpleNamespace(status=lambda: "RUNNING")
    assert S.fetch(svc, 1, root) == {"1_pilot": "RUNNING"}


def test_no_credentials_in_anything_written(root):
    sign(root); live_ok(root)
    S.submit_job(FakeService(), 1, "1_pilot", root, factory(FakeSampler())); S.fetch(FakeService(), 1, root)
    for f in list((root / "raw/hardware").rglob("*.json")) + list((root / "prereg").rglob("*")):
        low = f.read_text(errors="ignore").lower() if f.is_file() else ""
        assert "token" not in low and "apikey" not in low and "api_key" not in low
    src = (REAL / "src/qtrust/submit.py").read_text()
    assert "token=" not in src and ".save_account(" not in src


# ------------------------------------------------------------------ analysis helpers
def test_assemble_parses_labels_and_ignores_the_cz_twin(root):
    prm = Params(dt=DT)
    res = {"counts": {"P18_cal0": {"0": 1}, "P18_cal1": {"1": 1}, "P18_Jt0.4_fractional": {"a": 1},
                      "P18_Jt0.4_cz": {"b": 1}, "P18_Jt0.4_fold1": {"c": 1}, "P18_Jt0.4_fold2": {"d": 1}, "P40_cal0": {"x": 1}}}
    S.acct_dir(root, 1)
    (S.acct_dir(root, 1) / "jobs.json").write_text(json.dumps({"j": {"job_id": "i", "labels": []}}))
    (S.acct_dir(root, 1) / "j_results.json").write_text(json.dumps(res))
    d = S.assemble(root, 1, "P18", prm)
    assert d["cal"] == [{"0": 1}, {"1": 1}] and d["fwd"] == {4: {"a": 1}} and d["zne"] == {4: {1: {"c": 1}, 2: {"d": 1}}}
    assert S.assemble(root, 1, "P12", prm) is None


def test_drift_table_flags_only_significant_differences():
    base = dict(graph_id="P18", N=4, method="raw", observable="m", sites="0")
    a = pd.DataFrame([dict(base, estimate=0.50, se=0.01), dict(base, sites="1", estimate=0.30, se=0.01)])
    b = pd.DataFrame([dict(base, estimate=0.51, se=0.01), dict(base, sites="1", estimate=0.45, se=0.01)])
    dr = S.drift_table(a, b).set_index("sites")
    assert not dr.loc["0", "drift_flag"] and dr.loc["1", "drift_flag"]
    assert dr.loc["1", "drift_z"] == pytest.approx(-0.15 / np.sqrt(2e-4))
