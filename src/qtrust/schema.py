"""Schemas and validators for the submission tables. A validator returns a list of problems (empty = valid);
``require_valid`` raises SchemaError listing all of them."""
from __future__ import annotations

import math
import re

import pandas as pd

RESULTS_COLUMNS = [
    "graph_id", "physical_id", "n", "J", "hx", "hz", "dt", "N", "t_Jt", "observable", "site_indices", "method",
    "approximation_setting", "estimate", "ci_low", "ci_high", "reference", "reference_kind", "validation_status",
    "source", "execution_block", "related_job_id", "notes"]
RESOURCES_COLUMNS = [
    "kind", "graph_id", "physical_id", "n", "dt", "method", "setting", "error_status", "exit_reason", "wall_s", "cpu_s",
    "peak_tree_rss_bytes", "max_processes", "workers", "term_count_or_bond_dim", "max_Jt_completed", "host_cpu",
    "logical_cores", "gpu", "compiled_2q_count", "compiled_2q_depth", "shots", "estimated_qpu_s", "observed_qpu_s",
    "job_id", "run_hash", "experiment_id"]
SOURCES = {"exact_numerics", "classical_approximation", "simulated_noisy", "hardware"}
STATUSES = {"reference", "exact_reference", "no_reference", "supported", "inconsistent", "inconclusive",
            "mitigation_failed", "classical_stability_only", "no_hardware"}
EXACT_KINDS = {"full_exact", "lightcone_exact"}
METADATA_KEYS = ["created_utc", "frozen_dt", "python", "platform", "packages", "seeds", "backend", "snapshot", "patches",
                 "circuits", "policy", "mitigation", "qpu", "job_ids", "ai_assistance"]


class SchemaError(ValueError):
    pass


def _bad(df: pd.DataFrame, mask, msg: str, out: list[str]):
    if len(df) and bool(mask.any()):
        out.append(f"{msg} ({int(mask.sum())} rows, first index {int(mask[mask].index[0])})")


def validate_results(df: pd.DataFrame, frozen_dt: float) -> list[str]:
    out: list[str] = []
    if list(df.columns) != RESULTS_COLUMNS:
        return [f"columns differ: missing {sorted(set(RESULTS_COLUMNS) - set(df.columns))}, "
                f"extra {sorted(set(df.columns) - set(RESULTS_COLUMNS))}"]
    _bad(df, ~df.dt.apply(lambda x: math.isclose(x, frozen_dt, rel_tol=0, abs_tol=1e-12)), f"dt != frozen dt {frozen_dt}", out)
    _bad(df, ((df.N * df.dt) - df.t_Jt).abs() > 1e-9, "t_Jt != N*dt", out)
    _bad(df, ~df.source.isin(SOURCES), "unknown source", out)
    _bad(df, ~df.validation_status.isin(STATUSES), "unknown validation_status", out)
    _bad(df, (df.validation_status == "supported") & (df.source != "hardware"), "'supported' on non-hardware data", out)
    fin = df.estimate.apply(lambda x: x is not None and math.isfinite(x))
    # a failed estimator is mitigation_failed; where the exact reference does not exist the frozen trust rule reports no_reference first,
    # and the reason survives in `notes` (hardware rows), so a non-finite value is never a verdict about accuracy
    nofail_ok = df.validation_status.eq("mitigation_failed") | (df.validation_status.eq("no_reference") & df.reference_kind.eq("none"))
    _bad(df, ~fin & ~nofail_ok, "non-finite estimate without mitigation_failed", out)
    _bad(df, ~fin & df.source.eq("hardware") & df.notes.fillna("").str.contains(r"failed_reason=(?:nan|None)(?:;|$)"),
         "non-finite hardware estimate without a recorded failure reason", out)
    # finite point but no interval (too few valid bootstrap replicates) is also mitigation_failed by policy
    _bad(df, fin & df.validation_status.eq("mitigation_failed") & df.source.eq("hardware") & df.ci_low.notna(),
         "finite estimate with an interval marked failed", out)
    has_ref = df.reference.apply(lambda x: x is not None and math.isfinite(x))
    _bad(df, has_ref & ~df.reference_kind.isin(EXACT_KINDS | {"classical_stability"}), "reference present but kind not recognised", out)
    _bad(df, ~has_ref & (df.reference_kind != "none"), "no reference but reference_kind != 'none'", out)
    _bad(df, ~has_ref & ~df.validation_status.isin({"no_reference", "classical_stability_only", "reference"}) &
         df.source.isin({"classical_approximation"}), "approximation without reference must be flagged no_reference", out)
    both = df.ci_low.notna() & df.ci_high.notna()
    _bad(df, both & (df.ci_low > df.ci_high), "ci_low > ci_high", out)
    _bad(df, df.ci_low.notna() & ~both | df.ci_high.notna() & ~both, "only one interval endpoint present", out)
    _bad(df, ~df.physical_id.astype(str).str.fullmatch(r"[0-9a-f]{16}"), "physical_id is not a 16-hex id", out)
    _bad(df, df.observable.isna() | df.method.isna(), "missing observable/method", out)
    hw = df.source.eq("hardware")
    _bad(df, hw & (df.related_job_id.fillna("") == ""), "hardware row without a related_job_id", out)
    _bad(df, hw & (df.reference_kind == "none") & df.validation_status.isin({"supported", "inconsistent"}),
         "hardware verdict 'supported'/'inconsistent' without a reference", out)
    return out


def validate_resources(df: pd.DataFrame) -> list[str]:
    out: list[str] = []
    if list(df.columns) != RESOURCES_COLUMNS:
        return [f"columns differ: missing {sorted(set(RESOURCES_COLUMNS) - set(df.columns))}, "
                f"extra {sorted(set(df.columns) - set(RESOURCES_COLUMNS))}"]
    cl = df[df.kind == "classical"]
    _bad(cl, cl.exit_reason.isna(), "classical run without exit_reason", out)
    done = cl[cl.error_status.isin(["ok", "timed_out", "memory_limited"])]
    _bad(done, done.peak_tree_rss_bytes.isna() | (done.peak_tree_rss_bytes <= 0), "classical run without whole-tree RSS", out)
    _bad(done, done.wall_s.isna() | (done.wall_s <= 0) | done.cpu_s.isna(), "classical run without wall/cpu time", out)
    _bad(cl, cl.host_cpu.isna() | cl.logical_cores.isna(), "classical run without host description", out)
    hw = df[df.kind == "compile"]
    _bad(hw, hw.compiled_2q_depth.isna() | hw.compiled_2q_count.isna(), "compiled circuit without gate count/depth", out)
    _bad(hw, hw.compiled_2q_depth > 300, "compiled depth above the 300 ceiling", out)
    est = df[df.kind == "job_estimate"]
    _bad(est, est.estimated_qpu_s.isna(), "job estimate without estimated_qpu_s", out)
    _bad(df, df.observed_qpu_s.notna() & df.job_id.isna(), "observed QPU usage without a job id", out)
    hj = df[df.kind == "hardware_job"]
    _bad(hj, hj.job_id.isna() | hj.observed_qpu_s.isna() | hj.estimated_qpu_s.isna() | hj.shots.isna(),
         "hardware_job row without job id / observed usage / pre-submission estimate / shots", out)
    hc = df[df.kind == "hardware_circuit"]
    _bad(hc, hc.job_id.isna() | hc.compiled_2q_count.isna() | hc.compiled_2q_depth.isna() | hc.shots.isna(),
         "hardware_circuit row without job id / gate count / depth / shots", out)
    _bad(hc, hc.compiled_2q_depth > 300, "executed circuit above the 300 two-qubit-depth ceiling", out)
    return out


def validate_metadata(d: dict) -> list[str]:
    out = [f"missing key: {k}" for k in METADATA_KEYS if k not in d]
    if "frozen_dt" in d and not isinstance(d["frozen_dt"], (int, float)):
        out.append("frozen_dt is not a number")
    blob = repr(d)
    for pat, name in ((r"/home/\w+", "local home path"), (r"(?i)(api[_-]?key|token)\s*[:=]\s*['\"]?\w{12,}", "credential-like string")):
        if re.search(pat, blob):
            out.append(f"metadata contains a {name}")
    ids, qpu = d.get("job_ids") or [], str(d.get("qpu", ""))
    if ids and qpu == "none submitted":
        out.append("job ids present although qpu == 'none submitted'")
    if not ids and qpu.startswith("executed"):
        out.append("qpu says executed but job_ids is empty")
    if ids and not d.get("hardware"):
        out.append("job ids present but no hardware provenance block")
    if ids and isinstance(d.get("backend"), dict) and str(d["backend"].get("live", "")).lower().startswith("none"):
        out.append("backend.live says no live backend although jobs were executed")
    if ids and "NOT LIVE" in repr(d.get("backend")).replace("OFFLINE, used only", ""):
        out.append("backend presented as offline although jobs were executed")
    return out


def cross_check(res: pd.DataFrame, rsc: pd.DataFrame, meta: dict) -> list[str]:
    """results.csv, resources.csv and metadata.json must tell the same hardware story."""
    out: list[str] = []
    ids = set(meta.get("job_ids") or [])
    hw_rows = res[res.source == "hardware"]
    hj = rsc[rsc.kind == "hardware_job"]
    if bool(len(hw_rows)) != bool(ids) or bool(len(hj)) != bool(ids):
        out.append(f"hardware presence differs: results {len(hw_rows)} rows, resources {len(hj)} jobs, metadata {len(ids)} ids")
    if set(hj.job_id.dropna()) != ids:
        out.append("job ids in resources.csv differ from metadata.json")
    used = {j for cell in hw_rows.related_job_id.dropna() for j in str(cell).split(";") if j}
    if not used <= ids:
        out.append("results.csv references job ids absent from metadata.json")
    tot = meta.get("hardware", {}) and meta["hardware"].get("total_reported_usage_s")
    if ids and abs(float(hj.observed_qpu_s.sum()) - float(tot)) > 1e-6:
        out.append("observed usage in resources.csv differs from metadata.json")
    key = ["graph_id", "N", "method", "observable", "site_indices", "approximation_setting"]
    if len(hw_rows) and hw_rows.duplicated(key).any():
        out.append("duplicate hardware result rows")
    return out


def require_valid(problems: list[str], what: str) -> None:
    if problems:
        raise SchemaError(f"{what} invalid:\n  - " + "\n  - ".join(problems))
