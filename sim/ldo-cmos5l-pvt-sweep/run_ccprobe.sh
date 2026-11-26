#!/usr/bin/env bash
# E3 Cc-width probe at P3 (issue #219) -- DR-0015 experiment E3.
#
#   sim/ldo-cmos5l-pvt-sweep/run_ccprobe.sh                    # batch fleet
#   sim/ldo-cmos5l-pvt-sweep/run_ccprobe.sh --validate         # local, 1 deck
#   sim/ldo-cmos5l-pvt-sweep/run_ccprobe.sh --plan-only
#
# DR-0015's class-2 mechanism attributes the heavy-load stability misses to a
# third pole inside the loop bandwidth but leaves the attribution between the
# compensation network and the EAOUT gate node unquantified ("E3 separates
# the two"). This campaign is exactly E3, and nothing more: THREE loop-gain
# runs at DR-0015's P3 (ff / -40 C / res_wcs, 50 mA, 0.33 uF, 0 mohm) with
# the compensation capacitor Cc at 0.5x / 1x / 2x of its committed width
# (DR-0005's own sensitivity levels, and the same table run_sweep.sh's
# tt/27C `loopgain_ccsens_*` points use -- those run at the LEGACY operating
# point, which is precisely the gap E3 names: P3 differs in corner AND
# operating point). The override is a substituted COPY of the design netlist
# (only XCc's w= token changes, via ccprobe.py subst -- the unit-tested
# Python mirror of run_sweep.sh's subst_cc_width, FATALing on drift instead
# of silently simulating the nominal netlist three times); the committed
# netlists under design/sg13cmos5l/netlist/ stay byte-unchanged, and the 1x
# copy is byte-identical to them. No spec row, threshold, verdict or record
# is touched: sim/ stays append-only and DR-0015 stays Proposed.
#
# Each run uses the SAME batch-backend fleet path as run_sweep.sh --batch,
# run_loopgain2.sh and run_e1op.sh. The three decks differ in their
# `.include`d design-netlist copy (the Cc width lives inside the included
# netlist, so --variant-lines cannot hoist it into a shared corners.lib),
# which means THREE request groups = THREE fleet jobs. That is expected;
# do not try to force one request.
#
# The loop-gain AC ceiling is FIXED at run_sweep.sh's default (100meg, via
# ac_sweep.py) rather than taken as an input: the campaign's like-for-like
# gate compares the 1x trace against the committed same-vintage baseline
# (record 20261012-074813-c94873ba's P3 row) which ran exactly this analysis
# line, so a configurable ceiling would quietly break that comparison's
# like-for-like premise. P3's whole structure (both 0 dB crossings, the
# critical-line crossing at 1.159 MHz) sits far below 100 MHz.
#
# This script never launches a local ngspice GRID: --validate runs exactly
# ONE single-corner deck locally (a debug probe, not a grid -- the 0.5x
# render at P3, so a substitution bug fails here rather than on the fleet);
# the three campaign points run only on the batch fleet, and a failed
# submission is reported as such -- never a local fallback.
#
# Environment (same conventions as run_loopgain2.sh / run_e1op.sh):
#   SWEEP_BATCH_PLAN_ONLY      parse + group + print the plan, submit nothing
#   SWEEP_BATCH_REUSE_WORK     an earlier --work dir for byte-identical
#                              request reuse (interruption recovery)
set -euo pipefail

VALIDATE=0
for arg in "$@"; do
  case "${arg}" in
    --validate) VALIDATE=1 ;;
    --plan-only) export SWEEP_BATCH_PLAN_ONLY=1 ;;
    -h|--help) sed -n '2,52p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "run_ccprobe.sh: unknown argument '${arg}'" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
DESIGN_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"
ERRAMP_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice"

# The AC ceiling is fixed (see header); ac_sweep.py owns the numbers.
LG_AC_MAX="$(python3 "${SCRIPT_DIR}/ac_sweep.py" ceiling 100meg)"
EXPECT_ROWS_LG="$(python3 "${SCRIPT_DIR}/ac_sweep.py" rows "${LG_AC_MAX}")"
LG_AC_LINE="$(python3 "${SCRIPT_DIR}/ac_sweep.py" line "${LG_AC_MAX}")"
if ! grep -qxF "ac dec 20 1 @@LG_AC_MAX@@" "${SCRIPT_DIR}/testbench/tb_loopgain_cmos5l.spice.tmpl"; then
  echo "run_ccprobe.sh: tb_loopgain_cmos5l.spice.tmpl no longer has 'ac dec 20 1 @@LG_AC_MAX@@'." >&2
  exit 3
fi

# The loop-gain template must still mirror ldo_core_cmos5l (positive
# assertion, cheap, no PDK). The negative controls live in run_sweep.sh
# --check-topology-guard (CI).
"${SCRIPT_DIR}/run_sweep.sh" --check-topology

# The width table this driver substitutes with comes from ccprobe.py (the
# unit-tested contract); refuse to run if it has drifted from run_sweep.sh's
# own Cc block or from the committed design netlist's XCc line -- the drift
# guards proper live in test_ccprobe.py (CI), this one is the cheap runtime
# re-assertion.
python3 - "${SCRIPT_DIR}" <<'PYEOF' || exit 3
import sys
sys.path.insert(0, sys.argv[1])
import test_ccprobe  # noqa: F401  (importing runs nothing; calls below do)
test_ccprobe.width_table_matches_run_sweep()
test_ccprobe.nominal_width_tracks_design_netlist()
print("run_ccprobe.sh: Cc contract re-asserted against run_sweep.sh + design netlist")
PYEOF

export PDK=ihp-sg13cmos5l
# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/tools/preflight.sh"

if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_ccprobe.sh: no resolvable ${PDK} install -- see sim/env.sh output above." >&2
  exit 3
fi
# Fail closed on a PDK-pin mismatch: the record's provenance must describe
# the install that ACTUALLY ran. Same posture as run_e1op.sh's pin check,
# with one addition: a fleet-synced install (2am fleet PDK bundle) carries
# its recorded commit in .pdk-store.json's "version" instead of the fetch
# script's .fetched-version marker -- same pin contract, different marker
# writer. A superseded install still refuses to run.
PDK_PIN_EXPECTED="$(python3 -c 'import json; print(json.load(open("'"${SIM_DIR}"'/pdk-cmos5l.json"))["pinned_commit"])')"
if [[ -f "${PDK_ROOT}/${PDK}/.fetched-version" ]]; then
  PDK_PIN_FOUND="$(cat "${PDK_ROOT}/${PDK}/.fetched-version")"
elif [[ -d "${PDK_ROOT}/${PDK}/.git" ]]; then
  PDK_PIN_FOUND="$(git -C "${PDK_ROOT}/${PDK}" rev-parse HEAD)"
elif [[ -f "${PDK_ROOT}/${PDK}/.pdk-store.json" ]]; then
  PDK_PIN_FOUND="$(python3 -c 'import json; print(json.load(open("'"${PDK_ROOT}/${PDK}/.pdk-store.json"'"))["version"])')"
else
  PDK_PIN_FOUND=""
fi
if [[ "${PDK_PIN_FOUND}" != "${PDK_PIN_EXPECTED}" ]]; then
  echo "run_ccprobe.sh: ${PDK} install at PDK_ROOT=${PDK_ROOT} is '${PDK_PIN_FOUND:-unidentified}'," >&2
  echo "run_ccprobe.sh:   but sim/pdk-cmos5l.json pins ${PDK_PIN_EXPECTED} -- refusing to run." >&2
  echo "run_ccprobe.sh:   E3 evidence must come from the pinned install (scripts/fetch-ihp-sg13cmos5l.sh);" >&2
  echo "run_ccprobe.sh:   point PDK_ROOT at it and re-run." >&2
  exit 3
fi
echo "run_ccprobe.sh: ${PDK} install verified at the pinned commit ${PDK_PIN_FOUND}"
OSDI_DIR="${SG13G2_OSDI_DIR}"

if [[ ! -f "${DESIGN_NETLIST}" || ! -f "${ERRAMP_NETLIST}" ]]; then
  echo "run_ccprobe.sh: design netlists not found -- regenerate them first:" >&2
  echo "run_ccprobe.sh:   python3 design/netlist.py --design sg13cmos5l" >&2
  exit 3
fi

# name cc_label   (DR-0015 E3: three runs at P3, Cc at 0.5x/1x/2x nominal)
POINTS=(
  "0.5x"
  "1x"
  "2x"
)
# P3's operating point, in the same ngspice syntax the templates and
# dynamic_doe.netlist_values use (DR-0015's six-points table, point P3).
P3_CORNER="ff"; P3_RES="wcs"; P3_TEMP="-40"; P3_LOAD_A="50000e-6"; P3_COUT_F="330n"

# point ids come straight from the contract module (cannot collide across
# the three labels; a drift there fails the campaign before any submit).
mapfile -t PIDS < <(python3 - "${SCRIPT_DIR}" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import ccprobe
for lab in ccprobe.CC_LABELS:
    print(ccprobe.point_id(lab))
PYEOF
)

render_deck() {  # <cc_label> <cc_netlist_copy> <out> <csv>
  local label="$1" cc_netlist="$2" out="$3" csv="$4"
  local cc_w_desc
  cc_w_desc="$(python3 - "${SCRIPT_DIR}" "${label}" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import ccprobe
print(ccprobe.cc_w_desc(sys.argv[2]))
PYEOF
)"
  sed \
    -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
    -e "s|@@PDK@@|${PDK}|g" \
    -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
    -e "s|@@MOS_SECTION@@|mos_${P3_CORNER}|g" \
    -e "s|@@RES_SECTION@@|res_${P3_RES}|g" \
    -e "s|@@CAP_SECTION@@|cap_typ|g" \
    -e "s|@@TEMP@@|${P3_TEMP}|g" \
    -e "s|@@LG_AC_MAX@@|${LG_AC_MAX}|g" \
    -e "s|@@CC_W@@|${cc_w_desc}|g" \
    -e "s|@@DESIGN_NETLIST@@|${cc_netlist}|g" \
    -e "s|@@LOAD_A@@|${P3_LOAD_A}|g" \
    -e "s|@@COUT_F@@|${P3_COUT_F}|g" \
    -e "s|@@COUT_BOTTOM@@|0|g" \
    -e "s|@@ESR_LINE@@|* ESR=0: Cout wired directly to ground (P3)|g" \
    -e "s|@@AC_CSV@@|${csv}|g" \
    "${SCRIPT_DIR}/testbench/tb_loopgain_cmos5l.spice.tmpl" > "${out}"
}

screen_point() {  # <point_id> -- exit 0 iff log clean AND export complete
  local point_id="$1"
  local log="${CORNERS_OUT}/${point_id}.log"
  local csv="${CORNERS_OUT}/${point_id}_ac.csv"
  [[ -f "${log}" ]] || return 1
  # singular matrix: the shared single-pass predicate (singular_screen.py,
  # issue #383), same rule as run_sweep.sh's screen.
  if grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error|gmin stepping failed|no convergence|iteration limit reached" "${log}" \
     || ! python3 "${SCRIPT_DIR}/singular_screen.py" check-log "${log}"; then
    return 1
  fi
  python3 "${SCRIPT_DIR}/ac_sweep.py" check-trace "${csv}" "${LG_AC_MAX}" || return 1
  return 0
}

# --------------------------------------------------------------------------- #
# --validate: ONE single-corner deck (the 0.5x render at P3), run LOCALLY
# (a debug probe, not a grid), screened in-place BEFORE any fleet submission.
# --------------------------------------------------------------------------- #
if [[ ${VALIDATE} -eq 1 ]]; then
  if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
    echo "run_ccprobe.sh: OSDI models missing/unloadable -- run PDK=${PDK} sim/tools/build-osdi.sh first." >&2
    exit 3
  fi
  command -v ngspice >/dev/null 2>&1 || { echo "run_ccprobe.sh: ngspice not on PATH." >&2; exit 3; }
  TMP="$(mktemp -d)"
  trap 'rm -rf "${TMP}"' EXIT
  echo "run_ccprobe.sh: --validate: one P3 deck (Cc 0.5x) at ${LG_AC_LINE} in ${TMP}"
  python3 "${SCRIPT_DIR}/ccprobe.py" subst "${DESIGN_NETLIST}" "${TMP}/design_cc0.5x.spice" 0.5x
  render_deck 0.5x "${TMP}/design_cc0.5x.spice" "${TMP}/val_ccprobe.spice" "${TMP}/val_ccprobe_ac.csv"
  # The override must actually reach the deck: the rendered netlist names the
  # substituted copy (not the committed file) and carries the 0.5x width --
  # the negative case (a copy that still says w=170e-6) is ccprobe.py's
  # raise, exercised by test_ccprobe.py.
  grep -q "${TMP}/design_cc0.5x.spice" "${TMP}/val_ccprobe.spice" || {
    echo "run_ccprobe.sh: --validate: the deck does not include the substituted copy" >&2
    exit 1
  }
  grep -qF "XCc OUT MZ cap_cmomi w=85e-6 l=30e-6" "${TMP}/design_cc0.5x.spice" || {
    echo "run_ccprobe.sh: --validate: the substituted copy does not carry the 0.5x width" >&2
    exit 1
  }
  ngspice -b "${TMP}/val_ccprobe.spice" > "${TMP}/val_ccprobe.log" 2>&1 || {
    echo "run_ccprobe.sh: --validate: ngspice FAILED -- see ${TMP}/val_ccprobe.log" >&2
    exit 1
  }
  bad="$(python3 "${SCRIPT_DIR}/ac_sweep.py" check-trace "${TMP}/val_ccprobe_ac.csv" "${LG_AC_MAX}" || true)"
  if [[ -n "${bad}" ]]; then
    echo "run_ccprobe.sh: --validate: export screening failed: ${bad}" >&2
    exit 1
  fi
  vout_op="$(sed -n 's/^LOOPGAIN_VOUT_OP //p' "${TMP}/val_ccprobe.log")"
  python3 - "${vout_op}" <<'PYEOF' || exit 1
import sys
v = sys.argv[1] if len(sys.argv) > 1 else ""
if not v or not (1.7 <= float(v) <= 1.9):
    sys.exit(f"validate: VOUT op {v!r} outside the 1.7-1.9 V regulation band")
PYEOF
  echo "run_ccprobe.sh: --validate OK (VOUT op ${vout_op} V, Cc 0.5x reached the deck)"
  exit 0
fi

# --------------------------------------------------------------------------- #
# batch campaign: render + queue the three points, submit via batch_backend.py,
# screen, reduce, write the record.
# --------------------------------------------------------------------------- #
[[ -f "${OSDI_DIR}/psp103.osdi" ]] || {
  echo "run_ccprobe.sh: ${OSDI_DIR}/psp103.osdi missing -- run PDK=${PDK} sim/tools/build-osdi.sh first." >&2
  exit 3
}
command -v klt >/dev/null 2>&1 || { echo "run_ccprobe.sh: klt not on PATH." >&2; exit 3; }

REPO_GIT_SHA="$(cd "${REPO_ROOT}" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"
# The record file names come from the contract module (ccprobe.py check /
# record-md / _pdk_provenance all address records/<rid>.<BENCH>.*), never
# from a second copy of the tag here -- test_ccprobe.py asserts this.
BENCH="$(python3 - "${SCRIPT_DIR}" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import ccprobe
print(ccprobe.BENCH)
PYEOF
)"
EXPERIMENT_DIR="${SCRIPT_DIR}"
SNAPSHOTS_OUT="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
CORNERS_OUT="${EXPERIMENT_DIR}/corners/${RECORD_ID}"
RECORDS_DIR="${EXPERIMENT_DIR}/records"
EVIDENCE_DIR="${EXPERIMENT_DIR}/evidence/${RECORD_ID}"
OUT_CSV="${RECORDS_DIR}/${RECORD_ID}.${BENCH}.csv"
OUT_JSON="${EVIDENCE_DIR}/ccprobe-report.json"
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.${BENCH}.md"
MANIFEST="${RECORDS_DIR}/${RECORD_ID}.${BENCH}.manifest.tsv"
mkdir -p "${SNAPSHOTS_OUT}" "${CORNERS_OUT}" "${EVIDENCE_DIR}"

BATCH_WORK="$(mktemp -d "${TMPDIR:-/tmp}/ldo-cmos5l-ccprobe.XXXXXX")"
BATCH_QUEUE="${BATCH_WORK}/queue.tsv"
: > "${BATCH_QUEUE}"

for i in "${!POINTS[@]}"; do
  label="${POINTS[$i]}"
  pid="${PIDS[$i]}"
  cc_netlist="${SNAPSHOTS_OUT}/design_cc${label}.spice"
  # The substituted COPY (exit 4 = the substitution did not reach the deck:
  # the same FATAL run_sweep.sh's subst_cc_width carries). The committed
  # design netlist is never written; for 1x the copy is byte-identical to it.
  python3 "${SCRIPT_DIR}/ccprobe.py" subst "${DESIGN_NETLIST}" "${cc_netlist}" "${label}"
  netlist="${SNAPSHOTS_OUT}/${pid}.spice"
  csv="${CORNERS_OUT}/${pid}_ac.csv"
  render_deck "${label}" "${cc_netlist}" "${netlist}" "${csv}"
  printf '%s\t%s\n' "${pid}" "${netlist}" >> "${BATCH_QUEUE}"
done
echo "run_ccprobe.sh: queued $(wc -l < "${BATCH_QUEUE}") points (DR-0015 E3 at P3): ${PIDS[*]}"
echo "run_ccprobe.sh: the three decks differ in their .include'd design-netlist copy,"
echo "run_ccprobe.sh:   so expect THREE request groups (three fleet jobs) -- not one."

if [[ -n "${SWEEP_BATCH_PLAN_ONLY:-}" ]]; then
  python3 "${SCRIPT_DIR}/batch_backend.py" run --queue "${BATCH_QUEUE}" \
    --corners-out "${CORNERS_OUT}" --work "${BATCH_WORK}" --osdi-dir "${OSDI_DIR}" \
    --variant-lines '^(Iload|Cout|Resr) ' --plan-only
  echo "run_ccprobe.sh: SWEEP_BATCH_PLAN_ONLY set -- plan printed, nothing submitted;" >&2
  echo "run_ccprobe.sh: delete ${SNAPSHOTS_OUT} and ${CORNERS_OUT} by hand." >&2
  exit 0
fi

batch_rc=0
python3 "${SCRIPT_DIR}/batch_backend.py" run \
  --queue "${BATCH_QUEUE}" --corners-out "${CORNERS_OUT}" \
  --work "${BATCH_WORK}" --osdi-dir "${OSDI_DIR}" \
  --variant-lines '^(Iload|Cout|Resr) ' \
  ${SWEEP_BATCH_REUSE_WORK:+--reuse-work "${SWEEP_BATCH_REUSE_WORK}"} || batch_rc=$?
if [[ ${batch_rc} -ne 0 ]]; then
  echo "run_ccprobe.sh: batch_backend.py exited ${batch_rc}; the affected points are screened as FAILED below." >&2
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
  if screen_point "${pid}"; then
    passed=$((passed + 1))
  else
    echo "run_ccprobe.sh: FAILED ${pid} -- see ${CORNERS_OUT}/${pid}.log" >&2
    failed_points+=("${pid}")
  fi
done < "${BATCH_QUEUE}"

if [[ ${passed} -eq 0 ]]; then
  echo "run_ccprobe.sh: no points passed screening -- refusing to reduce or write a record." >&2
  exit 1
fi

# --- Reduction + record ------------------------------------------------------ #
reduce_rc=0
python3 "${SCRIPT_DIR}/ccprobe.py" reduce --record "${RECORD_ID}" \
  --corners-dir "${CORNERS_OUT}" --out-csv "${OUT_CSV}" --out-json "${OUT_JSON}" || reduce_rc=$?

# --- Manifest (house columns; per-point provenance) -------------------------- #
# Written BEFORE record-md: the record's provenance section quotes this
# manifest's pdk column, so the manifest must exist when the md is rendered.
{
  printf 'bench\tpoint_id\tcc_label\tcc_w\tmos\tres\ttemp_c\tload_a\tcout_f\tesr_ohm\tnetlist\tnetlist_sha256\tcc_netlist\tcc_netlist_sha256\tcommitted_netlist_unchanged\tinvocation\tgit_sha\tpdk\tngspice\n'
  for i in "${!POINTS[@]}"; do
    label="${POINTS[$i]}"
    pid="${PIDS[$i]}"
    netlist="${SNAPSHOTS_OUT}/${pid}.spice"
    cc_netlist="${SNAPSHOTS_OUT}/design_cc${label}.spice"
    sha="$(sha256sum "${netlist}" | cut -d' ' -f1)"
    ccsha="$(sha256sum "${cc_netlist}" | cut -d' ' -f1)"
    # AC 1's invariant, per point: the committed design netlist is byte-
    # unchanged (trivially true -- nothing writes it -- but asserted here so
    # the manifest itself carries the proof next to every substituted copy).
    if diff -q "${cc_netlist}" "${DESIGN_NETLIST}" >/dev/null 2>&1; then
      committed_unchanged="1x_byte_identical"
    else
      committed_unchanged="substituted_copy_only"
    fi
    # Each point lives in its OWN request group (the three decks differ in
    # their .included design-netlist copy): map the point to its group by
    # name, never assume all points share the first group's request.
    group=""
    for d in "${CORNERS_OUT}/_batch"/g[0-9]*_"${pid}"; do
      [[ -d "$d" ]] && { group="$(basename "$d")"; break; }
    done
    [[ -n "${group}" ]] || { echo "run_ccprobe.sh: no batch group for ${pid}" >&2; exit 1; }
    invocation="klt sim --backend batch corners/${RECORD_ID}/_batch/${group}/request.json (batch_backend.py; ${P3_CORNER}__${P3_RES}__cap_typ @ ${P3_TEMP}C, Cc ${label})"
    printf 'ccprobe\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t0\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "${pid}" "${label}" \
      "$(python3 - "${SCRIPT_DIR}" "${label}" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import ccprobe
print(ccprobe.cc_w(sys.argv[2]))
PYEOF
)" \
      "${P3_CORNER}" "${P3_RES}" "${P3_TEMP}" "${P3_LOAD_A}" "${P3_COUT_F}" \
      "${netlist#"${REPO_ROOT}/"}" "${sha}" \
      "${cc_netlist#"${REPO_ROOT}/"}" "${ccsha}" \
      "${committed_unchanged}" \
      "${invocation}" \
      "${REPO_GIT_SHA}" "${PDK} ${PDK_PIN_FOUND}" \
      "${BATCH_NGSPICE_VERSION:-unknown}"
  done
} > "${MANIFEST}"

python3 "${SCRIPT_DIR}/ccprobe.py" record-md --record "${RECORD_ID}"

echo "run_ccprobe.sh: record ${RECORD_ID}: ${passed}/${total} points passed screening (${NGSPICE_VERSION});"
echo "run_ccprobe.sh:   reduction ${OUT_CSV}"
echo "run_ccprobe.sh:   record    ${MD_OUT}"
echo "run_ccprobe.sh:   manifest  ${MANIFEST}"

if [[ ${#failed_points[@]} -gt 0 || ${batch_rc} -ne 0 ]]; then
  exit 1
fi
if [[ ${reduce_rc} -ne 0 ]]; then
  echo "run_ccprobe.sh: reduction reported failed checks (exit ${reduce_rc}) -- the record is" >&2
  echo "run_ccprobe.sh: written but marked INCOMPLETE; see ${OUT_JSON} failed_checks." >&2
  exit "${reduce_rc}"
fi
exit 0
