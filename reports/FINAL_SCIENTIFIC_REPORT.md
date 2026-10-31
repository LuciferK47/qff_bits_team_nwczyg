# When can we trust a quantum simulation? Final report (TEAM-NWCZYG)

## Abstract
We simulate Trotterised mixed-field Ising dynamics (J = 1, hx = 1.25, hz = -0.60, start |0...0>, J·δt = 0.1) on connected heavy-hex patches of `ibm_fez` (12, 18, 24, 40 qubits),
validate the circuit against independent exact numerics, benchmark two classical approximations (MPS, Pauli propagation) under a hard 20-minute budget, and run the same pre-registered
28-circuit manifest on the real device from two independent accounts about 20 hours apart (6 jobs, 720 896 shots, 202 s of QPU time). We report raw, readout-corrected and zero-noise-extrapolated
estimates of one-, two- and four-site statistics with bootstrap intervals and a multi-gate trust verdict. Main results: (i) the fixed circuit is validated (Trotter error <= 0.014, circuit = Aer = numpy kernel to 2e-15);
(ii) on 18 qubits classical MPS is more accurate than the hardware, so hardware noise is the binding limit there; at 40 qubits nothing is validated beyond Jt = 0.5;
(iii) **ZNE failed its pre-declared held-out check on both accounts** (selected model RMSE 0.118 / 0.096 vs raw 0.094 / 0.077); (iv) the two windows disagree beyond shot noise for 31 % of the matched estimates, and one physical
pair violates the readout-independence assumption in the second window; (v) four-site statistics are not less accurate than one-site means on P18, but become unresolvable at 16 384 shots earlier because their signal is small.
We claim no quantum advantage.

## 1. Fixed circuit and graph
Patches are connected subgraphs of the `ibm_fez` coupling map (all selected couplings kept, open boundaries): P12 (12 qubits, tree), P18 (18), P24 (24), P40 (40 qubits, 41 couplings, 2 independent cycles, diameter 22: elongated, a weak test of 2-D difficulty).
`H = -J Σ Z_i Z_j - Σ (hx X_i + hz Z_i)`, one step `S(δt) = F(δt/2) B(δt) F(δt/2)` with exact single-qubit field gates (adjacent halves merged), `RZZ(-2Jδt)` per edge, edges scheduled in 3 colour layers; `U_N = S^N`.
Checks (tests): both signs of hx and hz, bond sign vs `expm`, bit order (X on one qubit), N = 0 identity (m = G = 1, C = κ = 0), U†U|0>=|0>, merged vs unmerged halves, and mutation checks (flipping a sign makes tests fail).
Observables fixed before any hardware data: every m_i, M, every edge C_ij, and 3-4 four-site clusters (centre plus three neighbours) for G and κ; κ uses all 15 subset moments (two independent formulas).

## 2. Exact references and time step
J·δt = 0.2 (the statement's start value) gave a worst error 0.055 > 0.02, so **J·δt = 0.1 was frozen** (0.2 results kept apart as exploratory). Fixed circuit vs exp(-iHt) (sparse `expm_multiply`) <= 0.0139 on P12/P18;
δt vs δt/2 <= 0.0104 up to P24; Aer vs kernel <= 2e-15. These are small-patch evidence, not a bound for P40. Level statistics at the table parameters ⟨r⟩ = 0.52 (statement: about 0.53); the hz = 0 chain 0.413 full spectrum, 0.38-0.40 inside symmetry sectors (`validation.md` §3).
Reversing hz changes M(t) on P12 by up to 0.71 (`figures/hz_reversal_P12.png`). Hardware is compared with the **fixed circuit**, so Trotter error is separate from classical truncation and from noise.

## 3. Classical approximation
MPS (quimb, χ 32-256) and sparse Pauli propagation (coarse/medium/fine), each run in a supervised child process with a hard 1200 s limit, whole-process-tree memory sampling and per-time checkpoints (`resources.csv`).
P12: MPS exact to display precision for χ >= 64. P18: χ256 within 0.017 of exact to Jt = 5 (1163 s of 1200 s). P24: MPS χ >= 128 times out beyond Jt = 2; Pauli medium 0.014-0.071 at Jt 3-5. P40: exact light-cone reference only
to Jt = 0.5; MPS agrees across χ to 1e-4 at Jt = 1.0 (stability, not validation) and disagrees (0.058 between χ32 and χ64) at Jt = 2. Timeouts are reported as such. This is a statement about our CPU and budget, not about intrinsic hardness.

## 4. Hardware protocol
Backend `ibm_fez`, fractional RZZ via the live target, SamplerV2 Batch, twirling and dynamical decoupling off (IBM lists Pauli twirling, PEA-based ZNE and PEC as unsupported with fractional gates; TREX is supported), 16 384 shots per forward/folded circuit and 4 x 4096 shots of structured
readout calibration per patch. P18 forward at Jt 0, 0.4, 0.8, 1, 2, 3; P40 at 0, 0.4, 1, 2, 3; ZNE by **manual** global folding (fold 1 and 2 carry 3x and 5x the two-qubit gates, barriers preserve the pairs; the factors 3 and 5 are **nominal**: the effective noise amplification was not measured) on P18 at Jt 0.4/0.8/1.0 and P40 at 1.0.
Maximum compiled two-qubit depth 150 (ceiling 300). Pre-registration (policy, configs, analysis code, circuits; sha `5360308738170cc5410562cb971a3050`) and a two-person typed approval tied to that hash (not a cryptographic signature) preceded every job; a pilot job fixed the usage rate.
Details, job ids and times: `HARDWARE_PROVENANCE.md`.

## 5. Mitigation and uncertainty
Readout: independent asymmetric per-qubit assignment errors from four structured calibrations, corrected moments (never clipped), with an independence z-test on every coupled pair. ZNE: models linear / Richardson / exponential, model selected on
Jt 0.4 and 1.0 by a rule fixed in code, validated at the unused Jt 0.8, disqualified if > 5 % of fits fail. Intervals: joint multinomial bootstrap (B = 2000) of every block including calibration and folds, recomputing all moments together; an interval is reported only
if >= 99 % of replicates are finite. Verdict (`supported` / `inconsistent` / `inconclusive` / `mitigation_failed` / `no_reference`) needs a reference, a finite estimate, a resolved signal, agreement within 0.05 and passing systematics (readout gate, held-out ZNE, cross-account drift); simulated data are never `supported`.
Estimator check on the exact distribution: bias <= 0.0013, bootstrap coverage 0.83-0.98 (30 replicates per observable, so each value is uncertain by about ±0.05).
The 95 % intervals contain shot noise and calibration resampling only and are conditional on a stationary, per-qubit readout model; they do not cover drift, correlated readout or the uncertainty of the ZNE noise factor.
Estimator health (`ESTIMATOR_HEALTH.md`): 69 of 4 230 hardware estimates are non-finite (37 `mitigation_failed`, 32 `no_reference`, all exponential-ZNE sign-change fits) and 30 more have a finite estimate but no interval; "no validated reference" and "estimator failed" are independent axes and the frozen statuses are unchanged.

## 6. Results
Held-out ZNE, readout, drift, class accuracy and P40: see `findings.md` §4 with figures `hardware_*.png`. Key numbers:
- Held-out RMSE (P18, Jt 0.8, 45 observables), account 1 / 2: raw 0.094 / 0.077; readout 0.092 / 0.085; selected linear ZNE 0.118 / 0.096; limit 0.05 (exponential 0.095 / 0.107 is over only 36 / 38 of the 45 observables with a finite fit and is not comparable).
- Readout independence: account 2, P18, physical pair 16-23 (logical 0-4), z = +6.66 against the pre-specified 4; account 1 maximum 3.00.
- Drift: 650 of 2 115 matched estimates beyond 4 shot-noise SEs (correlated comparisons; account and calibration window are confounded, so this is drift between windows ~20 h apart, not an effect of the account); largest z-scores in Jt = 0 circuits; median absolute difference 0.027.
- P18 readout-corrected, Jt >= 0.4, within 0.05 of exact: m 0.61, C 0.69, G 0.85, κ 0.93 (always-0 predictor: 0.33, 0.20, 0.20, 0.60); RMSE 0.100 / 0.073 / 0.037 / 0.025.
- Resources: 6 jobs, 202 s reported usage of 600 s, 56 executions, 720 896 shots.

## 7. Answers to the three questions (this device, these windows, these patches, our tolerances)
1. *Four-site before one-site?* Not in accuracy; earlier in resolvability (κ signal 0.001-0.03 vs interval half-width 0.015). No general ordering is claimed.
2. *Classical approximation or hardware noise?* 18 qubits: hardware noise (MPS χ256 <= 0.017 to Jt = 5 vs hardware median error 0.03-0.06; ZNE did not help). 24 qubits: comparable. 40 qubits: neither is validated beyond Jt = 0.5.
3. *Trotter error vs approximation error vs noise:* <= 0.014 vs the continuous-time evolution on small patches, separate from truncation (<= 0.017 for P18 MPS χ256) and from hardware error (median 0.03-0.06).

## 8. Literature context (sources checked 2026-10-31)
- IBM Quantum documentation, *Fractional gates*: RZZ angles 0 < θ <= π/2; Pauli twirling, PEA-based ZNE and PEC unsupported with fractional gates; measurement twirling (TREX) supported; manual folding is not discussed, so our manual folds are assessed on our own compiled circuits (https://quantum.cloud.ibm.com/docs/en/guides/fractional-gates).
- IBM Quantum documentation, *Estimate job run time*: usage is the time the QPU is locked to execute a workload, read with `job.usage()` (https://quantum.cloud.ibm.com/docs/en/guides/estimate-job-run-time).
- Kim et al., *Evidence for the utility of quantum computing before fault tolerance*, Nature 618 (2023), https://www.nature.com/articles/s41586-023-06096-3: Ising dynamics with error mitigation on IBM hardware; different circuits and observables, so no numbers are transferred.
- Begušić, Gray and Chan, *Fast and converged classical simulations of evidence for the utility of quantum computing before fault tolerance*, Science Advances 10, eadk4321 (2024): approximate classical methods (sparse Pauli dynamics, tensor networks) reproduced that experiment; this is why a classical timeout or a disagreement with noisy hardware is not treated as quantum advantage here.
- Tindall, Fishman, Stoudenmire and Sels, *Efficient tensor network simulation of IBM's Eagle kicked Ising experiment*, PRX Quantum 5, 010308 (2024): geometry-aware belief-propagation tensor networks; one reason why we do not equate "40 qubits" with classical hardness and state P40's narrow geometry.
- Koenig, Reinecke, Hahn and Wellens, *Inverted-circuit zero-noise extrapolation for quantum-gate error mitigation*, Phys. Rev. A 110, 042625 (2024): the actual noise-scaling factor of an amplified circuit is the main difficulty of ZNE; our fold factors are nominal, which is one candidate explanation for the failure, not a diagnosis.
- Software: IBM `pauli-prop` (https://github.com/Qiskit/pauli-prop), `quimb` (https://github.com/jcmgray/quimb), Qiskit, Qiskit Aer, qiskit-ibm-runtime, pinned in `requirements.lock`.
Community pages (Kaggle mapping competition, Reddit threads) were read and not used as evidence: the competition concerns qubit placement, not these dynamics, and the threads are anecdotal.

## 9. Limitations
`LIMITATIONS.md`. Reproduction: `REPRODUCIBILITY.md`. Requirement-by-requirement evidence: `SUBMISSION_COMPLIANCE.md`.
