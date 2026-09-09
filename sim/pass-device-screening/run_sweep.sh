#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/pass-device-screening/run_sweep.sh
#
#   sim/pass-device-screening/run_sweep.sh --check-env   # CI-weight preflight:
#     generates + syntax-checks one netlist per bench (mos_tt/27C) via
#     `ngspice -b`, without running the full corner grid or writing a
#     records/ entry. This is the "syntax/--check-env pass" .github/
#     workflows/ci.yml wires up -- CI has no business minting append-only
#     evidence on every push (see sim/README.md "CI: syntax/--check-env
#     only, never a records/ entry").
#
# (PDK_ROOT/PDK may also be left unset if the PDK is installed under one of
# the usual prefixes sim/env.sh checks.) Requires ngspice on PATH plus the
# OSDI device models sim/tools/build-osdi.sh builds; does not require xschem
# or klt. Full methodology, what this sweep measures and does not, and the
# pinned PDK revision are documented in sim/pass-device-screening/README.md
# and sim/pdk.json -- read those first if a result here looks surprising.
#
# Screens sg13_hv_pmos (Mpass's device flavor, design/README.md "Pass
# device") against:
#   - the dropout test point (Vin=2.10V, Vout=1.80V, gate at 0V, per
#     spec/porting-plan.md Sec 1.4/2.1): Vth (constant-current method, at
#     this SAME dropout Vds) and Ron*W;
#   - gate capacitance at that same bias (small-signal AC);
#   - the continuous-short current-limit condition (Vout=0V at
#     Vin_max=3.63V, gate at 0V, per Sec 2.1/2.3): terminal voltages and
#     drain current per micron, checked against the PDK's own stated
#     sg13_hv_pmos ratings.
#
# Swept across device size {w1u_l0.4u, w1u_l0.5u, w1u_l1.0u (normalized,
# Ron*W's methodology), w300u_l0.5u (the schematic's as-drawn Mpass size,
# a direct cross-check)} x process corner {tt,ff,ss,sf,fs}
# (cornerMOShv.lib's five sections) x temperature {-40,27,125}. The
# supply-voltage axis {2.97,3.30,3.63} is DELIBERATELY NOT an independent
# sweep axis here: both the dropout point (Vin=2.10V, fixed) and the
# continuous-short stress point (Vin=3.63V, the Input row's own +10%
# corner) are defined as fixed absolute test points, not relative to a
# swept nominal supply -- see spec/porting-plan.md Sec 1.4 ("dropout is
# measured at Vin = Vout + dropout, NOT at Vin_min") and README.md
# "Corner grid and axes swept" for the full rationale. So the corner grid
# actually swept here is process x temperature (5 x 3 = 15 points), full
# factorial, applied identically to every device size and to both the
# dropout and stress benches.
set -euo pipefail

CHECK_ENV=0
for arg in "$@"; do
  case "${arg}" in
    --check-env) CHECK_ENV=1 ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "run_sweep.sh: unknown argument '${arg}'" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"

# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"

if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_sweep.sh: no resolvable ${PDK:-ihp-sg13g2} install -- see sim/env.sh output above." >&2
  exit 3
fi

if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
  echo "run_sweep.sh: OSDI models missing/unloadable -- run sim/tools/build-osdi.sh first:" >&2
  "${SIM_DIR}/tools/build-osdi.sh" --check || true
  exit 3
fi

command -v ngspice >/dev/null 2>&1 || { echo "run_sweep.sh: ngspice not on PATH." >&2; exit 3; }
NGSPICE_VERSION="$(ngspice -v 2>&1 | sed -n '2p')"

OSDI_DIR="${SG13G2_OSDI_DIR}"

if [[ ${CHECK_ENV} -eq 1 ]]; then
  echo "run_sweep.sh: --check-env: syntax-checking both benches at mos_tt/27C (w1u_l0.5u), no records written."
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp}"' EXIT
  rc=0
  for bench in dropout stress; do
    template="${SCRIPT_DIR}/testbench/tb_${bench}_pmos.spice.tmpl"
    netlist="${tmp}/${bench}_check.spice"
    sed \
      -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
      -e "s|@@PDK@@|${PDK}|g" \
      -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
      -e "s|@@MOS_SECTION@@|mos_tt|g" \
      -e "s|@@TEMP@@|27|g" \
      -e "s|@@W@@|1u|g" \
      -e "s|@@L@@|0.5u|g" \
      -e "s|@@DC_CSV@@|${tmp}/${bench}_check_dc.csv|g" \
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
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.md"
mkdir -p "${SNAPSHOTS_OUT}" "${CORNERS_OUT}" "${RECORDS_DIR}"

# --- Sweep grid ----------------------------------------------------------
CORNERS=(tt ss ff sf fs)
TEMPS=(-40 27 125)
# label:W:L -- W=1u entries are the Ron*W-normalized characterization
# (Ron*W is ~independent of W in the linear region, so a fixed W=1u lets
# Ron*W be read off directly); w300u_l0.5u is the schematic's as-drawn
# Mpass size (design/README.md "Pass device"), a direct cross-check that
# the normalization holds. L=0.4u is included because it is an actual
# characterized test-structure length in the PDK's own process spec
# (VTPHV10x04/IDSPHV04, libs.doc/doc/SG13G2_os_process_spec.pdf p.9),
# giving a real measured Vth/Id reference to sanity-check this sweep's own
# extraction against -- see README.md "Cross-check against the process
# spec". L=1.0u is the "few multiples" long-channel point.
DEVICES=(
  "w1u_l0.4u:1u:0.4u"
  "w1u_l0.5u:1u:0.5u"
  "w1u_l1.0u:1u:1.0u"
  "w300u_l0.5u:300u:0.5u"
)

DROPOUT_RAW="${CSV_OUT}.dropout.raw"
STRESS_RAW="${CSV_OUT}.stress.raw"
echo "device_label,w_um,l_um,corner,temp_c,vg_v,id_a" > "${DROPOUT_RAW}"
echo "device_label,w_um,l_um,corner,temp_c,id_stress_a,vsg_v,vds_v,vdg_v" > "${STRESS_RAW}"

total=0
passed=0
failed_points=()
declare -A CGATE_AT   # key "device_label|corner|temp" -> cgate farads

run_point() {
  local bench="$1" device_label="$2" w="$3" l="$4" corner="$5" temp="$6"
  local mos_section="mos_${corner}"
  local point_id="${bench}_${device_label}_${corner}_${temp}c"
  local template="${EXPERIMENT_DIR}/testbench/tb_${bench}_pmos.spice.tmpl"
  local netlist="${SNAPSHOTS_OUT}/${point_id}.spice"
  local log="${CORNERS_OUT}/${point_id}.log"

  total=$((total + 1))

  if [[ "${bench}" == "dropout" ]]; then
    local dc_csv="${CORNERS_OUT}/${point_id}_dc.csv"
    sed \
      -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
      -e "s|@@PDK@@|${PDK}|g" \
      -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
      -e "s|@@MOS_SECTION@@|${mos_section}|g" \
      -e "s|@@TEMP@@|${temp}|g" \
      -e "s|@@W@@|${w}|g" \
      -e "s|@@L@@|${l}|g" \
      -e "s|@@DC_CSV@@|${dc_csv}|g" \
      "${template}" > "${netlist}"

    local rc=0
    ngspice -b "${netlist}" > "${log}" 2>&1 || rc=$?

    if [[ ${rc} -ne 0 ]] || ! [[ -s "${dc_csv}" ]] || grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error" "${log}"; then
      echo "run_sweep.sh: FAILED ${point_id} (rc=${rc}) -- see ${log}" >&2
      failed_points+=("${point_id}")
      return
    fi

    local n_rows
    n_rows=$(wc -l < "${dc_csv}" | tr -d ' ')
    if [[ "${n_rows}" -lt 110 ]]; then
      echo "run_sweep.sh: FAILED ${point_id} -- only ${n_rows} dc rows (expected 121)" >&2
      failed_points+=("${point_id}")
      return
    fi

    local cgate
    cgate="$(grep '^DROPOUT_CGATE' "${log}" | awk '{print $2}')"
    if [[ -z "${cgate}" ]]; then
      echo "run_sweep.sh: FAILED ${point_id} -- no DROPOUT_CGATE in log" >&2
      failed_points+=("${point_id}")
      return
    fi
    CGATE_AT["${device_label}|${corner}|${temp}"]="${cgate}"

    # wrdata prints a redundant scale column before each requested vector
    # (see sim/gm-id-characterization's own documented gotcha): v(g) is the
    # sweep scale itself, so columns are (scale,v(g),scale,i(vout)) -> $1/$2
    # duplicate v(g), $3/$4 duplicate i(vout).
    awk -v dl="${device_label}" -v w="${w%u}" -v l="${l%u}" -v corner="${corner}" -v temp="${temp}" '
      { printf "%s,%s,%s,%s,%s,%.6f,%.6e\n", dl, w, l, corner, temp, $2, $4 }
    ' "${dc_csv}" >> "${DROPOUT_RAW}"

    passed=$((passed + 1))
  else
    sed \
      -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
      -e "s|@@PDK@@|${PDK}|g" \
      -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
      -e "s|@@MOS_SECTION@@|${mos_section}|g" \
      -e "s|@@TEMP@@|${temp}|g" \
      -e "s|@@W@@|${w}|g" \
      -e "s|@@L@@|${l}|g" \
      "${template}" > "${netlist}"

    local rc=0
    ngspice -b "${netlist}" > "${log}" 2>&1 || rc=$?

    if [[ ${rc} -ne 0 ]] || grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|fatal error" "${log}"; then
      echo "run_sweep.sh: FAILED ${point_id} (rc=${rc}) -- see ${log}" >&2
      failed_points+=("${point_id}")
      return
    fi

    local id_stress vsg vds vdg
    id_stress="$(grep '^STRESS_ID'  "${log}" | awk '{print $2}')"
    vsg="$(grep '^STRESS_VSG' "${log}" | awk '{print $2}')"
    vds="$(grep '^STRESS_VDS' "${log}" | awk '{print $2}')"
    vdg="$(grep '^STRESS_VDG' "${log}" | awk '{print $2}')"
    if [[ -z "${id_stress}" || -z "${vsg}" || -z "${vds}" || -z "${vdg}" ]]; then
      echo "run_sweep.sh: FAILED ${point_id} -- missing STRESS_* tag(s) in log" >&2
      failed_points+=("${point_id}")
      return
    fi

    echo "${device_label},${w%u},${l%u},${corner},${temp},${id_stress},${vsg},${vds},${vdg}" >> "${STRESS_RAW}"
    passed=$((passed + 1))
  fi
}

for device_entry in "${DEVICES[@]}"; do
  IFS=':' read -r device_label w l <<< "${device_entry}"
  for corner in "${CORNERS[@]}"; do
    for temp in "${TEMPS[@]}"; do
      run_point dropout "${device_label}" "${w}" "${l}" "${corner}" "${temp}"
      run_point stress  "${device_label}" "${w}" "${l}" "${corner}" "${temp}"
    done
  done
done

if [[ ${passed} -eq 0 ]]; then
  echo "run_sweep.sh: no points passed -- refusing to write a summary." >&2
  exit 1
fi

# Serialize the CGATE_AT associative array to JSON for the python
# post-processing step below (bash cannot pass an associative array to a
# subprocess directly).
CGATE_JSON="{"
first=1
for key in "${!CGATE_AT[@]}"; do
  [[ ${first} -eq 1 ]] || CGATE_JSON+=","
  first=0
  CGATE_JSON+="\"${key}\":${CGATE_AT[${key}]}"
done
CGATE_JSON+="}"
export CGATE_JSON

# --- Post-process: Vth (constant-current method, Id_crit = 100nA*(W/L),
# same convention sim/gm-id-characterization uses in sg13g2-opamp) and
# Ron*W at the dropout bias; implied pass-device width for 50mA/100mA at
# 300mV/200mV dropout targets; gate capacitance; continuous-short terminal
# stress vs. the PDK's stated sg13_hv_pmos ratings. ---
python3 - "${DROPOUT_RAW}" "${STRESS_RAW}" "${CSV_OUT}" <<'PYEOF'
import csv, sys, math
from collections import defaultdict

dropout_src, stress_src, dst = sys.argv[1], sys.argv[2], sys.argv[3]

dropout_groups = defaultdict(list)
with open(dropout_src) as f:
    r = csv.DictReader(f)
    for row in r:
        key = (row["device_label"], row["corner"], row["temp_c"])
        dropout_groups[key].append((float(row["vg_v"]), float(row["id_a"]), float(row["w_um"]), float(row["l_um"])))

stress_rows = {}
with open(stress_src) as f:
    r = csv.DictReader(f)
    for row in r:
        key = (row["device_label"], row["corner"], row["temp_c"])
        stress_rows[key] = row

VIN_DROPOUT = 2.10
VOUT_DROPOUT = 1.80
VDS_DROPOUT = VIN_DROPOUT - VOUT_DROPOUT  # 0.30V differential

out_rows = []
for key, pts in dropout_groups.items():
    device_label, corner, temp_c = key
    pts.sort(key=lambda t: t[0])  # ascending Vg
    w_um = pts[0][2]
    l_um = pts[0][3]

    # Row 0 (Vg=0) is the dropout bias point itself: Vsg=Vin (fully on).
    id_dropout = pts[0][1]
    ron = VDS_DROPOUT / id_dropout if id_dropout > 0 else float('nan')
    ron_w = ron * w_um

    # Vth via constant-current method AT THIS SAME Vds=0.30V bias (README.md
    # "Threshold voltage definition"). Device's own Vsg = Vin - Vg = 2.10-Vg,
    # so Vsg falls as Vg rises -- re-express in terms of Vsg descending
    # through the critical current, same log-interpolation technique
    # sim/gm-id-characterization/run_gmid_sweep.sh uses.
    i_crit = 100e-9 * (w_um / l_um)
    reexpr = [(VIN_DROPOUT - vg, idv) for (vg, idv, _, _) in pts]
    reexpr.sort(key=lambda t: t[0])  # ascending Vsg
    vth = None
    for a, b in zip(reexpr, reexpr[1:]):
        (vsg_a, id_a), (vsg_b, id_b) = a, b
        lo, hi = (a, b) if id_a <= id_b else (b, a)
        if lo[1] <= i_crit <= hi[1] and hi[1] > lo[1]:
            log_lo, log_hi = math.log(max(lo[1], 1e-18)), math.log(max(hi[1], 1e-18))
            if log_hi != log_lo:
                frac = (math.log(i_crit) - log_lo) / (log_hi - log_lo)
                vth = lo[0] + frac * (hi[0] - lo[0])
            break

    cgate = None
    ck = f"{device_label}|{corner}|{temp_c}"
    # cgate is looked up from the shell-side dict via env below.
    out_rows.append({
        "device_label": device_label, "w_um": w_um, "l_um": l_um,
        "corner": corner, "temp_c": temp_c,
        "id_dropout_a": id_dropout, "ron_ohm": ron, "ron_w_ohm_um": ron_w,
        "vth_v": vth, "cgate_ck": ck,
    })

import os
cgate_env = os.environ.get("CGATE_JSON", "")
import json
cgate_map = json.loads(cgate_env) if cgate_env else {}

with open(dst, "w", newline="") as f:
    fieldnames = [
        "device_label", "w_um", "l_um", "corner", "temp_c",
        "id_dropout_a", "vth_v", "ron_ohm", "ron_w_ohm_um", "cgate_f",
        "implied_w_um_50ma_300mv", "implied_w_um_100ma_200mv",
        "id_stress_a", "id_stress_a_per_um", "vsg_stress_v", "vds_stress_v", "vdg_stress_v",
        "vsg_exceeds_3p3v_rating",
    ]
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for row in sorted(out_rows, key=lambda r: (r["device_label"], r["corner"], float(r["temp_c"]))):
        cgate = cgate_map.get(row.pop("cgate_ck"))
        ron_w = row["ron_w_ohm_um"]
        implied_50 = (0.05 * ron_w / 0.30) if ron_w == ron_w else float('nan')
        implied_100 = (0.10 * ron_w / 0.20) if ron_w == ron_w else float('nan')

        srow = stress_rows.get((row["device_label"], row["corner"], row["temp_c"]), {})
        id_stress = float(srow.get("id_stress_a", "nan"))
        w_um = row["w_um"]
        id_stress_per_um = id_stress / w_um if w_um else float('nan')
        vsg_stress = float(srow.get("vsg_v", "nan"))

        w.writerow({
            "device_label": row["device_label"], "w_um": f"{row['w_um']:.4f}",
            "l_um": f"{row['l_um']:.4f}", "corner": row["corner"], "temp_c": row["temp_c"],
            "id_dropout_a": f"{row['id_dropout_a']:.6e}",
            "vth_v": (f"{row['vth_v']:.4f}" if row["vth_v"] is not None else ""),
            "ron_ohm": f"{row['ron_ohm']:.4f}",
            "ron_w_ohm_um": f"{ron_w:.4f}",
            "cgate_f": (f"{cgate:.6e}" if cgate is not None else ""),
            "implied_w_um_50ma_300mv": f"{implied_50:.2f}",
            "implied_w_um_100ma_200mv": f"{implied_100:.2f}",
            "id_stress_a": f"{id_stress:.6e}",
            "id_stress_a_per_um": f"{id_stress_per_um:.6e}",
            "vsg_stress_v": f"{vsg_stress:.4f}",
            "vds_stress_v": f"{float(srow.get('vds_v', 'nan')):.4f}",
            "vdg_stress_v": f"{float(srow.get('vdg_v', 'nan')):.4f}",
            "vsg_exceeds_3p3v_rating": ("YES" if abs(vsg_stress) > 3.3 else "no"),
        })
PYEOF

rm -f "${DROPOUT_RAW}" "${STRESS_RAW}"

# --- Completeness matrix: every (device, corner, temp) cell present ---
COMPLETENESS_OK=1
for device_entry in "${DEVICES[@]}"; do
  IFS=':' read -r device_label _ _ <<< "${device_entry}"
  for corner in "${CORNERS[@]}"; do
    for temp in "${TEMPS[@]}"; do
      n=$(awk -F, -v dl="${device_label}" -v c="${corner}" -v t="${temp}" \
        'NR>1 && $1==dl && $4==c && $5==t {n++} END{print n+0}' "${CSV_OUT}")
      if [[ "${n}" -ne 1 ]]; then
        echo "run_sweep.sh: INCOMPLETE ${device_label}/${corner}/${temp}c -- ${n} rows (expected 1)" >&2
        COMPLETENESS_OK=0
      fi
    done
  done
done

# --- Sanity checks (issue #13 Test Plan): binding corner for dropout is
# ss/125C (worst Ron*W), binding corner for stress is ff/-40C (worst |Id|,
# though Vsg/Vds/Vdg are bias-imposed and identical across all corners);
# Vsg at the continuous-short stress point exceeds the PDK's stated 3.3V
# max VGS rating at EVERY corner (it is set purely by Vin_max=3.63V and
# gate=0V, both external, not a per-corner-dependent quantity). ---
SANITY_LOG="${CORNERS_OUT}/sanity_checks.txt"
python3 - "${CSV_OUT}" "${SANITY_LOG}" <<'PYEOF'
import csv, sys
src, dst = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(src)))
lines = []
ok = True

w1u_rows = [r for r in rows if r["device_label"] == "w1u_l0.5u"]
worst_dropout = max(w1u_rows, key=lambda r: float(r["ron_w_ohm_um"]))
lines.append(
    f"INFO binding dropout corner (worst Ron*W, w1u_l0.5u): "
    f"{worst_dropout['corner']}/{worst_dropout['temp_c']}C "
    f"Ron*W={float(worst_dropout['ron_w_ohm_um']):.1f} ohm.um"
)
if not (worst_dropout["corner"] == "ss" and worst_dropout["temp_c"] == "125"):
    lines.append("NOTE binding dropout corner is NOT ss/125C as expected by spec/porting-plan.md sec 1.4 -- see record for the actual value.")

worst_stress = max(w1u_rows, key=lambda r: float(r["id_stress_a_per_um"]))
lines.append(
    f"INFO binding stress corner (worst Id/um, w1u_l0.5u): "
    f"{worst_stress['corner']}/{worst_stress['temp_c']}C "
    f"Id/um={float(worst_stress['id_stress_a_per_um']):.6e} A/um"
)
if not (worst_stress["corner"] == "ff" and worst_stress["temp_c"] == "-40"):
    lines.append("NOTE binding stress corner is NOT ff/-40C as expected by spec/porting-plan.md sec 1.4 -- see record for the actual value.")

n_exceed = sum(1 for r in rows if r["vsg_exceeds_3p3v_rating"] == "YES")
verdict = "PASS" if n_exceed == len(rows) else ("FAIL" if n_exceed == 0 else "MIXED")
lines.append(f"{verdict} Vsg at continuous-short stress (|Vsg|=3.63V, bias-imposed) exceeds the PDK's stated 3.3V max VGS rating at {n_exceed}/{len(rows)} points (expected: all, since Vsg is set purely by Vin_max/gate bias, not corner-dependent).")
if verdict == "FAIL":
    ok = False

with open(dst, "w") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
sys.exit(0 if ok else 1)
PYEOF
SANITY_RC=$?

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: pass-device-screening"
  echo "- **Claim**: sg13_hv_pmos (Mpass's flavor, design/README.md \"Pass"
  echo "  device\") screened at the dropout test point (Vin=2.10V,"
  echo "  Vout=1.80V, gate=0V) for Vth, Ron*W and Cgate, and at the"
  echo "  continuous-short current-limit condition (Vout=0V, Vin=3.63V,"
  echo "  gate=0V) for terminal voltage/current stress -- the input to"
  echo "  spec/porting-plan.md Sec 4 item 1."
  echo "- **Devices**: sg13_hv_pmos (PSP103.6 via psp103.osdi),"
  echo "  W/L = {1um x 0.4/0.5/1.0um (Ron*W-normalized), 300um x 0.5um"
  echo "  (design/ldo_core.sch's as-drawn Mpass size, a direct cross-check)},"
  echo "  ng=1, m=1."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\` (IHP-Open-PDK v0.3.0)."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by"
  echo "  \`sim/tools/build-osdi.sh\`."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  device_labels=""
  for device_entry in "${DEVICES[@]}"; do
    IFS=':' read -r dl _ _ <<< "${device_entry}"
    device_labels+="${device_labels:+, }${dl}"
  done
  echo "- **Corner matrix run**: device {${device_labels}} x process"
  echo "  {${CORNERS[*]}} (cornerMOShv.lib, space-separated above) x"
  echo "  temperature {${TEMPS[*]}}C = ${total} points (both benches"
  echo "  combined: dropout + continuous-short-stress). The supply-voltage"
  echo "  axis is NOT independently swept -- both test points are fixed"
  echo "  absolute Vin values by definition (Vin=2.10V dropout,"
  echo "  Vin=3.63V=Input-row-max stress), not relative to a swept nominal"
  echo "  supply corner. See README.md \"Corner grid and axes swept\"."
  echo "- **Result**: ${passed}/${total} points PASS (ngspice exit 0, all"
  echo "  expected outputs present)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Completeness matrix**: $( [[ ${COMPLETENESS_OK} -eq 1 ]] && echo 'OK -- every (device,corner,temp) cell has exactly 1 row' || echo 'INCOMPLETE -- see stderr log above' )"
  echo "- **Sanity checks** (see \`corners/${RECORD_ID}/sanity_checks.txt\`):"
  while IFS= read -r line; do echo "  - ${line}"; done < "${SANITY_LOG}"
  echo "- **Netlist provenance**: bare-device deck (this experiment"
  echo "  instantiates sg13_hv_pmos directly, per"
  echo "  \`testbench/tb_dropout_pmos.spice.tmpl\` /"
  echo "  \`testbench/tb_stress_pmos.spice.tmpl\`), cross-referenced against"
  echo "  \`design/ldo_core.sch\`'s Mpass topology (common-source, source to"
  echo "  VIN, drain to VOUT, body to VIN) at the design's own repo git sha"
  echo "  \`${REPO_GIT_SHA}\` -- not extracted from or instantiating"
  echo "  \`design/netlist/ldo_core.spice\` directly, since this is a"
  echo "  device-characterization study, not a circuit-level bench (same"
  echo "  posture as sim/gm-id-characterization in the sibling"
  echo "  sg13g2-opamp repo)."
  echo "- **Links**:"
  echo "  - Templates: \`testbench/tb_dropout_pmos.spice.tmpl\`,"
  echo "    \`testbench/tb_stress_pmos.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs + per-point DC sweep CSVs:"
  echo "    \`corners/${RECORD_ID}/\`"
  echo "  - Parsed, merged CSV (all points, all derived quantities):"
  echo "    \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #13."
} > "${MD_OUT}"

echo "run_sweep.sh: wrote ${MD_OUT} and ${CSV_OUT}"
echo "run_sweep.sh: ${passed}/${total} points passed; completeness=$( [[ ${COMPLETENESS_OK} -eq 1 ]] && echo OK || echo INCOMPLETE ); sanity=$( [[ ${SANITY_RC} -eq 0 ]] && echo PASS || echo FAIL )"

if [[ ${#failed_points[@]} -gt 0 || ${COMPLETENESS_OK} -ne 1 || ${SANITY_RC} -ne 0 ]]; then
  exit 1
fi
exit 0
