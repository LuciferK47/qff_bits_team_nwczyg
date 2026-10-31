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

## 4. Hardware (two accounts, ibm_fez; measured 2026-10-30 and 2026-10-31)
Pre-registered manifest (sha `5360308738170cc5410562cb971a3050`): 28 circuits in 3 jobs per account, 101 s measured QPU usage each, all shots returned.
Account 1 ran on 30 Oct 10:43 UTC, account 2 (identical manifest, run by the second teammate on their own account) on 31 Oct 07:10 UTC, about 20 h later.
Analysis: `qtrust analyse-hardware --accounts 1,2 --B 2000` (`logs/analyse_hardware_acct12.log`; rows in `raw/hardware/hardware_results.csv`, drift in
`raw/hardware/drift_account2_vs_1.csv`). Exact references exist for P18 at Jt 0, 0.4, 0.8, 1, 2, 3 and for P40 only at Jt 0 and 0.4; P40 at larger Jt is `no_reference`.
The account-1-only analysis written earlier is superseded by this section. Everything is one device and two calibration windows.

- **Drift between the two windows is real.** Of 2 115 matched estimates, 650 (31 %) differ by more than 4 standard errors (median |z| 2.35, max 68.6). The absolute
  differences are modest (median 0.027; by class: m 0.039, M 0.024, C 0.022, G 0.023, κ 0.013; largest 1.43). The standard errors are shot-noise bootstrap
  errors only, so they understate window-to-window variation. By pre-declared rule these rows are demoted from `supported` to `inconclusive`.
  Flagged share by method: raw 243/720, readout 213/720, ZNE exp 49/225, linear 94/225, richardson 51/225.
- **Readout independence gate.** Passed for account 1 on all circuits. For **account 2 it failed on every P18 circuit** (it passed on P40). Independent-readout
  correction is therefore not admissible for account 2's P18 data under our own rule, and those rows cannot be `supported`. We did not investigate which qubit pair triggered it.
- **ZNE did not help, on either account.** The model selected on calibration times Jt 0.4/1.0 was `linear` on both. Held-out (Jt 0.8, P18, all observables) RMSE for account 1 / account 2:
  raw 0.094 / 0.077, readout 0.092 / 0.085, linear 0.118 / 0.096 (selected), exp 0.095 / 0.107, richardson 0.191 / 0.083. The selected model is worse than the unmitigated estimate on both
  accounts and above the pre-declared limit (0.05), so **no ZNE row is `supported`** (0 on both accounts). The simulated rehearsal, where ZNE helped, does not describe this device for ZNE.
- **Raw and readout-corrected, after the drift and independence demotions.** `supported` raw / readout rows: account 1 192 / 225 (down from 247 / 271 before the drift check), account 2 89 / 103.
  Pooled over both accounts and both methods (rows with an exact reference), the `supported` fraction falls with evolution time: 269/540 at Jt 0, 224/540 at 0.4, then 32/180, 23/180, 32/180, 29/180 at Jt 0.8, 1, 2, 3
  (P18 only from Jt 0.8). By class: C 311/760, m 228/752, G 42/128, κ 26/128, M 2/32. These fractions mix patches and times and are not a ranking of how hard each class is.
  RMS error vs exact, raw (account 1 / 2): 0.076 / 0.066; readout-corrected 0.072 / 0.055.
- **P40.** Measured, but references exist only at Jt ≤ 0.4, so nothing beyond that is validated.
- **What this supports:** unmitigated or readout-corrected hardware statistics on P18/P40 agree with exact references within the policy tolerance for short evolution (Jt ≲ 0.4) and in a
  minority of cases at Jt ≥ 0.8; after the drift check no hardware statistic at Jt ≥ 0.8 is `supported` in most cases, and ZNE adds nothing. **Not claimed:** any longer-time or P40 result,
  any cause of the account-2 readout failure, and any generalisation beyond this device and these two windows.

## 5. What we can honestly claim now
1. A validated, reproducible pipeline (circuits, exact references, classical baselines with honest resource limits, mitigation with held-out checks, multi-gate trust policy) exists and is tested.
2. On patches up to 24 qubits the tested classical methods reproduce the exact fixed-circuit statistics to ≤ 0.02 for Jt ≤ 2 (to Jt = 5 on P12, and on P18 only
   with MPS χ = 256, which used 1163 s of the 1200 s limit). Beyond Jt = 2 on P24 none did within the limit. Hardware results in the validated window should be
   compared against the exact reference, not a classical guess.
3. On P40, classical numbers are exact only to Jt = 0.5, stable to Jt = 1.0 and unreliable beyond; hardware at P40 Jt ≥ 2 would have **no trusted reference**.
4. We make **no claim** about whether the quantum device is more or less trustworthy than the classical methods until hardware data are analysed.
