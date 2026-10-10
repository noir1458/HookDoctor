#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONPATH="$PWD/src"
export HOOKDOCTOR_EVIDENCE_DIR="${HOOKDOCTOR_EVIDENCE_DIR:-$PWD/docs/evidence/fixture-gate}"
if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    echo 'ENVIRONMENT: requires Linux x86-64; run bash scripts/dev.sh bash scripts/verify-fixtures.sh' >&2
    exit 3
fi
mkdir -p "$HOOKDOCTOR_EVIDENCE_DIR"
python3 -m unittest discover -s tests -p test_fixtures.py -v 2>&1 | tee "$HOOKDOCTOR_EVIDENCE_DIR/tests.txt"
