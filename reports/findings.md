# Findings: when can we trust each kind of statistic? (offline phase)

**Scope.** Everything here is offline: exact numerics, classical approximations, and noisy *simulation*. **No hardware data exist yet**, so no
statement below says anything about the real device. Numbers are measured values from `raw/` (details and commands in `reports/validation.md`).
Setting: Trotterised mixed-field Ising, J·δt = 0.1 (frozen), heavy-hex patches P12/P18/P24/P40 of ibm_fez (offline snapshot, not live).
Observable classes: m (1-site), M (mean m), C (2-site edge covariance), G (4-site raw), κ (4-site fourth cumulant).

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

## 3. Mitigation in simulation (P12, `simulated_noisy`; no hardware)
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

## 4. Hardware (account 1 only; measured on ibm_fez, 2026-10-30)
Pre-registered manifest (sha `5360308738170cc5410562cb971a3050`): 28 circuits in 3 jobs, 101 s measured QPU usage, all shots returned. Analysis:
`qtrust analyse-hardware --accounts 1 --B 2000` (`logs/analyse_hardware_acct1.log`, rows in `raw/hardware/hardware_results.csv`).
**Scope limits:** one account and one calibration window, so the cross-account drift gate has NOT been applied and every `supported` below is provisional;
the account-2 repeat has NOT been run. Exact references exist for P18 at Jt 0, 0.4, 0.8, 1, 2, 3 and for P40 only at Jt 0 and 0.4; P40 at larger Jt has no reference.

- **Raw and readout-corrected estimates.** Of the rows with an exact reference, 247 raw (and 275 readout-corrected, counting `supported` in the log) rows are `supported`. Fraction of `supported`
  (raw + readout rows together) falls with time: 200/270 at Jt 0, 160/270 at 0.4, then 41/90, 33/90, 44/90, 40/90 at Jt 0.8, 1, 2, 3 (P18 only from 0.8 on).
  P18 RMS error vs exact over all observables, raw / readout: m 0.104 / 0.093, C 0.074 / 0.079, G 0.041 / 0.035, κ 0.026 / 0.025, M 0.046 / 0.037.
  Readout correction changes these only slightly. Median |error| is about 0.02 at Jt 0.4 and 0.03–0.05 beyond, with worst cases up to 0.47 (Jt 1).
- **ZNE did not help on this hardware.** The model selected on calibration times Jt 0.4/1.0 was `linear`; on the held-out time Jt 0.8 its RMSE over all P18 rows
  was 0.118 versus 0.094 for the raw estimate, so it failed the pre-declared held-out check (`heldout_rmse_max 0.05`). Consequently **no ZNE row is `supported`**
  (0 of 135 selected-model rows). exp and richardson were not better (richardson was worst: held-out RMSE 0.19, errors up to 1.5 at Jt 1). In the rehearsal on simulated
  independent noise ZNE did help, so the simulation's noise model does not describe this device well for ZNE.
- **Readout independence gate** passed on all calibration pairs, so the independent-readout correction was admissible here.
- **Class pattern.** Smallest errors are for the 4-site classes (G, κ; RMS 0.03–0.04) and largest for the single-site m (0.09–0.10) and edge C (0.07–0.08). No class
  ranking beyond these numbers is claimed: one patch with exact references over the whole range, one calibration window.
- **P40.** The 40-qubit runs were measured, but exact references only cover Jt ≤ 0.5, so only Jt 0 and 0.4 can be checked. Beyond that, the hardware numbers are `no_reference`.
- **Not claimed:** any statement about the drift between accounts or days, and any hardware statement that depends on the account-2 repeat.

## 5. What we can honestly claim now
1. A validated, reproducible pipeline (circuits, exact references, classical baselines with honest resource limits, mitigation with held-out checks, multi-gate trust policy) exists and is tested.
2. On patches up to 24 qubits the tested classical methods reproduce the exact fixed-circuit statistics to ≤ 0.02 for Jt ≤ 2 (to Jt = 5 on P12, and on P18 only
   with MPS χ = 256, which used 1163 s of the 1200 s limit). Beyond Jt = 2 on P24 none did within the limit. Hardware results in the validated window should be
   compared against the exact reference, not a classical guess.
3. On P40, classical numbers are exact only to Jt = 0.5, stable to Jt = 1.0 and unreliable beyond; hardware at P40 Jt ≥ 2 would have **no trusted reference**.
4. We make **no claim** about whether the quantum device is more or less trustworthy than the classical methods until hardware data are analysed.
