# Hardware manifest

> **Historical pre-submission plan (dry run, FakeFez target, 2026-10-30 morning).** The jobs were later executed on the live `ibm_fez` target; see the
> section "Executed" at the end and `reports/HARDWARE_PROVENANCE.md`. The plan below is kept unchanged as the record of what was pre-registered.


* frozen J*dt = **0.1**, shots 16384 per forward/ZNE circuit, 4096 per calibration circuit
* data source: **FakeFez snapshot (offline, NOT live)** — not a live backend
* fractional RZZ/RX added to the FakeFez target with CZ/SX calibration as an ASSUMPTION (offline, not live); verify with service.backend(name, use_fractional_gates=True)
* gates enforced at build time: ISA valid, measurement map, compiled 2q depth <= 300 (flag > 250, aim <= 100)

## QPU usage estimates (seconds; estimates only, replaced by `job.usage()` after the pilot)

| job | executions | detailed model | IBM quick rule | PDF 0.5 ms/shot |
|---|---:|---:|---:|---:|
| 1_pilot | 65536 | 18.6 | 24.9 | 32.8 |
| 2_forward | 163840 | 43.9 | 59.3 | 81.9 |
| 3_zne | 131072 | 36.3 | 47.9 | 65.5 |

Total (detailed / PDF-rate): 99 s / 180 s of a 600 s allocation (cap 420 s).

## Circuits

| job | circuit | variant | shots | n_2q | depth_2q | duration_us | isa_ok | measure_map_ok | low_headroom | qpy_sha |
|---|---|---|---|---|---|---|---|---|---|---|
| 1_pilot | P18_cal0 | cz | 4096 | 0 | 0 | 1.6 | True | True | False | fd8ae99605c4a2d8 |
| 1_pilot | P18_cal1 | cz | 4096 | 0 | 0 | 1.6 | True | True | False | c2a7c0b772901242 |
| 1_pilot | P18_cal2 | cz | 4096 | 0 | 0 | 1.6 | True | True | False | 06babe1ddaded5cb |
| 1_pilot | P18_cal3 | cz | 4096 | 0 | 0 | 1.6 | True | True | False | 0bd8767b8d92a22d |
| 1_pilot | P18_Jt0.0_fractional | fractional | 16384 | 0 | 0 | 1.6 | True | True | False | 058a5d70182690f5 |
| 1_pilot | P18_Jt0.4_fractional | fractional | 16384 | 72 | 12 | 2.9 | True | True | False | 57b17e3c2c0d2253 |
| 1_pilot | P18_Jt0.4_cz | cz | 16384 | 144 | 24 | 4.6 | True | True | False | c46a36cf96e5f1e0 |
| 2_forward | P18_Jt0.8_fractional | fractional | 16384 | 144 | 24 | 4.2 | True | True | False | 8cd0ac743069c15b |
| 2_forward | P18_Jt1.0_fractional | fractional | 16384 | 180 | 30 | 4.8 | True | True | False | 573f2aa8fe6496e7 |
| 2_forward | P18_Jt2.0_fractional | fractional | 16384 | 360 | 60 | 8.1 | True | True | False | f58dae3f0e880168 |
| 2_forward | P18_Jt3.0_fractional | fractional | 16384 | 540 | 90 | 11.3 | True | True | False | 3f1f71148f537b77 |
| 2_forward | P40_cal0 | cz | 4096 | 0 | 0 | 1.6 | True | True | False | 5080fe89481d15c4 |
| 2_forward | P40_cal1 | cz | 4096 | 0 | 0 | 1.6 | True | True | False | 9856966f91acdadd |
| 2_forward | P40_cal2 | cz | 4096 | 0 | 0 | 1.6 | True | True | False | 62881f6128dfc8cc |
| 2_forward | P40_cal3 | cz | 4096 | 0 | 0 | 1.6 | True | True | False | c256e3325d22259e |
| 2_forward | P40_Jt0.0_fractional | fractional | 16384 | 0 | 0 | 1.6 | True | True | False | ff731e510f14e729 |
| 2_forward | P40_Jt0.4_fractional | fractional | 16384 | 164 | 12 | 2.9 | True | True | False | 079eaefe020219be |
| 2_forward | P40_Jt1.0_fractional | fractional | 16384 | 410 | 30 | 4.8 | True | True | False | f82af762b8ef2f44 |
| 2_forward | P40_Jt2.0_fractional | fractional | 16384 | 820 | 60 | 8.1 | True | True | False | 4f27d3d8b6306dcf |
| 2_forward | P40_Jt3.0_fractional | fractional | 16384 | 1230 | 90 | 11.3 | True | True | False | e145246406a9fcb4 |
| 3_zne | P18_Jt0.4_fold1 | fractional | 16384 | 216 | 36 | 5.4 | True | True | False | e919c74d32c44170 |
| 3_zne | P18_Jt0.4_fold2 | fractional | 16384 | 360 | 60 | 7.9 | True | True | False | 6237b04c144839f8 |
| 3_zne | P18_Jt0.8_fold1 | fractional | 16384 | 432 | 72 | 9.1 | True | True | False | 5d776e926f641ed4 |
| 3_zne | P18_Jt0.8_fold2 | fractional | 16384 | 720 | 120 | 14.0 | True | True | False | f63d797dfb3aedc3 |
| 3_zne | P18_Jt1.0_fold1 | fractional | 16384 | 540 | 90 | 10.9 | True | True | False | f88003be35cb06a3 |
| 3_zne | P18_Jt1.0_fold2 | fractional | 16384 | 900 | 150 | 17.1 | True | True | False | 07d3797d9360f065 |
| 3_zne | P40_Jt1.0_fold1 | fractional | 16384 | 1230 | 90 | 10.9 | True | True | False | bd48a27aaff9003c |
| 3_zne | P40_Jt1.0_fold2 | fractional | 16384 | 2050 | 150 | 17.1 | True | True | False | 45527000fcf14116 |

## Pre-submission checklist (historical; all steps were carried out, see "Executed")

1. Each teammate saves their own Open Plan credentials with `QiskitRuntimeService.save_account`; never in code or logs.
2. `qtrust live-check --account N`: `service.backend('ibm_fez', use_fractional_gates=True)`; recompile every circuit on the LIVE target, compare depths with this table, re-run all gates (stops if rzz is unavailable).
3. `qtrust preregister`, then BOTH teammates sign `prereg/APPROVAL.md` (names, date, current sha). The organisers said the mentor reviews after the answer is screened, so this pre-registration with typed approval replaces a pre-hardware mentor review.
4. Pilot job only (`qtrust submit --job 1_pilot`: P18 calibration + Jt 0, 0.4 in both compilations); `qtrust fetch`; the measured `job.usage()` rescales every later estimate; then 2_forward and 3_zne.
5. Account 2 repeats the identical frozen manifest in a later calibration window (drift check).

## Executed (2026-10-30 / 2026-10-31)
1. Each teammate saved their own Open Plan credentials locally; nothing was written to the repository.
2. `qtrust live-check --account N` passed on both accounts (ibm_fez, 156 qubits, fractional RZZ available, no compiled depth growth; 28 circuits recompiled on the live target, max 2q depth 150).
3. `qtrust preregister` (sha `5360308738170cc5410562cb971a3050`, 2026-10-30 08:18:57 UTC); both teammates typed their names into `prereg/APPROVAL.md` on 2026-10-30.
4. Account 1: pilot, forward, ZNE (10:43-10:55 UTC on 30 Oct). Account 2: identical logical manifest (07:10-07:15 UTC on 31 Oct).
5. Measured usage: 19 + 45 + 37 = **101 s per account, 202 s in total**, against the estimates of 114.9 s per account made before submission (table above is the earlier dry-run model: 99 s detailed / 180 s PDF rate).
   Per-job estimates, usage, job ids and per-circuit gate counts and depths: `resources.csv` (`hardware_job`, `hardware_circuit`), `reports/HARDWARE_PROVENANCE.md`.
