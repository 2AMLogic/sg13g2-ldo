#!/usr/bin/env bash
# Run the issue-#165 current-limiter smoke requests, one local unit each.
# Usage: run_smoke.sh <record-dir> [request-name ...]
# Requires PDK_ROOT (source sim/env.sh with PDK=ihp-sg13cmos5l) and an
# ngspice that can load the PDK's OSDI v0.4 models: set NGSPICE_BIN to its
# path (ngspice 42 cannot; ngspice 46 can). Raw klt reports land in
# <record-dir>/raw/<name>.sim.json. Exit 0/3 are accepted (3 = a limit
# failed; these requests declare no limits).
#
# Every request is a SINGLE nominal unit (tt / 27 C / 3.30 V), so
# `--backend local` is explicit and no grid is launched here. This script
# must never be turned into a loop over corners: grids go through `klt sim`
# corner requests on the batch fleet.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rec="$(mkdir -p "$1" && cd "$1" && pwd)"; shift
NAMES=("$@")
[[ ${#NAMES[@]} -gt 0 ]] || NAMES=(forced-vout load-sweep disabled)
: "${NGSPICE_BIN:?set NGSPICE_BIN to an ngspice >= 44 that loads OSDI v0.4}"
PDK=ihp-sg13cmos5l source "${HERE}/../env.sh" >/dev/null
: "${PDK_ROOT:?}"; export PDK_ROOT
shim="$(mktemp -d)"; trap 'rm -rf "${shim}"' EXIT
ln -s "${NGSPICE_BIN}" "${shim}/ngspice"
export PATH="${shim}:${PATH}"
mkdir -p "${rec}/raw"
for n in "${NAMES[@]}"; do
  set +e
  klt sim "${HERE}/request-${n}.json" --backend local -o "${rec}/artifacts/${n}" --format json > "${rec}/raw/${n}.sim.json"
  rc=$?
  set -e
  echo "${n}: klt sim exit ${rc}" >&2
  [[ $rc -eq 0 || $rc -eq 3 ]] || echo "RUN PROBLEM for ${n} (exit ${rc})" >&2
done
