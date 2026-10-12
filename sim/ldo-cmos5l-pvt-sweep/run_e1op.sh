#!/usr/bin/env bash
# E1 DC operating-point extraction campaign (issue #158).
#
#   sim/ldo-cmos5l-pvt-sweep/run_e1op.sh                    # batch fleet
#   sim/ldo-cmos5l-pvt-sweep/run_e1op.sh --validate         # local, tt/27 only
#   sim/ldo-cmos5l-pvt-sweep/run_e1op.sh --plan-only
#
# DR-0015's follow-up brief prices experiment E1 as FOUR DC operating-point
# extractions at its selected points P1/P2/P5/P6 (spec/decision-records/
# DR-0015-....md, "The six points" + the E1 row of the experiments table):
#
#   P1  ss / 125 C / res_bcs   0 mA   1.00 uF   0 mohm
#   P2  ff / -40 C / res_wcs   0 mA   1.00 uF   0 mohm
#   P5  ss / 125 C / res_wcs   0 mA   3.45 uF   0 mohm
#   P6  ss / 125 C / res_bcs   1 mA   1.00 uF   0 mohm
#
# Each run uses the SAME batch-backend fleet path as run_sweep.sh --batch and
# run_loopgain2.sh (one klt sim request, four corners): the deck
# (tb_e1op_cmos5l.spice.tmpl) is the flattened loop-gain bench's circuit --
# whose FB/FBAMP break draws zero current, so its DC operating point is the
# closed loop's -- plus a non-invasive divider replica and a `.save` card
# naming the exported device operating-point parameters (ids/gm/gds of all
# fourteen MOS wrappers, pass-device cgs/cgd/cdd/vth, XMn3 cgs/cgd). The
# analysis is a three-point DC sweep bracketing Vin = 3.30 V; the export's
# middle row IS the operating point. e1_oppoints.py reduces, checks and
# writes the record; nothing here touches a threshold, a historical record
# or a spec row -- sim/ stays append-only and DR-0015 stays Proposed.
#
# This script never launches a local ngspice GRID: --validate runs exactly
# ONE single-corner deck at tt/27C (a debug probe, not a grid); the four
# campaign points run only on the batch fleet, and a failed submission is
# reported as such -- never a local fallback.
#
# Environment (same conventions as run_loopgain2.sh):
#   SWEEP_BATCH_PLAN_ONLY      parse + group + print the plan, submit nothing
#   SWEEP_BATCH_REUSE_WORK     an earlier --work dir for byte-identical
#                              request reuse (interruption recovery)
set -euo pipefail

VALIDATE=0
for arg in "$@"; do
  case "${arg}" in
    --validate) VALIDATE=1 ;;
    --plan-only) export SWEEP_BATCH_PLAN_ONLY=1 ;;
    -h|--help) sed -n '2,43p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "run_e1op.sh: unknown argument '${arg}'" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
DESIGN_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"
ERRAMP_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice"

# The e1op template must still mirror ldo_core_cmos5l (positive assertion,
# cheap, no PDK). The negative controls live in run_sweep.sh
# --check-topology-guard (CI).
"${SCRIPT_DIR}/run_sweep.sh" --check-topology

export PDK=ihp-sg13cmos5l
# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/tools/preflight.sh"

if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_e1op.sh: no resolvable ${PDK} install -- see sim/env.sh output above." >&2
  exit 3
fi
# Fail closed on a PDK-pin mismatch: the record's provenance must describe
# the install that ACTUALLY ran, so the resolved install is read here
# (fetcher installs answer via .fetched-version, older git-based ones via
# rev-parse) and must equal sim/pdk-cmos5l.json's pinned_commit. A run on a
# superseded install would otherwise be free to mislabel itself as the pin.
PDK_PIN_EXPECTED="$(python3 -c 'import json; print(json.load(open("'"${SIM_DIR}"'/pdk-cmos5l.json"))["pinned_commit"])')"
if [[ -f "${PDK_ROOT}/${PDK}/.fetched-version" ]]; then
  PDK_PIN_FOUND="$(cat "${PDK_ROOT}/${PDK}/.fetched-version")"
elif [[ -d "${PDK_ROOT}/${PDK}/.git" ]]; then
  PDK_PIN_FOUND="$(git -C "${PDK_ROOT}/${PDK}" rev-parse HEAD)"
else
  PDK_PIN_FOUND=""
fi
if [[ "${PDK_PIN_FOUND}" != "${PDK_PIN_EXPECTED}" ]]; then
  echo "run_e1op.sh: ${PDK} install at PDK_ROOT=${PDK_ROOT} is '${PDK_PIN_FOUND:-unidentified}'," >&2
  echo "run_e1op.sh:   but sim/pdk-cmos5l.json pins ${PDK_PIN_EXPECTED} -- refusing to run." >&2
  echo "run_e1op.sh:   E1 evidence must come from the pinned install (scripts/fetch-ihp-sg13cmos5l.sh);" >&2
  echo "run_e1op.sh:   point PDK_ROOT at it and re-run." >&2
  exit 3
fi
echo "run_e1op.sh: ${PDK} install verified at the pinned commit ${PDK_PIN_FOUND}"
OSDI_DIR="${SG13G2_OSDI_DIR}"

if [[ ! -f "${DESIGN_NETLIST}" || ! -f "${ERRAMP_NETLIST}" ]]; then
  echo "run_e1op.sh: design netlists not found -- regenerate them first:" >&2
  echo "run_e1op.sh:   python3 design/netlist.py --design sg13cmos5l" >&2
  exit 3
fi
if [[ ! -f "${OSDI_DIR}/psp103.osdi" ]]; then
  echo "run_e1op.sh: ${OSDI_DIR}/psp103.osdi missing -- run PDK=${PDK} sim/tools/build-osdi.sh first." >&2
  exit 3
fi
command -v klt >/dev/null 2>&1 || { echo "run_e1op.sh: klt not on PATH." >&2; exit 3; }

# name mos_section res_section temp_c load_a cout_f   (DR-0015 P1/P2/P5/P6)
POINTS=(
  "P1 mos_ss res_bcs 125  0     1u"
  "P2 mos_ff res_wcs -40 0     1u"
  "P5 mos_ss res_wcs 125  0     3.45u"
  "P6 mos_ss res_bcs 125  0.001 1u"
)
# Point ids in the campaign convention
# e1op_dyn_<mos>_<temp>c_r<res>_i<load>ua_c<cout>nf_e0mohm (same token shape
# dynamic_doe.py uses; Cout tokenized in nF, load in uA, ESR = 0).
PIDS=()
for _p in "${POINTS[@]}"; do
  read -r _name mos res temp load_a cout_f <<< "${_p}"
  PIDS+=("$(python3 - "${mos}" "${res}" "${temp}" "${load_a}" "${cout_f}" <<'PYEOF'
import sys
mos, res, temp, load_a, cout_f = sys.argv[1:6]
print(f"e1op_dyn_{mos.replace('mos_', '')}_{temp}c_r{res.replace('res_', '')}_"
      f"i{int(round(float(load_a) * 1e6))}ua_c"
      f"{int(round(float(cout_f.rstrip('u')) * 1000))}nf_e0mohm")
PYEOF
)")
done
# The wrdata token contract the template declares must equal the reducer's
# QUANTITIES list (deck and reducer cannot drift silently).
diff <(sed -n 's/^wrdata \S* //p' "${SCRIPT_DIR}/testbench/tb_e1op_cmos5l.spice.tmpl" | tr ' ' '\n' | grep -v '^$') \
     <(python3 "${SCRIPT_DIR}/e1_oppoints.py" tokens) >/dev/null || {
  echo "run_e1op.sh: tb_e1op template wrdata tokens != e1_oppoints.py QUANTITIES." >&2
  exit 3
}

render_deck() {  # <mos> <res> <temp> <load_a> <cout_f> <out> <csv>
  local mos="$1" res="$2" temp="$3" load_a="$4" cout_f="$5" out="$6" csv="$7"
  sed \
    -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
    -e "s|@@PDK@@|${PDK}|g" \
    -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
    -e "s|@@MOS_SECTION@@|${mos}|g" \
    -e "s|@@RES_SECTION@@|${res}|g" \
    -e "s|@@CAP_SECTION@@|cap_typ|g" \
    -e "s|@@TEMP@@|${temp}|g" \
    -e "s|@@CC_W@@|170u (nominal)|g" \
    -e "s|@@DESIGN_NETLIST@@|${DESIGN_NETLIST}|g" \
    -e "s|@@LOAD_A@@|${load_a}|g" \
    -e "s|@@COUT_F@@|${cout_f}|g" \
    -e "s|@@COUT_BOTTOM@@|0|g" \
    -e "s|@@ESR_LINE@@|* ESR=0: Cout wired directly to ground (all four E1 points)|g" \
    -e "s|@@DC_CSV@@|${csv}|g" \
    "${SCRIPT_DIR}/testbench/tb_e1op_cmos5l.spice.tmpl" > "${out}"
}

point_field() {  # <index> <field 2..6: mos res temp load_a cout_f>
  local -a f
  read -r _name f2 f3 f4 f5 f6 <<< "${POINTS[$1]}"
  case "$2" in
    2) echo "${f2}" ;; 3) echo "${f3}" ;; 4) echo "${f4}" ;; 5) echo "${f5}" ;;
    6) echo "${f6}" ;;
  esac
}

# --------------------------------------------------------------------------- #
# --validate: ONE single-corner deck at tt/27C, run LOCALLY (a debug probe,
# not a grid), screened in-place BEFORE any fleet submission.
# --------------------------------------------------------------------------- #
if [[ ${VALIDATE} -eq 1 ]]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "${TMP}"' EXIT
  echo "run_e1op.sh: --validate: one tt/27C deck at 1 mA / 1 uF in ${TMP}"
  render_deck mos_tt res_typ 27 0.001 1u "${TMP}/val_e1op.spice" "${TMP}/val_e1op_dc.csv"
  ngspice -b "${TMP}/val_e1op.spice" > "${TMP}/val_e1op.log" 2>&1 || {
    echo "run_e1op.sh: --validate: ngspice FAILED -- see ${TMP}/val_e1op.log" >&2
    exit 1
  }
  vout_op="$(sed -n 's/^E1OP_VOUT_OP //p' "${TMP}/val_e1op.log")"
  python3 - "${vout_op}" <<'PYEOF' || exit 1
import sys
v = sys.argv[1] if len(sys.argv) > 1 else ""
if not v or not (1.7 <= float(v) <= 1.9):
    sys.exit(f"validate: VOUT op {v!r} outside the 1.7-1.9 V regulation band")
PYEOF
  python3 "${SCRIPT_DIR}/e1_oppoints.py" check-export "${TMP}/val_e1op_dc.csv"
  echo "run_e1op.sh: --validate OK (VOUT op ${vout_op} V)"
  exit 0
fi

# --------------------------------------------------------------------------- #
# batch campaign: render + queue the four points, submit via batch_backend.py,
# screen, reduce, write the record.
# --------------------------------------------------------------------------- #
REPO_GIT_SHA="$(cd "${REPO_ROOT}" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"
EXPERIMENT_DIR="${SCRIPT_DIR}"
SNAPSHOTS_OUT="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
CORNERS_OUT="${EXPERIMENT_DIR}/corners/${RECORD_ID}"
RECORDS_DIR="${EXPERIMENT_DIR}/records"
EVIDENCE_DIR="${EXPERIMENT_DIR}/evidence/${RECORD_ID}"
OUT_CSV="${RECORDS_DIR}/${RECORD_ID}.e1op.csv"
OUT_JSON="${EVIDENCE_DIR}/e1op-report.json"
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.e1op.md"
MANIFEST="${RECORDS_DIR}/${RECORD_ID}.e1op.manifest.tsv"
mkdir -p "${SNAPSHOTS_OUT}" "${CORNERS_OUT}" "${EVIDENCE_DIR}"

BATCH_WORK="$(mktemp -d "${TMPDIR:-/tmp}/ldo-cmos5l-e1op.XXXXXX")"
BATCH_QUEUE="${BATCH_WORK}/queue.tsv"
: > "${BATCH_QUEUE}"

for i in "${!POINTS[@]}"; do
  pid="${PIDS[$i]}"
  netlist="${SNAPSHOTS_OUT}/${pid}.spice"
  csv="${CORNERS_OUT}/${pid}_dc.csv"
  render_deck "$(point_field "${i}" 2)" "$(point_field "${i}" 3)" \
    "$(point_field "${i}" 4)" "$(point_field "${i}" 5)" "$(point_field "${i}" 6)" \
    "${netlist}" "${csv}"
  printf '%s\t%s\n' "${pid}" "${netlist}" >> "${BATCH_QUEUE}"
done
echo "run_e1op.sh: queued $(wc -l < "${BATCH_QUEUE}") points (DR-0015 P1/P2/P5/P6): ${PIDS[*]}"

if [[ -n "${SWEEP_BATCH_PLAN_ONLY:-}" ]]; then
  python3 "${SCRIPT_DIR}/batch_backend.py" run --queue "${BATCH_QUEUE}" \
    --corners-out "${CORNERS_OUT}" --work "${BATCH_WORK}" --osdi-dir "${OSDI_DIR}" \
    --variant-lines '^(Iload|Cout|Resr) ' --plan-only
  echo "run_e1op.sh: SWEEP_BATCH_PLAN_ONLY set -- plan printed, nothing submitted;" >&2
  echo "run_e1op.sh: delete ${SNAPSHOTS_OUT} and ${CORNERS_OUT} by hand." >&2
  exit 0
fi

batch_rc=0
python3 "${SCRIPT_DIR}/batch_backend.py" run \
  --queue "${BATCH_QUEUE}" --corners-out "${CORNERS_OUT}" \
  --work "${BATCH_WORK}" --osdi-dir "${OSDI_DIR}" \
  --variant-lines '^(Iload|Cout|Resr) ' \
  ${SWEEP_BATCH_REUSE_WORK:+--reuse-work "${SWEEP_BATCH_REUSE_WORK}"} || batch_rc=$?
if [[ ${batch_rc} -ne 0 ]]; then
  echo "run_e1op.sh: batch_backend.py exited ${batch_rc}; the affected points are screened as FAILED below." >&2
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
  log="${CORNERS_OUT}/${pid}.log"
  csv="${CORNERS_OUT}/${pid}_dc.csv"
  if [[ -f "${log}" ]] \
     && ! grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error|gmin stepping failed|no convergence|iteration limit reached|no writable vector" "${log}" \
     && python3 "${SCRIPT_DIR}/e1_oppoints.py" check-export "${csv}" >/dev/null 2>&1; then
    passed=$((passed + 1))
  else
    echo "run_e1op.sh: FAILED ${pid} -- see ${log}" >&2
    failed_points+=("${pid}")
  fi
done < "${BATCH_QUEUE}"

if [[ ${passed} -eq 0 ]]; then
  echo "run_e1op.sh: no points passed screening -- refusing to reduce or write a record." >&2
  exit 1
fi

# --- Reduction + record ------------------------------------------------------ #
reduce_rc=0
python3 "${SCRIPT_DIR}/e1_oppoints.py" reduce --record "${RECORD_ID}" \
  --corners-dir "${CORNERS_OUT}" --out-csv "${OUT_CSV}" --out-json "${OUT_JSON}" || reduce_rc=$?

# --- Manifest (house columns; per-point provenance) -------------------------- #
# Written BEFORE record-md: the record's provenance section quotes this
# manifest's pdk column, so the manifest must exist when the md is rendered.
{
  printf 'bench\tpoint_id\tmos\tres\ttemp_c\tload_a\tcout_f\tesr_ohm\tnetlist\tnetlist_sha256\tinvocation\tgit_sha\tpdk\tngspice\n'
  for i in "${!POINTS[@]}"; do
    pid="${PIDS[$i]}"
    netlist="${SNAPSHOTS_OUT}/${pid}.spice"
    sha="$(sha256sum "${netlist}" | cut -d' ' -f1)"
    group="$(ls "${CORNERS_OUT}/_batch/" | grep '^g[0-9]' | head -1)"
    invocation="klt sim --backend batch corners/${RECORD_ID}/_batch/${group}/request.json (batch_backend.py; corner $(point_field "${i}" 2)__$(point_field "${i}" 3)__cap_typ @ $(point_field "${i}" 4)C)"
    printf 'e1op\t%s\t%s\t%s\t%s\t%s\t%s\t0\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "${pid}" \
      "$(point_field "${i}" 2)" "$(point_field "${i}" 3)" "$(point_field "${i}" 4)" \
      "$(point_field "${i}" 5)" "$(point_field "${i}" 6)" \
      "${netlist#"${REPO_ROOT}/"}" "${sha}" "${invocation}" \
      "${REPO_GIT_SHA}" "${PDK} ${PDK_PIN_FOUND}" \
      "${BATCH_NGSPICE_VERSION:-unknown}"
  done
} > "${MANIFEST}"

python3 "${SCRIPT_DIR}/e1_oppoints.py" record-md --record "${RECORD_ID}"

echo "run_e1op.sh: record ${RECORD_ID}: ${passed}/${total} points passed screening (${NGSPICE_VERSION});"
echo "run_e1op.sh:   reduction ${OUT_CSV}"
echo "run_e1op.sh:   record    ${MD_OUT}"
echo "run_e1op.sh:   manifest  ${MANIFEST}"

if [[ ${#failed_points[@]} -gt 0 || ${batch_rc} -ne 0 ]]; then
  exit 1
fi
if [[ ${reduce_rc} -ne 0 ]]; then
  echo "run_e1op.sh: reduction reported failed checks (exit ${reduce_rc}) -- the record is" >&2
  echo "run_e1op.sh: written but marked INCOMPLETE; see ${OUT_JSON} failed_checks." >&2
  exit "${reduce_rc}"
fi
exit 0
