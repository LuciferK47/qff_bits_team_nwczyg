# Estimator health of the hardware table

Generated read-only from the frozen `raw/hardware/hardware_results.csv` (4 230 rows) by `hwanalysis.estimator_health`; table: `estimator_health.csv`. **No `trust_status` was changed.**
Two different things can be wrong with a row and they are independent: *no validated reference exists* (P40 beyond Jt = 0.5, reported as `no_reference`) and *the estimator failed* (non-finite estimate or no valid interval).
The frozen policy gives `no_reference` precedence over estimator failure, so the primary status alone hides the second axis; this page shows it.

| axis | rows | detail |
|---|---:|---|
| non-finite point estimate | **69** | 37 `mitigation_failed` (P18) + 32 `no_reference` (P40); every one is an exponential-ZNE fit with `failed_reason = sign_change` |
| finite estimate, no valid interval (< 99 % finite bootstrap replicates) | **30** | 18 `mitigation_failed` (P18) + 12 `no_reference` (P40); all exponential ZNE, `insufficient_finite_bootstrap` |
| any of the above | 99 | per account / patch below |

| account | patch | method | non-finite estimate | interval missing | primary status |
|---|---|---|---:|---:|---|
| 1 | P18 | zne_exp | 21 | 7 | mitigation_failed |
| 2 | P18 | zne_exp | 16 | 11 | mitigation_failed |
| 1 | P40 | zne_exp | 21 | 5 | no_reference |
| 2 | P40 | zne_exp | 11 | 7 | no_reference |

Raw, readout-corrected, linear and Richardson ZNE rows have finite estimates and intervals everywhere. No non-finite estimate is `supported` or `inconsistent` (test: `tests/test_verification_evidence.py`).
Reading: the exponential extrapolation is unstable on these data (sign change in the three noise levels), which is one more reason the ZNE model cannot be trusted here; the selected model (linear) did not fail numerically, it failed the held-out check.
