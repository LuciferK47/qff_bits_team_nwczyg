"""Read-only check of the archived hardware jobs against IBM's own records.

Run by the account owner (``qtrust verify-jobs --account N``). It only reads: it looks each archived job id up with the saved
account and records the status, backend, reported usage and timestamps IBM returns. It never submits, never writes credentials and
never changes the archived counts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USAGE_TOL_S = 0.5


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _get(fn, default=None):
    try:
        return fn()
    except Exception:                                   # service differences must not abort the verification
        return default


def verify_jobs(service, account: int, root: Path = ROOT) -> dict:
    d = root / "raw" / "hardware" / f"account{account}"
    jobs = json.loads((d / "jobs.json").read_text())
    out = {"account": account, "checked_utc": _utc(), "jobs": {}}
    for name, rec in jobs.items():
        archived = json.loads((d / f"{name}_results.json").read_text()) if (d / f"{name}_results.json").exists() else None
        entry = {"job_id": rec["job_id"], "archived_backend": rec["backend"], "archived_usage_s": archived and archived["usage_s"]}
        try:
            run = service.job(rec["job_id"])
        except Exception as e:
            entry.update(found=False, error=f"{type(e).__name__}")
            out["jobs"][name] = entry
            continue
        status = _get(run.status)
        usage = _get(run.usage)
        backend = _get(lambda: run.backend().name if callable(getattr(run.backend(), "name", None)) is False else run.backend().name())
        metrics = _get(run.metrics, {}) or {}
        ts = (metrics.get("timestamps") or {}) if isinstance(metrics, dict) else {}
        entry.update(found=True, ibm_status=str(getattr(status, "name", status)), ibm_backend=backend,
                     ibm_usage_s=None if usage is None else float(usage), ibm_timestamps={k: str(v) for k, v in ts.items()},
                     backend_matches=backend == rec["backend"],
                     usage_matches=(usage is not None and archived is not None and abs(float(usage) - archived["usage_s"]) <= USAGE_TOL_S))
        out["jobs"][name] = entry
    out["all_verified"] = all(e.get("found") and e.get("backend_matches") and e.get("usage_matches")
                              and e.get("ibm_status", "").upper() in ("DONE", "COMPLETED") for e in out["jobs"].values())
    (d / "job_verification.json").write_text(json.dumps(out, indent=1))
    return out
