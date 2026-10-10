#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONPATH="$PWD/src"
bash scripts/verify-fixtures.sh
mkdir -p docs/evidence/acceptance
python3 -m unittest discover -s tests -v 2>&1 | tee docs/evidence/acceptance/tests.txt
python3 -m hookdoctor --help > docs/evidence/acceptance/help.txt
python3 -m hookdoctor --version > docs/evidence/acceptance/version.txt
bash scripts/demo.sh | tee docs/evidence/acceptance/demo.txt
