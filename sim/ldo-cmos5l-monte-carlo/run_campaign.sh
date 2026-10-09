#!/usr/bin/env bash
# sg13g2-ldo -- SG13CMOS5L row-2 (output accuracy) Monte Carlo campaign
# (issue #56). Cold-start entry point; methodology in README.md.
#
#   run_campaign.sh submit <record-dir>    run the five klt sim requests on the
#                                          batch fleet, raw reports -> <record-dir>/raw/
#   run_campaign.sh analyse <record-dir>   split per population, run klt yield,
#                                          cross-checks -> <record-dir>/yield/,
#                                          <record-dir>/crosscheck.json, <record-dir>.csv
#
# Every simulation is a `klt sim --backend batch` request (corners and
# monte_carlo expressed in the request; the grid runs on the Spot fleet, never
# on the submitting host). The submitting host needs: klt (client), the
# batch-fleet credentials klt's batch backend documents, and the PDK checkout
# that row2-corners.lib names under $PDK_ROOT (sim/pdk-cmos5l.json) -- the
# model files are staged from there with the job.
#
# `analyse` needs a klt whose klt_yield_native extension imports (set
# KLT_YIELD=/path/to/klt; default: klt on PATH). See README.md "Toolchain".
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUESTS=(probe mc attribution negctl repro)

usage() { sed -n '2,20p' "$0" >&2; exit 2; }
[[ $# -eq 2 ]] || usage
cmd="$1"; rec="$(mkdir -p "$2" && cd "$2" && pwd)"

case "$cmd" in
  submit)
    # shellcheck source=/dev/null
    PDK=ihp-sg13cmos5l source "${HERE}/../env.sh"
    : "${PDK_ROOT:?PDK_ROOT must name the dir holding ihp-sg13cmos5l/ and ihp-sg13g2/}"
    export PDK_ROOT
    mkdir -p "${rec}/raw"
    for name in "${REQUESTS[@]}"; do
      echo "submitting request-row2-${name}.json" >&2
      set +e
      klt sim "${HERE}/request-row2-${name}.json" --backend batch \
        -o "${rec}/artifacts/${name}" --format json \
        > "${rec}/raw/row2-${name}.sim.json"
      rc=$?
      set -e
      # 0 = every unit passed, 3 = a limit failed (expected for the negative
      # control and possible for real draws); anything else is a failed run.
      echo "row2-${name}: klt sim exit ${rc}" >&2
      [[ $rc -eq 0 || $rc -eq 3 ]] || { echo "submit failed for ${name}" >&2; exit 1; }
    done
    ;;
  analyse)
    KLT_YIELD="${KLT_YIELD:-klt}"
    raw="${rec}/raw"
    out="${rec}/yield"
    python3 "${HERE}/build_yield_inputs.py" --report "${raw}/row2-mc.sim.json" \
      --negctl "${raw}/row2-negctl.sim.json" --outdir "${out}"
    python3 "${HERE}/build_yield_inputs.py" --report "${raw}/row2-attribution.sim.json" \
      --no-target-yield --outdir "${out}/attribution"
    # klt yield runs from inside the directory holding each sample-set
    # document and writes its report beside it, so the report's `samples`
    # field is a bare file name that resolves relative to the report itself
    # -- the path klt signoff re-hashes for a yield citation's content_hash.
    run_yield() {  # <dir>
      local d="$1" f base rc
      : > "${d}/exit-codes.txt"
      for f in "${d}"/*.samples.json; do
        base="$(basename "${f}" .samples.json)"
        set +e
        (cd "${d}" && "${KLT_YIELD}" yield "${base}.samples.json" --format json) \
          > "${d}/${base}.yield.json"
        rc=$?
        (cd "${d}" && "${KLT_YIELD}" yield "${base}.samples.json") > "${d}/${base}.yield.txt"
        set -e
        echo "${base}: klt yield exit ${rc}" | tee -a "${d}/exit-codes.txt" >&2
        [[ $rc -eq 0 || $rc -eq 3 ]] || { echo "klt yield failed on ${f}" >&2; exit 1; }
      done
    }
    run_yield "${out}"
    run_yield "${out}/attribution"
    python3 "${HERE}/crosscheck.py" "${rec}" --csv "${rec}.csv" > "${rec}/crosscheck.json"
    echo "wrote ${rec}/crosscheck.json and ${rec}.csv" >&2
    ;;
  *) usage ;;
esac
