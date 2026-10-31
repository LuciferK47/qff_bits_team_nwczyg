# Limitations

What the results do **not** show, in the order a skeptical reader should check.

1. **ZNE failed on hardware.** The model chosen on calibration times (linear, Jt 0.4/1.0) has held-out RMSE 0.118 (account 1) and 0.096 (account 2) at Jt 0.8, worse than the
   raw estimate (0.094 / 0.077) and above the pre-declared 0.05 limit; exp and richardson did not rescue it, and switching model after seeing the data would be exploratory.
   The simulated rehearsal, where ZNE helped, does not describe this device. We did not measure the effective noise amplification of the folds, so even the 1x/3x/5x labels are nominal.
2. **Account 2 violates the readout-independence assumption on P18.** One physical pair (16-23, logical 0-4) has |z| = 6.66 against the pre-specified 4 (account 1 maximum 3.0).
   The excess sits in the all-zeros calibration state. This identifies *where*, not *why* (readout crosstalk, drift, imperfect preparation or something else). Per-pair
   correction is exploratory and cannot fix an arbitrary four-site cumulant with overlapping correlated errors; the frozen verdicts were not changed.
3. **Drift between the two windows is large and only partly explained.** 650 of 2 115 matched estimates differ by more than 4 shot-noise standard errors. These
   comparisons share circuits, times and calibrations (they are strongly correlated), so 31 % is not a probability of failure and the count is not 650 independent tests. The standard
   errors contain shot noise only, so they understate time-dependent systematics. The two largest drift z-scores (|z| = 69 and 63) are in the Jt = 0 circuits (raw P40, qubit 38: m = 0.98 on account 1 vs 0.52 on account 2, and the four-site
   G containing it); a Jt = 0 circuit has no entangling gates, which points to readout or state preparation of that qubit, not to the dynamics.
4. **Reliability rankings from `supported` fractions are confounded** by the readout gate (account 2 P18 can never be `supported`), the drift demotion and the absolute
   0.05 tolerance. The class comparison therefore reports error, signal size and interval width side by side (`reports/hardware_class_table.csv`) and counts what a predictor that
   always answers 0 would achieve. It supports statements about *this device, these two windows and this tolerance*, not a general ordering of one-site against four-site statistics.
5. **The 0.05 hardware and 0.02 classical tolerances are team policy choices**, not universal trust criteria.
6. **P40 is a narrow heavy-hex patch** (40 qubits, 41 couplings, 2 independent cycles, diameter 22, cut width 4): friendly to one-dimensional tensor-network orderings and not
   evidence of generic two-dimensional difficulty. Exact references exist only to Jt = 0.5; MPS results agree across bond dimension to Jt = 1.0 (stability, not validation);
   beyond that nothing is validated, so hardware vs classical disagreement there says nothing about which is right. A more compact 40-qubit candidate (P40c) was found but not benchmarked.
7. **Classical timing is machine- and budget-specific** (laptop CPU, 20 min hard limit per run). A timeout is not evidence of intrinsic hardness, and the work cited in `FINAL_SCIENTIFIC_REPORT.md`
   shows that specialised classical methods can reproduce hardware experiments that looked out of reach. We claim no quantum advantage.
8. **The reference for hardware is the fixed Trotter circuit at J·dt = 0.1, not exp(-iHt).** The Trotter error (<= 0.014 on P12/P18, dt vs dt/2 <= 0.010 to P24) is a small-patch
   result and is not a bound for P40.
9. **Statistical intervals are shot noise (plus calibration resampling) only.** They do not contain drift, correlated readout, or the calibration changing between the
   calibration circuits and the forward circuits.
10. **Not done:** the optional disturbance-spreading (echo) extension; any GPU run; the P40c benchmark; a third calibration window; a full backend-properties archive.
11. **Job verification scope:** IBM's records confirm that the six job ids exist, completed on ibm_fez and report the archived usage (`job_verification.json`, run by each account owner). They do not
    re-verify the measurement counts themselves, which are the values saved by `qtrust fetch`.
12. **Repository access:** the collaborator invitation for `AresTheWarGod42` is pending acceptance by the organisers.
13. **AI assistance:** an AI assistant wrote most of the code, tests and draft reports; the authors directed the work, ran the hardware and signed the approval. Every check is a re-runnable test.
