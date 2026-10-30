# Project status: "When can we trust a quantum simulation?" (Problem B)

Date: 2026-10-30. Team: TEAM-NWCZYG. Target backend: `ibm_fez`. Account 1 hardware data exist (28 circuits, 101 s, `raw/hardware/account1/`); **their analysis and the account-2 repeat are not yet reported.**
All data are offline: exact numerics, classical approximations, FakeFez snapshot (offline, NOT live), and `simulated_noisy` runs (calibration-derived noise, not hardware).

## Decisions fixed
- **J·δt = 0.1** (frozen). δt = 0.2 results are kept only as exploratory under `raw/exploratory_dt0.2/`.
- Hard 20-minute wall-clock limit per (patch, method, setting) classical run.
- Organisers (2026-10-30): QPU time = each teammate's own free Open Plan account (10 min/month each); any backend/method allowed; mentor reviews after the
  answer is screened; a 100-minute reserve and a high-VRAM machine exist "if needed". Still unanswered: deadlines, upload location, outage fallback, job limits.
- Approval gate before any QPU job: signed pre-registration (hashes of policy, configs, analysis code, planned circuits) + both teammates' written approval.
  Account 1 = pilot + full manifest; account 2 = repeat of the identical manifest in a later calibration window (drift check).

## Done (all offline; details in `validation.md`, `findings.md`, `audit_response.md`)
- Patches P12/P18/P24/P40 (all couplings kept); P40 is elongated (diameter 22, cycle rank 2); compact candidate P40c saved, **not benchmarked**.
- 167 tests; mutation checks; circuit = numpy kernel = Aer (≤ 2e-15).
- Trotter error at δt = 0.1 ≤ 0.014 vs exp(−iHt), ≤ 0.010 dt-vs-dt/2 on P12/P18/P24.
- Classical benchmarks at δt = 0.1 with supervised budgets (MPS and Pauli propagation, all four patches); P40 exact reference only to Jt = 0.5, MPS χ-stable at Jt = 1.0, unreliable beyond.
- Simulated mitigation rehearsal (P12, CZ and assumed-fractional): model picked on Jt 0.4/1.0, validated on held-out Jt 0.8; readout-independence gate and correlated-readout control.
- Multi-gate trust policy v2; simulated rows can never be `supported`.
- Hardware dry run: 28 circuits in 3 jobs (7 pilot, 13 forward, 8 ZNE) compiled and gated (max 2q depth 150), estimated 99–180 s per account of the 600 s allocation.
- Approval-gated hardware code (`submit.py`: preregister, live-check, submit, fetch, analyse-hardware) tested with a fake service; I never run it.
- Exports (`results.csv`, `resources.csv`, `metadata.json`) schema-validated; figures regenerated from saved data.

## Not done / NOT EXECUTED
- Live check against `ibm_fez` (needs your account); fractional-gate availability unknown; fractional timing in the dry run is an **assumption**.
- Any hardware job; hardware analysis; class-by-class hardware trust map.
- GPU work (exact P40 references beyond Jt = 0.5, higher-χ MPS): blocked on organiser access.
- P40c benchmark; optional echo experiment.
- Clean-environment rebuild from the zip (`scripts/verify_release.sh` needs network for pinned wheels): run before submission.
- `configs/team.yaml` is filled with TEAM-NWCZYG (leading hyphen dropped; confirm).

## Release checklist (in order)
1. `pytest` (full) green. 2. `python scripts/reproduce_all.py`. 3. `python scripts/build_zip.py` → `dist/TEAM-NWCZYG.zip`. 4. `scripts/verify_release.sh` on a networked machine.
5. After hardware (if approved): `qtrust analyse-hardware --accounts 1,2`, update `findings.md` §4 with measured results only.

## Known limits
- Classical results depend on my 20-minute budget and CPU hardware; longer budgets or a GPU would extend the confirmed ranges.
- Pauli propagation "fine" completes only 1–2 times before the limit; reported as `timed_out`, not as a physics failure.
- The simulated noise is independent and calibration-derived; mitigation validated there says the pipeline works, not that the device behaves that way.
- The gap-ratio excess (0.413 vs ≈ 0.39) is partly explained by mixing symmetry sectors (each sector 0.38–0.40); one system size only.
