#!/usr/bin/env bash
# E4 divider/Cc probe at DR-0015 point P5 (issue #315).
#
#   sim/ldo-cmos5l-pvt-sweep/run_e4.sh                 # batch fleet: 4 points x 3 benches
#   sim/ldo-cmos5l-pvt-sweep/run_e4.sh --validate      # local, ONE deck (e1op, R_div 0.5x)
#   sim/ldo-cmos5l-pvt-sweep/run_e4.sh --probe         # fleet, ONE deck (loopgain, 1x/1x)
#   sim/ldo-cmos5l-pvt-sweep/run_e4.sh --plan-only
#
# DR-0015's Disposition derives a tension between ratified rows 3+6+7+10 at
# 0 mA and Cout >= 1.6 uF and defers it to "probe E4": at point P5
#
#   P5  ss / 125 C / res_wcs   0 mA   3.45 uF   0 mohm
#
# cross the feedback divider's length (R_div in {1x, 0.5x}, BOTH XRtop and
# XRbot so the divider ratio is unchanged) with the Miller cap's width (Cc in
# {1x, 0.65x}, the w= token of XCc with l held at 30e-6) and read, at each of
# the four points, the loop-gain and PSRR benches DR-0015 names plus the E1
# operating-point bench -- the last because the brief asks for the MEASURED
# divider current, DC VOUT and Iq, and the fleet path drops the AC
# templates' informational `op` echo. Both knobs are testbench-local
# substitutions on a COPY of the design netlist (e4_divider_cc.py's override
# contract: design/sg13cmos5l/netlist/*.spice is never written), and the
# flattened/replica divider lines the loop-gain and E1 benches carry in their
# own text are patched and verified per deck (e4_divider_cc.py patch-deck
# refuses a deck whose copy moved while its own lines stayed nominal).
#
# This script never launches a local ngspice GRID: --validate runs exactly
# ONE single-corner deck locally (a debug probe, not a grid); the twelve
# campaign decks run only on the batch fleet, and a failed submission is
# reported as such -- never a local fallback. --probe submits exactly ONE
# deck (the 1x/1x loop-gain deck: the like-for-like P5 baseline) to the
# fleet into a scratch dir to confirm, before the campaign, that the batch
# path loads the models (every run must show loaded models; a run against
# unloaded models is a failure). Its results are a gate, not a record.
#
# e4_divider_cc.py then reduces, checks and writes the record; nothing here
# touches a threshold, a historical record or a spec row -- sim/ stays
# append-only and DR-0015 stays Proposed.
#
# Environment (same conventions as run_e1op.sh):
#   SWEEP_BATCH_PLAN_ONLY      parse + group + print the plan, submit nothing
#   SWEEP_BATCH_REUSE_WORK     an earlier --work dir for byte-identical
#                              request reuse (interruption recovery)
set -euo pipefail

MODE=campaign
for arg in "$@"; do
  case "${arg}" in
    --validate) MODE=validate ;;
    --probe) MODE=probe ;;
    --plan-only) export SWEEP_BATCH_PLAN_ONLY=1 ;;
    -h|--help) sed -n '2,41p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "run_e4.sh: unknown argument '${arg}'" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
E4="${SCRIPT_DIR}/e4_divider_cc.py"
DESIGN_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"
ERRAMP_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice"

# The loop-gain template must still carry the canonical ceiling line (issue
# #128); the three templates must still mirror ldo_core_cmos5l (positive
# assertion, cheap, no PDK -- the negative controls live in run_sweep.sh
# --check-topology-guard). The override contract's own lines (the committed
# XCc / XRtop / XRbot and the templates' flattened copies) are asserted by
# e4_divider_cc.py at every substitution: a drift fails loudly.
LG_AC_MAX="$(python3 "${SCRIPT_DIR}/ac_sweep.py" ceiling 100meg)"
EXPECT_ROWS_AC="$(python3 "${SCRIPT_DIR}/ac_sweep.py" rows "${LG_AC_MAX}")"
python3 "${SCRIPT_DIR}/ac_sweep.py" check-template "${SCRIPT_DIR}/testbench/tb_loopgain_cmos5l.spice.tmpl"
"${SCRIPT_DIR}/run_sweep.sh" --check-topology

export PDK=ihp-sg13cmos5l
# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/tools/preflight.sh"

if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_e4.sh: no resolvable ${PDK} install -- see sim/env.sh output above." >&2
  exit 3
fi
# Fail closed on a PDK-pin mismatch (shared check: sim/tools/pdk_pin.py).
PDK_PIN_FOUND="$(python3 "${SIM_DIR}/tools/pdk_pin.py" \
  --pdk-root "${PDK_ROOT}" --pdk "${PDK}" \
  --pin-file "${SIM_DIR}/pdk-cmos5l.json" \
  --caller "run_e4.sh" --campaign "E4")" || exit $?
echo "run_e4.sh: ${PDK} install verified at the pinned commit ${PDK_PIN_FOUND}"
OSDI_DIR="${SG13G2_OSDI_DIR}"

if [[ ! -f "${DESIGN_NETLIST}" || ! -f "${ERRAMP_NETLIST}" ]]; then
  echo "run_e4.sh: design netlists not found -- regenerate them first:" >&2
  echo "run_e4.sh:   python3 design/netlist.py --design sg13cmos5l" >&2
  exit 3
fi
if [[ ! -f "${OSDI_DIR}/psp103.osdi" ]]; then
  echo "run_e4.sh: ${OSDI_DIR}/psp103.osdi missing -- run PDK=${PDK} sim/tools/build-osdi.sh first." >&2
  exit 3
fi

# The four points, in the order the record tabulates them:
#   <rdiv label> <rdiv l> <cc label> <cc w>
POINTS=(
  "1x   25.43e-6   1x    170e-6"
  "1x   25.43e-6   0.65x 110.5e-6"
  "0.5x 12.715e-6  1x    170e-6"
  "0.5x 12.715e-6  0.65x 110.5e-6"
)
BENCHES=(loopgain psrr e1op)

point_field() {  # <index> <field 1..4: rdiv label, rdiv l, cc label, cc w>
  read -r f1 f2 f3 f4 <<< "${POINTS[$1]}"
  case "$2" in 1) echo "${f1}" ;; 2) echo "${f2}" ;; 3) echo "${f3}" ;; 4) echo "${f4}" ;; esac
}

key_of() {  # <rdiv label> <cc label>
  python3 "${E4}" point-key "$1" "$2"
}

point_id() {  # <bench> <rdiv label> <cc label>
  python3 "${E4}" point-id "$1" "$2" "$3"
}

# One renderer for every deck (#236): sim/tools/render_deck.py, the same
# module run_sweep.sh and run_e1op.sh call; it fails loudly on any
# unsubstituted @@TOKEN@@.
render_deck() {  # <bench> <design copy> <cc w> <out> <csv>
  local bench="$1" copy="$2" w="$3" out="$4" csv="$5"
  python3 "${SIM_DIR}/tools/render_deck.py" \
    "${SCRIPT_DIR}/testbench/tb_${bench}_cmos5l.spice.tmpl" "${out}" \
    "PDK_ROOT=${PDK_ROOT}" "PDK=${PDK}" "OSDI_DIR=${OSDI_DIR}" \
    "MOS_SECTION=mos_ss" "RES_SECTION=res_wcs" "CAP_SECTION=cap_typ" \
    "TEMP=125" "LG_AC_MAX=${LG_AC_MAX}" "CC_W=${w}" \
    "DESIGN_NETLIST=${copy}" "LOAD_A=0" "COUT_F=3.45u" \
    "COUT_BOTTOM=0" \
    "ESR_LINE=* ESR=0: Cout wired directly to ground (P5)" \
    "AC_CSV=${csv}" "DC_CSV=${csv}"
}

# Write the overridden design-netlist copy for one point (refuses any line
# drift; at 1x/1x the copy is byte-identical to the committed netlist).
write_copy() {  # <rdiv label> <rdiv l> <cc label> <cc w> <dir>
  local rdiv="$1" l="$2" cc="$3" w="$4" dir="$5"
  mkdir -p "${dir}"
  local out
  out="${dir}/ldo_core_cmos5l_$(key_of "${rdiv}" "${cc}").spice"
  python3 "${E4}" design-copy "${DESIGN_NETLIST}" "${out}" --w "${w}" --l "${l}"
  echo "${out}"
}

# Render one deck and apply the bench's own divider legs, verifying that the
# overridden lines are the ones the deck simulates (fails the run otherwise).
build_deck() {  # <bench> <design copy> <rdiv l> <cc w> <out> <csv>
  local bench="$1" copy="$2" l="$3" w="$4" out="$5" csv="$6"
  render_deck "${bench}" "${copy}" "${w}" "${out}" "${csv}"
  python3 "${E4}" patch-deck "${out}" --bench "${bench}" --design "${copy}" --w "${w}" --l "${l}"
}

screen_point() {  # <point_id> <ac|dc> -- exit 0 iff log clean AND export complete
  local pid="$1" kind="$2"
  local log="${CORNERS_OUT}/${pid}.log"
  local csv="${CORNERS_OUT}/${pid}_${kind}.csv"
  [[ -f "${log}" ]] || return 1
  if grep -qiE "osdi_load_failed|Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error|gmin stepping failed|no convergence|iteration limit reached|no writable vector" "${log}" \
     || grep -iE "singular matrix" "${log}" | grep -qivE "^[[:space:]]*Warning:"; then
    return 1
  fi
  case "${pid}" in
    loopgain_*) python3 "${SCRIPT_DIR}/ac_sweep.py" check-trace "${csv}" "${LG_AC_MAX}" >/dev/null 2>&1 || return 1 ;;
    psrr_*)     [[ "$(wc -l < "${csv}")" -eq "${EXPECT_ROWS_AC}" ]] || return 1 ;;
    e1op_*)     python3 "${SCRIPT_DIR}/e1_oppoints.py" check-export "${csv}" >/dev/null 2>&1 || return 1 ;;
  esac
  return 0
}

# --------------------------------------------------------------------------- #
# --validate: ONE single-corner deck at P5 with R_div 0.5x, run LOCALLY (a
# debug probe, not a grid): the E1 operating-point bench, because its KCL
# check ties the real divider (the pass device's current at 0 mA) to the
# replica ammeter -- so a deck whose flattened legs and replica were not both
# scaled cannot pass it. Screened in-place BEFORE any fleet submission.
# --------------------------------------------------------------------------- #
if [[ "${MODE}" == validate ]]; then
  command -v ngspice >/dev/null 2>&1 || { echo "run_e4.sh: ngspice not on PATH." >&2; exit 3; }
  TMP="$(mktemp -d)"
  trap 'rm -rf "${TMP}"' EXIT
  echo "run_e4.sh: --validate: one e1op deck at P5 with R_div 0.5x in ${TMP}"
  copy="$(write_copy 0.5x 12.715e-6 1x 170e-6 "${TMP}/copies")"
  build_deck e1op "${copy}" 12.715e-6 170e-6 "${TMP}/val_e4.spice" "${TMP}/val_e4_dc.csv"
  ngspice -b "${TMP}/val_e4.spice" > "${TMP}/val_e4.log" 2>&1 || {
    echo "run_e4.sh: --validate: ngspice FAILED -- see ${TMP}/val_e4.log" >&2
    exit 1
  }
  if grep -qiE "osdi_load_failed|Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error" "${TMP}/val_e4.log"; then
    echo "run_e4.sh: --validate: a model did not load -- see ${TMP}/val_e4.log" >&2
    exit 1
  fi
  python3 "${SCRIPT_DIR}/e1_oppoints.py" check-export "${TMP}/val_e4_dc.csv"
  # The reduced operating point must pass every E1 check except liveness (a
  # fleet-only measurement), and the divider current must have risen
  # against the committed E1 P5 row -- halving the legs' length lowers their
  # resistance; by how much is measured, not assumed (rhigh does not scale
  # linearly with l).
  python3 - "${SCRIPT_DIR}" "${TMP}/val_e4_dc.csv" \
    "${REPO_ROOT}/sim/ldo-cmos5l-pvt-sweep/records/20261012-115531-cfa681f9.e1op.csv" <<'PYEOF'
import csv, sys
sys.path.insert(0, sys.argv[1])
import e4_divider_cc as e
dc, failed = e.dc_reading(sys.argv[2], None, e.e1.CC_F_NOMINAL)
assert [f for f in failed if f != "liveness"] == [], failed
with open(sys.argv[3], newline="") as fh:
    p5 = [r for r in csv.DictReader(fh) if r["point"] == "P5"][0]
committed_idiv = float(p5["op:i(vdivsense)"])
if not dc["dc:i_div_a"] > 1.5 * committed_idiv:
    sys.exit(f"validate: replica divider current {dc['dc:i_div_a']:.4e} A did not rise "
             f"above the committed 1x value {committed_idiv:.4e} A")
print(f"validate: VOUT {dc['dc:vout_v']:.6f} V; I_div replica {dc['dc:i_div_a']:.4e} A, "
      f"pass {dc['dc:i_div_pass_a']:.4e} A (committed 1x {committed_idiv:.4e} A; "
      f"measured ratio {dc['dc:i_div_a'] / committed_idiv:.3f}x); "
      f"Iq {dc['dc:iq_a']:.4e} A")
PYEOF
  echo "run_e4.sh: --validate OK"
  exit 0
fi

command -v klt >/dev/null 2>&1 || { echo "run_e4.sh: klt not on PATH." >&2; exit 3; }

# --------------------------------------------------------------------------- #
# --probe: ONE fleet submission -- the 1x/1x loop-gain deck at P5, into a
# scratch dir. Confirms the batch path loads the models (the runner's
# preload of the six staged OSDI binaries, verified by batch_backend.py and
# re-read from backend.json here) before the campaign is submitted, and that
# the like-for-like baseline reads like the committed P5. Nothing is kept.
# --------------------------------------------------------------------------- #
if [[ "${MODE}" == probe ]]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "${TMP}"' EXIT
  CORNERS_OUT="${TMP}/corners"
  copy="$(write_copy 1x 25.43e-6 1x 170e-6 "${TMP}/copies")"
  pid="$(point_id loopgain 1x 1x)"
  build_deck loopgain "${copy}" 25.43e-6 170e-6 "${TMP}/${pid}.spice" "${CORNERS_OUT}/${pid}_ac.csv"
  printf '%s\t%s\n' "${pid}" "${TMP}/${pid}.spice" > "${TMP}/queue.tsv"
  echo "run_e4.sh: --probe: one fleet submission (${pid}, 1 request, 1 corner)"
  BATCH_BACKEND="${SCRIPT_DIR}/batch_backend.py"
  if ! python3 "${BATCH_BACKEND}" run --queue "${TMP}/queue.tsv" --corners-out "${CORNERS_OUT}" \
       --work "${TMP}/work" --osdi-dir "${OSDI_DIR}" --plan-only; then
    echo "run_e4.sh: --probe: the plan did not parse -- see above." >&2
    exit 1
  fi
  probe_rc=0
  python3 "${BATCH_BACKEND}" run --queue "${TMP}/queue.tsv" --corners-out "${CORNERS_OUT}" \
    --work "${TMP}/work" --osdi-dir "${OSDI_DIR}" || probe_rc=$?
  if [[ ${probe_rc} -ne 0 ]]; then
    echo "run_e4.sh: --probe: batch_backend.py exited ${probe_rc} -- the batch path did NOT" >&2
    echo "run_e4.sh:   complete cleanly. See ${CORNERS_OUT}/_batch/*/ for the job id and" >&2
    echo "run_e4.sh:   the OSDI provenance; report it on the issue, do not fall back locally." >&2
    exit 1
  fi
  if ! screen_point "${pid}" ac; then
    echo "run_e4.sh: --probe: the returned deck did not pass screening -- see ${CORNERS_OUT}/${pid}.log" >&2
    exit 1
  fi
  python3 - "${SCRIPT_DIR}" "${CORNERS_OUT}" "${pid}" <<'PYEOF'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import e4_divider_cc as e
corners, pid = sys.argv[2], sys.argv[3]
ok, why = e.models_loaded(corners)[pid]
if not ok:
    sys.exit(f"probe: model load NOT confirmed: {why}")
with open(os.path.join(corners, "_batch", "backend.json")) as fh:
    be = json.load(fh)
r = e.loopgain_reading(os.path.join(corners, pid + "_ac.csv"))
print(f"probe: OSDI preload verified {len(be['jobs'][0]['osdi_preload_verified'])}/6 "
      f"(job {be['jobs'][0]['job_id']}, runner klt {be['jobs'][0]['runner_klt_version']}, "
      f"engine {be['engines']})")
print(f"probe: 1x/1x P5 loop gain: f_ug {r['lg:f_ug_hz']:.2f} Hz, PM {r['lg:pm_deg']:.2f} deg "
      f"({r['lg:pm_verdict']}), GM {r['lg:gm_db']:.2f} dB ({r['lg:gm_verdict']}: {r['lg:gm_reasons']})")
print("probe: committed P5 (DR-0015 row): f_ug 1052 Hz, PM 17.61 deg, GM 64.26 dB (ambiguous: ceiling_unbounded)")
PYEOF
  echo "run_e4.sh: --probe OK: the batch path loads its models; the campaign may be submitted."
  exit 0
fi

# --------------------------------------------------------------------------- #
# batch campaign: write the four copies, render + patch + verify the twelve
# decks, submit via batch_backend.py, screen, reduce, write the record.
# --------------------------------------------------------------------------- #
REPO_GIT_SHA="$(cd "${REPO_ROOT}" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"
EXPERIMENT_DIR="${SCRIPT_DIR}"
SNAPSHOTS_OUT="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
COPIES_OUT="${SNAPSHOTS_OUT}/design-netlist-e4"
CORNERS_OUT="${EXPERIMENT_DIR}/corners/${RECORD_ID}"
RECORDS_DIR="${EXPERIMENT_DIR}/records"
EVIDENCE_DIR="${EXPERIMENT_DIR}/evidence/${RECORD_ID}"
OUT_CSV="${RECORDS_DIR}/${RECORD_ID}.e4.csv"
OUT_JSON="${EVIDENCE_DIR}/e4-report.json"
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.e4.md"
MANIFEST="${RECORDS_DIR}/${RECORD_ID}.e4.manifest.tsv"
mkdir -p "${SNAPSHOTS_OUT}" "${COPIES_OUT}" "${CORNERS_OUT}" "${EVIDENCE_DIR}"

BATCH_WORK="$(mktemp -d "${TMPDIR:-/tmp}/ldo-cmos5l-e4.XXXXXX")"
BATCH_QUEUE="${BATCH_WORK}/queue.tsv"
: > "${BATCH_QUEUE}"

# one design-netlist copy per point
declare -A COPY_PATH
for i in "${!POINTS[@]}"; do
  rdiv="$(point_field "${i}" 1)"; l="$(point_field "${i}" 2)"
  cc="$(point_field "${i}" 3)"; w="$(point_field "${i}" 4)"
  COPY_PATH["$(key_of "${rdiv}" "${cc}")"]="$(write_copy "${rdiv}" "${l}" "${cc}" "${w}" "${COPIES_OUT}")"
done

for i in "${!POINTS[@]}"; do
  rdiv="$(point_field "${i}" 1)"; l="$(point_field "${i}" 2)"
  cc="$(point_field "${i}" 3)"; w="$(point_field "${i}" 4)"
  key="$(key_of "${rdiv}" "${cc}")"
  copy="${COPY_PATH["${key}"]}"
  for bench in "${BENCHES[@]}"; do
    pid="$(point_id "${bench}" "${rdiv}" "${cc}")"
    netlist="${SNAPSHOTS_OUT}/${pid}.spice"
    case "${bench}" in
      loopgain|psrr) csv="${CORNERS_OUT}/${pid}_ac.csv" ;;
      e1op)          csv="${CORNERS_OUT}/${pid}_dc.csv" ;;
    esac
    build_deck "${bench}" "${copy}" "${l}" "${w}" "${netlist}" "${csv}"
    printf '%s\t%s\n' "${pid}" "${netlist}" >> "${BATCH_QUEUE}"
  done
done
echo "run_e4.sh: queued $(wc -l < "${BATCH_QUEUE}") decks (${#BENCHES[@]} benches x ${#POINTS[@]} points at P5)"

if [[ -n "${SWEEP_BATCH_PLAN_ONLY:-}" ]]; then
  python3 "${SCRIPT_DIR}/batch_backend.py" run --queue "${BATCH_QUEUE}" \
    --corners-out "${CORNERS_OUT}" --work "${BATCH_WORK}" --osdi-dir "${OSDI_DIR}" --plan-only
  echo "run_e4.sh: SWEEP_BATCH_PLAN_ONLY set -- plan printed, nothing submitted;" >&2
  echo "run_e4.sh: delete ${SNAPSHOTS_OUT} and ${CORNERS_OUT} by hand." >&2
  exit 0
fi

batch_rc=0
python3 "${SCRIPT_DIR}/batch_backend.py" run \
  --queue "${BATCH_QUEUE}" --corners-out "${CORNERS_OUT}" \
  --work "${BATCH_WORK}" --osdi-dir "${OSDI_DIR}" \
  ${SWEEP_BATCH_REUSE_WORK:+--reuse-work "${SWEEP_BATCH_REUSE_WORK}"} || batch_rc=$?
if [[ ${batch_rc} -ne 0 ]]; then
  echo "run_e4.sh: batch_backend.py exited ${batch_rc}; the affected points are screened as FAILED below." >&2
fi
if [[ -f "${CORNERS_OUT}/_batch/backend.env" ]]; then
  # shellcheck source=/dev/null
  source "${CORNERS_OUT}/_batch/backend.env"
  NGSPICE_VERSION="${BATCH_NGSPICE_VERSION} (EDA batch fleet runner, klt ${BATCH_RUNNER_KLT})"
else
  NGSPICE_VERSION="unknown (no backend.env: the submission failed)"
fi

total=0
passed=0
failed_points=()
while IFS=$'\t' read -r pid _netlist; do
  total=$((total + 1))
  case "${pid}" in
    loopgain_*|psrr_*) kind=ac ;;
    *) kind=dc ;;
  esac
  if screen_point "${pid}" "${kind}"; then
    passed=$((passed + 1))
  else
    echo "run_e4.sh: FAILED ${pid} -- see ${CORNERS_OUT}/${pid}.log" >&2
    failed_points+=("${pid}")
  fi
done < "${BATCH_QUEUE}"

if [[ ${passed} -eq 0 ]]; then
  echo "run_e4.sh: no points passed screening -- refusing to reduce or write a record." >&2
  exit 1
fi

# --- Reduction + record ------------------------------------------------------ #
reduce_rc=0
python3 "${E4}" reduce --record "${RECORD_ID}" \
  --corners-dir "${CORNERS_OUT}" --out-csv "${OUT_CSV}" --out-json "${OUT_JSON}" || reduce_rc=$?

# --- Manifest (house columns; per-deck provenance) --------------------------- #
# Written BEFORE record-md: the record's provenance section quotes this
# manifest's pdk column, so the manifest must exist when the md is rendered.
{
  printf 'bench\tpoint_id\trdiv\tcc\tmos\tres\ttemp_c\tload_a\tcout_f\tesr_ohm\tnetlist\tnetlist_sha256\tdesign_netlist\tdesign_netlist_sha256\tinvocation\tgit_sha\tpdk\tngspice\n'
  for i in "${!POINTS[@]}"; do
    rdiv="$(point_field "${i}" 1)"; cc="$(point_field "${i}" 3)"
    key="$(key_of "${rdiv}" "${cc}")"
    copy="${COPY_PATH["${key}"]}"
    copy_rel="${copy#"${REPO_ROOT}/"}"
    copy_sha="$(sha256sum "${copy}" | cut -d' ' -f1)"
    for bench in "${BENCHES[@]}"; do
      pid="$(point_id "${bench}" "${rdiv}" "${cc}")"
      netlist="${SNAPSHOTS_OUT}/${pid}.spice"
      sha="$(sha256sum "${netlist}" | cut -d' ' -f1)"
      group="$(awk -F'\t' -v p="${pid}" '$1==p {print $2}' "${CORNERS_OUT}/_batch/points.tsv")"
      invocation="klt sim --backend batch corners/${RECORD_ID}/_batch/${group}/request.json (batch_backend.py; corner mos_ss__res_wcs__cap_typ @ 125C)"
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "${bench}" "${pid}" "${rdiv}" "${cc}" "mos_ss" "res_wcs" "125" "0" "3.45u" "0" \
        "${netlist#"${REPO_ROOT}/"}" "${sha}" "${copy_rel}" "${copy_sha}" "${invocation}" \
        "${REPO_GIT_SHA}" "${PDK} ${PDK_PIN_FOUND}" "${BATCH_NGSPICE_VERSION:-unknown}"
    done
  done
} > "${MANIFEST}"

python3 "${E4}" record-md --record "${RECORD_ID}"

echo "run_e4.sh: record ${RECORD_ID}: ${passed}/${total} decks passed screening (${NGSPICE_VERSION});"
echo "run_e4.sh:   reduction ${OUT_CSV}"
echo "run_e4.sh:   record    ${MD_OUT}"
echo "run_e4.sh:   manifest  ${MANIFEST}"

if [[ ${#failed_points[@]} -gt 0 || ${batch_rc} -ne 0 ]]; then
  exit 1
fi
if [[ ${reduce_rc} -ne 0 ]]; then
  echo "run_e4.sh: reduction reported failed checks (exit ${reduce_rc}) -- the record is" >&2
  echo "run_e4.sh: written but marked INCOMPLETE; see ${OUT_JSON} failed_checks." >&2
  exit "${reduce_rc}"
fi
exit 0
