#!/usr/bin/env bash
# Clean-room check of the submission archive: unzip, fresh Python 3.12 venv from the lock, tests, offline reproduction.
# Needs network ONLY for installing the pinned wheels. Usage: scripts/verify_release.sh dist/team_name.zip
set -euo pipefail
ZIP=$(readlink -f "$1")
TMP=$(mktemp -d)
cd "$TMP" && unzip -q "$ZIP" && uv venv --python 3.12 .venv -q
VIRTUAL_ENV="$TMP/.venv" uv pip sync -q requirements.lock && VIRTUAL_ENV="$TMP/.venv" uv pip install -q -e .
.venv/bin/python -m pytest -q -p no:warnings -x
.venv/bin/python scripts/reproduce_all.py
echo "release verified in $TMP"
