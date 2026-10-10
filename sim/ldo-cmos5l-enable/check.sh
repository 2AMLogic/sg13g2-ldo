#!/usr/bin/env bash
# Offline, stdlib-only record check (#96): regenerate derived.txt and
# summary.csv from records/<id>/raw/*.sim.json and fail on any byte of drift
# against the committed files.  No PDK, ngspice or klt needed.
# usage: check.sh <record-dir>
set -euo pipefail
export LC_ALL=C
here=$(cd "$(dirname "$0")" && pwd)
rec=${1:?usage: check.sh <record-dir>}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
rc=0
python3 "$here/derive.py" "$rec/raw" > "$tmp/derived.txt"
python3 "$here/summarize.py" "$rec"/raw/*.sim.json > "$tmp/summary.csv"
for f in derived.txt summary.csv; do
  if cmp -s "$tmp/$f" "$rec/$f"; then
    echo "ok: $rec/$f reproduces from raw/"
  else
    echo "DRIFT: $rec/$f differs from regenerated output" >&2
    diff "$rec/$f" "$tmp/$f" | head -20 >&2 || true
    rc=1
  fi
done
exit $rc
