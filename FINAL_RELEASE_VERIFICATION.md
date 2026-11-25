# Final release verification (outside the archive)

Recorded 2026-10-31 (UTC times). This file is deliberately not inside `TEAM-NWCZYG.zip`: an archive cannot contain the record of its own verification.

**Archive:** `TEAM-NWCZYG.zip`, 464 files, 9 524 242 bytes, SHA-256 `06e99dc9de5f5c993c1e503c098ac77d7cdffce1866778d1fc144426a15a13bf` (post-judging correction, 2026-11-25: README readout row and team table, compliance notes; supersedes `3841c2be…`, the archive judged on 2026-10-31, tag `judged-2026-10-31`), `ee890667…` and `ead45048…`) (identical for `dist/` and the repository root copy; the Release asset is uploaded from the same file).
**Environment:** Python 3.12 (fresh venv from `requirements.lock`), Linux.

| step | command | result |
|---|---|---|
| full tests in the repo | `python -m pytest -q` | PASS, exit 0 (`logs/pytest_final4.log`) |
| build | `python scripts/build_zip.py` | PASS: 464 files, 5 sanitized, no missing/forbidden |
| clean-room check of this exact archive | `scripts/verify_release.sh dist/TEAM-NWCZYG.zip` | PASS, exit 0, 2026-10-31 2026-11-25 06:24:56-06:32:55 UTC (`logs/verify_release8.log`; run with `UV_NO_CONFIG=1` because this machine's `/etc/uv/uv.toml` holds a key uv 0.9.18 rejects; no repository or config file was changed); full tests and offline reproduction |
| independent checker v2 | `python scripts/independent_checks_v2.py . <outdir>` | PASS 18/18 (archive equals repository for every non-log file) |
| home-path scan of text files in the zip | grep `/home/kushagrasingh` | 0 hits; no `.venv`, `.git`, `.env` |

Row gates (clean-room output): `results.csv` 15 108 rows (4 230 hardware), `resources.csv` 121 rows, `metadata.json` 18 keys; 2 115 drift comparisons (650 flagged) verified by the checker.
Frozen evidence: `evidence_hashes.csv` unchanged (68/68 match), supplementary `job_verification_hashes.csv` 2/2, pre-registration 39/39, approval sha `5360308738170cc5410562cb971a3050`; no change under `raw/`, `prereg/`, `configs/`.

NOT RUN (by design or scope): any IBM call or QPU job by the assistant; an independent 2 000-bootstrap recomputation from raw counts by a third party (the team's own deterministic re-run is recorded in `reports/REPRODUCIBILITY.md`); GitHub collaborator acceptance (organisers).
