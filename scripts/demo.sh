#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONPATH="$PWD/src"
# The outer bound also covers all builds, checks and stream draining together.
python3 - <<'PY'
import os
import sys
from hookdoctor.process import run_bounded
env = {k: v for k, v in os.environ.items() if not k.startswith('LD_')}
env['LC_ALL'] = 'C'
result = run_bounded([sys.executable, 'scripts/demo.py'], env=env, timeout=115, max_bytes=5242880)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
if result.timed_out:
    print('Demo exceeded its 115-second execution bound', file=sys.stderr)
    raise SystemExit(4)
if result.output_limited:
    print('Demo exceeded its captured output bound', file=sys.stderr)
    raise SystemExit(5)
raise SystemExit(result.returncode)
PY
