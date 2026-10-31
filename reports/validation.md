# Validation report (offline sections; the hardware results are in findings.md §4)

Frozen parameters: J=1, hx=1.25, hz=-0.60, **J·δt = 0.1**, start |0…0⟩, second-order split. Every number below comes
from a saved file under `raw/` (path given) or from the test suite. Data sources are labelled: `exact_numerics`,
`classical_approximation`, `simulated_noisy` (calibration-derived noise on FakeFez, **not hardware**).

## 1. Test suite
- 167 tests (`pytest`), all offline. The full run exited 0 (`logs/pytest_full.log`); `test_submit.py` (15 tests, added afterwards)
  and the trust/manifest/hardware/rehearsal files were re-run after the last code edits and passed. **A final full run is
  repeated before the archive is built** (see the release checklist in STATUS.md).
- Covered: field/bond signs for both signs of hx and hz; circuit = independent numpy kernel = Aer; bit order and
  clbit→physical map; κ from all 15 subset moments (two implementations); mutation checks (5 injected bugs all caught);
  light-cone exact = full exact; supervisor hard kill with partial checkpoint kept; non-finite ZNE never `supported`;
  manifest refuses depth > 300; correlated-readout gate trips; submit refuses without a signed pre-registration.

## 2. Exact numerics and Trotter error (J·δt = 0.1)
Largest |difference| over all 1-, 2-, 4-site observables (`raw/exact/*_trotter_error_dt0.1.csv`):

| Jt | P12 circuit vs exp(-iHt) | P18 circuit vs exp(-iHt) | P12 dt vs dt/2 | P18 dt vs dt/2 | P24 dt vs dt/2 |
|---:|---:|---:|---:|---:|---:|
| 0.4 | 0.0139 | 0.0138 | 0.0104 | 0.0104 | 0.0104 |
| 1.0 | 0.0074 | 0.0070 | 0.0056 | 0.0053 | 0.0056 |
| 2.0 | 0.0063 | 0.0053 | 0.0047 | 0.0040 | 0.0052 |
| 3.0 | 0.0066 | 0.0034 | 0.0049 | 0.0025 | 0.0051 |
| 5.0 | 0.0055 | 0.0028 | 0.0041 | 0.0021 | 0.0032 |

All are below the 0.02 target. For P24 only the dt-vs-dt/2 comparison exists (sparse exp(-iHt) is too large); it is a
convergence check, not a continuous-time error. P40 has no Trotter-error table.
At J·δt = 0.2 the worst error was 0.055 (misses the target): this is why 0.1 was frozen; those runs are kept apart in
`raw/exploratory_dt0.2/` and `figures/exploratory_dt0.2/`.

Aer statevector of the actual Qiskit circuit vs the numpy kernel: max amplitude difference ≤ 2e-15 (P12, P18; N up to 30)
(`raw/exact/P{12,18}_aer_check_dt0.1.csv`).

## 3. Level statistics (optional item)
At the table parameters and the frozen J·δt = 0.1 (`raw/exact/level_statistics_dt0.1.csv`, 12 qubits, 4096 levels): P12 tree with hz scaled on one site ⟨r⟩ = **0.523**;
12-site chain with hz scaled on the end site 0.524 (the statement expects about 0.53); 12-site chain with hz = 0 (integrable control) 0.413 for the full spectrum
(expected about 0.39). At J·δt = 0.2 (exploratory) the three values were 0.518 / 0.520 / 0.428.
Diagnosis of the hz = 0 excess (`reports/level_statistics_diagnosis.csv`): inside the four (parity, mirror) symmetry sectors ⟨r⟩ = **0.381, 0.400, 0.390, 0.390** (commutator norm ≈ 2e-14,
so the sectors are exact); superposing independent sectors raises the full-spectrum value. Each sector is consistent with Poisson (0.386). This is a partial explanation from one system size, not a proof.

## 3b. Reversed hz (Step 2 item 3)
`raw/exact/P12_hz_reversal_dt0.1.csv`, `figures/hz_reversal_P12.png`: exact M(t) of the fixed circuit on P12 with hz = -0.6 and hz = +0.6 (same J, hx, δt). The contrast
M(-0.6) - M(+0.6) is 0 at Jt = 0, -0.08 at 0.4, -0.60 at 1, -0.64 at 2, -0.54 at 3, -0.71 at 4 and -0.59 at 5: the sign of hz matters strongly, as it must.

## 4. Classical methods vs exact (budget 20 min hard per run, supervised child process)
Source: `raw/classical_dt0.1/*.json|csv`; status/wall/peak-tree-RSS from the supervisor. "max err" is the worst observable error
against the exact fixed circuit **where a reference exists**.

| run | status | wall (s) | peak tree RSS (GB) | last Jt | max err vs exact |
|---|---|---:|---:|---:|---:|
| P12 MPS χ=32 / 64 / 128 / 256 | ok | 15–23 | 2.1 | 5.0 | 0.0155 / 0 / 0 / 0 |
| P12 Pauli coarse / medium / fine | ok / ok / timed out | 44 / 218 / 1201 | 2.3 / 2.6 / 4.2 | 5.0 / 5.0 / 2.0 | 0.215 / 0.088 / 0.054 |
| P18 MPS χ=32 / 64 / 128 / 256 | ok | 46 / 518 / 800 / 1163 | 2.2–2.3 | 5.0 | 0.212 / 0.114 / 0.062 / 0.017 |
| P18 Pauli coarse / medium / fine | ok / ok / timed out | 107 / 372 / 1201 | 2.4 / 2.8 / 4.8 | 5.0 / 5.0 / 1.0 | 0.157 / 0.064 / 0.007 |
| P24 MPS χ=32 / 64 / 128 / 256 | ok / timed out / timed out / timed out | 83 / 1200 / 1200 / 1200 | 2.2–2.4 | 5.0 / 3.0 / 2.0 / 2.0 | 0.344 / 0.117 / 0.0006 / 0 |
| P24 Pauli coarse / medium / fine | ok / ok / timed out | 130 / 480 / 1200 | 2.4 / 2.8 / 5.4 | 5.0 / 5.0 / 1.0 | 0.170 / 0.095 / 0.014 |
| P40 MPS χ=32 | ok | 242 | 2.3 | 3.0 | 0 (refs only to Jt 0.5) |
| P40 MPS χ=64 / 128 / 256 | timed out | 1200 | 2.3–2.4 | 2.0 / 1.0 / 1.0 | 0 (refs only to Jt 0.5) |
| P40 Pauli coarse / medium / fine | ok / ok / timed out | 178 / 671 / 1200 | 2.4 / 3.1 / 7.2 | 3.0 / 3.0 / 1.0 | 0.021 / 0.004 / 0.0005 |

A timed-out run keeps every time it finished; "last Jt" is the last time with results. A timeout says the method ran out of
budget, not that the physics is wrong. Pauli "fine" (2^18 terms) completes one to a few times, **not only t=0** (an earlier
note said t=0 only; that was a scheduling artefact fixed by stage-wise slicing).
Memory is the sampled sum over the whole process tree, so the exact reference no longer leaks into method records.

### P40 reference coverage and cross-method agreement
The exact light-cone reference on P40 exists only at N = 0, 4, 5 (Jt ≤ 0.5): larger cones exceed the 26-qubit limit
(single-site cones reach 29 qubits at N=6, 32 at N=7). Beyond Jt = 0.5 the rows have `validation_status = no_reference`.
Max |difference| between methods on all 90 P40 observables (computed from the saved moment tables):

| pair | Jt=0.4 | Jt=0.5 | Jt=1.0 | Jt=2.0 | Jt=3.0 |
|---|---:|---:|---:|---:|---:|
| MPS χ32 vs Pauli medium | 0.003 | 0.004 | 0.031 | 0.085 | 0.244 |
| MPS χ32 vs χ64 | 0 | 0 | 0.0001 | 0.058 | – |
| MPS χ64 vs χ128 vs χ256 | 0 | 0 | 0.0000 | – | – |
| Pauli medium vs fine | 0.003 | 0.004 | 0.031 | – | – |

So P40 is **χ-stable at Jt = 1.0** (stability evidence only, not exactness) and **not stable at Jt ≥ 2** (χ32 and χ64 already differ by 0.058;
at Jt = 3 only χ32 finished).

## 5. Noisy-simulation rehearsal (P12, `simulated_noisy`, B = 2000)
Protocol fixed in code before the run: ZNE model chosen on calibration times Jt ∈ {0.4, 1.0}; performance reported at the
held-out time Jt = 0.8; models disqualified above 5 % fit failures (`raw/noisy_sim_dt0.1/*_selection.json`).

| variant | selected model | held-out RMSE raw → readout → selected ZNE | CI coverage (selected ZNE) | failed fits (selected) |
|---|---|---|---:|---:|
| CZ (FakeFez noise) | richardson | 0.042 → 0.038 → 0.0175 | 0.90 | 0 |
| fractional (ASSUMED RZZ error = CZ error) | linear | 0.022 → 0.018 → 0.0087 | 0.97 | 0 |

Non-selected models at the held-out time (reported, not used to pick): CZ exp RMSE 0.016 with **8 of 30 fits failed**, CZ linear 0.024
(coverage 0.47); fractional exp 0.008 (coverage 1.0), richardson 0.014. Raw and readout-corrected intervals cover the truth only
3–43 % because they contain shot noise but not the remaining systematic error. All 1 020 simulated rows are `inconclusive`,
`inconsistent` or `mitigation_failed`: **none is `supported`**, by rule, since they are not hardware.
Readout-independence gate: passes on the independent-noise rehearsal (worst |z| = 1.76); in the control with correlated flips injected
on edge 0–5 it trips at |z| = 176 while every other edge stays below 1.4 (`raw/noisy_sim_dt0.1/P12_correlated_readout_control.json`).
Limits: the noise model is calibration-derived and independent by construction; a pass here says the code works, not that the real device is independent.

## 6. Hardware: dry run, live check and execution
Dry run (`reports/hardware_manifest.md`, historical): every circuit compiled for the FakeFez target with fractional-gate timing **assumed** equal to CZ; ISA checks passed, measure map clbit i ← physical nodes[i],
maximum compiled two-qubit depth 150 (ceiling 300). Live check (`raw/hardware/account{1,2}/live_check.json`): ibm_fez with fractional RZZ available, recompiled circuits did not grow in depth.
Executed on 2026-10-30/31: 6 jobs, 56 circuit executions, 720 896 shots, 202 s reported usage (`HARDWARE_PROVENANCE.md`); results in `findings.md` §4.

## 7. Estimator check on the exact case
`reports/cumulant_bias_exact.csv`: sampling the exact P18 distribution at the hardware shot count (200 repetitions per time) and applying the pipeline's raw-moment estimator, the mean bias of every class is at most 0.0013 in absolute value
(shot-noise SD 0.002-0.008); percentile-bootstrap coverage of the 95 % interval 0.83-0.98 (30 replicates per observable, so each coverage value is uncertain by about ±0.05). Validates the estimator, not the device.
