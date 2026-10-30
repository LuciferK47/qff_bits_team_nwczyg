#!/usr/bin/env bash
# Sequential offline queue at the frozen dt (no QPU access). Fail-fast shell; every step's exit code and FULL output
# (stdout+stderr, unfiltered) go to raw/queue_dt0.1.log. A failing step is recorded and the queue continues; the
# script exits non-zero if any step failed.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=raw/queue_dt0.1.log
FAILED=0
step() {
  local name=$1; shift
  echo "== $name start $(date -Is)" | tee -a "$LOG"
  set +e; "$@" >>"$LOG" 2>&1; local rc=$?; set -e
  echo "== $name exit_code=$rc end $(date -Is)" | tee -a "$LOG"
  if [ "$rc" -ne 0 ]; then FAILED=$((FAILED + 1)); fi
}
NS=0,4,10,20,30,40,50
step "classical P12" $PY scripts/run_classical.py P12 --Ns "$NS"
step "classical P18" $PY scripts/run_classical.py P18 --Ns "$NS"
step "classical P24" $PY scripts/run_classical.py P24 --Ns "$NS"
step "classical P40" $PY scripts/run_classical.py P40 --Ns 0,4,5,10,20,30 --ref-Ns 0,4,5
echo "== queue finished failed_steps=$FAILED $(date -Is)" | tee -a "$LOG"
exit $FAILED
