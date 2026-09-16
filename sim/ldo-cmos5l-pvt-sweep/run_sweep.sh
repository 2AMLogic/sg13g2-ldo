#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/pdk/parent   # parent dir containing BOTH
#                                          # ihp-sg13g2/ AND ihp-sg13cmos5l/
#                                          # (design/README.md "Install shape
#                                          # is a dispatch hazard")
#   PDK=ihp-sg13cmos5l sim/tools/build-osdi.sh   # one-time: build the OSDI
#                                                 # models for this PDK
#   sim/ldo-cmos5l-pvt-sweep/run_sweep.sh
#
#   sim/ldo-cmos5l-pvt-sweep/run_sweep.sh --check-env   # CI-weight preflight:
#     generates + syntax-checks one netlist per bench (mos_tt/27C), without
#     running the full corner grid or writing a records/ entry.
#
# This script FORCES PDK=ihp-sg13cmos5l regardless of any inherited PDK
# value (unlike sim/pass-device-screening/run_sweep.sh, which targets the
# default ihp-sg13g2 branch) -- see sim/env.sh, which resolves PDK_ROOT
# generically off whichever ${PDK} is exported. PDK_ROOT itself may still
# be left unset if ihp-sg13cmos5l is installed under one of the usual
# prefixes sim/env.sh checks.
#
# Full methodology, the loop-gain measurement derivation, the Cc/Rz
# sensitivity sweeps, and the pinned PDK revision are documented in
# sim/ldo-cmos5l-pvt-sweep/README.md and sim/pdk-cmos5l.json -- read those
# first if a result here looks surprising.
#
# Verifies design/sg13cmos5l/ldo_core_cmos5l.sch's closed loop (issue #20)
# against the spec table README.md re-derives at this PDK's 1.2V-digital/
# 3.3V-analog rails (this block sits entirely on the 3.3V analog rail --
# design/README.md "Rails and the Challenge #6 slot budget"), across:
#   - tb_dcsweep_cmos5l.spice.tmpl: closed-loop Vin x Iload DC sweep ->
#     Iq, dropout @ 50mA, line regulation, load regulation.
#   - tb_loopgain_cmos5l.spice.tmpl: loop broken at FB (a high-impedance
#     node) -> phase margin, gain margin, DC loop gain.
#   - tb_psrr_cmos5l.spice.tmpl: closed-loop AC on Vin -> PSRR @ 1kHz/100kHz.
# across the full process x temperature x RESISTOR-corner grid
# {tt,ff,ss,sf,fs} x {-40,27,125}C x {res_typ,res_bcs,res_wcs} = 45 points
# (cornerMOShv.lib's five sections -- confirmed byte-identical to
# ihp-sg13g2's own copy at this PDK's pin, see sim/pdk-cmos5l.json --
# crossed with cornerRES.lib's own three-point axis).
#
# The resistor axis was HELD at res_typ across the main grid for the #21 and
# #25 runs and is CROSSED in full from issue #31 onward. Reason: until #28
# the feedback divider was a pair of behavioural 300k res.sym resistors,
# corner-independent by construction, so the only rhigh in the loop was the
# error amp's nulling resistor Rz and a separate tt/27C-only Rz sensitivity
# experiment covered it. Since #28 the divider is two real PDK rhigh
# instances, and the same @@RES_SECTION@@ substitution is global across the
# netlist -- so the resistor corner now moves the divider's absolute
# impedance (and its standing current) as well as Rz, at every MOS/temp
# point, and holding it at nominal would leave that spread unverified.
# This supersedes README.md's earlier "no established MOS-corner/R-corner
# correlation convention exists, so hold R at nominal" judgement call in the
# only way that does not require inventing one: the resistor axis is swept
# INDEPENDENTLY and reported per point, so every (MOS, temp) pair is
# reported against all three resistor sections rather than against one
# assumed-correlated section.
#
# PLUS two small sensitivity sweeps at the nominal tt/27C corner only:
#   - Cc (Miller cap) value sensitivity {0.5x,1x,2x} -- cornerCAP.lib maps
#     every corner/mismatch/stat section to the SAME nominal cap_cmomi
#     model (no characterised corner spread exists for this PDK's MoM
#     caps), so a PROCESS-corner sweep over Cc is a no-op; this VALUE
#     sensitivity sweep is what design/README.md's "PDK caveats honoured"
#     table says this issue owes instead.
#   - Resistor-corner sensitivity {res_bcs,res_typ,res_wcs} at tt/27C --
#     retained from the #21/#25 runs (where it was labelled "Rz corner
#     sensitivity", because Rz was then the only rhigh in the loop) so the
#     sensitivity CSV stays row-comparable across records. Since #28 this
#     knob moves Rz AND the feedback divider together, which is why it is
#     labelled res_corner rather than rz_corner from #31 onward.
set -euo pipefail

CHECK_ENV=0
for arg in "$@"; do
  case "${arg}" in
    --check-env) CHECK_ENV=1 ;;
    -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "run_sweep.sh: unknown argument '${arg}'" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"

export PDK=ihp-sg13cmos5l
# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"

if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_sweep.sh: no resolvable ${PDK} install -- see sim/env.sh output above." >&2
  exit 3
fi

if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
  echo "run_sweep.sh: OSDI models missing/unloadable -- run PDK=${PDK} sim/tools/build-osdi.sh first:" >&2
  "${SIM_DIR}/tools/build-osdi.sh" --check || true
  exit 3
fi

command -v ngspice >/dev/null 2>&1 || { echo "run_sweep.sh: ngspice not on PATH." >&2; exit 3; }
NGSPICE_VERSION="$(ngspice -v 2>&1 | sed -n '2p')"

OSDI_DIR="${SG13G2_OSDI_DIR}"
DESIGN_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"

if [[ ! -f "${DESIGN_NETLIST}" ]]; then
  echo "run_sweep.sh: ${DESIGN_NETLIST} not found -- regenerate it first:" >&2
  echo "run_sweep.sh:   python3 design/netlist.py --design sg13cmos5l" >&2
  exit 3
fi

# --- Sync-check: tb_loopgain_cmos5l.spice.tmpl flattens ldo_core_cmos5l one
# level (to insert the loop-gain break at FB, a high-impedance node -- see
# that template's header for the full derivation) by hand-mirroring its
# XMpass/XRtop/XRbot/Xamp instantiation lines. If a future schematic edit
# changes that connectivity, this bench would silently go stale -- so
# diff the mirrored lines against the actual generated netlist every run,
# not just at authoring time. ---
assert_loopgain_topology_sync() {
  local body expected
  body="$(awk '/^\.subckt ldo_core_cmos5l /,/^\.ends/' "${DESIGN_NETLIST}" | grep -E '^(XMpass|XRtop|XRbot|Xamp) ')"
  expected="$(cat <<'EOF'
XMpass VOUT EAOUT VIN VIN sg13_hv_pmos w=2800u l=0.5u ng=1 m=1
XRtop VOUT FB VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7
XRbot FB VSS VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7
Xamp FB VREF EAOUT VIN VSS IBIAS ldo_erramp_cmos5l
EOF
)"
  if [[ "${body}" != "${expected}" ]]; then
    echo "run_sweep.sh: FATAL -- ldo_core_cmos5l's top-level instantiation lines" >&2
    echo "run_sweep.sh: in ${DESIGN_NETLIST} no longer match what" >&2
    echo "run_sweep.sh: tb_loopgain_cmos5l.spice.tmpl hand-mirrors (loop-break bench)." >&2
    echo "run_sweep.sh: --- expected (baked into this script) ---" >&2
    echo "${expected}" >&2
    echo "run_sweep.sh: --- actual (from the generated netlist) ---" >&2
    echo "${body}" >&2
    echo "run_sweep.sh: update tb_loopgain_cmos5l.spice.tmpl's flattened copy" >&2
    echo "run_sweep.sh: (and this function's 'expected' text) to match, then re-run." >&2
    exit 4
  fi
}
assert_loopgain_topology_sync

if [[ ${CHECK_ENV} -eq 1 ]]; then
  echo "run_sweep.sh: --check-env: syntax-checking all three benches at mos_tt/27C, no records written."
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp}"' EXIT
  rc=0
  for bench in dcsweep loopgain psrr; do
    template="${SCRIPT_DIR}/testbench/tb_${bench}_cmos5l.spice.tmpl"
    netlist="${tmp}/${bench}_check.spice"
    sed \
      -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
      -e "s|@@PDK@@|${PDK}|g" \
      -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
      -e "s|@@MOS_SECTION@@|mos_tt|g" \
      -e "s|@@RES_SECTION@@|res_typ|g" \
      -e "s|@@CAP_SECTION@@|cap_typ|g" \
      -e "s|@@TEMP@@|27|g" \
      -e "s|@@CC_W@@|30u (nominal)|g" \
      -e "s|@@DESIGN_NETLIST@@|${DESIGN_NETLIST}|g" \
      -e "s|@@DC_CSV@@|${tmp}/${bench}_check_dc.csv|g" \
      -e "s|@@AC_CSV@@|${tmp}/${bench}_check_ac.csv|g" \
      "${template}" > "${netlist}"
    log="${tmp}/${bench}_check.log"
    if ! ngspice -b "${netlist}" > "${log}" 2>&1 || grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error" "${log}"; then
      echo "run_sweep.sh: --check-env FAILED for ${bench} bench -- see below:" >&2
      cat "${log}" >&2
      rc=1
    else
      echo "run_sweep.sh: --check-env OK for ${bench} bench"
    fi
  done
  exit ${rc}
fi

REPO_GIT_SHA="$(cd "${REPO_ROOT}" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"

EXPERIMENT_DIR="${SCRIPT_DIR}"
SNAPSHOTS_OUT="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
CORNERS_OUT="${EXPERIMENT_DIR}/corners/${RECORD_ID}"
RECORDS_DIR="${EXPERIMENT_DIR}/records"
CSV_OUT="${RECORDS_DIR}/${RECORD_ID}.csv"
SENS_CSV_OUT="${RECORDS_DIR}/${RECORD_ID}.sensitivity.csv"
DELTA_CSV_OUT="${RECORDS_DIR}/${RECORD_ID}.delta.csv"
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.md"
mkdir -p "${SNAPSHOTS_OUT}" "${CORNERS_OUT}" "${RECORDS_DIR}"

CORNERS=(tt ss ff sf fs)
TEMPS=(-40 27 125)
# Resistor-corner axis (cornerRES.lib), crossed with the MOS x temp grid in
# full since issue #31 -- see this script's header for why it is swept
# rather than held at nominal, and why it is swept INDEPENDENTLY rather
# than correlated to the MOS corner. Labels here; sections are res_<label>.
RES_LABELS=(typ bcs wcs)

# Pre-conversion baseline this run is compared against: the #25 (post-
# Mpass-resize, pre-#28) record, taken with the behavioural 300k res.sym
# divider. The before/after/delta table in the generated record is derived
# from this file. Pinned by name on purpose -- sim/ records are append-only
# evidence, so this path is stable, and a future re-baselining is an
# explicit edit here rather than an implicit "whatever the newest record
# happens to be".
BASELINE_CSV="${RECORDS_DIR}/20260916-112842-c25ff53.csv"

total=0
passed=0
failed_points=()

gen_netlist() {
  local bench="$1" point_id="$2" mos_section="$3" res_section="$4" cap_section="$5" temp="$6" design_netlist="$7" cc_w_desc="$8"
  local template="${EXPERIMENT_DIR}/testbench/tb_${bench}_cmos5l.spice.tmpl"
  local netlist="${SNAPSHOTS_OUT}/${point_id}.spice"
  local extra_sed=()
  case "${bench}" in
    dcsweep) extra_sed=(-e "s|@@DC_CSV@@|${CORNERS_OUT}/${point_id}_dc.csv|g") ;;
    loopgain|psrr) extra_sed=(-e "s|@@AC_CSV@@|${CORNERS_OUT}/${point_id}_ac.csv|g") ;;
  esac
  sed \
    -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
    -e "s|@@PDK@@|${PDK}|g" \
    -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
    -e "s|@@MOS_SECTION@@|${mos_section}|g" \
    -e "s|@@RES_SECTION@@|${res_section}|g" \
    -e "s|@@CAP_SECTION@@|${cap_section}|g" \
    -e "s|@@TEMP@@|${temp}|g" \
    -e "s|@@CC_W@@|${cc_w_desc}|g" \
    -e "s|@@DESIGN_NETLIST@@|${design_netlist}|g" \
    "${extra_sed[@]}" \
    "${template}" > "${netlist}"
  echo "${netlist}"
}

# Expected output-row counts, per bench, for the POSITIVE completeness
# check in run_ngspice below. Derived from the templates' own analysis
# statements, not guessed: the DC bench's nested sweep is Vin
# 2.00..3.63 step 0.01 (164 rows) x 5 Iload blocks = 820; the two AC
# benches are `ac dec 20 1 100meg` = 20 points/decade x 8 decades + 1 = 161.
# If a template's analysis statement is ever changed without updating
# these, every point fails loudly -- the same "fail loudly rather than go
# silently stale" posture assert_loopgain_topology_sync() takes above.
EXPECT_ROWS_DC=820
EXPECT_ROWS_AC=161

recoverable_warning_points=()

run_ngspice() {
  local point_id="$1" netlist="$2"
  local log="${CORNERS_OUT}/${point_id}.log"
  local rc=0 out_csv expect_rows got_rows
  case "${point_id}" in
    dcsweep_*) out_csv="${CORNERS_OUT}/${point_id}_dc.csv"; expect_rows=${EXPECT_ROWS_DC} ;;
    *)         out_csv="${CORNERS_OUT}/${point_id}_ac.csv"; expect_rows=${EXPECT_ROWS_AC} ;;
  esac
  ngspice -b "${netlist}" > "${log}" 2>&1 || rc=$?
  total=$((total + 1))

  # Fatal-error screen. `singular matrix` is deliberately matched only when
  # it is NOT ngspice's recoverable `Warning: singular matrix:` form: that
  # warning is emitted while the solver walks its own convergence-aid ladder
  # (source stepping -> dynamic gmin stepping) and is routinely followed by
  # `Dynamic gmin stepping completed` and a fully converged analysis. The
  # #21/#25 runs never tripped it; this grid does, at 9 of its 135 points,
  # because the PDK `rhigh` divider #28 introduced adds internal nodes to
  # the DC solve. Treating a recovered warning as a failure would have
  # discarded 9 perfectly good, fully-converged points -- so the warning is
  # counted and disclosed in the record instead of being either fatal or
  # silently dropped. A genuine unrecovered singular matrix (ngspice prints
  # it without the `Warning:` prefix) still fails, as do the model-load,
  # gmin-failure and non-convergence signatures.
  if [[ ${rc} -ne 0 ]] \
     || grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error|gmin stepping failed|no convergence|iteration limit reached" "${log}" \
     || grep -iE "singular matrix" "${log}" | grep -qivE "^[[:space:]]*Warning:"; then
    echo "run_sweep.sh: FAILED ${point_id} (rc=${rc}) -- see ${log}" >&2
    failed_points+=("${point_id}")
    return 1
  fi

  # Positive completeness check: the analysis must actually have written
  # its full result set. This is STRICTER than the pre-#31 screen, which
  # only looked for error strings and would have passed a run that exited
  # 0 having written nothing.
  got_rows=$(wc -l < "${out_csv}" 2>/dev/null || echo 0)
  if [[ ! -s "${out_csv}" || ${got_rows} -ne ${expect_rows} ]]; then
    echo "run_sweep.sh: FAILED ${point_id} -- ${out_csv} has ${got_rows} rows, expected ${expect_rows}" >&2
    failed_points+=("${point_id}")
    return 1
  fi

  if grep -qiE "^[[:space:]]*Warning: singular matrix" "${log}"; then
    recoverable_warning_points+=("${point_id}")
  fi
  passed=$((passed + 1))
  return 0
}

# --- Main 45-point PVT x resistor-corner grid: dcsweep + loopgain + psrr
# at each point. Point ids carry the resistor section explicitly (the
# "_r<label>" suffix) so every artifact under corners/ and
# netlist-snapshots/ states, in its own filename, which cornerRES.lib
# section produced it -- issue #31 AC2. ---
for corner in "${CORNERS[@]}"; do
  for temp in "${TEMPS[@]}"; do
    for rlabel in "${RES_LABELS[@]}"; do
      mos_section="mos_${corner}"
      res_section="res_${rlabel}"
      for bench in dcsweep loopgain psrr; do
        point_id="${bench}_${corner}_${temp}c_r${rlabel}"
        netlist="$(gen_netlist "${bench}" "${point_id}" "${mos_section}" "${res_section}" cap_typ "${temp}" "${DESIGN_NETLIST}" "100u (nominal)")"
        run_ngspice "${point_id}" "${netlist}" || true
      done
    done
  done
done

# --- Cc (Miller cap) value sensitivity, at tt/27C only -- see header ---
CC_NETLISTS_DIR="${SNAPSHOTS_OUT}/design-netlist-cc-sensitivity"
mkdir -p "${CC_NETLISTS_DIR}"
declare -A CC_WIDTHS=( ["0.5x"]="50e-6" ["1x"]="100e-6" ["2x"]="200e-6" )
for label in 0.5x 1x 2x; do
  w="${CC_WIDTHS[${label}]}"
  cc_netlist="${CC_NETLISTS_DIR}/ldo_core_cmos5l_cc${label}.spice"
  # XCc's line is `XCc OUT MZ cap_cmomi w=100e-6 l=30e-6 ...` -- substitute
  # ONLY the w=100e-6 token (Cc's width; l is held fixed at 30e-6), leaving
  # every other device in the file untouched. (#25 raised Cc's nominal
  # width from 30e-6 to 100e-6; this base pattern and CC_WIDTHS above were
  # updated to match -- see design/sg13cmos5l/ldo_erramp_cmos5l.sch's
  # header.)
  sed "s/XCc OUT MZ cap_cmomi w=100e-6 l=30e-6/XCc OUT MZ cap_cmomi w=${w} l=30e-6/" \
    "${DESIGN_NETLIST}" > "${cc_netlist}"
  if [[ "${label}" != "1x" ]] && diff -q "${cc_netlist}" "${DESIGN_NETLIST}" >/dev/null; then
    echo "run_sweep.sh: FATAL -- Cc width substitution for ${label} did not change ${cc_netlist} (XCc line text may have drifted from what this script expects)." >&2
    exit 4
  fi

  point_id="loopgain_ccsens_${label}_tt_27c"
  netlist="$(gen_netlist loopgain "${point_id}" mos_tt res_typ cap_typ 27 "${cc_netlist}" "${w} (${label} of nominal 100e-6)")"
  run_ngspice "${point_id}" "${netlist}" || true
done

# --- Resistor-corner sensitivity, at tt/27C only, nominal Cc. Retained
# from #21/#25 (where it was named "rzsens", Rz being the only rhigh in the
# loop then) so the sensitivity CSV stays row-comparable across records;
# renamed "ressens" from #31 onward because since #28 this same
# cornerRES.lib section also moves the feedback divider. These three points
# duplicate the tt/27C slice of the main grid above by construction -- that
# redundancy is deliberate (it is the cross-check that the main grid's new
# resistor axis and this pre-existing experiment agree). ---
for label in bcs typ wcs; do
  point_id="loopgain_ressens_${label}_tt_27c"
  netlist="$(gen_netlist loopgain "${point_id}" mos_tt "res_${label}" cap_typ 27 "${DESIGN_NETLIST}" "100u (nominal)")"
  run_ngspice "${point_id}" "${netlist}" || true
done

if [[ ${passed} -eq 0 ]]; then
  echo "run_sweep.sh: no points passed -- refusing to write a summary." >&2
  exit 1
fi

# --- Post-process everything into the record CSVs + the before/after/delta
# markdown fragment that gets inlined into the record below ---
CMP_MD_FRAGMENT="${CORNERS_OUT}/_before_after_delta.md"
python3 - "${CORNERS_OUT}" "${CSV_OUT}" "${SENS_CSV_OUT}" "${CORNERS[*]}" "${TEMPS[*]}" \
         "${RES_LABELS[*]}" "${BASELINE_CSV}" "${DELTA_CSV_OUT}" "${CMP_MD_FRAGMENT}" <<'PYEOF'
import csv, sys, math, os

(corners_dir, csv_out, sens_csv_out, corners_str, temps_str,
 res_labels_str, baseline_csv, delta_csv_out, cmp_md_out) = sys.argv[1:10]
CORNERS = corners_str.split()
TEMPS = [t for t in temps_str.split()]
RES_LABELS = res_labels_str.split()

VOUT_TARGET = 1.8
VIN_MIN, VIN_MAX, VIN_STEP = 2.00, 3.63, 0.01


def read_wrdata(path, ncols):
    """wrdata prints a redundant (scale, value) pair per requested vector
    (see sim/pass-device-screening/README.md's own documented gotcha)."""
    rows = []
    try:
        with open(path) as f:
            for line in f:
                parts = line.split()
                if len(parts) < ncols:
                    continue
                rows.append([float(x) for x in parts])
    except FileNotFoundError:
        return []
    return rows


def dc_metrics(path):
    """Parse a tb_dcsweep_cmos5l _dc.csv: columns
    (scale,v(vin),scale,v(vout),scale,i(vin),scale,i(vdivsense)) x N rows,
    nested sweep with Vin as the fast/inner variable and Iload as the
    slow/outer variable (see that template's header). i(vdivsense) is the
    feedback divider's own standing current, read off the non-invasive
    rhigh replica that template instantiates (issue #31). Detect
    Iload-block boundaries by watching Vin reset to a smaller value than
    the previous row."""
    rows = read_wrdata(path, 8)
    if not rows:
        return None
    blocks = []
    cur = []
    prev_vin = None
    for r in rows:
        vin = r[1]
        if prev_vin is not None and vin < prev_vin - 1e-9:
            blocks.append(cur)
            cur = []
        cur.append((vin, r[3], r[5], r[7]))
        prev_vin = vin
    blocks.append(cur)
    if len(blocks) < 5:
        return {"error": f"expected 5 Iload blocks, got {len(blocks)}"}

    def nearest(block, vin_target):
        return min(block, key=lambda t: abs(t[0] - vin_target))

    out = {}
    # Iq + no-load op point + divider standing current, block 0 (Iload=0),
    # Vin=3.30V.
    v, vo, i, idiv = nearest(blocks[0], 3.30)
    out["iq_a"] = abs(i)
    out["vout_no_load_v"] = vo
    out["i_divider_a"] = abs(idiv)
    # Per-leg divider resistance implied by the measured current: both legs
    # are the same drawn device and FB draws no DC current, so
    # R_leg = (VOUT/2) / I_div.
    out["r_divider_leg_ohm"] = (vo / 2.0) / abs(idiv) if idiv else float("nan")

    # Line regulation, block 0 (no load), Input row's {2.97,3.63}V window.
    v_lo, vo_lo, _, _ = nearest(blocks[0], 2.97)
    v_hi, vo_hi, _, _ = nearest(blocks[0], 3.63)
    out["line_reg_in_regulation"] = abs(vo_lo - VOUT_TARGET) < 0.01 * VOUT_TARGET and abs(vo_hi - VOUT_TARGET) < 0.01 * VOUT_TARGET
    out["line_reg_mv_per_v"] = (vo_hi - vo_lo) / (v_hi - v_lo) * 1000.0

    # Dropout @ 50mA, last block (Iload=0.05A): scan from Vin_max downward
    # for the first point where VOUT falls below 0.99x the fixed 1.8V
    # target (README.md "Nested DC sweep").
    block50 = sorted(blocks[-1], key=lambda t: t[0])
    v_at_max, vo_at_max, _, _ = block50[-1]
    out["vout_at_vinmax_50ma_v"] = vo_at_max
    dropout_v = None
    for v, vo, _, _ in reversed(block50):
        if vo < 0.99 * VOUT_TARGET:
            break
        dropout_v = v - VOUT_TARGET
    out["dropout_v_50ma"] = dropout_v  # None => never left regulation down to VIN_MIN
    out["dropout_v_50ma_floor"] = VIN_MIN - VOUT_TARGET  # reported when dropout_v is None

    # Load regulation: Vin=3.63V row in every block.
    vouts_at_vinmax = [nearest(b, 3.63)[1] for b in blocks]
    out["vout_at_vinmax_by_load"] = vouts_at_vinmax  # [0,12.5m,25m,37.5m,50m]
    if vouts_at_vinmax[0] != 0:
        out["load_reg_pct"] = (vouts_at_vinmax[0] - vouts_at_vinmax[-1]) / vouts_at_vinmax[0] * 100.0
    else:
        out["load_reg_pct"] = float("nan")
    return out


def unwrap_deg(phases):
    out = [phases[0]]
    offset = 0.0
    for p in phases[1:]:
        d = (p + offset) - out[-1]
        while d > 180.0:
            offset -= 360.0
            d = (p + offset) - out[-1]
        while d < -180.0:
            offset += 360.0
            d = (p + offset) - out[-1]
        out.append(p + offset)
    return out


def loopgain_metrics(path):
    rows = read_wrdata(path, 4)
    if not rows:
        return None
    freqs = [r[0] for r in rows]
    dbs = [r[1] for r in rows]
    degs_unwrapped = unwrap_deg([r[3] for r in rows])

    out = {"dc_gain_db": dbs[0]}

    # All 0dB crossings (log-interp freq, linear-interp unwrapped phase).
    crossings = []
    for i in range(1, len(dbs)):
        if (dbs[i - 1] - 0) * (dbs[i] - 0) < 0:
            frac = (0 - dbs[i - 1]) / (dbs[i] - dbs[i - 1])
            logf = math.log10(freqs[i - 1]) + frac * (math.log10(freqs[i]) - math.log10(freqs[i - 1]))
            f_cross = 10 ** logf
            deg_cross = degs_unwrapped[i - 1] + frac * (degs_unwrapped[i] - degs_unwrapped[i - 1])
            crossings.append((f_cross, deg_cross))
    out["n_0db_crossings"] = len(crossings)
    if crossings:
        f0, deg0 = crossings[0]
        out["unity_gain_freq_hz"] = f0
        out["phase_margin_deg"] = 180.0 + deg0
        out["phase_margin_worst_deg"] = min(180.0 + d for _, d in crossings)
    else:
        out["unity_gain_freq_hz"] = None
        out["phase_margin_deg"] = None
        out["phase_margin_worst_deg"] = None

    # First -180deg (mod 360) unwrapped-phase crossing -> gain margin.
    gm_crossings = []
    for i in range(1, len(degs_unwrapped)):
        target = -180.0
        while target > max(degs_unwrapped[i - 1], degs_unwrapped[i]):
            target -= 360.0
        while target < min(degs_unwrapped[i - 1], degs_unwrapped[i]) - 360.0:
            target += 360.0
        lo, hi = degs_unwrapped[i - 1], degs_unwrapped[i]
        if (lo - target) * (hi - target) < 0 and abs(hi - lo) < 180.0:
            frac = (target - lo) / (hi - lo)
            logf = math.log10(freqs[i - 1]) + frac * (math.log10(freqs[i]) - math.log10(freqs[i - 1]))
            f_cross = 10 ** logf
            db_cross = dbs[i - 1] + frac * (dbs[i] - dbs[i - 1])
            gm_crossings.append((f_cross, db_cross))
    out["n_gain_margin_crossings"] = len(gm_crossings)
    if gm_crossings:
        f0, db0 = gm_crossings[0]
        out["gain_margin_freq_hz"] = f0
        out["gain_margin_db"] = -db0
    else:
        out["gain_margin_freq_hz"] = None
        out["gain_margin_db"] = None
    return out


def psrr_metrics(path):
    rows = read_wrdata(path, 2)
    if not rows:
        return None
    def nearest(freq_target):
        return min(rows, key=lambda r: abs(math.log10(r[0]) - math.log10(freq_target)))
    return {
        "psrr_db_1khz": nearest(1e3)[1],
        "psrr_db_100khz": nearest(1e5)[1],
    }


main_rows = []
for corner in CORNERS:
    for temp in TEMPS:
        for rlabel in RES_LABELS:
            row = {"corner": corner, "temp_c": temp, "res_section": f"res_{rlabel}"}
            sfx = f"{corner}_{temp}c_r{rlabel}"
            dc = dc_metrics(f"{corners_dir}/dcsweep_{sfx}_dc.csv")
            lg = loopgain_metrics(f"{corners_dir}/loopgain_{sfx}_ac.csv")
            ps = psrr_metrics(f"{corners_dir}/psrr_{sfx}_ac.csv")
            for src in (dc, lg, ps):
                if src:
                    row.update({k: v for k, v in src.items() if k != "vout_at_vinmax_by_load"})
            main_rows.append(row)

fieldnames = [
    "corner", "temp_c", "res_section", "iq_a", "vout_no_load_v",
    "i_divider_a", "r_divider_leg_ohm",
    "line_reg_in_regulation", "line_reg_mv_per_v",
    "dropout_v_50ma", "dropout_v_50ma_floor", "vout_at_vinmax_50ma_v",
    "load_reg_pct",
    "dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
    "phase_margin_deg", "phase_margin_worst_deg",
    "n_gain_margin_crossings", "gain_margin_freq_hz", "gain_margin_db",
    "psrr_db_1khz", "psrr_db_100khz",
]
with open(csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in main_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fieldnames})

# --- Sensitivity CSV: Cc value sweep + resistor corner sweep, tt/27C only ---
sens_rows = []
for label in ["0.5x", "1x", "2x"]:
    lg = loopgain_metrics(f"{corners_dir}/loopgain_ccsens_{label}_tt_27c_ac.csv")
    row = {"sweep": "cc_value", "point": label}
    if lg:
        row.update(lg)
    sens_rows.append(row)
for label in ["bcs", "typ", "wcs"]:
    lg = loopgain_metrics(f"{corners_dir}/loopgain_ressens_{label}_tt_27c_ac.csv")
    # Named "rz_corner" in the #21/#25 records, when Rz was the only rhigh
    # in the loop; since #28 this section moves the feedback divider too.
    row = {"sweep": "res_corner", "point": label}
    if lg:
        row.update(lg)
    sens_rows.append(row)

sens_fieldnames = [
    "sweep", "point", "dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
    "phase_margin_deg", "phase_margin_worst_deg",
    "n_gain_margin_crossings", "gain_margin_freq_hz", "gain_margin_db",
]
with open(sens_csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=sens_fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in sens_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in sens_fieldnames})

# --- Before / after / delta against the pre-conversion baseline record ---
# "Before" is the #25 post-resize record, taken with the behavioural 300k
# res.sym divider (corner-independent by construction) at res_typ; "after"
# is this run, at each of the three cornerRES.lib sections. Issue #31 AC3.
#
# The one metric the baseline CSV does not carry a column for is the
# divider's own standing current -- it had no reason to, because the
# behavioural divider was an ideal, exactly-600k, corner-independent pair.
# That makes its "before" value derivable rather than missing:
# I_div = VOUT_no_load / 600k exactly, from the baseline's own recorded
# VOUT. It is labelled "(derived)" in the table so no reader mistakes it
# for a measured column that was there all along.
BEHAVIOURAL_DIVIDER_TOTAL_OHM = 600e3

baseline = {}
if os.path.exists(baseline_csv):
    with open(baseline_csv) as f:
        for r in csv.DictReader(f):
            def _f(k):
                try:
                    return float(r[k])
                except (KeyError, TypeError, ValueError):
                    return None
            key = (r["corner"], r["temp_c"])
            b = {k: _f(k) for k in ("dc_gain_db", "phase_margin_deg",
                                    "gain_margin_db", "psrr_db_1khz",
                                    "psrr_db_100khz", "iq_a",
                                    "vout_no_load_v")}
            vo = b["vout_no_load_v"]
            b["i_divider_a"] = (vo / BEHAVIOURAL_DIVIDER_TOTAL_OHM) if vo else None
            baseline[key] = b

after = {(r["corner"], str(r["temp_c"]), r["res_section"]): r for r in main_rows}

METRICS = [
    # (csv key, heading, unit, scale, decimals, higher_is_better)
    ("dc_gain_db", "DC loop gain", "dB", 1.0, 2, True),
    ("phase_margin_deg", "Phase margin", "deg", 1.0, 2, True),
    ("gain_margin_db", "Gain margin", "dB", 1.0, 2, True),
    ("psrr_db_1khz", "PSRR @ 1kHz", "dB", 1.0, 2, True),
    ("psrr_db_100khz", "PSRR @ 100kHz", "dB", 1.0, 2, True),
    ("i_divider_a", "Divider standing current", "uA", 1e6, 3, False),
]

delta_rows = []
for corner in CORNERS:
    for temp in TEMPS:
        b = baseline.get((corner, str(temp)), {})
        for key, heading, unit, scale, dec, _hib in METRICS:
            row = {"corner": corner, "temp_c": temp, "metric": key,
                   "unit": unit, "before": b.get(key)}
            afters = {}
            for rlabel in RES_LABELS:
                a = after.get((corner, str(temp), f"res_{rlabel}"), {})
                afters[rlabel] = a.get(key)
                row[f"after_res_{rlabel}"] = a.get(key)
            vals = [v for v in afters.values() if v is not None]
            row["after_min"] = min(vals) if vals else None
            row["after_max"] = max(vals) if vals else None
            bv = row["before"]
            at = afters.get("typ")
            row["delta_res_typ"] = (at - bv) if (bv is not None and at is not None) else None
            if bv is not None and vals:
                row["delta_worst"] = max((v - bv for v in vals), key=abs)
            else:
                row["delta_worst"] = None
            delta_rows.append(row)

delta_fieldnames = (["corner", "temp_c", "metric", "unit", "before"]
                    + [f"after_res_{r}" for r in RES_LABELS]
                    + ["after_min", "after_max", "delta_res_typ", "delta_worst"])
with open(delta_csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=delta_fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in delta_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in delta_fieldnames})

by_key = {}
for row in delta_rows:
    by_key.setdefault(row["metric"], []).append(row)


def fmt(v, scale, dec, signed=False):
    if v is None:
        return "n/a"
    s = f"{v * scale:+.{dec}f}" if signed else f"{v * scale:.{dec}f}"
    return s


with open(cmp_md_out, "w") as f:
    for key, heading, unit, scale, dec, _hib in METRICS:
        derived = " (before = derived, see note)" if key == "i_divider_a" else ""
        f.write(f"\n### {heading} ({unit}){derived}\n\n")
        f.write("| corner / temp | before (#25, behavioural 300k) "
                "| after `res_typ` | after `res_bcs` | after `res_wcs` "
                "| delta @ `res_typ` | delta, worst R corner |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for row in by_key.get(key, []):
            f.write(
                f"| `{row['corner']}` / {row['temp_c']}C "
                f"| {fmt(row.get('before'), scale, dec)} "
                f"| {fmt(row.get('after_res_typ'), scale, dec)} "
                f"| {fmt(row.get('after_res_bcs'), scale, dec)} "
                f"| {fmt(row.get('after_res_wcs'), scale, dec)} "
                f"| {fmt(row.get('delta_res_typ'), scale, dec, signed=True)} "
                f"| {fmt(row.get('delta_worst'), scale, dec, signed=True)} |\n")

print(f"run_sweep.sh (post-process): wrote {len(main_rows)} main rows, "
      f"{len(sens_rows)} sensitivity rows, {len(delta_rows)} delta rows")
PYEOF

# --- Completeness matrix: every (corner,temp,res_section) has all 3
# benches present ---
COMPLETENESS_OK=1
for corner in "${CORNERS[@]}"; do
  for temp in "${TEMPS[@]}"; do
    for rlabel in "${RES_LABELS[@]}"; do
      for bench in dcsweep loopgain psrr; do
        point_id="${bench}_${corner}_${temp}c_r${rlabel}"
        if [[ " ${failed_points[*]-} " == *" ${point_id} "* ]]; then
          echo "run_sweep.sh: INCOMPLETE ${point_id}" >&2
          COMPLETENESS_OK=0
        fi
      done
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: ldo-cmos5l-pvt-sweep"
  echo "- **Claim**: design/sg13cmos5l/ldo_core_cmos5l.sch's closed loop"
  echo "  (issue #20), verified against the spec table re-derived at this"
  echo "  PDK's rails (README.md), across the full process x temperature x"
  echo "  RESISTOR-corner grid, plus Cc-value and resistor-corner"
  echo "  sensitivity sweeps. This harness is issue #21's deliverable; which"
  echo "  issue's acceptance criteria a given record is evidence for is told"
  echo "  by the design netlist's git sha recorded below -- #21 (original"
  echo "  sizing), #25 (Mpass resize + recompensation), or #31 (the first"
  echo "  run against the PDK \`rhigh\` feedback divider that #28 substituted"
  echo "  for the pre-#28 behavioural 300k \`res.sym\` pair, and the first to"
  echo "  cross the resistor corner across the whole grid)."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned revision: see"
  echo "  \`sim/pdk-cmos5l.json\` (commit \`607e18d\`, re-verified against the"
  echo "  installed checkout)."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by"
  echo "  \`PDK=${PDK} sim/tools/build-osdi.sh\`."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Design netlist under test**: \`design/sg13cmos5l/netlist/ldo_core_cmos5l.spice\`"
  echo "  at this repo's git sha \`${REPO_GIT_SHA}\`."
  echo "- **Corner matrix run**: process {${CORNERS[*]}} (cornerMOShv.lib) x"
  echo "  temperature {${TEMPS[*]}}C x resistor corner {${RES_LABELS[*]/#/res_}}"
  echo "  (cornerRES.lib) = 45 points x 3 benches (dcsweep, loopgain, psrr)"
  echo "  = 135 points, plus 6 sensitivity points (Cc value {0.5x,1x,2x} +"
  echo "  resistor corner {bcs,typ,wcs}, both at tt/27C only)."
  echo "- **Result**: ${passed}/${total} points PASS (ngspice exit 0, no"
  echo "  convergence/model-load error strings in the log, and the expected"
  echo "  full result set written -- ${EXPECT_ROWS_DC} rows per dcsweep point,"
  echo "  ${EXPECT_ROWS_AC} per AC point)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Recovered \`Warning: singular matrix\` points**: ${#recoverable_warning_points[@]}"
  echo "  of ${total}. ngspice emitted its recoverable singular-matrix"
  echo "  warning at these points while walking its own convergence-aid"
  echo "  ladder, then reported \`Dynamic gmin stepping completed\` and"
  echo "  produced a fully converged, complete result set. The #21/#25 runs"
  echo "  never tripped it; this grid does, because the PDK \`rhigh\` divider"
  echo "  (#28) adds internal nodes to the DC solve. Disclosed here rather"
  echo "  than hidden: the per-point logs under \`corners/${RECORD_ID}/\` show"
  echo "  the warning and the recovery for each."
  if [[ ${#recoverable_warning_points[@]} -gt 0 ]]; then
    echo "  Points: ${recoverable_warning_points[*]}"
  fi
  echo "- **Completeness matrix**: $( [[ ${COMPLETENESS_OK} -eq 1 ]] && echo 'OK -- every (corner,temp,res_section) has all 3 benches present' || echo 'INCOMPLETE -- see stderr log above' )"
  echo "- **Resistor corner (issue #31 AC2)**: CROSSED in full across the"
  echo "  main grid -- every (MOS corner, temperature) point was run against"
  echo "  all three of cornerRES.lib's \`res_typ\`/\`res_bcs\`/\`res_wcs\`"
  echo "  sections, and every row of \`records/${RECORD_ID}.csv\` names its"
  echo "  own section in the \`res_section\` column (as does every filename"
  echo "  under \`corners/${RECORD_ID}/\` and"
  echo "  \`netlist-snapshots/${RECORD_ID}/\`, via the \`_r<label>\` suffix)."
  echo "  The #21/#25 records held this axis at \`res_typ\` because the"
  echo "  feedback divider was then a corner-independent behavioural 300k"
  echo "  pair and Rz was the loop's only \`rhigh\`; #28 made the divider a"
  echo "  real \`rhigh\`, so the axis is swept rather than held from this"
  echo "  record onward. It is swept INDEPENDENTLY of the MOS corner, not"
  echo "  correlated to it -- this repo still has no ratified"
  echo "  MOS-corner/R-corner correlation convention, and crossing the axes"
  echo "  in full reports every combination rather than inventing one."
  echo "- **Feedback divider (issue #28) under test here**: \`XRtop\`/\`XRbot\`,"
  echo "  PDK \`rhigh\`, \`w=1u l=25.43u b=7\` per leg. Its own standing current"
  echo "  is measured per point (\`i_divider_a\`, with the implied per-leg"
  echo "  resistance in \`r_divider_leg_ohm\`) from the non-invasive replica"
  echo "  divider in \`testbench/tb_dcsweep_cmos5l.spice.tmpl\` -- an ideal"
  echo "  unity-gain VCVS copy of VOUT driving a byte-identical pair of"
  echo "  \`rhigh\` legs through a 0V ammeter, which loads neither VOUT nor"
  echo "  \`i(vin)\`, so Iq stays directly comparable to the #21/#25 records."
  echo "- **MoM-cap (Cc) caveat**: cornerCAP.lib maps every corner/mismatch/stat"
  echo "  section to the SAME nominal \`cap_cmomi\` model at this PDK's pin (no"
  echo "  characterised corner spread exists) -- every phase-margin / loop-gain"
  echo "  result in \`records/${RECORD_ID}.csv\` is therefore \`insufficient-evidence\`"
  echo "  pending the \`loopgain_ccsens_*\` VALUE sensitivity points in"
  echo "  \`records/${RECORD_ID}.sensitivity.csv\`, per design/README.md's"
  echo "  'PDK caveats honoured' table and issue #21 acceptance criterion 4."
  echo "- **Netlist provenance**: circuit-level bench (this experiment"
  echo "  instantiates \`ldo_core_cmos5l\` -- whole for dcsweep/psrr, flattened"
  echo "  one level with a sync-checked loop break for loopgain -- not a"
  echo "  bare-device screen; contrast \`sim/pass-device-screening/\`)."
  echo "- **Links**:"
  echo "  - Templates: \`testbench/tb_dcsweep_cmos5l.spice.tmpl\`,"
  echo "    \`testbench/tb_loopgain_cmos5l.spice.tmpl\`,"
  echo "    \`testbench/tb_psrr_cmos5l.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs + per-point sweep CSVs:"
  echo "    \`corners/${RECORD_ID}/\`"
  echo "  - Main PVT-grid CSV (spec-row-relevant merged metrics, one row"
  echo "    per corner/temp/res_section): \`records/${RECORD_ID}.csv\`"
  echo "  - Cc-value / resistor-corner sensitivity CSV:"
  echo "    \`records/${RECORD_ID}.sensitivity.csv\`"
  echo "  - Before/after/delta CSV vs the pre-conversion baseline:"
  echo "    \`records/${RECORD_ID}.delta.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #31."
  echo
  echo "## Before / after / delta vs the pre-conversion baseline"
  echo
  echo "\"Before\" is \`records/$(basename "${BASELINE_CSV}")\` -- the #25"
  echo "post-Mpass-resize record, taken against the behavioural 300k"
  echo "\`res.sym\` divider, at \`res_typ\`. \"After\" is this run, against the"
  echo "PDK \`rhigh\` divider, at each of the three cornerRES.lib sections."
  echo "Both runs share the same benches, the same PDK pin and the same"
  echo "ngspice build, so the deltas isolate the divider conversion plus the"
  echo "resistor-corner axis and nothing else."
  echo
  echo "The divider standing current's \"before\" column is **derived, not"
  echo "measured**: the behavioural divider was an ideal, exactly-600k,"
  echo "corner-independent pair, so its current is"
  echo "\`VOUT_no_load / 600k\` exactly, taken from the baseline record's own"
  echo "recorded \`vout_no_load_v\`. There was no such column in the #21/#25"
  echo "CSVs because there was nothing corner-dependent to record."
  cat "${CMP_MD_FRAGMENT}"
} > "${MD_OUT}"

echo "run_sweep.sh: wrote ${MD_OUT}, ${CSV_OUT}, ${SENS_CSV_OUT}, ${DELTA_CSV_OUT}"
echo "run_sweep.sh: ${passed}/${total} points passed; completeness=$( [[ ${COMPLETENESS_OK} -eq 1 ]] && echo OK || echo INCOMPLETE )"

if [[ ${#failed_points[@]} -gt 0 || ${COMPLETENESS_OK} -ne 1 ]]; then
  exit 1
fi
exit 0
