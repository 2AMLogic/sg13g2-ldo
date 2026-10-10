#!/usr/bin/env bash
# Submit the issue-#67 enable-interface smoke requests to the batch fleet, one
# request at a time. Usage: run_smoke.sh <record-dir> [request-name ...]
# Requires PDK_ROOT (source sim/env.sh with PDK=ihp-sg13cmos5l). Raw klt
# reports land in <record-dir>/raw/<name>.sim.json. Exit 0/3 are accepted
# (3 = a limit failed; these requests declare no limits).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rec="$(mkdir -p "$1" && cd "$1" && pwd)"; shift
NAMES=("$@")
[[ ${#NAMES[@]} -gt 0 ]] || NAMES=(enable-reg baseline-reg disabled-reg enable-rload disabled-rload enable-leak enable-ensweep enable-psrr baseline-psrr enable-loopgain baseline-loopgain)
PDK=ihp-sg13cmos5l source "${HERE}/../env.sh" >/dev/null
: "${PDK_ROOT:?}"; export PDK_ROOT
mkdir -p "${rec}/raw"
for n in "${NAMES[@]}"; do
  set +e
  klt sim "${HERE}/request-${n}.json" --backend batch -o "${rec}/artifacts/${n}" --format json > "${rec}/raw/${n}.sim.json"
  rc=$?
  set -e
  echo "${n}: klt sim exit ${rc}" >&2
  [[ $rc -eq 0 || $rc -eq 3 ]] || echo "SUBMIT/RUN PROBLEM for ${n} (exit ${rc})" >&2
done
