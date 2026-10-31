# Response to the repository audit (IBM_quant_audit_package)

Status as of 2026-10-30. "Evidence" points to a test, a saved file or a report section. Anything not done is marked **NOT DONE** or
**NOT EXECUTED** with the reason. Update 2026-10-31: the hardware runs (two accounts, 28 circuits each) have since been executed under the signed pre-registration; their analysis is in `findings.md` §4. Rows below that say NOT EXECUTED describe the state when the audit was answered, unless marked otherwise.

| item | finding | fix | evidence | status |
|---|---|---|---|---|
| CRITICAL 01 | NaN ZNE estimates received verdicts (2 `supported`) | `zne_fit` returns a `FitResult`; `bootstrap` records `n_valid`, never calls `percentile` on empty data, returns NaN interval + `failed_reason` below 99 % valid replicates; `classify`/`assess` map any non-finite value to `mitigation_failed` | tests in `test_mitigation.py`, `test_trust.py`; archived-CSV regression; `results.csv` has no `supported` simulated row | done |
| CRITICAL 02 | Classical benchmarks at dt = 0.2, hardware plan at 0.1 | **J·δt frozen at 0.1** (`configs/heavy_hex.yaml`, `Params`); all classical, exact and rehearsal data regenerated at 0.1; dt = 0.2 data moved to `raw/exploratory_dt0.2/` and `figures/exploratory_dt0.2/`, never overlaid | `validation.md` §2, §4, §5; `raw/classical_dt0.1/` | done |
| HIGH 03 | P40 unreferenced predictions dropped | `compare()` keeps every completed (N, observable) with `reference_kind = none`, `validation_status = no_reference`; raw moments saved per run | `results.csv` has 1 260 `no_reference` classical rows; `figures/P40_predictions_unvalidated.png`; test with reference only at N ≤ 5 | done |
| HIGH 04 | Trust rule conflated tolerance agreement with validity | multi-gate `assess`: reference_status, mitigation_valid, signal_resolved, statistical_status, systematics_validated, source; `supported` needs all; simulated data can never be `supported`; policy v2 (pre-hardware amendment, adds `systematics` thresholds) | `configs/trust_policy.yaml`, `test_trust.py` | done |
| HIGH 05 | ZNE not validated on unused times or the final gate family | model chosen on calibration times Jt 0.4/1.0 by a rule fixed in code, performance reported at held-out Jt 0.8, fit failures disqualify (> 5 %), B = 2000 joint bootstrap, both CZ and an (assumed) fractional-RZZ noise variant | `validation.md` §5; `raw/noisy_sim_dt0.1/*_selection.json`. Held-out check in the hardware analysis is implemented (`submit.analyse_hardware`), not run on hardware | done in simulation; **hardware NOT EXECUTED** |
| HIGH 06 | Memory/CPU claims were lifetime high-water marks | every run in its own child process (`classical/supervise.py`), whole-process-tree RSS/CPU sampled by `psutil`, hard kill at 1200 s with per-time checkpoints; exact reference computed once and cached separately; `ru_maxrss` removed | `test_supervise.py`; `resources.csv` | done. Usable approximation settings: Pauli fine completes only 1–2 times before the limit (reported as `timed_out`), so "≥ 3 usable settings" is met for coarse/medium and **openly limited** for fine |
| HIGH 07 | P40 is elongated | documented (40/41, cycle rank 2, diameter 22, cut 4); compact candidate `P40c` (3 cycles, diameter 14) found and saved with a topology table | `reports/topology_comparison.csv`, `findings.md` §2 | partly done: **P40c NOT benchmarked**; longer-time P40 checks **NOT DONE** (needs GPU) |
| HIGH 08 | Readout independence not validated in the pipeline | independence z-score gate (|z| < 4) on structured calibration preps inside the rehearsal and the hardware analysis; pair-joint 4×4 fallback; correlated-readout control | control trips at |z| = 176, others < 1.4 (`validation.md` §5) | done in simulation; real-device independence **NOT MEASURED** |
| HIGH 09 | Manifest recorded failures but did not gate | `build_jobs` raises `ManifestGateError` on ISA failure, wrong measure map or compiled 2q depth > 300; > 250 flagged; ZNE moved to shallow times; experiment ids; later found and fixed a gap (P18 Jt 0.8 unfolded run was missing) | `test_manifest.py`, `reports/hardware_manifest.md` | done (dry run). Live-target gates **NOT EXECUTED** (`qtrust live-check` exists, not run) |
| MEDIUM 10 | Step 6 schema unfinished | `schema.py` + `export.py` write and validate `results.csv`, `resources.csv`, `metadata.json`; `scripts/reproduce_all.py` regenerates from `raw/` offline | `logs/reproduce.log` (10 878 + 59 rows, validated) | done. Clean-machine rebuild: see STATUS release checklist |
| MEDIUM 11 | Hash lacked physical identity | `Patch.physical_id`, `experiment_id(patch, prm, N, circuit_sha)`; structural hash kept | `ids.py`, `test_graph.py`, `test_manifest.py` | done |
| MEDIUM 12 | Figures and gap-ratio | figures rewritten (signed trajectories, error plots with gaps/timeouts marked, provenance footers); gap ratio diagnosed by symmetry sectors | `figures/`, `validation.md` §3 | figures done; gap ratio **partly explained** (sectors ≈ Poisson; one size only) |
| MEDIUM 13 | Hygiene | no `eval`; `set -euo pipefail` with logged exit codes; run-hash-gated `skip_done`; README/STATUS overclaims corrected | `test_bench.py`, `scripts/run_queue.sh`, `logs/` | done |

## Audit "work left" list
Gate 0 (1–4): done. Gate 1 (5–8): 5, 6, 8 done in simulation/offline; 7 partly (compact graph found, not benchmarked). Gate 2 (9–10): code written
(`live-check`, pilot gate, usage rescaling); **executed on 2026-10-30/31** (live check, pilot, forward and ZNE jobs on both accounts; see `findings.md` §4). Gate 3 (11–12): **NOT EXECUTED**; no hardware
data, so no class-by-class hardware comparison exists.

## Changes made after the audit that the audit did not ask for
- The organisers' reply (own Open Plan accounts, mentor review after screening) replaced the "mentor review before the first job" gate by a signed
  pre-registration (`qtrust preregister`, `prereg/APPROVAL.md`) checked by `qtrust submit`.
- Two accounts: the second repeats the same frozen manifest as a drift check; a significant drift demotes `supported` to `inconclusive`.
- Policy v2 adds the thresholds for those gates before any hardware data exist.

## Suggested claim (adopted)
Our evidence is offline. We implemented and cross-checked the simulation, exact references up to 24 qubits, classical baselines under hard resource limits
(P40 exact only to Jt = 0.5, stable to Jt = 1.0, unreliable beyond), and a mitigation/trust pipeline validated in simulation. Whether the real device can be trusted
for each statistic is **not yet measured**.

## Second audit (31 Oct, `FINAL_CRITICAL_AUDIT`) and what was done
| finding | verdict | action |
|---|---|---|
| BLOCKER A: `results.csv` has no hardware rows; `resources.csv` no observed usage; `metadata.json` says nothing ran | confirmed | `export.py` + `hwdata.py` now include 4 230 hardware rows, 6 `hardware_job` and 56 `hardware_circuit` rows and a hardware provenance block; `schema.cross_check` makes the three files agree; regression tests in `tests/test_export.py` |
| BLOCKER B: contradictory reports | confirmed | findings, STATUS, validation, hardware_manifest (kept as a labelled historical plan) updated; README summary |
| HIGH C: no hardware figures | confirmed | 9 new figures, regenerated by `reproduce_all.py` |
| HIGH D: account-2 readout failure unlocalised | confirmed and localised | physical pair 16-23, z = 6.66 (`reports/readout_independence.csv`); mechanism not established; frozen verdicts unchanged |
| HIGH E: do not rank reliability by support fractions | agreed, and stronger than stated: the fractions are confounded by gates and drift | class table with error, signal, interval width and an always-0 baseline |
| MEDIUM F: hz-reversal plot | confirmed | `figures/hz_reversal_P12.png` |
| MEDIUM G/H: provenance, clean-room check | done | `HARDWARE_PROVENANCE.md`, evidence hash table and tests, `verify_release.sh` rerun |
| Not flagged by the audit: cumulant bias on the exact case | added | `reports/cumulant_bias_exact.csv` |
| Zip delivery and repo access | done / HUMAN | zip committed and attached to a GitHub Release; collaborator invitation pending |
The audit's numbers (held-out RMSEs, 650/2 115 drift, pair z = 6.6605, 202 s) were re-derived from the raw files and agree.

## Third audit (independent final audit, 2026-10-31)
| finding | verdict | action |
|---|---|---|
| `REPRODUCIBILITY.md` points to the old offline-only clean-room log | confirmed | now `logs/verify_release3.log`; older logs marked historical; a test reads the named log |
| two `job_verification.json` not in the 68-row evidence ledger | confirmed | append-only `reports/job_verification_hashes.csv` + test; original ledger unchanged; provenance text corrected |
| 69 non-finite estimates (32 `no_reference`) hidden behind primary status | confirmed; the true count of rows without a valid estimate or interval is 99 (30 more lack an interval) | `ESTIMATOR_HEALTH.md`, `estimator_health.csv`, test; statuses unchanged |
| clean-room run not on the exact final archive | confirmed | `scripts/verify_release.sh` run on the rebuilt zip, recorded outside it in `FINAL_RELEASE_VERIFICATION.md` |
| "signed" approval overstated | confirmed | worded as typed, hash-tied approval, not a cryptographic signature |
| fold factors presented as noise factors | confirmed | marked nominal (gate counts) everywhere |
| exp-ZNE RMSE shown beside 45-observable RMSEs | confirmed | n = 36 / 38 of 45 stated, marked not comparable |
| coverage 0.83-0.98 without uncertainty | confirmed | "± 0.05 (30 replicates)" added |
| account vs window confounded; CI conditional on stationary readout | confirmed | stated in report and limitations |
| re-run `reproduce_all.py` in the repository | not adopted | no export code change; the clean-room run regenerates everything |
| put the final verification log inside the zip | not adopted | an archive cannot contain the log of its own verification; recorded outside it |
| pending collaborator invite | rulebook 5.2.3 asks for "invited or added" | recorded as PASS (invited); acceptance remains the organisers' |

