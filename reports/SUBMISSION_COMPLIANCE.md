# Submission compliance (TEAM-NWCZYG)

Each line item of the problem statement ("When can we trust a quantum simulation?") and of the QFF 2026 rulebook, with the evidence path and a status:
**PASS** = implemented and checked by a test or a saved result; **PARTIAL** = done with a stated limitation; **NOT DONE** = deliberately not done;
**HUMAN** = cannot be verified from the repository and needs a person to check.

## Problem statement
| item | status | evidence / note |
|---|---|---|
| 1. One device geometry; connected patches 8-12 / 16-20 / 32-64, all couplings kept, open boundaries | PASS | `raw/patches/P12,P18,P24,P40.json`, `figures/patch_*.png`, `configs/heavy_hex.yaml`. P40 = 40 qubits, 41 couplings (2 independent cycles, diameter 22): elongated, so a weak test of 2-D difficulty (`reports/topology_comparison.csv`). Largest-region optional patch not attempted. |
| 1. Hamiltonian, J=1, hx=1.25, hz=-0.60, start |0..0>, second-order split, exact field gates, RZZ(-2J dt), both signs checked | PASS | `src/qtrust/circuits.py`, `tests/test_circuits.py` (sign tests with mutation checks). |
| 1. Initial J·dt = 0.20 | PARTIAL (allowed) | Frozen at **0.1** after 0.2 missed the 0.02 target (worst 0.055; exploratory data kept apart in `raw/exploratory_dt0.2/`). The statement allows freezing after the Step 2 checks and reporting the shorter range. |
| 1. Output: drawing, edge list, parameter file, verified circuit | PASS | as above |
| 2. Observables m, M, C, G, kappa; all m, all edge C, >= 3 four-site clusters chosen before hardware | PASS | `src/qtrust/moments.py` (all 15 subset moments; two independent kappa formulas), clusters fixed in `raw/patches/*.json` before any hardware data. |
| 2.1 Aer statevector at Jt = 0, 0.4, 1, 2, 3, 4, 5; N=0 identity; bit order; U†U | PASS | `raw/exact/P*_aer_check_dt0.1.csv` (Aer vs kernel <= 2e-15); `tests/test_circuits.py`. |
| 2.2 Sparse-expm comparison on 8-12 qubits; dt halving on the largest affordable patch; max difference < 0.02 | PASS | circuit vs exp(-iHt) <= 0.0139 (P12, P18); dt vs dt/2 <= 0.0104 up to P24 (`raw/exact/*_trotter_error_dt0.1.csv`). Small-patch agreement is evidence, not a bound for all sizes. |
| 2.3 Plot M(t); repeat with hz reversed | PASS | `figures/hz_reversal_P12.png`, `raw/exact/P12_hz_reversal_dt0.1.csv` (contrast up to 0.71), `tests/test_hwanalysis.py`. |
| 2.4 (optional) level statistics <r> | PASS | `raw/exact/level_statistics_dt0.1.csv` (table parameters), `reports/level_statistics_diagnosis.csv` (symmetry sectors explain the excess for the hz=0 chain). |
| 3. One approximation route with >= 3 settings; accuracy vs runtime and peak memory with CPU spec; attempt 32-64 qubits | PASS | MPS (chi 32/64/128/256) and Pauli propagation (coarse/medium/fine), supervised with a hard 20 min limit, whole-process-tree memory, host CPU in `resources.csv`. P40 attempted; exact reference only to Jt = 0.5. Timeouts are reported, not hidden. |
| 4. Small patch with exact answers + a larger patch | PASS | P18 (18 qubits, exact) and P40 (40 qubits) on ibm_fez (`raw/hardware/`). |
| 4. Backend gates, couplings, durations, rep delay, calibration; fractional-gate check; compiled counts, depth, durations saved | PASS / PARTIAL | `live_check.json` (gates, rep delay 0.25 ms, per-pair CZ error), compiled QPY files and per-circuit counts/depth in `resources.csv`. Full backend property dump not archived. |
| 4. Depth: aim <= 100, ceiling 300 for every executed circuit | PASS | maximum compiled two-qubit depth 150 (folded Jt=1.0 circuits); `resources.csv`. |
| 4. Noisy Aer check on the small patch with a stated noise model | PASS | `raw/noisy_sim_dt0.1/`, `reports/validation.md` §5 (simulated; fractional RZZ error assumed equal to CZ). |
| 4. QPU allocation <= 10 min; pilot first; estimate before, reported usage after | PASS | 6 jobs, 202 s reported; estimates and observed usage per job in `resources.csv` and `reports/HARDWARE_PROVENANCE.md`. |
| 4. Readout calibration and corrected 1-4 site probabilities; independence check | PASS | structured calibration + asymmetric correction (`mitigation.py`); the independence gate **failed on account 2 / P18** (physical pair 16-23, z = 6.66), see `reports/readout_independence.csv`. |
| 4. One further correction (ZNE >= 3 levels), chosen on some times, validated on unused ones | PASS (negative result) | manual global folding 1x/3x/5x; model chosen on Jt 0.4/1.0, validated on Jt 0.8; **failed the pre-declared check on both accounts** (`reports/hardware_heldout_zne.csv`). |
| 4. 95% intervals by bootstrapping with all moments recomputed together, calibration and blocks included; cumulant bias on the exact case; no clipping | PASS | joint multinomial bootstrap B=2000; `reports/cumulant_bias_exact.csv` (estimator on the exact distribution). Intervals are shot-noise only, not systematics. |
| 4. Output: raw and corrected curves, small-patch errors, resource usage | PASS | `figures/hardware_*.png`, `reports/hardware_class_table.csv`, `resources.csv`. |
| 5. Disturbance-spreading extension | NOT DONE | optional; no reversal circuit was run or claimed. |
| 6.1 `src/`, README, pinned environment, reproduce command, packages and AI disclosure, sign / bit-order / t=0 / reversal checks | PASS | `README.md`, `requirements.lock`, `scripts/reproduce_all.py`, `tests/`. |
| 6.2 `results.csv`, `resources.csv` with the required columns, one row per measured quantity or run | PASS | 15 108 / 121 rows including hardware (`tests/test_export.py`). |
| 6.3 `raw/`, `metadata.json` (counts, calibrations, references, edges, compiled circuits, layout, backend, job ids, timestamps, versions, seeds, mitigation settings; no credentials) | PASS | `raw/hardware/`, `metadata.json`; credential scan in `src/qtrust/package.py`. |
| 6. Archive `team_name.zip` | PASS | `TEAM-NWCZYG.zip` at the repository root and as a GitHub Release asset (see below). |

## QFF rulebook
| item | status | evidence / note |
|---|---|---|
| Private GitHub repository named `qff_bits_<team_name>` | PASS | `qff_bits_team_nwczyg` (registered name TEAM-NWCZYG, lowercase with underscores as the rulebook recommends); private (checked with the GitHub API on 2026-10-31). |
| Collaborator `AresTheWarGod42` | HUMAN | invitation sent (shows as pending); the organisers have to accept it. |
| Ready before 31 Oct 2026 11:59 PM IST | HUMAN | final push time is the last commit on `main`. |
| Repository identifies the project and all members with names and registration details | PASS | README Team table (names, QFF IDs, emails). |
| README: overview, quantum component, setup/run | PASS | `README.md`. |
| Pre-existing vs hackathon work; third-party licences | PASS | README sections "Pre-existing versus hackathon work" and "Reused packages and AI assistance". |
| Further organiser instructions followed | HUMAN | none were received by the team; the organisers did not answer the team's questions. |

## Human-only checklist (cannot be done by the code)
- [x] Each teammate ran `python -m qtrust.cli verify-jobs --account N` and pushed `raw/hardware/accountN/job_verification.json` (IBM-side confirmation: 6/6 jobs DONE, usage matches; 2026-10-31).
- [ ] `AresTheWarGod42` has accepted the collaborator invitation (Settings -> Collaborators).
- [ ] The repository is still **Private**.
- [ ] The last commit on `main` is the final one and was pushed before 11:59 PM IST; the Release `final-submission` contains `TEAM-NWCZYG.zip`.
- [ ] Check the Discord / website for any announced submission instruction.
