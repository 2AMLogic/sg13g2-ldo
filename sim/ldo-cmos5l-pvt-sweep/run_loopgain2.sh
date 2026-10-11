#!/usr/bin/env bash
# Two-injection (Middlebrook) loop-gain comparison campaign (issue #135).
#
#   sim/ldo-cmos5l-pvt-sweep/run_loopgain2.sh                    # batch fleet
#   sim/ldo-cmos5l-pvt-sweep/run_loopgain2.sh --validate         # local, nominal only
#   sim/ldo-cmos5l-pvt-sweep/run_loopgain2.sh --loopgain-ac-max=10g
#
# A focused campaign (NOT another full sweep): at every point of the same
# 45-point PVT grid as record 20261011-070111-5391c68 (5 MOS corners x
# 3 temperatures x 3 resistor corners, legacy operating point 1 mA / 1 uF /
# 0 ohm, EN tied to VIN), it runs THREE decks through the SAME batch-backend
# path as run_sweep.sh --batch:
#
#   loopgain_ctl_<point>   tb_loopgain_cmos5l.spice.tmpl   single-injection
#                          CONTROL on today's design bytes: the like-for-like
#                          baseline (the historical record's trace is also
#                          cross-checked in the record md) and the validation
#                          target the two-injection reconstruction must
#                          reproduce in-band.
#   loopgain2v_<point>     tb_loopgain2v_cmos5l.spice.tmpl  voltage injection:
#                          the same break, exporting the RAW COMPLEX probe
#                          responses v(fb), v(fbamp).
#   loopgain2i_<point>     tb_loopgain2i_cmos5l.spice.tmpl  current injection:
#                          loop intact behind a 0 V ammeter, shunt AC current
#                          into the driven side (FBAMP).
#
# loopgain2.py then reconstructs Middlebrook's general (bilateral) loop gain
# T = (Tv*Ti - 1)/(Tv + Ti + 2) per frequency (Tv = -v(fb)/v(fbamp),
# Ti = -i_m/(1 + i_m); L = T in this repo's convention), bounds its
# export-rounding resolution per frequency, validates every point against
# its control under the tolerances stated in loopgain2.py's header, writes
# the RESOLVED PREFIX of each trace in the classic 4-column layout, and
# emits the comparison CSV + diagnostics JSON + record md.
# row10_loopgain2.py classifies the traces under the UNCHANGED DR-0014
# rules (a trace truncated below the ceiling is reported ambiguous).
# Nothing here edits a threshold, a ceiling rule or a historical record;
# sim/ stays append-only.
#
# The AC ceiling is the same validated runner input as run_sweep.sh's
# (--loopgain-ac-max / SWEEP_LOOPGAIN_AC_MAX; default here 10g -- the whole
# point of this campaign is the behaviour above the in-band crossing, and
# 10 GHz is the baseline record's axis). ac_sweep.py validates it.
#
# This script never launches a local ngspice GRID: --validate runs exactly
# three single-corner decks at tt/27C (a debug probe, not a grid); the
# 45-point campaign runs only on the batch fleet, and a failed submission is
# reported as such -- never a local fallback.
#
# Environment (same conventions as run_sweep.sh --batch):
#   SWEEP_BATCH_CONCURRENCY    klt requests in flight (default 2)
#   SWEEP_BATCH_PLAN_ONLY      parse + group + print the plan, submit nothing
#   SWEEP_BATCH_REUSE_WORK     an earlier --work dir for byte-identical
#                              request reuse (interruption recovery)
set -euo pipefail

VALIDATE=0
LOOPGAIN_AC_MAX="${SWEEP_LOOPGAIN_AC_MAX:-10g}"
for arg in "$@"; do
  case "${arg}" in
    --validate) VALIDATE=1 ;;
    --loopgain-ac-max=*) LOOPGAIN_AC_MAX="${arg#--loopgain-ac-max=}" ;;
    -h|--help) sed -n '2,53p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "run_loopgain2.sh: unknown argument '${arg}'" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
DESIGN_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"
ERRAMP_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice"

# Validate + canonicalise the ceiling before anything else runs.
LG_AC_MAX="$(python3 "${SCRIPT_DIR}/ac_sweep.py" ceiling "${LOOPGAIN_AC_MAX}")" || {
  echo "run_loopgain2.sh: invalid --loopgain-ac-max / SWEEP_LOOPGAIN_AC_MAX '${LOOPGAIN_AC_MAX}'." >&2
  exit 2
}
EXPECT_ROWS_LG="$(python3 "${SCRIPT_DIR}/ac_sweep.py" rows "${LG_AC_MAX}")"
LG_AC_LINE="$(python3 "${SCRIPT_DIR}/ac_sweep.py" line "${LG_AC_MAX}")"
for tmpl in loopgain loopgain2v loopgain2i; do
  if ! grep -qxF "ac dec 20 1 @@LG_AC_MAX@@" "${SCRIPT_DIR}/testbench/tb_${tmpl}_cmos5l.spice.tmpl"; then
    echo "run_loopgain2.sh: tb_${tmpl}_cmos5l.spice.tmpl no longer has 'ac dec 20 1 @@LG_AC_MAX@@'." >&2
    exit 3
  fi
done

# The three templates must still mirror ldo_core_cmos5l (positive assertion,
# cheap, no PDK). The negative controls live in run_sweep.sh
# --check-topology-guard (CI).
"${SCRIPT_DIR}/run_sweep.sh" --check-topology

export PDK=ihp-sg13cmos5l
# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/tools/preflight.sh"

if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_loopgain2.sh: no resolvable ${PDK} install -- see sim/env.sh output above." >&2
  exit 3
fi
OSDI_DIR="${SG13G2_OSDI_DIR}"

if [[ ! -f "${DESIGN_NETLIST}" || ! -f "${ERRAMP_NETLIST}" ]]; then
  echo "run_loopgain2.sh: design netlists not found -- regenerate them first:" >&2
  echo "run_loopgain2.sh:   python3 design/netlist.py --design sg13cmos5l" >&2
  exit 3
fi

# Rendering: the same substitution set run_sweep.sh's gen_netlist applies,
# at the legacy operating point (1 mA / 1 uF / 0 ohm; ESR=0 comment).
# The control bench reuses the single-injection template verbatim; only its
# point-id prefix (loopgain_ctl_) differs, so the three benches' exports
# never collide in one corners dir.
render_deck() {  # <bench> <mos_section> <res_section> <temp> <out> <csv>
  local bench="$1" mos="$2" res="$3" temp="$4" out="$5" csv="$6"
  local tmpl="tb_${bench}_cmos5l.spice.tmpl"
  [[ "${bench}" == "loopgain_ctl" ]] && tmpl="tb_loopgain_cmos5l.spice.tmpl"
  sed \
    -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
    -e "s|@@PDK@@|${PDK}|g" \
    -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
    -e "s|@@MOS_SECTION@@|${mos}|g" \
    -e "s|@@RES_SECTION@@|${res}|g" \
    -e "s|@@CAP_SECTION@@|cap_typ|g" \
    -e "s|@@TEMP@@|${temp}|g" \
    -e "s|@@LG_AC_MAX@@|${LG_AC_MAX}|g" \
    -e "s|@@CC_W@@|170u (nominal)|g" \
    -e "s|@@DESIGN_NETLIST@@|${DESIGN_NETLIST}|g" \
    -e "s|@@LOAD_A@@|0.001|g" \
    -e "s|@@COUT_F@@|1u|g" \
    -e "s|@@COUT_BOTTOM@@|0|g" \
    -e "s|@@ESR_LINE@@|* ESR=0: Cout wired directly to ground (campaign default)|g" \
    -e "s|@@AC_CSV@@|${csv}|g" \
    "${SCRIPT_DIR}/testbench/${tmpl}" > "${out}"
}

CORNERS=(tt ss ff sf fs)
TEMPS=(-40 27 125)
RES_LABELS=(typ bcs wcs)
BENCHES=(loopgain_ctl loopgain2v loopgain2i)
# Columns each bench's wrdata export promises (screening; loopgain2.py
# re-validates the content on reconstruction).
declare -A BENCH_COLS=( [loopgain_ctl]=4 [loopgain2v]=8 [loopgain2i]=4 )

screen_point() {  # <point_id> -- exit 0 iff log clean AND export complete
  local point_id="$1"
  local log="${CORNERS_OUT}/${point_id}.log"
  local csv="${CORNERS_OUT}/${point_id}_ac.csv"
  local bench="${point_id%%_[a-z][a-z]_*}"
  [[ -f "${log}" ]] || return 1
  if grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error|gmin stepping failed|no convergence|iteration limit reached" "${log}" \
     || grep -iE "singular matrix" "${log}" | grep -qivE "^[[:space:]]*Warning:"; then
    return 1
  fi
  python3 "${SCRIPT_DIR}/loopgain2.py" check-export "${csv}" "${BENCH_COLS[${bench}]}" "${LG_AC_MAX}" || return 1
  return 0
}

# --------------------------------------------------------------------------- #
# --validate: three single-corner decks at tt/27C, run LOCALLY (a debug
# probe, not a grid), reconstructed and checked against the stated
# tolerances BEFORE any fleet submission. Also proves the DC operating point
# is unchanged across the three benches (the op echo each deck writes).
# --------------------------------------------------------------------------- #
if [[ ${VALIDATE} -eq 1 ]]; then
  if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
    echo "run_loopgain2.sh: OSDI models missing/unloadable -- run PDK=${PDK} sim/tools/build-osdi.sh first." >&2
    exit 3
  fi
  command -v ngspice >/dev/null 2>&1 || { echo "run_loopgain2.sh: ngspice not on PATH." >&2; exit 3; }
  TMP="$(mktemp -d)"
  trap 'rm -rf "${TMP}"' EXIT
  echo "run_loopgain2.sh: --validate: three tt/27C decks at ${LG_AC_LINE} in ${TMP}"
  for bench in "${BENCHES[@]}"; do
    pid="val_${bench}"
    render_deck "${bench}" mos_tt res_typ 27 "${TMP}/${pid}.spice" "${TMP}/${pid}_ac.csv"
    ngspice -b "${TMP}/${pid}.spice" > "${TMP}/${pid}.log" 2>&1 || {
      echo "run_loopgain2.sh: --validate: ngspice FAILED on ${pid} -- see ${TMP}/${pid}.log" >&2
      exit 1
    }
    rows="$(wc -l < "${TMP}/${pid}_ac.csv")"
    [[ ${rows} -eq ${EXPECT_ROWS_LG} ]] || {
      echo "run_loopgain2.sh: --validate: ${pid}: ${rows} rows, expected ${EXPECT_ROWS_LG}" >&2
      exit 1
    }
  done
  # DC operating point identity across the three decks (echoed by each op).
  vout_ops=()
  for bench in "${BENCHES[@]}"; do
    vout_ops+=("$(sed -n "s/^LOOPGAIN[A-Z0-9_]*_VOUT_OP //p" "${TMP}/val_${bench}.log")")
  done
  echo "run_loopgain2.sh: --validate: VOUT op per deck: ${vout_ops[*]}"
  python3 - "${TMP}" <<'PYEOF'
import math, sys
tmp = sys.argv[1]
ops = []
for b in ("loopgain_ctl", "loopgain2v", "loopgain2i"):
    v = None
    for ln in open(f"{tmp}/val_{b}.log"):
        if "_VOUT_OP " in ln:
            v = float(ln.split()[-1])
    ops.append(v)
spread = (max(ops) - min(ops)) if all(v is not None for v in ops) else float("nan")
print(f"validate: DC VOUT op spread across the three decks: {spread:.3g} V")
if not (spread <= 1e-6):
    sys.exit(f"validate: DC operating point moved across the decks ({ops}); the benches are not bias-matched")
PYEOF
  # Reconstruction + the stated tolerance checks (loopgain2.py is strict).
  python3 - "${SCRIPT_DIR}" "${TMP}" <<'PYEOF'
import sys
script_dir, tmp = sys.argv[1], sys.argv[2]
sys.path.insert(0, script_dir)
import loopgain2 as lg2
import ac_metrics as am

rec = lg2.reconstruct(f"{tmp}/val_loopgain2v_ac.csv", f"{tmp}/val_loopgain2i_ac.csv")
x = lg2.validate_against_control(rec, f"{tmp}/val_loopgain_ctl_ac.csv")
combined = f"{tmp}/val_loopgain2_ac.csv"
lg2.write_loopgain_trace(combined, rec["freqs"][:rec["cut"]], rec["T"][:rec["cut"]])
lg2m = am.loopgain_metrics(combined)
ctlm = am.loopgain_metrics(f"{tmp}/val_loopgain_ctl_ac.csv")
d = rec["diag"]
print(f"validate: resolved to {d['resolved_to_hz']:.3g} Hz; {d['n_resolved_above_cut']} resolved "
      f"samples above the cut; bound above the cut {d['bound_db_above_cut']} dB")
print(f"validate: Tv-vs-control identity {x['v2ctl_max_rel_diff']:.3g} (tol {lg2.TOL_DECK_IDENTITY:g}); "
      f"LF agreement {x['lf_agree_max_rel']:.3g} (tol {lg2.TOL_LF_AGREE:g})")
print(f"validate: control : PM {ctlm['phase_margin_deg']:.2f} deg, GM {ctlm['gain_margin_db']:.2f} dB, "
      f"{ctlm['n_0db_crossings']} 0 dB crossings, UGF {ctlm['unity_gain_freq_hz']:.4g} Hz")
print(f"validate: Middlebrook T : PM {lg2m['phase_margin_deg']:.2f} deg, GM {lg2m['gain_margin_db']:.2f} dB, "
      f"{lg2m['n_0db_crossings']} 0 dB crossings, UGF {lg2m['unity_gain_freq_hz']:.4g} Hz")
PYEOF
  echo "run_loopgain2.sh: --validate OK (all loopgain2.py tolerances held)"
  exit 0
fi

# --------------------------------------------------------------------------- #
# batch campaign: render + queue 45 x 3 decks, submit via batch_backend.py,
# screen, reconstruct, compare, classify, write the record.
# --------------------------------------------------------------------------- #
[[ -f "${OSDI_DIR}/psp103.osdi" ]] || {
  echo "run_loopgain2.sh: ${OSDI_DIR}/psp103.osdi missing -- run PDK=${PDK} sim/tools/build-osdi.sh first." >&2
  exit 3
}
command -v klt >/dev/null 2>&1 || { echo "run_loopgain2.sh: klt not on PATH." >&2; exit 3; }

REPO_GIT_SHA="$(cd "${REPO_ROOT}" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"
EXPERIMENT_DIR="${SCRIPT_DIR}"
SNAPSHOTS_OUT="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
CORNERS_OUT="${EXPERIMENT_DIR}/corners/${RECORD_ID}"
RECORDS_DIR="${EXPERIMENT_DIR}/records"
EVIDENCE_DIR="${EXPERIMENT_DIR}/evidence/${RECORD_ID}"
CMP_CSV="${RECORDS_DIR}/${RECORD_ID}.loopgain2.csv"
CMP_JSON="${EVIDENCE_DIR}/loopgain2-report.json"
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.loopgain2.md"
mkdir -p "${SNAPSHOTS_OUT}" "${CORNERS_OUT}" "${EVIDENCE_DIR}"

BATCH_WORK="$(mktemp -d "${TMPDIR:-/tmp}/ldo-cmos5l-loopgain2.XXXXXX")"
BATCH_QUEUE="${BATCH_WORK}/queue.tsv"
: > "${BATCH_QUEUE}"

for corner in "${CORNERS[@]}"; do
  for temp in "${TEMPS[@]}"; do
    for rlabel in "${RES_LABELS[@]}"; do
      mos_section="mos_${corner}"
      res_section="res_${rlabel}"
      for bench in "${BENCHES[@]}"; do
        point_id="${bench}_${corner}_${temp}c_r${rlabel}"
        netlist="${SNAPSHOTS_OUT}/${point_id}.spice"
        csv="${CORNERS_OUT}/${point_id}_ac.csv"
        render_deck "${bench}" "${mos_section}" "${res_section}" "${temp}" "${netlist}" "${csv}"
        printf '%s\t%s\n' "${point_id}" "${netlist}" >> "${BATCH_QUEUE}"
      done
    done
  done
done
echo "run_loopgain2.sh: queued $(wc -l < "${BATCH_QUEUE}") points (${#BENCHES[@]} benches x 45 grid points) at ${LG_AC_LINE}"

if [[ -n "${SWEEP_BATCH_PLAN_ONLY:-}" ]]; then
  python3 "${SCRIPT_DIR}/batch_backend.py" run --queue "${BATCH_QUEUE}" \
    --corners-out "${CORNERS_OUT}" --work "${BATCH_WORK}" --osdi-dir "${OSDI_DIR}" \
    --submit-concurrency "${SWEEP_BATCH_CONCURRENCY:-2}" --plan-only
  echo "run_loopgain2.sh: SWEEP_BATCH_PLAN_ONLY set -- plan printed, nothing submitted;" >&2
  echo "run_loopgain2.sh: delete ${SNAPSHOTS_OUT} and ${CORNERS_OUT} by hand." >&2
  exit 0
fi

batch_rc=0
python3 "${SCRIPT_DIR}/batch_backend.py" run \
  --queue "${BATCH_QUEUE}" --corners-out "${CORNERS_OUT}" \
  --work "${BATCH_WORK}" --osdi-dir "${OSDI_DIR}" \
  --submit-concurrency "${SWEEP_BATCH_CONCURRENCY:-2}" \
  ${SWEEP_BATCH_REUSE_WORK:+--reuse-work "${SWEEP_BATCH_REUSE_WORK}"} || batch_rc=$?
if [[ ${batch_rc} -ne 0 ]]; then
  echo "run_loopgain2.sh: batch_backend.py exited ${batch_rc}; the affected points are screened as FAILED below." >&2
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
while IFS=$'\t' read -r point_id _netlist; do
  total=$((total + 1))
  if screen_point "${point_id}"; then
    passed=$((passed + 1))
  else
    echo "run_loopgain2.sh: FAILED ${point_id} -- see ${CORNERS_OUT}/${point_id}.log" >&2
    failed_points+=("${point_id}")
  fi
done < "${BATCH_QUEUE}"

if [[ ${passed} -eq 0 ]]; then
  echo "run_loopgain2.sh: no points passed screening -- refusing to reconstruct or write a record." >&2
  exit 1
fi

# --- Reconstruction + per-point comparison (loopgain2.py) ------------------- #
report_rc=0
python3 "${SCRIPT_DIR}/loopgain2.py" report \
  --corners-dir "${CORNERS_OUT}" --ceiling "${LG_AC_MAX}" \
  --out-csv "${CMP_CSV}" --out-json "${CMP_JSON}" || report_rc=$?
if [[ ${report_rc} -ne 0 ]]; then
  echo "run_loopgain2.sh: loopgain2.py report FAILED (${report_rc}); the record md is still written below," >&2
  echo "run_loopgain2.sh: marking every invalid point in it. This campaign is NOT clean evidence." >&2
fi

# --- Cross-check the control against the HISTORICAL baseline record --------- #
# The campaign's own control is the like-for-like comparison baseline. The
# committed 20261011-070111-5391c68 trace at the same point additionally
# ties this run to the historical evidence: same design bytes (sha256s
# below), same PDK pin, same analysis line, so the two single-injection
# traces must agree to solver/reduction precision. Reported (max over the
# whole axis, all 45 points); > 1 dB would mean the historical comparison
# is NOT like-for-like and fails the campaign loudly.
BASELINE_RID="20261011-070111-5391c68"
BASELINE_CMP_JSON="${EVIDENCE_DIR}/ctl-vs-baseline.json"
python3 - "${SCRIPT_DIR}" "${CORNERS_OUT}" "${BASELINE_RID}" "${BASELINE_CMP_JSON}" <<'PYEOF'
import json, math, os, sys
sys.path.insert(0, sys.argv[1])
import loopgain2 as lg2

corners_dir, base_rid, out_json = sys.argv[2], sys.argv[3], sys.argv[4]
per_point = {}
for sfx in lg2.all_suffixes(corners_dir):
    ours = os.path.join(corners_dir, f"{lg2.CTL_PREFIX}{sfx}{lg2.SUFFIX}")
    hist = os.path.join(os.path.dirname(corners_dir), base_rid,
                        f"loopgain_{sfx}{lg2.SUFFIX}")
    if not os.path.isfile(hist):
        per_point[sfx] = {"error": "baseline trace missing"}
        continue
    f1, L1 = lg2.read_loopgain_trace(ours)
    f2, L2 = lg2.read_loopgain_trace(hist)
    if len(f1) != len(f2) or any(not math.isclose(a, b, rel_tol=1e-9) for a, b in zip(f1, f2)):
        per_point[sfx] = {"error": "frequency axis differs from the baseline trace"}
        continue
    d = max(abs(lg2.db(a) - lg2.db(b)) for a, b in zip(L1, L2))
    per_point[sfx] = {"max_abs_db_diff": d}
worst = max((v["max_abs_db_diff"] for v in per_point.values() if "max_abs_db_diff" in v),
            default=None)
bad = [k for k, v in per_point.items() if "error" in v]
doc = {"baseline_record": base_rid, "per_point": per_point,
       "max_abs_db_diff_over_points": worst, "errors": bad,
       "expectation": ("same design bytes, PDK pin and analysis line: the traces must "
                       "agree to solver/reduction precision; > 1 dB fails the campaign")}
with open(out_json, "w") as f:
    json.dump(doc, f, indent=1)
    f.write("\n")
print(f"ctl-vs-baseline({base_rid}): max |dB diff| over 45 points = {worst:.3g} dB", file=sys.stderr)
if bad or (worst is not None and worst > 1.0):
    sys.exit(f"ctl-vs-baseline: NOT like-for-like (errors: {bad}; worst {worst} dB)")
PYEOF
baseline_rc=$?
if [[ ${baseline_rc} -ne 0 ]]; then
  echo "run_loopgain2.sh: the control does NOT match the historical baseline record -- see ${BASELINE_CMP_JSON}" >&2
  exit 1
fi

# --- Completeness over the 45 grid points ----------------------------------- #
COMPLETENESS_OK=1
for corner in "${CORNERS[@]}"; do
  for temp in "${TEMPS[@]}"; do
    for rlabel in "${RES_LABELS[@]}"; do
      for bench in "${BENCHES[@]}"; do
        point_id="${bench}_${corner}_${temp}c_r${rlabel}"
        if [[ " ${failed_points[*]-} " == *" ${point_id} "* ]]; then
          echo "run_loopgain2.sh: INCOMPLETE ${point_id}" >&2
          COMPLETENESS_OK=0
        fi
      done
    done
  done
done

# --- Record md --------------------------------------------------------------- #
# Generated offline from the committed files only (loopgain2.py record-md),
# so `loopgain2.py check` can byte-compare it.
if ! python3 "${SCRIPT_DIR}/loopgain2.py" record-md --record "${RECORD_ID}"; then
  echo "run_loopgain2.sh: record md generation FAILED" >&2
  exit 1
fi

# --- DR-0014 classification of the reconstructed traces (unchanged rules) --- #
row10_rc=0
python3 "${SCRIPT_DIR}/row10_loopgain2.py" --record "${RECORD_ID}" || row10_rc=$?
if [[ ${row10_rc} -ne 0 ]]; then
  echo "run_loopgain2.sh: row10_loopgain2.py classification FAILED" >&2
  exit 1
fi

echo "run_loopgain2.sh: record ${RECORD_ID}: ${passed}/${total} points passed screening (${NGSPICE_VERSION});"
echo "run_loopgain2.sh:   comparison ${CMP_CSV}"
echo "run_loopgain2.sh:   record     ${MD_OUT}"
echo "run_loopgain2.sh:   evidence   ${EVIDENCE_DIR}/row10-margins.{csv,json,md}"

if [[ ${#failed_points[@]} -gt 0 || ${COMPLETENESS_OK} -ne 1 || ${report_rc} -ne 0 ]]; then
  exit 1
fi
exit 0
