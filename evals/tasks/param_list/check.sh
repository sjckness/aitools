#!/usr/bin/env bash
# exit 0 = task risolta. cwd = copia di lavoro di repo/
set -e
python3 -m unittest discover -s tests -q
if ls "$(dirname "$0")"/hidden/test_*.py >/dev/null 2>&1; then
  PYTHONPATH=. python3 -m unittest discover -s "$(dirname "$0")/hidden" -q
fi
