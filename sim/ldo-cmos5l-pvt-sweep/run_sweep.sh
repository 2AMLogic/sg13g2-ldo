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
#
# PLUS, from issue #35, a Cc value-TOLERANCE window at the two corners that
# actually bind it (ss/125C x {res_bcs,res_wcs}), with BOTH the loopgain and
# psrr benches run at every width. The tt/27C sensitivity points above were
# a fair robustness test while tt/27C was near the worst case; since #31
# crossed the resistor corner it is not (DR-0004), and at tt/27C every spec
# row passes with tens of degrees / dB to spare, so those three points can
# no longer show that the PASS verdict survives a wrong MoM-cap value. The
# tolerance window measures the two opposing bounds directly: too small a Cc
# loses phase margin at res_bcs/125C, too large a Cc loses PSRR@1kHz. Both
# experiments are kept -- the tt/27C one for record-to-record comparability,
# the tolerance one because it is the claim that actually needs support.
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
      -e "s|@@CC_W@@|nominal (--check-env)|g" \
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

# Baseline this run is compared against. The before/after/delta table in the
# generated record is derived from this file. Pinned by name on purpose --
# sim/ records are append-only evidence, so this path is stable, and a
# re-baselining is an explicit edit here rather than an implicit "whatever
# the newest record happens to be".
#
# RE-BASELINED BY #35, from the #25 record (20260916-112842-c25ff53) to the
# #31 one. Reason: #25 held the resistor axis at res_typ, so it has no
# res_bcs/res_wcs rows to compare against -- and res_bcs/125C is exactly
# where #31 found the phase-margin gap #35 exists to close. The #31 record
# is the last run before the #35 compensation change, shares this run's
# benches, PDK pin, ngspice build and full 45-point grid, and is the
# baseline issue #35 names. Comparing against it makes the before/after a
# like-for-like, same-section comparison at every point rather than a
# same-corner-different-section one.
BASELINE_CSV="${RECORDS_DIR}/20260916-210331-9d3ace1.csv"

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
        netlist="$(gen_netlist "${bench}" "${point_id}" "${mos_section}" "${res_section}" cap_typ "${temp}" "${DESIGN_NETLIST}" "170u (nominal)")"
        run_ngspice "${point_id}" "${netlist}" || true
      done
    done
  done
done

# --- Cc (Miller cap) value sensitivity, at tt/27C only -- see header ---
CC_NETLISTS_DIR="${SNAPSHOTS_OUT}/design-netlist-cc-sensitivity"
mkdir -p "${CC_NETLISTS_DIR}"
CC_NOMINAL_W="170e-6"
declare -A CC_WIDTHS=( ["0.5x"]="85e-6" ["1x"]="170e-6" ["2x"]="340e-6" )

# Substitute ONLY the w= token on XCc's line (Cc's width; l is held fixed at
# 30e-6), leaving every other device in the file untouched. `${CC_NOMINAL_W}`
# must track design/sg13cmos5l/ldo_erramp_cmos5l.sch's own Cc width -- #20
# drew 30e-6, #25 raised it to 100e-6, #35 raised it to 170e-6 -- and the
# substitution FATALs below if the XCc line text has drifted from what this
# expects, rather than silently simulating the nominal netlist three times.
subst_cc_width() {  # <out-netlist> <width>
  local out="$1" w="$2"
  sed "s/XCc OUT MZ cap_cmomi w=${CC_NOMINAL_W} l=30e-6/XCc OUT MZ cap_cmomi w=${w} l=30e-6/" \
    "${DESIGN_NETLIST}" > "${out}"
  if [[ "${w}" != "${CC_NOMINAL_W}" ]] && diff -q "${out}" "${DESIGN_NETLIST}" >/dev/null; then
    echo "run_sweep.sh: FATAL -- Cc width substitution to ${w} did not change ${out} (XCc line text may have drifted from what this script expects; CC_NOMINAL_W=${CC_NOMINAL_W})." >&2
    exit 4
  fi
}

for label in 0.5x 1x 2x; do
  w="${CC_WIDTHS[${label}]}"
  cc_netlist="${CC_NETLISTS_DIR}/ldo_core_cmos5l_cc${label}.spice"
  subst_cc_width "${cc_netlist}" "${w}"

  point_id="loopgain_ccsens_${label}_tt_27c"
  netlist="$(gen_netlist loopgain "${point_id}" mos_tt res_typ cap_typ 27 "${cc_netlist}" "${w} (${label} of nominal ${CC_NOMINAL_W})")"
  run_ngspice "${point_id}" "${netlist}" || true
done

# --- Cc VALUE-TOLERANCE window, at the two corners that actually bind
# (issue #35).
#
# The {0.5x,1x,2x} points above run at tt/27C, where every spec row passes
# with tens of degrees / dB to spare -- so they cannot, on their own, show
# that the PASS verdict survives a wrong MoM-cap value. They were a fair
# test while tt/27C was near the worst case; since #31 crossed the resistor
# corner it is not (DR-0004). What binds Cc is a pair of opposing rows at
# ss/125C:
#
#   - too SMALL a Cc puts the Rz*Cc phase-lead zero above the loop's
#     crossover at res_bcs/125C, where Rz has shrunk to ~0.60x nominal,
#     and PM >= 45deg fails -- the DR-0004 failure this issue exists to fix;
#   - too LARGE a Cc drags the dominant pole (and with it the loop gain at
#     1kHz, which is what sets PSRR there) down until PSRR@1kHz > 50dB
#     fails.
#
# So this experiment sweeps Cc's width across that window at ss/125C against
# BOTH resistor sections that hold a worst case (res_bcs and res_wcs) and
# runs BOTH the loopgain and psrr benches at every point, so the two bounds
# are measured rather than asserted. DR-0005 cites the resulting edges.
# ---
CC_TOL_WIDTHS=(85e-6 110e-6 130e-6 170e-6 220e-6 259e-6 340e-6)
for w in "${CC_TOL_WIDTHS[@]}"; do
  cc_netlist="${CC_NETLISTS_DIR}/ldo_core_cmos5l_cctol_${w}.spice"
  subst_cc_width "${cc_netlist}" "${w}"
  for rlabel in bcs wcs; do
    for bench in loopgain psrr; do
      point_id="${bench}_cctol_${w}_ss_125c_r${rlabel}"
      netlist="$(gen_netlist "${bench}" "${point_id}" mos_ss "res_${rlabel}" cap_typ 125 "${cc_netlist}" "${w} (Cc tolerance window)")"
      run_ngspice "${point_id}" "${netlist}" || true
    done
  done
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
  netlist="$(gen_netlist loopgain "${point_id}" mos_tt "res_${label}" cap_typ 27 "${DESIGN_NETLIST}" "170u (nominal)")"
  run_ngspice "${point_id}" "${netlist}" || true
done

# --- Divider attribution, over the whole 45-point grid (issue #31 AC3/AC4).
#
# Crossing the resistor corner moves TWO rhigh devices at once: the feedback
# divider #28 converted, and the error amp's nulling resistor Rz (already a
# PDK rhigh since #20). A raw before/after against the #21/#25 records
# therefore cannot, on its own, say which of the two a margin shift belongs
# to -- and this issue exists to answer exactly that about the divider.
#
# So: re-run the loop-gain bench at every main-grid point with the divider
# swapped BACK to the pre-#28 behavioural 300k pair while everything else
# (MOS corner, temperature, resistor section, Cc) is held identical. The
# difference between these points and the main grid's loopgain points is
# the divider conversion's own contribution, with Rz's spread held common
# to both sides and cancelled out.
#
# The substitution is applied to the GENERATED bench netlist, not to the
# design netlist: tb_loopgain_cmos5l.spice.tmpl flattens ldo_core_cmos5l
# one level (see its header), so the divider lines it actually simulates
# are the mirrored copies in the bench, not the ones inside the .include'd
# subckt. Substituting the design netlist would silently change nothing.
BEHDIV_TOP='XRtop VOUT FB VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7'
BEHDIV_BOT='XRbot FB VSS VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7'
for corner in "${CORNERS[@]}"; do
  for temp in "${TEMPS[@]}"; do
    for rlabel in "${RES_LABELS[@]}"; do
      point_id="loopgain_divattr_${corner}_${temp}c_r${rlabel}"
      netlist="$(gen_netlist loopgain "${point_id}" "mos_${corner}" "res_${rlabel}" cap_typ "${temp}" "${DESIGN_NETLIST}" "170u (nominal)")"
      sed -e "s|^${BEHDIV_TOP}\$|Rtop VOUT FB 300k m=1|" \
          -e "s|^${BEHDIV_BOT}\$|Rbot FB VSS 300k m=1|" \
          "${netlist}" > "${netlist}.behdiv"
      mv "${netlist}.behdiv" "${netlist}"
      if ! grep -q '^Rtop VOUT FB 300k m=1$' "${netlist}" \
         || ! grep -q '^Rbot FB VSS 300k m=1$' "${netlist}"; then
        echo "run_sweep.sh: FATAL -- behavioural-divider substitution did not take in ${netlist}" >&2
        echo "run_sweep.sh: (tb_loopgain_cmos5l.spice.tmpl's flattened divider lines may have drifted)." >&2
        exit 4
      fi
      run_ngspice "${point_id}" "${netlist}" || true
    done
  done
done

if [[ ${passed} -eq 0 ]]; then
  echo "run_sweep.sh: no points passed -- refusing to write a summary." >&2
  exit 1
fi

# --- Post-process everything into the record CSVs + the before/after/delta
# markdown fragment that gets inlined into the record below ---
CMP_MD_FRAGMENT="${CORNERS_OUT}/_before_after_delta.md"
python3 - "${CORNERS_OUT}" "${CSV_OUT}" "${SENS_CSV_OUT}" "${CORNERS[*]}" "${TEMPS[*]}" \
         "${RES_LABELS[*]}" "${BASELINE_CSV}" "${DELTA_CSV_OUT}" "${CMP_MD_FRAGMENT}" \
         "${CC_TOL_WIDTHS[*]}" "${CC_NOMINAL_W}" <<'PYEOF'
import csv, sys, math, os

(corners_dir, csv_out, sens_csv_out, corners_str, temps_str,
 res_labels_str, baseline_csv, delta_csv_out, cmp_md_out,
 cc_tol_widths_str, cc_nominal_w) = sys.argv[1:12]
CORNERS = corners_str.split()
TEMPS = [t for t in temps_str.split()]
RES_LABELS = res_labels_str.split()
CC_TOL_WIDTHS = cc_tol_widths_str.split()

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

# --- Cc value-tolerance CSV: the two opposing bounds on Cc, measured at the
# corners that actually bind them (issue #35 / DR-0005). PM comes from the
# loopgain bench and PSRR from the psrr bench at the SAME point, so a row can
# be read as "at this Cc, at this corner, here is every stability/PSRR row
# the spec table asks for". ---
cc_nominal_f = float(cc_nominal_w)
cctol_rows = []
for w_str in CC_TOL_WIDTHS:
    for rlabel in ["bcs", "wcs"]:
        sfx = f"cctol_{w_str}_ss_125c_r{rlabel}"
        lg = loopgain_metrics(f"{corners_dir}/loopgain_{sfx}_ac.csv")
        ps = psrr_metrics(f"{corners_dir}/psrr_{sfx}_ac.csv")
        row = {"cc_w": w_str,
               "cc_x_nominal": float(w_str) / cc_nominal_f,
               "corner": "ss", "temp_c": 125, "res_section": f"res_{rlabel}"}
        for src in (lg, ps):
            if src:
                row.update(src)
        row["pm_ok"] = (row.get("phase_margin_deg") is not None
                        and row["phase_margin_deg"] >= 45.0)
        row["gm_ok"] = (row.get("gain_margin_db") is not None
                        and row["gain_margin_db"] >= 10.0)
        row["psrr_1khz_ok"] = (row.get("psrr_db_1khz") is not None
                               and row["psrr_db_1khz"] > 50.0)
        row["psrr_100khz_ok"] = (row.get("psrr_db_100khz") is not None
                                 and row["psrr_db_100khz"] > 20.0)
        row["all_ok"] = all(row[k] for k in
                            ("pm_ok", "gm_ok", "psrr_1khz_ok", "psrr_100khz_ok"))
        cctol_rows.append(row)

cctol_fieldnames = [
    "cc_w", "cc_x_nominal", "corner", "temp_c", "res_section",
    "dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
    "phase_margin_deg", "gain_margin_db", "psrr_db_1khz", "psrr_db_100khz",
    "pm_ok", "gm_ok", "psrr_1khz_ok", "psrr_100khz_ok", "all_ok",
]
cctol_csv_out = csv_out.replace(".csv", ".cc-tolerance.csv")
with open(cctol_csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cctol_fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in cctol_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in cctol_fieldnames})

# --- Before / after / delta against the pinned baseline record ---
# "Before" is the baseline record named by BASELINE_CSV. From issue #35 that
# is the #31 record -- the first run against BOTH the PDK `rhigh` feedback
# divider (#28) and the full crossed resistor axis, and the run that found
# the res_bcs/125C phase-margin gap #35 exists to close. Because that record
# already carries one row per (corner, temperature, res_section), the
# comparison is like-for-like at every one of the 45 grid points: same
# benches, same PDK pin, same ngspice build, same resistor section on both
# sides, so the deltas isolate the compensation change and nothing else.
#
# (The #21/#25 records key on (corner, temperature) only -- they held the
# resistor axis at res_typ -- so pointing BASELINE_CSV back at one of them
# leaves the res_bcs/res_wcs "before" cells empty rather than silently
# comparing against the wrong section. That is the intended behaviour: a
# missing cell reads "n/a", it does not read as a zero delta.)
baseline = {}
if os.path.exists(baseline_csv):
    with open(baseline_csv) as f:
        for r in csv.DictReader(f):
            def _f(k):
                try:
                    return float(r[k])
                except (KeyError, TypeError, ValueError):
                    return None
            key = (r["corner"], r["temp_c"], r.get("res_section", "res_typ"))
            baseline[key] = {k: _f(k) for k in
                             ("dc_gain_db", "phase_margin_deg", "unity_gain_freq_hz",
                              "gain_margin_db", "psrr_db_1khz", "psrr_db_100khz",
                              "iq_a", "vout_no_load_v", "i_divider_a",
                              "line_reg_mv_per_v", "load_reg_pct",
                              "dropout_v_50ma")}

after = {(r["corner"], str(r["temp_c"]), r["res_section"]): r for r in main_rows}

METRICS = [
    # (csv key, heading, unit, scale, decimals, higher_is_better)
    ("phase_margin_deg", "Phase margin", "deg", 1.0, 2, True),
    ("gain_margin_db", "Gain margin", "dB", 1.0, 2, True),
    ("unity_gain_freq_hz", "Unity-gain frequency", "kHz", 1e-3, 2, None),
    ("dc_gain_db", "DC loop gain", "dB", 1.0, 2, True),
    ("psrr_db_1khz", "PSRR @ 1kHz", "dB", 1.0, 2, True),
    ("psrr_db_100khz", "PSRR @ 100kHz", "dB", 1.0, 2, True),
    ("iq_a", "Iq, no load", "uA", 1e6, 3, False),
    ("dropout_v_50ma", "Dropout @ 50mA", "V", 1.0, 3, False),
    ("line_reg_mv_per_v", "Line regulation", "mV/V", 1.0, 3, False),
    ("load_reg_pct", "Load regulation", "%", 1.0, 4, False),
    ("vout_no_load_v", "Output accuracy (VOUT, no load)", "V", 1.0, 5, None),
    ("i_divider_a", "Divider standing current", "uA", 1e6, 3, False),
]

delta_rows = []
for corner in CORNERS:
    for temp in TEMPS:
        for rlabel in RES_LABELS:
            section = f"res_{rlabel}"
            b = baseline.get((corner, str(temp), section), {})
            a = after.get((corner, str(temp), section), {})
            for key, heading, unit, scale, dec, _hib in METRICS:
                bv, av = b.get(key), a.get(key)
                delta_rows.append({
                    "corner": corner, "temp_c": temp, "res_section": section,
                    "metric": key, "unit": unit, "before": bv, "after": av,
                    "delta": (av - bv) if (bv is not None and av is not None) else None,
                })

delta_fieldnames = ["corner", "temp_c", "res_section", "metric", "unit",
                    "before", "after", "delta"]
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


# --- Divider attribution: same point, same resistor section, divider
# swapped back to the pre-#28 behavioural 300k pair. The difference is the
# conversion's OWN contribution, with Rz's corner spread common to both
# sides and therefore cancelled.
attr_rows = []
for corner in CORNERS:
    for temp in TEMPS:
        for rlabel in RES_LABELS:
            sfx = f"{corner}_{temp}c_r{rlabel}"
            beh = loopgain_metrics(f"{corners_dir}/loopgain_divattr_{sfx}_ac.csv")
            rh = after.get((corner, str(temp), f"res_{rlabel}"), {})
            row = {"corner": corner, "temp_c": temp, "res_section": f"res_{rlabel}"}
            for key in ("phase_margin_deg", "gain_margin_db", "dc_gain_db"):
                bv = (beh or {}).get(key)
                av = rh.get(key)
                row[f"{key}_behavioural_divider"] = bv
                row[f"{key}_rhigh_divider"] = av
                row[f"{key}_divider_delta"] = (av - bv) if (bv is not None and av is not None) else None
            attr_rows.append(row)

attr_fieldnames = ["corner", "temp_c", "res_section"]
for key in ("phase_margin_deg", "gain_margin_db", "dc_gain_db"):
    attr_fieldnames += [f"{key}_behavioural_divider", f"{key}_rhigh_divider",
                        f"{key}_divider_delta"]
attr_csv_out = delta_csv_out.replace(".delta.csv", ".divider-attribution.csv")
with open(attr_csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=attr_fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in attr_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in attr_fieldnames})

with open(cmp_md_out, "w") as f:
    BASELINE_LABEL = os.path.basename(baseline_csv).replace(".csv", "")
    for key, heading, unit, scale, dec, _hib in METRICS:
        rows = by_key.get(key, [])
        deltas = [r["delta"] for r in rows if r.get("delta") is not None]
        worst = max(deltas, key=abs) if deltas else None
        f.write(f"\n### {heading} ({unit})\n\n")
        if deltas:
            f.write(f"Largest change across all {len(deltas)} compared points: "
                    f"**{fmt(worst, scale, dec, signed=True)} {unit}**.\n\n")
        f.write(f"| corner / temp / R corner | before (`{BASELINE_LABEL}`) "
                "| after (this run) | delta |\n")
        f.write("|---|---|---|---|\n")
        for row in rows:
            f.write(
                f"| `{row['corner']}` / {row['temp_c']}C / `{row['res_section']}` "
                f"| {fmt(row.get('before'), scale, dec)} "
                f"| {fmt(row.get('after'), scale, dec)} "
                f"| {fmt(row.get('delta'), scale, dec, signed=True)} |\n")

    # --- Cc value-tolerance window (issue #35 / DR-0005). ---
    f.write("\n### `Cc` value-tolerance window, at the corners that bind it\n\n")
    f.write("`cornerCAP.lib` maps every corner/mismatch/stat section to the\n"
            "SAME nominal `cap_cmomi` model at this PDK's pin, so there is no\n"
            "characterised MoM-cap corner spread to sweep -- and the PDK's own\n"
            "documentation flags the model as not validated on CMOS5L silicon.\n"
            "Tolerance to a wrong cap VALUE is therefore the only robustness\n"
            "this caveat can be given, and it is measured here rather than\n"
            "asserted: `Cc`'s width is swept at `ss`/125C against both resistor\n"
            "sections that hold a worst case, with the loop-gain AND PSRR\n"
            "benches run at every point. A small `Cc` fails from below (the\n"
            "`Rz*Cc` zero lands above crossover at `res_bcs`, where `Rz` has\n"
            "shrunk to ~0.60x); a large `Cc` fails from above (the dominant\n"
            "pole, and with it the 1 kHz loop gain that sets PSRR, drops too\n"
            f"far). Machine-readable: `records/{os.path.basename(cctol_csv_out)}`.\n\n")
    f.write("| `Cc` w | x nominal | R corner | PM (deg) | GM (dB) "
            "| PSRR@1kHz (dB) | PSRR@100kHz (dB) | all spec rows met |\n")
    f.write("|---|---|---|---|---|---|---|---|\n")
    for row in cctol_rows:
        f.write(
            f"| `{row['cc_w']}` | {row['cc_x_nominal']:.2f}x "
            f"| `{row['res_section']}` "
            f"| {fmt(row.get('phase_margin_deg'), 1.0, 2)} "
            f"| {fmt(row.get('gain_margin_db'), 1.0, 2)} "
            f"| {fmt(row.get('psrr_db_1khz'), 1.0, 2)} "
            f"| {fmt(row.get('psrr_db_100khz'), 1.0, 2)} "
            f"| {'yes' if row['all_ok'] else '**NO**'} |\n")
    # A width counts as passing only if EVERY row at that width passes --
    # one of the two binding sections failing is a failing width, not a
    # half-passing one.
    by_w = {}
    for r in cctol_rows:
        by_w.setdefault(r["cc_w"], []).append(r)
    ok_w = [w for w in CC_TOL_WIDTHS if all(r["all_ok"] for r in by_w.get(w, []))]
    bad_w = [w for w in CC_TOL_WIDTHS if w not in ok_w]
    if ok_w:
        lo, hi = ok_w[0], ok_w[-1]
        f.write(f"\nEvery swept width from `{lo}` to `{hi}` meets every spec row at\n"
                f"both binding corners. The nominal is `{cc_nominal_w}`, so the\n"
                f"verdict tolerates a MoM-cap value from x{float(lo) / cc_nominal_f:.2f} to "
                f"x{float(hi) / cc_nominal_f:.2f}\nof what this model says it is.\n")
    if bad_w:
        f.write("\nWidths that do NOT hold every row at both binding corners: "
                + ", ".join(f"`{w}`" for w in bad_w)
                + ".\nThey are in the sweep on purpose: a tolerance window with no\n"
                  "measured ends is not a tolerance window.\n")

    # --- Mechanical spec gate. Thresholds are the repo root README.md's
    # DRAFT spec table verbatim (the same table sim/ldo-cmos5l-pvt-sweep's
    # own Results section is stated against), evaluated against EVERY point
    # in this run's grid. This is computed, not asserted in prose, so a
    # record can never claim a PASS its own CSV contradicts -- and so a
    # regression in a future run surfaces in the record itself rather than
    # relying on a reader re-deriving it from the CSV.
    SPEC = [
        ("phase_margin_deg", "Phase margin >= 45 deg", lambda v: v >= 45.0, "deg", 2),
        ("gain_margin_db", "Gain margin >= 10 dB", lambda v: v >= 10.0, "dB", 2),
        ("iq_a", "Iq (no load) < 30 uA", lambda v: v < 30e-6, "A", 9),
        ("psrr_db_1khz", "PSRR @ 1kHz > 50 dB", lambda v: v > 50.0, "dB", 2),
        ("psrr_db_100khz", "PSRR @ 100kHz > 20 dB", lambda v: v > 20.0, "dB", 2),
        ("line_reg_mv_per_v", "Line regulation < 5 mV/V", lambda v: v < 5.0, "mV/V", 3),
        ("load_reg_pct", "Load regulation < 1 %", lambda v: v < 1.0, "%", 4),
        ("dropout_v_50ma", "Dropout @ 50mA < 300 mV", lambda v: v < 0.300, "V", 3),
        ("vout_no_load_v", "Output accuracy 1.8V +/-2%", lambda v: abs(v - 1.8) <= 0.036, "V", 5),
    ]
    f.write("\n### Ratified-spec gate, evaluated over every point in this grid\n\n")
    f.write("Thresholds are the repo root `README.md` spec table's, applied\n"
            "mechanically to this record's own CSV -- not restated by hand.\n\n")
    f.write("| Spec row | Points evaluated | Points failing | Worst point |\n")
    f.write("|---|---|---|---|\n")
    gate_failures = []
    for key, label, ok, unit, dec in SPEC:
        pts = [(r.get(key), r) for r in main_rows if r.get(key) is not None]
        bad = [(v, r) for v, r in pts if not ok(v)]
        if bad:
            worst = min(bad, key=lambda t: t[0]) if key != "load_reg_pct" else max(bad, key=lambda t: t[0])
            wv, wr = worst
            worst_s = (f"`{wr['corner']}`/{wr['temp_c']}C/`{wr['res_section']}` "
                       f"= {wv:.{dec}f} {unit}")
            gate_failures.append((label, len(bad), len(pts), worst_s))
        else:
            worst_s = "--"
        f.write(f"| {label} | {len(pts)} | **{len(bad)}** | {worst_s} |\n")
    if gate_failures:
        f.write("\n**Spec rows NOT met at every point in this grid:**\n\n")
        for label, nbad, npts, worst_s in gate_failures:
            f.write(f"- {label} -- fails at {nbad} of {npts} points; worst {worst_s}\n")
        f.write("\nEvery failing point is listed row by row in "
                f"`records/{os.path.basename(csv_out)}`. Per CLAUDE.md, no spec\n"
                "row is relaxed to make this record pass; see the experiment\n"
                "README's Results section and the decision record it cites.\n")
    else:
        f.write("\nEvery spec row above is met at every point in this grid.\n")

    f.write("\n### Divider attribution: the conversion's own contribution\n\n")
    f.write("Same point, same MOS corner, same temperature, same resistor\n"
            "section, same `Cc` -- the only difference is the feedback\n"
            "divider: the pre-#28 behavioural 300k pair vs the PDK `rhigh`\n"
            "pair now in the schematic. Because `Rz`'s corner spread is\n"
            "common to both sides, it cancels, and what is left is the\n"
            "divider conversion's own effect. (Machine-readable:\n"
            f"`records/{os.path.basename(attr_csv_out)}`.)\n\n")
    f.write("| corner / temp / R corner | PM, behavioural 300k (deg) "
            "| PM, PDK `rhigh` (deg) | PM delta (deg) "
            "| GM delta (dB) | loop gain delta (dB) |\n")
    f.write("|---|---|---|---|---|---|\n")
    for row in attr_rows:
        f.write(
            f"| `{row['corner']}` / {row['temp_c']}C / `{row['res_section']}` "
            f"| {fmt(row.get('phase_margin_deg_behavioural_divider'), 1.0, 2)} "
            f"| {fmt(row.get('phase_margin_deg_rhigh_divider'), 1.0, 2)} "
            f"| {fmt(row.get('phase_margin_deg_divider_delta'), 1.0, 2, signed=True)} "
            f"| {fmt(row.get('gain_margin_db_divider_delta'), 1.0, 2, signed=True)} "
            f"| {fmt(row.get('dc_gain_db_divider_delta'), 1.0, 2, signed=True)} |\n")

print(f"run_sweep.sh (post-process): wrote {len(main_rows)} main rows, "
      f"{len(sens_rows)} sensitivity rows, {len(cctol_rows)} Cc-tolerance rows, "
      f"{len(delta_rows)} delta rows, "
      f"{len(attr_rows)} divider-attribution rows")
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
  echo "  RESISTOR-corner grid, plus Cc-value, Cc-tolerance and"
  echo "  resistor-corner sensitivity sweeps. This harness is issue #21's"
  echo "  deliverable; which issue's acceptance criteria a given record is"
  echo "  evidence for is told by the design netlist's git sha recorded"
  echo "  below -- #21 (original sizing), #25 (Mpass resize +"
  echo "  recompensation), #31 (the first run against the PDK \`rhigh\`"
  echo "  feedback divider that #28 substituted for the pre-#28 behavioural"
  echo "  300k \`res.sym\` pair, and the first to cross the resistor corner"
  echo "  across the whole grid), or #35 (the \`Cc\` re-compensation that"
  echo "  closes the res_bcs/125C phase-margin gap #31 found)."
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
  echo "  resistor corner {bcs,typ,wcs}, both at tt/27C only), plus"
  echo "  ${#CC_TOL_WIDTHS[@]} Cc widths x {res_bcs,res_wcs} x {loopgain,psrr}"
  echo "  = $(( ${#CC_TOL_WIDTHS[@]} * 4 )) Cc value-tolerance points at ss/125C (issue #35),"
  echo "  plus the 45-point divider-attribution loop-gain sweep (issue #31)."
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
  echo "  \`records/${RECORD_ID}.sensitivity.csv\` and -- from issue #35 -- the"
  echo "  \`*_cctol_*\` value-TOLERANCE points in"
  echo "  \`records/${RECORD_ID}.cc-tolerance.csv\`, which measure how far the"
  echo "  cap value may be wrong in EITHER direction before a spec row fails,"
  echo "  at the corners that bind it rather than at tt/27C. Per"
  echo "  design/README.md's 'PDK caveats honoured' table and issue #21"
  echo "  acceptance criterion 4."
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
  echo "  - Cc value-tolerance CSV (Cc width swept at the two corners that"
  echo "    bind it, loopgain AND psrr at every point -- issue #35):"
  echo "    \`records/${RECORD_ID}.cc-tolerance.csv\`"
  echo "  - Before/after/delta CSV vs the pinned baseline record:"
  echo "    \`records/${RECORD_ID}.delta.csv\`"
  echo "  - Divider-attribution CSV (PDK \`rhigh\` divider vs the pre-#28"
  echo "    behavioural 300k pair, everything else held identical):"
  echo "    \`records/${RECORD_ID}.divider-attribution.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent)."
  echo
  echo "## Before / after / delta vs the pinned baseline record"
  echo
  echo "\"Before\" is \`records/$(basename "${BASELINE_CSV}")\`; \"after\" is this"
  echo "run. Both runs share the same benches, the same PDK pin, the same"
  echo "ngspice build and the same 45-point grid, and every row below compares"
  echo "the SAME (MOS corner, temperature, resistor section) point on both"
  echo "sides -- so the deltas isolate what changed in the design netlist"
  echo "between the two records and nothing else. A \`n/a\` cell means the"
  echo "baseline record has no row for that point (it is not a zero delta)."
  cat "${CMP_MD_FRAGMENT}"
} > "${MD_OUT}"

echo "run_sweep.sh: wrote ${MD_OUT}, ${CSV_OUT}, ${SENS_CSV_OUT}, ${CSV_OUT%.csv}.cc-tolerance.csv, ${DELTA_CSV_OUT}"
echo "run_sweep.sh: ${passed}/${total} points passed; completeness=$( [[ ${COMPLETENESS_OK} -eq 1 ]] && echo OK || echo INCOMPLETE )"

if [[ ${#failed_points[@]} -gt 0 || ${COMPLETENESS_OK} -ne 1 ]]; then
  exit 1
fi
exit 0
