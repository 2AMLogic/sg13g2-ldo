#!/usr/bin/env bash
# Shared --check-env decision path (issue #91). Source this file; it defines
# preflight_bench_ok, used by sim/pass-device-screening/run_sweep.sh and
# sim/ldo-cmos5l-pvt-sweep/run_sweep.sh.
#
#   preflight_bench_ok <bench> <netlist> <log> [preflight_validate.py args...]
#
# Runs `ngspice -b` on the netlist and returns 0 only if the simulator exited
# 0, the log has no fatal/model-load pattern, AND the bench's promised output
# artifacts validate (see sim/tools/preflight_validate.py). Otherwise prints
# a diagnosis (including the log) to stderr and returns 1. No spec thresholds
# and no records are involved. Output files named by --wrdata are removed
# before the run so a stale file can never satisfy the check.

PREFLIGHT_TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

preflight_bench_ok() {
  local bench="$1" netlist="$2" log="$3"
  shift 3
  local why="" arg
  local -a vargs=("$@")
  for ((i = 0; i < ${#vargs[@]}; i++)); do
    if [[ "${vargs[i]}" == --wrdata ]]; then
      arg="${vargs[i + 1]}"
      rm -f "${arg%:*:*}"
    fi
  done
  if ! ngspice -b "${netlist}" > "${log}" 2>&1; then
    why="ngspice exited nonzero"
  elif grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error" "${log}"; then
    why="fatal pattern in simulator log"
  elif ! python3 "${PREFLIGHT_TOOLS_DIR}/preflight_validate.py" --log "${log}" "${vargs[@]}" 2> "${log}.validate"; then
    why="missing or invalid output artifacts: $(tr '\n' ' ' < "${log}.validate")"
  fi
  rm -f "${log}.validate"
  if [[ -n "${why}" ]]; then
    echo "run_sweep.sh: --check-env FAILED for ${bench} bench (${why}) -- see below:" >&2
    cat "${log}" >&2
    return 1
  fi
  echo "run_sweep.sh: --check-env OK for ${bench} bench"
  return 0
}
