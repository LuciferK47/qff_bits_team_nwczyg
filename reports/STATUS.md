# Project status: "When can we trust a quantum simulation?" (Problem B)

Date: 2026-10-31. Team: TEAM-NWCZYG. Target backend: `ibm_fez`. Hardware data exist for both accounts (28 circuits, 101 s each); analysis in `findings.md` §4 (ZNE failed its held-out gate; 31 % of matched estimates drift between the two windows; account 2's readout-independence gate failed on P18).
Offline data: exact numerics, classical approximations, FakeFez snapshot (offline, NOT live), and `simulated_noisy` runs (calibration-derived noise, not hardware). Hardware data: `raw/hardware/`.

## Decisions fixed
- **J·δt = 0.1** (frozen). δt = 0.2 results are kept only as exploratory under `raw/exploratory_dt0.2/`.
- Hard 20-minute wall-clock limit per (patch, method, setting) classical run.
- Organisers (2026-10-30): QPU time = each teammate's own free Open Plan account (10 min/month each); any backend/method allowed; mentor reviews after the
  answer is screened; a 100-minute reserve and a high-VRAM machine exist "if needed". Still unanswered: deadlines, upload location, outage fallback, job limits.
- Approval gate before any QPU job: pre-registration (typed, hash-tied approval, not a cryptographic signature) (hashes of policy, configs, analysis code, planned circuits) + both teammates' written approval.
  Account 1 = pilot + full manifest; account 2 = repeat of the identical manifest in a later calibration window (drift check).

## Done (offline sections; hardware is in findings.md §4; details in `validation.md`, `findings.md`, `audit_response.md`)
- Patches P12/P18/P24/P40 (all couplings kept); P40 is elongated (diameter 22, cycle rank 2); compact candidate P40c saved, **not benchmarked**.
- Full test suite (offline); mutation checks; circuit = numpy kernel = Aer (≤ 2e-15).
- Trotter error at δt = 0.1 ≤ 0.014 vs exp(−iHt), ≤ 0.010 dt-vs-dt/2 on P12/P18/P24.
- Classical benchmarks at δt = 0.1 with supervised budgets (MPS and Pauli propagation, all four patches); P40 exact reference only to Jt = 0.5, MPS χ-stable at Jt = 1.0, unreliable beyond.
- Simulated mitigation rehearsal (P12, CZ and assumed-fractional): model picked on Jt 0.4/1.0, validated on held-out Jt 0.8; readout-independence gate and correlated-readout control.
- Multi-gate trust policy v2; simulated rows can never be `supported`.
- Hardware dry run: 28 circuits in 3 jobs (7 pilot, 13 forward, 8 ZNE) compiled and gated (max 2q depth 150), estimated 99–180 s per account of the 600 s allocation.
- Approval-gated hardware code (`submit.py`: preregister, live-check, submit, fetch, analyse-hardware) tested with a fake service; executed by the teammates on their own accounts: 6 jobs, 56 circuit executions, 720 896 shots, 202 s.
- Hardware exported into `results.csv` (4 230 rows), `resources.csv` (6 jobs, 56 circuits) and `metadata.json`; hardware figures; readout, drift, class and estimator-bias analyses (`reports/*.csv`); frozen-evidence hash tests; read-only `verify-jobs`.
- Exports (`results.csv`, `resources.csv`, `metadata.json`) schema-validated; figures regenerated from saved data.

## Not done / NOT EXECUTED
- Cause of the account-2 readout-independence failure on P18 (not investigated); hardware at P40 beyond Jt 0.4 (no reference); any third calibration window.
- GPU work (exact P40 references beyond Jt = 0.5, higher-χ MPS): blocked on organiser access.
- P40c benchmark; optional echo experiment.
- Acceptance of the collaborator invitation by `AresTheWarGod42` (organisers).

## Release checklist (in order)
1. `pytest` (full) green. 2. `python scripts/reproduce_all.py`. 3. `python scripts/build_zip.py` → `dist/TEAM-NWCZYG.zip`. 4. `scripts/verify_release.sh` on a networked machine.
5. Hardware: done (`qtrust analyse-hardware --accounts 1,2`, findings §4). 6. Push; Release `final-submission` with `TEAM-NWCZYG.zip`.

## Known limits
- Classical results depend on my 20-minute budget and CPU hardware; longer budgets or a GPU would extend the confirmed ranges.
- Pauli propagation "fine" completes only 1–2 times before the limit; reported as `timed_out`, not as a physics failure.
- The simulated noise is independent and calibration-derived; mitigation validated there says the pipeline works, not that the device behaves that way.
- The gap-ratio excess (0.413 vs ≈ 0.39) is partly explained by mixing symmetry sectors (each sector 0.38–0.40); one system size only.
