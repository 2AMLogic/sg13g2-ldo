#!/usr/bin/env bash
# sg13g2-ldo -- HBT (npn13G2 family / pnpMPA) pass-device screening (issue #139).
# Cold-start entry point; methodology in README.md.
#
#   run_sweep.sh --check-env           CI-weight preflight: ONE real corner (typ/27C)
#                                      of every request through `klt sim --backend
#                                      local`; requires the analysis to solve and the
#                                      witness measurements to resolve. Writes no
#                                      records/ entry (sim/README.md "CI: syntax/
#                                      --check-env only, never a records/ entry").
#   run_sweep.sh submit <record-dir>   run every request's full corner matrix as a
#                                      `klt sim --backend batch` job on the Spot fleet;
#                                      raw reports -> <record-dir>/raw/. The grid never
#                                      runs on the submitting host.
#   run_sweep.sh analyse <record-dir>  derive <record-dir>.csv and <record-dir>.md from
#                                      the committed raw reports (stdlib python).
#   run_sweep.sh check <record-dir>    offline (what CI runs): regenerate the CSV/MD from
#                                      the raw reports and fail on any byte of drift;
#                                      also re-checks the generated decks.
#
# The submitting host needs klt (client), the batch-fleet credentials klt's batch
# backend documents, and the ihp-sg13g2 PDK checkout under $PDK_ROOT (sim/pdk.json):
# decks/hbt-corners.lib names $PDK_ROOT/ihp-sg13g2/.../cornerHBT.lib and the client
# stages it with the job. Unlike the MOS decks there is NO OSDI build: the bipolar
# models are native ngspice (VBIC level 9 / Gummel-Poon level 1).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DECKS="${HERE}/decks"
DEVICES=(npn13G2 npn13G2l npn13G2v pnpMPA)
BENCHES=(ibsweep vcesweep)

usage() { sed -n '2,22p' "${BASH_SOURCE[0]}" >&2; exit 2; }
[[ $# -ge 1 ]] || usage

resolve_pdk() {
  # shellcheck source=/dev/null
  source "${HERE}/../env.sh"
  if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/ihp-sg13g2/libs.tech/ngspice/models" ]]; then
    echo "run_sweep.sh: no resolvable ihp-sg13g2 install under PDK_ROOT -- see sim/env.sh output." >&2
    exit 3
  fi
  export PDK_ROOT
}

case "$1" in
  --check-env)
    python3 "${HERE}/gen_decks.py" --check
    resolve_pdk
    command -v klt >/dev/null 2>&1 || { echo "run_sweep.sh: klt not on PATH." >&2; exit 3; }
    command -v ngspice >/dev/null 2>&1 || { echo "run_sweep.sh: ngspice not on PATH." >&2; exit 3; }
    tmp="$(mktemp -d)"
    trap 'rm -rf -- "${tmp}"' EXIT
    cp "${DECKS}"/* "${tmp}/"
    rc=0
    for dev in "${DEVICES[@]}"; do
      for bench in "${BENCHES[@]}"; do
        python3 "${HERE}/record.py" single-corner "${tmp}/request-${dev}-${bench}.json" "${tmp}/probe-${dev}-${bench}.json"
        set +e
        klt sim "${tmp}/probe-${dev}-${bench}.json" --backend local --format json \
          -o "${tmp}/out-${dev}-${bench}" > "${tmp}/report-${dev}-${bench}.json"
        set -e
        if python3 "${HERE}/record.py" preflight "${tmp}/report-${dev}-${bench}.json"; then
          echo "run_sweep.sh: --check-env OK for ${dev}/${bench} (typ/27C)"
        else
          echo "run_sweep.sh: --check-env FAILED for ${dev}/${bench}" >&2
          rc=1
        fi
      done
    done
    exit ${rc}
    ;;
  submit)
    [[ $# -eq 2 ]] || usage
    rec="$(mkdir -p "$2" && cd "$2" && pwd)"
    resolve_pdk
    mkdir -p "${rec}/raw"
    scratch="$(mktemp -d)"
    trap 'rm -rf -- "${scratch}"' EXIT
    for dev in "${DEVICES[@]}"; do
      for bench in "${BENCHES[@]}"; do
        echo "submitting request-${dev}-${bench}.json" >&2
        set +e
        (cd "${DECKS}" && klt sim "request-${dev}-${bench}.json" --backend batch \
          -o "${scratch}/${dev}-${bench}" --format json) \
          > "${rec}/raw/${dev}-${bench}.sim.json"
        r=$?
        set -e
        # 0 = every unit passed, 3 = a limit failed, 4 = a unit errored (here: a
        # `.meas` the device could not reach, e.g. a target current it cannot
        # deliver -- recorded as a null result, not a failed run).
        echo "${dev}-${bench}: klt sim exit ${r}" | tee -a "${rec}/raw/exit-codes.txt" >&2
        [[ $r -eq 0 || $r -eq 3 || $r -eq 4 ]] || { echo "submit failed for ${dev}-${bench}" >&2; exit 1; }
      done
    done
    ;;
  analyse)
    [[ $# -eq 2 ]] || usage
    rec="$(cd "$2" && pwd)"
    python3 "${HERE}/record.py" analyse "${rec}"
    ;;
  check)
    [[ $# -eq 2 ]] || usage
    rec="$(cd "$2" && pwd)"
    python3 "${HERE}/gen_decks.py" --check
    python3 "${HERE}/record.py" check "${rec}"
    ;;
  -h|--help) usage ;;
  *) usage ;;
esac
