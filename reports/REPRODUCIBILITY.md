# Reproducibility

Everything below runs offline from the saved data. **No IBM account, credential, network access or QPU time is needed**, and `scripts/reproduce_all.py`
blocks sockets while it runs.

## Environment (Python 3.12)
```bash
uv venv --python 3.12 .venv
VIRTUAL_ENV=.venv uv pip sync requirements.lock      # pinned, binary wheels only
VIRTUAL_ENV=.venv uv pip install -e .
```
(Windows, PowerShell: `py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1; python -m pip install -r requirements.lock; python -m pip install -e .`;
if a pinned wheel is missing for the platform use `requirements.in`.) Package versions of the run that produced the data are recorded in `metadata.json`.

## One command: tables, metadata and every figure
```bash
python scripts/reproduce_all.py
```
Expected output (the counts are checked by tests):

| file | content | expected |
|---|---|---|
| `results.csv` | exact references, classical approximations, simulated-noise rehearsal, **hardware** | 15 108 rows (10 878 offline + 4 230 hardware), 23 columns |
| `resources.csv` | classical runs, compile dry run, pre-submission estimates, **6 hardware jobs, 56 hardware circuits** | 121 rows |
| `metadata.json` | frozen Hamiltonian and step, seeds, versions, patches, policy, hardware provenance, job ids | 18 keys, 6 job ids, `qpu` = "executed: 6 jobs / 56 circuit executions ..." |
| `figures/*.png` | classical, simulated, **hardware** and control figures | regenerated from `raw/`, `reports/` |

Running it twice gives identical scientific columns (`tests/test_export.py::test_export_is_deterministic_in_its_scientific_columns`; only the creation timestamp in `metadata.json` changes).
`source` in `results.csv` separates `exact_numerics`, `classical_approximation`, `simulated_noisy` and `hardware`; simulated rows can never be `supported`.

## Tests
```bash
python -m pytest            # offline; includes the frozen-evidence, export-consistency and hardware-analysis checks
```
`tests/test_evidence.py` re-hashes every raw hardware file and the pre-registration/approval hash and re-derives 6 jobs / 56 executions / 720 896 shots / 202 s;
`tests/test_export.py` checks that the 4 230 hardware rows in `results.csv` equal `raw/hardware/hardware_results.csv` row by row and that results, resources and metadata agree;
`tests/test_verification_evidence.py` checks the supplementary ledger of the two IBM verification files, that no non-finite estimate is `supported`, and that this document names a current clean-room log;
`tests/test_hwanalysis.py` reproduces the numbers quoted in the reports (held-out RMSEs, the readout pair 16-23 diagnostic, drift counts).

## Clean-room check
```bash
python scripts/build_zip.py                      # dist/TEAM-NWCZYG.zip (no credentials, no .venv)
scripts/verify_release.sh dist/TEAM-NWCZYG.zip   # unzip, fresh venv from the lock, full tests, offline reproduction (needs network only to install wheels)
```
The latest clean-room log is `logs/verify_release3.log` (full hardware build: 15 108 results rows, 121 resources rows, 18 metadata keys, exit 0). `logs/verify_release.log` and `verify_release2.log` are
older offline-only builds, kept as history. A clean-room run cannot be recorded inside the archive it verifies, so the run on the exact final archive (command, exit code, SHA-256 of the zip) is recorded outside it
in `FINAL_RELEASE_VERIFICATION.md` at the repository root.

## Regenerating the hardware analysis from the raw counts
```bash
python -m qtrust.cli analyse-hardware --accounts 1,2 --B 2000      # reads raw/hardware, writes hardware_results.csv + drift table
python -c "from qtrust import hwanalysis as H; H.run_all()"         # readout diagnostic, class table, held-out ZNE, drift cases, estimator bias
```
These use the pre-registered analysis code and a fixed bootstrap seed. They take on the order of an hour on a laptop CPU. Checked on 2026-10-31: re-running `analyse-hardware --accounts 1,2 --B 2000`
from the raw counts into a scratch copy reproduced all 4 230 rows of `hardware_results.csv` (same columns, values equal within 1e-9, identical trust statuses) and all 2 115 drift comparisons (identical drift flags).
The `qtrust submit`, `fetch`, `live-check` and `verify-jobs` commands contact IBM and are **not** part of reproduction.

## What is not reproducible offline
The hardware counts themselves (they are the data), the IBM-side confirmation of the job ids (`qtrust verify-jobs`, run by the account owners), and the
wall-clock times of the classical benchmarks (they depend on the CPU, recorded per run in `resources.csv`).
