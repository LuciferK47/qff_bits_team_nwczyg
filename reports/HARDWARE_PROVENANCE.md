# Hardware provenance

What ran on a real quantum processor, when, under which approval, and what is (and is not) independently confirmed.

## Executed runs
Backend `ibm_fez` (156 qubits, fractional RZZ available, repetition delay 0.25 ms as read from the backend), SamplerV2 in **Batch** mode,
gate and measurement twirling off, dynamical decoupling off, no PEA/PEC (the IBM guide lists these as unsupported with fractional gates).
Two teammates each ran the **same logical manifest** (28 circuit executions in 3 jobs) on their own free Open Plan account.

| acct | job | IBM job id | submitted (UTC) | fetched (UTC) | executions | shots | estimate before submission (s) | reported usage (s) |
|---|---|---|---|---|---:|---:|---:|---:|
| 1 | 1_pilot | `dbi79j6ne4hc73be22d0` | 2026-10-30 10:43:24 | 2026-10-30 10:44:31 | 7 | 65 536 | 32.8 | 19 |
| 1 | 2_forward | `dbi7cc6ne4hc73be2600` | 2026-10-30 10:49:20 | 2026-10-30 10:51:51 | 13 | 163 840 | 45.0 | 45 |
| 1 | 3_zne | `dbi7e6ene4hc73be28b0` | 2026-10-30 10:53:13 | 2026-10-30 10:55:04 | 8 | 131 072 | 37.1 | 37 |
| 2 | 1_pilot | `dbip8mune4hc73bf3skg` | 2026-10-31 07:10:19 | 2026-10-31 07:11:50 | 7 | 65 536 | 32.8 | 19 |
| 2 | 2_forward | `dbip9io1h92s7383vpqg` | 2026-10-31 07:12:10 | 2026-10-31 07:13:25 | 13 | 163 840 | 45.0 | 45 |
| 2 | 3_zne | `dbipaa8hoj4c73b6nsg0` | 2026-10-31 07:13:44 | 2026-10-31 07:14:56 | 8 | 131 072 | 37.1 | 37 |
| | **total** | 6 jobs | | | **56** | **720 896** | 229.8 | **202** |

Total reported usage is **202 s**, against the 600 s team limit of the problem statement (and 10 min per Open Plan account). Account 1's live check ran at
2026-10-30 10:38:21 UTC, account 2's at 2026-10-31 07:03:13 UTC, so the two data sets are about 20 hours apart.
Estimates are the pre-submission values recorded in `jobs.json`: the pilot uses the problem statement's planning rate (0.5 ms per shot); the later two jobs use the
detailed time model rescaled by the pilot's measured usage (19 s). Usage is the value `job.usage()` returned when `qtrust fetch` saved it.

## Circuits
- Patches: **P18** (18 qubits, exact references available) and **P40** (40 qubits, 41 couplings, all kept). The physical qubits are identical on both accounts
  (`metadata.json` -> `hardware.accounts.*.live_check`). P18 uses physical qubits 16, 20-26, 36, 37, 40-46, 56.
- Per patch: four structured readout calibrations (all-0, all-1, two checkerboards of the bipartition), forward circuits at the frozen J·dt = 0.1,
  and for ZNE the folded circuits (fold 1 = 3x and fold 2 = 5x noise factor, barriers prevent cancellation). A CZ-compiled twin of P18 Jt 0.4 is kept only for the compilation comparison.
- Compiled on the **live** target of each account's window. The logical manifest is identical; the compiled binaries are not (their SHA-256 prefixes differ between
  accounts because the live calibration data differ). Per executed circuit: 2q gate count and depth in `resources.csv` (`hardware_circuit` rows); maximum compiled
  two-qubit depth **150** (ceiling 300). `tests/test_export.py` checks that fold 1 and fold 2 keep exactly 3x and 5x the two-qubit gates of the unfolded circuit.
- Compiled programs: `raw/hardware/account{1,2}/circuits/*.qpy` (QPY), hashes in `live_check.json` and `reports/evidence_hashes.csv`.

## Approval and pre-registration
Pre-registration `prereg/prereg.json` was created 2026-10-30 08:18:57 UTC and hashes the trust policy, configs, analysis code and the planned circuits
(`prereg_sha 5360308738170cc5410562cb971a3050`). `prereg/APPROVAL.md` carries the sha, both teammates' names and the date 2026-10-30; `qtrust submit`
refuses without it. All six jobs record this sha. The first hardware job was submitted two and a half hours after the pre-registration. The signed approval still
verifies today (`tests/test_evidence.py`), i.e. no pre-registered file changed after sign-off. Analysis and export code added later (`export`, `schema`, `figures`,
`hwanalysis`, `hwdata`, `verify`) is **not** pre-registered; it reads the frozen results and never alters a frozen verdict.

## Immutable evidence
`reports/evidence_hashes.csv` lists the SHA-256 of every file under `raw/hardware/account{1,2}/` and `prereg/` (68 files). `tests/test_evidence.py`
fails if any of them changes and re-derives 6 jobs / 56 executions / 720 896 shots / 202 s from the raw counts.

## What is and is not independently confirmed
- **Confirmed locally:** shot totals, label sets, hashes, usage sums, consistency of `results.csv` / `resources.csv` / `metadata.json` (tests).
- **Observed by the team on the IBM dashboard:** job `dbi79j6ne4hc73be22d0` shown as Completed on ibm_fez in Batch mode, 19 s usage (account 1 screenshot).
- **Confirmed against IBM's own records (2026-10-31):** each account owner ran the read-only `qtrust verify-jobs --account N`, which looks every archived job id up with their saved account and writes
  `raw/hardware/accountN/job_verification.json`. Result: all six jobs found, status `DONE`, backend `ibm_fez`, IBM-reported usage 19 / 45 / 37 s on both accounts, equal to the archived usage (account 1 checked 11:26:49 UTC,
  account 2 11:30:50 UTC). The files also carry IBM's created / running / finished timestamps. No credential is written to them. `metadata.json` records the verification state per account.
- **Calibration data at run time** are summarised by the live-check record (checked time, qubit count, couplings used, per-pair CZ error of the first pairs); the full backend
  properties were not archived.
