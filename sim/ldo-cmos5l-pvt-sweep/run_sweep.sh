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
# across the full process x temperature grid {tt,ff,ss,sf,fs} x
# {-40,27,125}C = 15 points (cornerMOShv.lib's five sections -- confirmed
# byte-identical to ihp-sg13g2's own copy at this PDK's pin, see
# sim/pdk-cmos5l.json), PLUS two small sensitivity sweeps at the nominal
# tt/27C corner only:
#   - Cc (Miller cap) value sensitivity {0.5x,1x,2x} -- cornerCAP.lib maps
#     every corner/mismatch/stat section to the SAME nominal cap_cmomi
#     model (no characterised corner spread exists for this PDK's MoM
#     caps), so a PROCESS-corner sweep over Cc is a no-op; this VALUE
#     sensitivity sweep is what design/README.md's "PDK caveats honoured"
#     table says this issue owes instead.
#   - Rz (nulling resistor) corner sensitivity {res_bcs,res_typ,res_wcs} --
#     rhigh DOES have a real, characterised corner spread (cornerRES.lib),
#     unlike Cc; this experiment holds Rz at res_typ across the main 15
#     point PVT grid (there is no established MOS-corner/R-corner
#     correlation convention in this repo yet -- see README.md "Resistor
#     corner: held at nominal across the MOS sweep, checked separately")
#     and checks its own spread's effect on phase margin here instead.
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
# XMpass/Rtop/Rbot/Xamp instantiation lines. If a future schematic edit
# changes that connectivity, this bench would silently go stale -- so
# diff the mirrored lines against the actual generated netlist every run,
# not just at authoring time. ---
assert_loopgain_topology_sync() {
  local body expected
  body="$(awk '/^\.subckt ldo_core_cmos5l /,/^\.ends/' "${DESIGN_NETLIST}" | grep -E '^(XMpass|Rtop|Rbot|Xamp) ')"
  expected="$(cat <<'EOF'
XMpass VOUT EAOUT VIN VIN sg13_hv_pmos w=300u l=0.5u ng=1 m=1
Rtop VOUT FB 300k m=1
Rbot FB VSS 300k m=1
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
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.md"
mkdir -p "${SNAPSHOTS_OUT}" "${CORNERS_OUT}" "${RECORDS_DIR}"

CORNERS=(tt ss ff sf fs)
TEMPS=(-40 27 125)

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

run_ngspice() {
  local point_id="$1" netlist="$2"
  local log="${CORNERS_OUT}/${point_id}.log"
  local rc=0
  ngspice -b "${netlist}" > "${log}" 2>&1 || rc=$?
  total=$((total + 1))
  if [[ ${rc} -ne 0 ]] || grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error|singular matrix|gmin stepping failed|no convergence" "${log}"; then
    echo "run_sweep.sh: FAILED ${point_id} (rc=${rc}) -- see ${log}" >&2
    failed_points+=("${point_id}")
    return 1
  fi
  passed=$((passed + 1))
  return 0
}

# --- Main 15-point PVT grid: dcsweep + loopgain + psrr at each point ---
for corner in "${CORNERS[@]}"; do
  for temp in "${TEMPS[@]}"; do
    mos_section="mos_${corner}"

    point_id="dcsweep_${corner}_${temp}c"
    netlist="$(gen_netlist dcsweep "${point_id}" "${mos_section}" res_typ cap_typ "${temp}" "${DESIGN_NETLIST}" "30u (nominal)")"
    run_ngspice "${point_id}" "${netlist}" || true

    point_id="loopgain_${corner}_${temp}c"
    netlist="$(gen_netlist loopgain "${point_id}" "${mos_section}" res_typ cap_typ "${temp}" "${DESIGN_NETLIST}" "30u (nominal)")"
    run_ngspice "${point_id}" "${netlist}" || true

    point_id="psrr_${corner}_${temp}c"
    netlist="$(gen_netlist psrr "${point_id}" "${mos_section}" res_typ cap_typ "${temp}" "${DESIGN_NETLIST}" "30u (nominal)")"
    run_ngspice "${point_id}" "${netlist}" || true
  done
done

# --- Cc (Miller cap) value sensitivity, at tt/27C only -- see header ---
CC_NETLISTS_DIR="${SNAPSHOTS_OUT}/design-netlist-cc-sensitivity"
mkdir -p "${CC_NETLISTS_DIR}"
declare -A CC_WIDTHS=( ["0.5x"]="15e-6" ["1x"]="30e-6" ["2x"]="60e-6" )
for label in 0.5x 1x 2x; do
  w="${CC_WIDTHS[${label}]}"
  cc_netlist="${CC_NETLISTS_DIR}/ldo_core_cmos5l_cc${label}.spice"
  # XCc's line is `XCc OUT MZ cap_cmomi w=30e-6 l=30e-6 ...` -- substitute
  # ONLY the w=30e-6 token (Cc's width; l is held fixed at 30e-6), leaving
  # every other device in the file untouched.
  sed "s/XCc OUT MZ cap_cmomi w=30e-6 l=30e-6/XCc OUT MZ cap_cmomi w=${w} l=30e-6/" \
    "${DESIGN_NETLIST}" > "${cc_netlist}"
  if [[ "${label}" != "1x" ]] && diff -q "${cc_netlist}" "${DESIGN_NETLIST}" >/dev/null; then
    echo "run_sweep.sh: FATAL -- Cc width substitution for ${label} did not change ${cc_netlist} (XCc line text may have drifted from what this script expects)." >&2
    exit 4
  fi

  point_id="loopgain_ccsens_${label}_tt_27c"
  netlist="$(gen_netlist loopgain "${point_id}" mos_tt res_typ cap_typ 27 "${cc_netlist}" "${w} (${label} of nominal 30e-6)")"
  run_ngspice "${point_id}" "${netlist}" || true
done

# --- Rz (nulling resistor) corner sensitivity, at tt/27C only, nominal Cc ---
for label_section in "bcs:res_bcs" "typ:res_typ" "wcs:res_wcs"; do
  label="${label_section%%:*}"
  res_section="${label_section##*:}"
  point_id="loopgain_rzsens_${label}_tt_27c"
  netlist="$(gen_netlist loopgain "${point_id}" mos_tt "${res_section}" cap_typ 27 "${DESIGN_NETLIST}" "30u (nominal)")"
  run_ngspice "${point_id}" "${netlist}" || true
done

if [[ ${passed} -eq 0 ]]; then
  echo "run_sweep.sh: no points passed -- refusing to write a summary." >&2
  exit 1
fi

# --- Post-process everything into the two record CSVs ---
python3 - "${CORNERS_OUT}" "${CSV_OUT}" "${SENS_CSV_OUT}" "${CORNERS[*]}" "${TEMPS[*]}" <<'PYEOF'
import csv, sys, math

corners_dir, csv_out, sens_csv_out, corners_str, temps_str = sys.argv[1:6]
CORNERS = corners_str.split()
TEMPS = [t for t in temps_str.split()]

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
    (scale,v(vin),scale,v(vout),scale,i(vin)) x N rows, nested sweep with
    Vin as the fast/inner variable and Iload as the slow/outer variable
    (see that template's header). Detect Iload-block boundaries by
    watching Vin reset to a smaller value than the previous row."""
    rows = read_wrdata(path, 6)
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
        cur.append((vin, r[3], r[5]))
        prev_vin = vin
    blocks.append(cur)
    if len(blocks) < 5:
        return {"error": f"expected 5 Iload blocks, got {len(blocks)}"}

    def nearest(block, vin_target):
        return min(block, key=lambda t: abs(t[0] - vin_target))

    out = {}
    # Iq + no-load op point, block 0 (Iload=0), Vin=3.30V.
    v, vo, i = nearest(blocks[0], 3.30)
    out["iq_a"] = abs(i)
    out["vout_no_load_v"] = vo

    # Line regulation, block 0 (no load), Input row's {2.97,3.63}V window.
    v_lo, vo_lo, _ = nearest(blocks[0], 2.97)
    v_hi, vo_hi, _ = nearest(blocks[0], 3.63)
    out["line_reg_in_regulation"] = abs(vo_lo - VOUT_TARGET) < 0.01 * VOUT_TARGET and abs(vo_hi - VOUT_TARGET) < 0.01 * VOUT_TARGET
    out["line_reg_mv_per_v"] = (vo_hi - vo_lo) / (v_hi - v_lo) * 1000.0

    # Dropout @ 50mA, last block (Iload=0.05A): scan from Vin_max downward
    # for the first point where VOUT falls below 0.99x the fixed 1.8V
    # target (README.md "Nested DC sweep").
    block50 = sorted(blocks[-1], key=lambda t: t[0])
    v_at_max, vo_at_max, _ = block50[-1]
    out["vout_at_vinmax_50ma_v"] = vo_at_max
    dropout_v = None
    for v, vo, _ in reversed(block50):
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
        row = {"corner": corner, "temp_c": temp}
        dc = dc_metrics(f"{corners_dir}/dcsweep_{corner}_{temp}c_dc.csv")
        lg = loopgain_metrics(f"{corners_dir}/loopgain_{corner}_{temp}c_ac.csv")
        ps = psrr_metrics(f"{corners_dir}/psrr_{corner}_{temp}c_ac.csv")
        for src in (dc, lg, ps):
            if src:
                row.update({k: v for k, v in src.items() if k != "vout_at_vinmax_by_load"})
        main_rows.append(row)

fieldnames = [
    "corner", "temp_c", "iq_a", "vout_no_load_v",
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

# --- Sensitivity CSV: Cc value sweep + Rz corner sweep, tt/27C only ---
sens_rows = []
for label in ["0.5x", "1x", "2x"]:
    lg = loopgain_metrics(f"{corners_dir}/loopgain_ccsens_{label}_tt_27c_ac.csv")
    row = {"sweep": "cc_value", "point": label}
    if lg:
        row.update(lg)
    sens_rows.append(row)
for label in ["bcs", "typ", "wcs"]:
    lg = loopgain_metrics(f"{corners_dir}/loopgain_rzsens_{label}_tt_27c_ac.csv")
    row = {"sweep": "rz_corner", "point": label}
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

print(f"run_sweep.sh (post-process): wrote {len(main_rows)} main rows, {len(sens_rows)} sensitivity rows")
PYEOF

# --- Completeness matrix: every (corner,temp) has all 3 benches present ---
COMPLETENESS_OK=1
for corner in "${CORNERS[@]}"; do
  for temp in "${TEMPS[@]}"; do
    for bench in dcsweep loopgain psrr; do
      point_id="${bench}_${corner}_${temp}c"
      if [[ " ${failed_points[*]-} " == *" ${point_id} "* ]]; then
        echo "run_sweep.sh: INCOMPLETE ${point_id}" >&2
        COMPLETENESS_OK=0
      fi
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: ldo-cmos5l-pvt-sweep"
  echo "- **Claim**: design/sg13cmos5l/ldo_core_cmos5l.sch's closed loop"
  echo "  (issue #20), verified against the spec table re-derived at this"
  echo "  PDK's rails (README.md), across the full process x temperature"
  echo "  PVT grid, plus Cc-value and Rz-corner sensitivity sweeps -- the"
  echo "  input to issue #21's acceptance criteria."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned revision: see"
  echo "  \`sim/pdk-cmos5l.json\` (commit \`607e18d\`, re-verified against the"
  echo "  installed checkout)."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by"
  echo "  \`PDK=${PDK} sim/tools/build-osdi.sh\`."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Design netlist under test**: \`design/sg13cmos5l/netlist/ldo_core_cmos5l.spice\`"
  echo "  at this repo's git sha \`${REPO_GIT_SHA}\`."
  echo "- **Corner matrix run**: process {${CORNERS[*]}} (cornerMOShv.lib) x"
  echo "  temperature {${TEMPS[*]}}C = 15 points x 3 benches (dcsweep,"
  echo "  loopgain, psrr) = 45 points, plus 6 sensitivity points (Cc value"
  echo "  {0.5x,1x,2x} + Rz corner {bcs,typ,wcs}, both at tt/27C only)."
  echo "- **Result**: ${passed}/${total} points PASS (ngspice exit 0, no"
  echo "  convergence/model-load error strings in the log)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Completeness matrix**: $( [[ ${COMPLETENESS_OK} -eq 1 ]] && echo 'OK -- every (corner,temp) has all 3 benches present' || echo 'INCOMPLETE -- see stderr log above' )"
  echo "- **Resistor corner**: held at \`res_typ\` (nominal) across the main"
  echo "  15-point PVT grid -- no established MOS-corner/R-corner"
  echo "  correlation convention exists yet in this repo (see README.md);"
  echo "  Rz's own real corner spread is checked separately via the"
  echo "  \`loopgain_rzsens_*\` sensitivity points instead."
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
  echo "    per corner/temp): \`records/${RECORD_ID}.csv\`"
  echo "  - Cc-value / Rz-corner sensitivity CSV:"
  echo "    \`records/${RECORD_ID}.sensitivity.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #21."
} > "${MD_OUT}"

echo "run_sweep.sh: wrote ${MD_OUT}, ${CSV_OUT}, ${SENS_CSV_OUT}"
echo "run_sweep.sh: ${passed}/${total} points passed; completeness=$( [[ ${COMPLETENESS_OK} -eq 1 ]] && echo OK || echo INCOMPLETE )"

if [[ ${#failed_points[@]} -gt 0 || ${COMPLETENESS_OK} -ne 1 ]]; then
  exit 1
fi
exit 0
