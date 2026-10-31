# qtrust — When can we trust a quantum simulation?

Validated Trotterised mixed-field Ising dynamics on IBM heavy-hex device patches:
`H = -J Σ_E Z_i Z_j - Σ_i (h_x X_i + h_z Z_i)`, `J=1, h_x=1.25, h_z=-0.60`, start `|0…0⟩`,
second-order split `U_N = S(δt)^N`, `S = F(δt/2) B(δt) F(δt/2)` (BITS Goa × IBM Qiskit Fall Fest, Problem B).

## One-paragraph summary
We validate the fixed Trotter circuit exactly (Trotter error <= 0.014, circuit = Aer = independent kernel), benchmark MPS and Pauli propagation under a hard 20-minute budget, and run the same pre-registered
28-circuit manifest on `ibm_fez` from two independent accounts about 20 h apart (6 jobs, 720 896 shots, **202 s** of QPU time). Findings: **ZNE failed its pre-declared held-out check on both accounts**
(selected model RMSE 0.118 / 0.096 vs raw 0.094 / 0.077); 31 % of matched estimates drift beyond shot noise between the windows and one physical pair (16-23) violates the readout-independence assumption in the second window;
on 18 qubits classical MPS is more accurate than the hardware; at 40 qubits nothing is validated beyond Jt = 0.5; four-site statistics are not less accurate than one-site means but become unresolvable at 16 384 shots earlier. No quantum advantage is claimed.
Start with `reports/FINAL_SCIENTIFIC_REPORT.md`; requirement-by-requirement evidence is in `reports/SUBMISSION_COMPLIANCE.md`, limits in `reports/LIMITATIONS.md`, reproduction in `reports/REPRODUCIBILITY.md`, hardware records in `reports/HARDWARE_PROVENANCE.md`.
`results.csv` (15 108 rows), `resources.csv` and `metadata.json` include the hardware data; `raw/hardware/` holds the lossless counts and compiled circuits.

> **Status (31 Oct 2026).** Offline pipeline at the frozen **J·δt = 0.1**; hardware executed after a signed pre-registration (sha `5360308738170cc5410562cb971a3050`) and passing live checks;
> analysis in `reports/findings.md` §4. Offline data come from the `FakeFez` snapshot (labelled *offline, NOT live*); noisy-simulation results are labelled `simulated_noisy` and can never be `supported`.
> IBM-side confirmation of the job ids is recorded by `qtrust verify-jobs` (read-only, run by each account owner) and is **not** implied by this repository alone.

## Team
**TEAM-NWCZYG** (BITS Pilani, Goa Campus × IBM Qiskit Fall Fest 2026, Advanced track, Problem B):

| member | QFF registration ID | email |
|---|---|---|
| Kushagra Singh (team leader) | QFF-D63728 | offkushagrasingh47@gmail.com |
| Krutiksinh Narendrasinh Rana | QFF-591869 | Knrana08@gmail.com |

GitHub accounts that committed to this repository: `LuciferK47` (repository owner), `Krut27`.

## What is the quantum-computing component?
The object under study is a Trotterised quantum many-body circuit (mixed-field Ising model on IBM heavy-hex qubit patches). The project asks
for which statistics (1-, 2- and 4-site) a noisy quantum computation can be trusted, by comparing exact references, classical approximations
(MPS, sparse Pauli propagation), noisy simulation with readout correction and zero-noise extrapolation, and, if approved and executed, runs on an
IBM Quantum backend. Hardware is a gated add-on: the repository reports only what was actually run.

## Pre-existing versus hackathon work
- **Written during the hackathon (29–31 Oct 2026), by the team with AI assistance (Claude):** everything under `src/`, `tests/`, `scripts/`, `configs/`,
  `reports/`, plus the saved results in `raw/`, `figures/` and the exported `results.csv`, `resources.csv`, `metadata.json`. No source code in this
  repository pre-dates the hackathon.
- **Third-party, used under their licences, not modified:** Qiskit, Qiskit Aer, qiskit-ibm-runtime (incl. `FoldRzzAngle`, `FakeFez`), `pauli-prop` (IBM),
  `quimb`, numpy, scipy, pandas, networkx, matplotlib, pytest (pinned in `requirements.lock`).
- **Provided by the organisers:** the problem statement (Problem B) and the offline `FakeFez` backend snapshot data shipped with qiskit-ibm-runtime.

## Setup (Python 3.12)
```bash
uv venv --python 3.12 .venv
VIRTUAL_ENV=.venv uv pip sync requirements.lock      # pinned, binary wheels only
VIRTUAL_ENV=.venv uv pip install -e .
.venv/bin/python -m pytest                           # all tests are offline
```
`mthree` was dropped from the environment: 2.8.1 imports `BackendV1`, which Qiskit 2.x removed. Readout correction is
implemented in `src/qtrust/mitigation.py` (and unit-tested against explicit assignment-matrix inversion).

## Commands
Offline:
| command | what it does |
|---|---|
| `python -m qtrust.cli patches` | build P12/P18/P24/P40 from the FakeFez snapshot, save JSON + drawings |
| `python scripts/run_classical.py PID --budget 1200 [--pauli ...] [--chi ...] [--Ns ...] [--ref-Ns ...]` | supervised Pauli-propagation and MPS benchmark vs exact (hard budget per run) |
| `python -m qtrust.cli exact --patches P12,P18 [--halving]` | exact fixed-circuit tables, Trotter-error and Aer checks at the frozen dt |
| `python -m qtrust.cli rehearsal --patch P12` | noisy-Aer dress rehearsal: readout correction + ZNE (held-out) + bootstrap + trust status |
| `python -m qtrust.cli manifest` | compile every planned hardware circuit, ISA/depth gates, usage estimate (**dry run**) |
| `python scripts/reproduce_all.py` | regenerate `results.csv`, `resources.csv`, `metadata.json` and every figure from saved data under `raw/` |
| `scripts/run_queue.sh` | the sequential offline queue used to produce the saved results |

Analysis of the saved hardware data (offline): `python -m qtrust.cli analyse-hardware --accounts 1,2 --B 2000` (pre-registered pipeline) and
`python -c "from qtrust import hwanalysis as H; H.run_all()"` (post-hoc diagnostics: readout independence per pair, class table, held-out ZNE, drift cases, estimator bias).

Contact IBM Quantum (run by a human, only after the approval gate below): `preregister`, `live-check --account N`,
`submit --account N --job {1_pilot,2_forward,3_zne}`, `fetch --account N`, and the read-only `verify-jobs --account N`
(records IBM's own status and usage for the archived job ids).

## Layout
`src/qtrust/` — `graph` (patches, edge colouring, light cones), `circuits`, `exact` (independent numpy kernel, sparse
`expm_multiply`, light-cone exact), `moments` (1–4-site moments, two independent κ formulas), `classical/{pauli,mps,bench}`,
`mitigation` (readout, ZNE folding), `bootstrap`, `trust` (policy), `hardware`/`manifest` (compile + dry run), `rehearsal`,
`figures`, `validate`; hardware: `submit` (gated submission, analysis), `hwdata` (hardware rows for the exports), `hwanalysis` (post-hoc diagnostics), `verify` (read-only job check).
`configs/trust_policy.yaml` was written **before** any hardware data existed.
Documents: `reports/FINAL_SCIENTIFIC_REPORT.md`, `SUBMISSION_COMPLIANCE.md`, `REPRODUCIBILITY.md`, `HARDWARE_PROVENANCE.md`, `LIMITATIONS.md`.

## What is verified (see `tests/`)
* Field unitary exact for **both signs of h_x and h_z**; bond sign `RZZ(-2Jδt)` checked against `expm`; wrong signs are detected.
* Circuit statevector = independent numpy kernel = Aer (to 6e-16); merged field halves = unmerged `S^N`; `U†U|0⟩=|0⟩`; `N=0` is the identity with `m=G=1, C=κ=0`.
* Qiskit little-endian bit order checked with an `X` on qubit 3 only; compiled classical-bit map is `clbit i ← physical nodes[i]`.
* κ from raw moments (all **15** subsets incl. triples) = the PDF's central-product definition = direct enumeration; a test shows the "no triples" shortcut is wrong when means ≠ 0.
* The test-suite itself was mutation-checked: flipping the bond sign, field angle, dropping `h_z` from the axis, reversing bit order, or dropping triple moments each makes tests fail.
* Light-cone exact references equal the full exact solver (≤ 2e-14); Pauli propagation is exact when untruncated; MPS is exact for large χ.
* Readout correction is exact for independent readout noise and is never clipped; manual ZNE folds survive compilation only because of barriers (a control test shows they cancel without them); bootstrap interval coverage on a synthetic experiment is checked.
* Every compiled circuit: RZZ angles in (0, π/2], only the patch's own couplings, no SWAPs, state-equivalent to the logical circuit (P12).

## QPU approval gate
`manifest` only compiles and estimates. Submission lives in `src/qtrust/submit.py` and is never run automatically; `submit` refuses unless:
1. `python -m qtrust.cli preregister` has hashed the policy, configs, analysis code and planned circuits, and nothing has changed since;
2. `prereg/APPROVAL.md` carries that sha, two different approver names and a date (the organisers said the mentor reviews after screening, so
   this signed pre-registration is our pre-hardware gate);
3. the account has a passing `live-check` (credentials saved by the user with `QiskitRuntimeService.save_account`, never in code, logs or the archive;
   `ibm_fez` must expose fractional gates; the offline fractional RZZ calibration is an **assumption**);
4. the pilot job was submitted and fetched first, and the job fits the 420 s per-account cap using the measured `job.usage()`.
Account 2 repeats the identical manifest in a later calibration window as a drift check.

## Reused packages and AI assistance
Qiskit, Qiskit Aer, qiskit-ibm-runtime (FoldRzzAngle, FakeFez), `pauli-prop` (IBM), `quimb`, numpy/scipy/pandas/networkx/matplotlib.
**AI use disclosure.** An AI assistant (Claude) was used extensively for implementation work: writing code, tests, scripts and draft reports.
After that first implementation, the authors directed the changes that followed (for example freezing J·δt = 0.1, the
pre-registration and two-person approval gate, the two-account hardware plan and the choice of what to submit). The authors chose the problem setup
and the policies, ran every hardware job themselves on their own IBM accounts, signed the pre-hardware approval,
and are responsible for the submission. Every check listed above is a test in `tests/` that can be re-run (`pytest`).

**Review and corrections.** An earlier version of this project was audited, and the audit found real problems (for example NaN mitigation
estimates receiving trust verdicts, classical benchmarks at a different time step than the hardware plan, and an incomplete trust rule). Each
finding was fixed, re-tested and documented with its evidence in `reports/audit_response.md`; later corrections found during the work (a missing
unfolded baseline circuit in the hardware manifest, wrong numbers in a draft findings table) are recorded in the reports as well.
