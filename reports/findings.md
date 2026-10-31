# Findings: when can we trust each kind of statistic? (offline phase)

**Scope.** Sections 1-3 are offline (exact numerics, classical approximations, noisy *simulation*); section 4 is **real hardware** (ibm_fez, two accounts, 30-31 Oct 2026);
section 5 answers the three questions of the problem statement. Numbers are measured values from `raw/`, `results.csv` and `reports/*.csv` (details and commands in
`reports/validation.md`, `REPRODUCIBILITY.md`). Setting: Trotterised mixed-field Ising, J·δt = 0.1 (frozen), heavy-hex patches P12/P18/P24/P40 of ibm_fez.
Observable classes: m (1-site), M (mean m), C (2-site edge covariance), G (4-site raw), κ (4-site fourth cumulant).
Provenance of each number: **offline simulation** (`exact_numerics`, `simulated_noisy`), **approximate classical** (MPS / Pauli propagation), **IBM ibm_fez account 1** (30 Oct), **IBM ibm_fez account 2** (31 Oct).

## 1. Classical approximability (best available method vs exact fixed circuit, max |error| over the class)
Best of {MPS χ ≤ 256, Pauli propagation coarse/medium/fine} that finished the time within the 20-minute hard limit.

| patch | Jt | m | M | C | G | κ | best method |
|---|---:|---:|---:|---:|---:|---:|---|
| P12 | 1–5 | 0 | 0 | 0 | 0 | 0 | MPS (exact to display precision at every χ ≥ 64) |
| P18 | 1 | 0 | 0 | 0 | 0 | 0 | MPS χ ≥ 64 |
| P18 | 2 | 0 | 0 | 0 | 0 | 0 | MPS χ256 |
| P18 | 3 | 1e-4 | 1e-4 | 7e-4 | 0 | 0 | MPS χ256 |
| P18 | 5 | 9e-3 | 7e-3 | 1.7e-2 | 2.9e-3 | 1e-3 | MPS χ256 (1163 s of 1200 s) |
| P24 | 1–2 | 0 | 0 | 0 | 0 | 0 | MPS χ ≥ 64 / χ256 |
| P24 | 3 | 7.1e-2 | 1.4e-2 | 5.5e-2 | 2.1e-2 | 1.5e-2 | Pauli medium (MPS χ64 for κ); χ ≥ 128 timed out before Jt = 3 |
| P24 | 5 | 4.6e-2 | 1.6e-2 | 5.3e-2 | 2.7e-2 | 2.2e-2 | Pauli medium / coarse |

Reading: a statistic is classically reproducible to the 0.02 target only where a method both finished and was checked against an exact
reference. On P24 beyond Jt = 2 within 20 minutes, **no tested method meets 0.02 for m and C**; κ and G are marginal. This is a statement about
my budget and implementation (CPU, 20 min), not about intrinsic hardness. In the table the higher-order classes (G, κ) have smaller absolute errors than m and C on P24 at Jt = 3 and 5, so they are not harder
to approximate classically in these runs; one patch and one method family only, so this is not a general statement.

## 2. P40: what can and cannot be said
- P40 is **elongated**: 40 qubits, 41 edges, cycle rank 2, diameter 22, MPS cut width 4. It is therefore close to a 1-D-like geometry for MPS
  (favourable to MPS) and a weak test of 2-D entanglement. A more compact candidate (`P40c`: 3 cycles, diameter 14, cut 4) is saved with a topology
  table (`reports/topology_comparison.csv`) but **was not benchmarked**.
- Exact reference only to Jt = 0.5 (light-cone limit). There, MPS errors are ≤ 6e-8 and Pauli errors 2e-2 (coarse) to 5e-4 (fine).
- At Jt = 1.0 all MPS runs (χ = 32…256) agree to 1e-4 → label `classical_stability_only`, **not validated**. Pauli medium differs by 0.03.
- At Jt ≥ 2 the methods disagree (χ32 vs χ64: 0.058; MPS χ32 vs Pauli medium: 0.085 at Jt = 2, 0.24 at Jt = 3). No P40 prediction at Jt ≥ 2 is trustworthy
  (`figures/P40_predictions_unvalidated.png`).

## 3. Mitigation in simulation (P12, `simulated_noisy`; NOT hardware)
Held-out time Jt = 0.8, model picked on Jt = 0.4, 1.0 only:
- Readout correction reduces RMSE modestly (0.042 → 0.038 CZ; 0.022 → 0.018 fractional).
- ZNE with the pre-selected model reduces it further (CZ richardson 0.0175; fractional linear 0.0087), with 0.90 / 0.97 interval coverage and no failed fits for the selected model.
- Other models fail more (CZ exp: 8/30 fits failed). Model choice matters and must be made before looking at hardware.
- Raw and readout-only intervals cover the truth in only 3–43 % of cases: their uncertainty is shot noise only.
- Held-out RMSE by observable class (Jt = 0.8, simulated):

  | variant (selected ZNE) | stage | m | M | C | G | κ |
  |---|---|---:|---:|---:|---:|---:|
  | CZ (richardson) | raw | 0.027 | 0.008 | 0.054 | 0.043 | 0.040 |
  | | readout | 0.026 | 0.006 | 0.050 | 0.037 | 0.036 |
  | | ZNE | 0.021 | 0.002 | 0.018 | 0.008 | 0.012 |
  | fractional (linear) | raw | 0.013 | 0.001 | 0.030 | 0.022 | 0.020 |
  | | readout | 0.012 | 0.0005 | 0.025 | 0.016 | 0.014 |
  | | ZNE | 0.007 | 0.0005 | 0.011 | 0.005 | 0.006 |

  Raw errors are largest for the multi-site classes (C, G, κ) and ZNE helps them most; after ZNE the largest remaining error in the CZ variant is in the
  single-site m (0.021) and C (0.018), the smallest in the aggregate M. I expected the 4-site classes to be the worst and the data do not show that
  here (one patch, one held-out time, simulated independent noise), so no class ranking is claimed beyond these numbers. The signal-resolved
  rule still marks near-zero κ `inconclusive` instead of `supported`.
- **Caveat that limits all of this:** the noise model is calibration-derived, independent between qubits, and its fractional-gate error is an assumption. It
  validates the *pipeline*, not the device.

## 4. Hardware (two accounts, ibm_fez; measured 2026-10-30 and 2026-10-31)
Pre-registered manifest (sha `5360308738170cc5410562cb971a3050`): 28 circuit executions in 3 jobs per account, 202 s reported usage in total (101 s each), 720 896 shots, all returned.
Account 1 ran on 30 Oct 10:43 UTC, account 2 (identical logical manifest, own account) on 31 Oct 07:10 UTC, about 20 h later. Job ids and times: `HARDWARE_PROVENANCE.md`.
Analysis: `qtrust analyse-hardware --accounts 1,2 --B 2000` (frozen verdicts, `raw/hardware/hardware_results.csv`, included in `results.csv` as `source = hardware`) plus post-hoc, descriptive
diagnostics (`reports/*.csv`, `src/qtrust/hwanalysis.py`) that never change a verdict. Exact references: P18 at Jt 0, 0.4, 0.8, 1, 2, 3; P40 only at Jt 0 and 0.4.

**4.1 ZNE failed.** The model chosen on Jt 0.4/1.0 was `linear` on both accounts. Held-out (Jt 0.8, P18, all 45 catalogue observables) RMSE, account 1 / account 2:
raw 0.094 / 0.077, readout 0.092 / 0.085, **linear (selected) 0.118 / 0.096**, exp 0.095 / 0.107 (only 36 / 38 of the 45 observables have a finite fit, so not comparable), richardson 0.191 / 0.083. The selected model is worse than the raw estimate on both accounts and above the
pre-declared 0.05 limit, so no ZNE row is `supported` (`reports/hardware_heldout_zne.csv`, `figures/hardware_zne_heldout.png`). In the rehearsal (simulated independent noise) ZNE helped; this device did not behave that way.
The folds are nominal 3x/5x noise factors (gate counts); their effective noise amplification was not measured.

**4.2 Readout independence.** Account 1 passed everywhere (P18 maximum |z| 3.00, P40 1.81). **Account 2 failed on P18** at one pair: logical 0-4 = physical 16-23, z = +6.66 (Bonferroni p < 1e-6 over the 18 tested
edges); no other P18 pair exceeds 2.7 and P40 stays below 2.3. The excess sits in the all-zeros calibration state (z = 10.3) and is absent in the all-ones state (z = -0.6). On account 1 one checkerboard state
alone reaches z = 5.0 for physical pair 25-26 while the pooled statistic (the pre-specified one) is 3.0, so pair-level structure is not unique to account 2. The mechanism is not established
(`reports/readout_independence.csv`, `figures/hardware_readout_independence.png`). By the pre-declared rule account 2's P18 rows cannot be `supported`; this was not altered.

**4.3 Drift.** 650 of 2 115 matched estimates differ by more than 4 shot-noise SEs between the windows (raw 243/720, readout 213/720, ZNE 194/675); they are correlated, not independent tests. The drift is concentrated in a few
qubits and pairs rather than uniform: the two largest z-scores (69, 63) are Jt = 0 circuits on P40 (qubit 38: m = 0.98 vs 0.52), i.e. a readout or preparation change, not dynamics; and on account 1 the P18 edge covariance C(1-2)
(physical 20-21) is far from the exact value at Jt 0.8-1.0 (-0.19 and -0.40 against +0.13 and +0.07) while account 2 is close (0.07 and -0.04). Median absolute window-to-window difference 0.027 (`reports/hardware_drift_cases.csv`, `figures/hardware_drift.png`).

**4.4 Accuracy by class (P18, readout-corrected, both accounts, Jt >= 0.4; `reports/hardware_class_table.csv`, `figures/hardware_class_error_vs_signal.png`).**
Support fractions are *not* used to rank classes (the readout gate and drift demotions remove whole accounts and times). Instead, with the 0.05 policy tolerance:

| class | n | within 0.05 of exact | an always-0 predictor would be within 0.05 | RMSE hardware | RMSE always-0 | signal resolved (CI excludes 0 or |exact| >= 0.05) |
|---|---:|---:|---:|---:|---:|---:|
| m (1-site) | 180 | 0.61 | 0.33 | 0.100 | 0.318 | 0.91 |
| C (edge) | 180 | 0.69 | 0.20 | 0.073 | 0.163 | 0.99 |
| G (4-site raw) | 40 | 0.85 | 0.20 | 0.037 | 0.121 | 0.92 |
| κ (4-site cumulant) | 40 | 0.93 | 0.60 | 0.025 | 0.084 | 0.60 |

Median relative error is about 0.2-0.3 for every class. The four-site statistics are *not less accurate* in absolute or relative terms than the one-site means here; they are less **resolvable**: their exact values are small
(|κ| about 0.001 at Jt 0.4 and 0.01-0.03 at Jt 2-3) while the 95 % half-width is about 0.015 with 16 384 shots, so κ is unresolved at Jt 0.4 (0 of 8 observables) and in 25-75 % of cases at Jt 2-3.

**4.5 Estimator check (exact case).** Sampling the exact P18 distribution with the hardware shot count (200 repetitions, Jt 0.4/0.8/1.0) and applying the pipeline's raw-moment estimator gives a mean bias of at most 0.0013 in
absolute value for every class (shot-noise SD 0.002-0.008), and a percentile-bootstrap coverage of the 95 % interval of 0.83-0.98 (mean 0.92; only 30 replicates per observable, so each coverage value is uncertain by about
+-0.05) (`reports/cumulant_bias_exact.csv`). The estimator is therefore not the source of the hardware errors; the intervals are, if anything, slightly narrow.

**4.6 P40.** Measured at 40 qubits; exact references only at Jt 0 and 0.4, where median errors are 0.002-0.046 (m max 0.65, one qubit). Beyond Jt 0.5 the hardware numbers are `no_reference`.

## 5. What we can honestly claim
Answers to the three questions of the problem statement, each limited to this device, these two windows, these patches and the 0.05 / 0.02 policy tolerances:

1. **Do four-qubit statistics become unreliable before single-qubit averages?** Not in accuracy: on P18 the 4-site G and κ are within tolerance more often than m and C, and their relative errors are similar
   (about 0.2-0.3). They become *unresolvable* with 16 384 shots earlier, because their signal is small; that is a statement about resolution, not about hardware fidelity. Near-zero κ is `inconclusive` by rule.
   The data are one patch with exact references and two windows, so no general ordering is claimed.
2. **Does classical approximation or hardware noise limit the trustworthy sizes and times?** On 18 qubits the classical methods are the more accurate ones (MPS chi 256 within 0.017 of exact to Jt = 5, using 1163 of the 1200 s
   budget), while the hardware median error is 0.03-0.06 and ZNE did not improve it; so hardware noise (and drift) is the limit there. At 24 qubits MPS stops converging within the budget beyond Jt = 2 and Pauli
   propagation is at 0.014-0.071, comparable to hardware. At 40 qubits no method is validated beyond Jt = 0.5 (MPS agrees across bond dimension to Jt = 1.0, which is stability, not validation), so the limit there is the missing reference.
3. **Trotter error.** Circuit vs exp(-iHt) <= 0.014 (P12, P18) and dt vs dt/2 <= 0.010 up to P24 at J·δt = 0.1, separate from classical truncation error and from hardware noise (all hardware comparisons use the fixed circuit).

What hardware supports: readout-corrected statistics agree with the exact fixed circuit within 0.05 for short evolution (Jt <= 0.4) and in a majority of 4-site cases later; one-site means and edge covariances exceed it in
about 40 % and 30 % of cases for Jt >= 0.4; ZNE adds nothing; a few qubits and pairs dominate the failures. **Not claimed:** quantum advantage, any statement beyond Jt = 0.5 at 40 qubits, any cause of the account-2 readout failure,
any ordering of classes beyond these numbers. See `LIMITATIONS.md`.
