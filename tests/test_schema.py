import numpy as np
import pandas as pd
import pytest

from qtrust import schema as S

NAN = float("nan")


def good_row(**kw):
    r = dict(graph_id="P12", physical_id="0123456789abcdef", n=12, J=1.0, hx=1.25, hz=-0.6, dt=0.1, N=4, t_Jt=0.4,
             observable="m", site_indices="3", method="mps", approximation_setting="chi64", estimate=0.5, ci_low=NAN,
             ci_high=NAN, reference=0.5, reference_kind="full_exact", validation_status="exact_reference",
             source="classical_approximation", execution_block="", related_job_id="", notes="")
    r.update(kw)
    return r


def df(*rows):
    return pd.DataFrame(list(rows), columns=S.RESULTS_COLUMNS)


def test_valid_table_passes():
    assert S.validate_results(df(good_row()), 0.1) == []


@pytest.mark.parametrize("kw,needle", [
    (dict(dt=0.2), "frozen dt"),
    (dict(t_Jt=0.5), "N*dt"),
    (dict(source="made_up"), "unknown source"),
    (dict(validation_status="great"), "unknown validation_status"),
    (dict(validation_status="supported"), "non-hardware"),
    (dict(estimate=NAN), "non-finite estimate"),
    (dict(reference=NAN, reference_kind="full_exact"), "reference_kind != 'none'"),
    (dict(reference=0.3, reference_kind="none"), "kind not recognised"),
    (dict(reference=NAN, reference_kind="none", validation_status="exact_reference"), "no_reference"),
    (dict(ci_low=0.9, ci_high=0.1), "ci_low > ci_high"),
    (dict(ci_low=0.1), "one interval endpoint"),
    (dict(physical_id="xyz"), "16-hex"),
])
def test_each_class_of_error_is_caught(kw, needle):
    problems = S.validate_results(df(good_row(**kw)), 0.1)
    assert any(needle in p for p in problems), problems


def test_nan_estimate_is_allowed_only_as_mitigation_failed():
    row = good_row(estimate=NAN, source="simulated_noisy", validation_status="mitigation_failed", reference_kind="full_exact")
    assert S.validate_results(df(row), 0.1) == []


def test_missing_columns_are_reported():
    assert "missing" in S.validate_results(df(good_row()).drop(columns=["notes"]), 0.1)[0]


def res_row(**kw):
    r = dict(kind="classical", graph_id="P12", physical_id="0123456789abcdef", n=12, dt=0.1, method="mps", setting="chi64",
             error_status="ok", exit_reason="ok", wall_s=3.0, cpu_s=3.0, peak_tree_rss_bytes=3e8, max_processes=1, workers=1,
             term_count_or_bond_dim=48, max_Jt_completed=5.0, host_cpu="cpu", logical_cores=12, gpu="none", compiled_2q_count=NAN,
             compiled_2q_depth=NAN, shots=NAN, estimated_qpu_s=NAN, observed_qpu_s=NAN, job_id=None, run_hash="ab", experiment_id=None)
    r.update(kw)
    return r


def rdf(*rows):
    return pd.DataFrame(list(rows), columns=S.RESOURCES_COLUMNS)


def test_resources_schema_catches_lifetime_rss_style_gaps_and_ceiling_violations():
    assert S.validate_resources(rdf(res_row())) == []
    assert any("RSS" in p for p in S.validate_resources(rdf(res_row(peak_tree_rss_bytes=NAN))))
    assert any("exit_reason" in p for p in S.validate_resources(rdf(res_row(exit_reason=None))))
    bad = res_row(kind="compile", compiled_2q_depth=301, compiled_2q_count=10)
    assert any("ceiling" in p for p in S.validate_resources(rdf(bad)))
    assert any("job id" in p for p in S.validate_resources(rdf(res_row(observed_qpu_s=12.0))))


def test_metadata_validator_rejects_paths_credentials_and_phantom_jobs():
    ok = {k: ("none submitted" if k == "qpu" else [] if k == "job_ids" else 0.1 if k == "frozen_dt" else "x") for k in S.METADATA_KEYS}
    assert S.validate_metadata(ok) == []
    assert any("home path" in p for p in S.validate_metadata({**ok, "python": "/home/someone/venv/bin/python"}))
    assert any("credential" in p for p in S.validate_metadata({**ok, "backend": "token = abcdefghijklmnop1234"}))
    assert any("job ids" in p for p in S.validate_metadata({**ok, "job_ids": ["abc"]}))
    with pytest.raises(S.SchemaError):
        S.require_valid(["boom"], "x")
