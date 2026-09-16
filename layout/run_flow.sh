#!/usr/bin/env bash
# One-command DRC + LVS flow for the SG13CMOS5L LDO layout (issue #28).
#
#   layout/run_flow.sh                # regenerate, verify, refresh the reports
#   layout/run_flow.sh --check        # verify the committed reports only
#
# Everything this repo claims about the layout comes out of this script, and
# every claim is re-runnable from a clean checkout with `klt` and an
# `ihp-sg13cmos5l` install on the usual search path. The stages:
#
#   1. generate      layout/sg13cmos5l-ldo_core_cmos5l/generate.py  -> .gds
#   2. drc-curated   klt drc --deck sg13cmos5l          (klt's own deck)
#   3. drc-pdk       the PDK's own ihp-sg13cmos5l.drc   (two invocations, see
#                    "DECK SPLIT" below)
#   4. drc-control   a deliberately broken copy of the GDS, to prove stages
#                    2 and 3 can actually see this layout's geometry
#   5. extract       klt extract --deck sg13cmos5l      -> .extracted.spice
#   6. lvs           klt lvs against the generated reference netlist
#   7. lvs-controls  two mutated references (topology + parameter) that MUST
#                    mismatch, plus an HV-marker control on the layout side
#
# DECK SPLIT (stage 3). The PDK's own deck cannot run end to end against the
# standalone KLayout on this host: several of its rules use a DRC-DSL
# construct (`with_angle(45, absolute)`) that KLayout 0.28.16 does not
# provide, and the script aborts at the first one it reaches. The rules that
# use it are Gat.g, M1.g/M1.i, Mn.g/Mn.i, Seal.k and the whole 3_2_angle
# table. So this script runs the deck in two invocations -- every table that
# does NOT contain such a rule at full strength, then the three that do in the
# deck's own reduced "precheck" mode, which skips exactly those sub-blocks and
# keeps each table's width/space rules -- and reports both counts plus the
# skipped-rule list. The skipped rules are all either 45-degree-geometry rules
# (this layout is Manhattan by construction, asserted in generate.py) or
# LV-FET channel-length rules (this design has no LV FET). See
# layout/README.md, "DRC: what actually ran".
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
CELL="ldo_core_cmos5l"
DIR="${HERE}/sg13cmos5l-${CELL}"
GDS="${DIR}/sg13cmos5l-${CELL}.gds"
TOP="sg13cmos5l_ldo_core_cmos5l"
REF="${DIR}/sg13cmos5l-${CELL}.lvs_reference.spice"
EXTRACTED="${DIR}/sg13cmos5l-${CELL}.extracted.spice"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

PDK_ROOT="${PDK_ROOT:-${HOME}/share/pdk}"
PDK_DECK="${PDK_ROOT}/ihp-sg13cmos5l/libs.tech/klayout/tech/drc/ihp-sg13cmos5l.drc"

# Every PDK-deck table that runs at full strength on this host.
TABLES_FULL="nwell pwellblock activ activfiller thickgateox gatpolyfiller psd \
cont contbar latchup via1 vian topvia1 topmetal1 topmetal1filler metalnfiller \
passiv pad metalslits lbe pin offgrid forbidden forbidden_cmos5l"
# The three tables that carry a rule this host's KLayout cannot evaluate; run
# in the deck's own precheck mode, which skips exactly those sub-blocks.
TABLES_PRECHECK="gatpoly metal1 metaln"

MODE="run"
if [[ "${1:-}" == "--check" ]]; then MODE="check"; fi

say() { printf '\n=== %s\n' "$*"; }

run_pdk_deck() {  # <gds> <report> <extra deck args...>
  local gds="$1" report="$2" rc=0; shift 2
  klayout -b -r "${PDK_DECK}" -rd "input=${gds}" -rd "report=${report}" \
    -rd no_feol=true -rd no_beol=true "$@" > "${report}.log" 2>&1 || rc=$?
  # Why this stage shells out to `klayout` directly instead of using `klt drc
  # --engine klayout`: a deck that writes its report file early and then
  # aborts part-way through leaves a short-but-valid report behind, and `klt`
  # reads that as `status: "clean", violation_count: 0` and exits 0 -- it
  # never inspects the klayout exit status or the `ERROR:` lines. Filed
  # upstream as klayout-tools#1941 with a 10-line generic repro. Until that
  # lands, both signals are checked here directly rather than trusted.
  if [[ "${rc}" -ne 0 ]] || grep -q '^ERROR' "${report}.log"; then
    echo "PDK deck aborted (klayout exit ${rc}) -- see ${report}.log" >&2
    grep '^ERROR' "${report}.log" >&2 || true
    return 1
  fi
  local rules items
  rules=$(grep -c 'Executing rule' "${report}.log" || true)
  items=$(grep -c '<item>' "${report}" || true)
  echo "  rules executed: ${rules}   violations: ${items}"
  echo "${items}" > "${report}.count"
  echo "${rules}" > "${report}.rules"
}

if [[ "${MODE}" == "check" ]]; then
  say "check mode -- the committed artifacts must reproduce, byte for byte"
  cp "${GDS}" "${WORK}/committed.gds"
  cp "${REF}" "${WORK}/committed.ref"
  python3 "${DIR}/generate.py" > /dev/null
  python3 "${REPO}/layout/lvs_reference.py" --cell "${CELL}" --top "${TOP}" > /dev/null
  cmp "${WORK}/committed.gds" "${GDS}" && echo "  GDS reproduces"
  cmp "${WORK}/committed.ref" "${REF}" && echo "  reference netlist reproduces"
  ( cd "${DIR}" && klt drc --check drc_report.json && klt lvs --check lvs_report.json )
  say "done (check)"
  exit 0
fi

say "1. generate"
python3 "${DIR}/generate.py"
python3 "${REPO}/layout/lvs_reference.py" --cell "${CELL}" --top "${TOP}" > /dev/null
echo "  reference netlist regenerated"

say "2. DRC -- klt's curated sg13cmos5l deck"
# Run from inside the cell directory with a bare filename: `klt drc --check`
# re-reads the input path out of the committed report, so a report that
# recorded an absolute path would only be checkable on the machine (and in the
# worktree) that produced it.
( cd "${DIR}" && klt drc --deck sg13cmos5l --format json "sg13cmos5l-${CELL}.gds" \
    > drc_report.json )
python3 - "${DIR}/drc_report.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  status: {d['status']}  violations: {d['violation_count']}  {d['rule_counts']}")
print(f"  rule categories in scope: {len(d['coverage']['deck_scope'])} -> "
      f"{', '.join(d['coverage']['deck_scope'])}")
sys.exit(0 if d['violation_count'] == 0 else 1)
PY

say "3. DRC -- the PDK's own ihp-sg13cmos5l deck"
echo " 3a. full-strength tables"
run_pdk_deck "${GDS}" "${WORK}/pdk_full.lyrdb" -rd "tables=${TABLES_FULL}"
echo " 3b. precheck-mode tables (${TABLES_PRECHECK})"
run_pdk_deck "${GDS}" "${WORK}/pdk_precheck.lyrdb" -rd precheck_drc=true \
  -rd "tables=${TABLES_PRECHECK}"

# The PDK deck has no JSON writer of its own, so this stage's own evidence is
# summarised here -- counts read back from the two .lyrdb reports and their
# logs, plus the exact invocation, so the numbers in layout/README.md can be
# traced without re-running anything.
python3 - "${DIR}/drc_pdk_deck_report.json" "${WORK}/pdk_full.lyrdb" \
  "${WORK}/pdk_precheck.lyrdb" "${PDK_DECK#"${PDK_ROOT}/"}" "${TABLES_FULL}" \
  "${TABLES_PRECHECK}" <<'PY'
import json, pathlib, subprocess, sys
out, full, pre, deck, tf, tp = sys.argv[1:7]
def read(stem):
    return {
        "rules_executed": int(pathlib.Path(stem + ".rules").read_text().strip()),
        "violations": int(pathlib.Path(stem + ".count").read_text().strip()),
    }
klayout_v = subprocess.run(["klayout", "-v"], capture_output=True, text=True).stdout.strip()
report = {
    "schema": "sg13g2-ldo.drc.pdk-deck/1",
    "deck": deck,  # relative to $PDK_ROOT -- the install is not in this repo
    "engine": f"standalone {klayout_v}",
    "invocations": [
        {"name": "full-strength tables", "tables": tf.split(),
         "deck_vars": ["no_feol=true", "no_beol=true"], **read(full)},
        {"name": "precheck-mode tables", "tables": tp.split(),
         "deck_vars": ["no_feol=true", "no_beol=true", "precheck_drc=true"], **read(pre)},
    ],
    "skipped_rules": {
        "Gat.a1, Gat.a2": "1.2 V (LV) FET channel-length rules; this design has no LV FET",
        "Gat.g, M1.g, M1.i, Mn.g, Mn.i": (
            "45-degree-geometry rules; unrunnable on this host (the deck uses "
            "with_angle(45, absolute), which this KLayout build does not provide) "
            "and vacuous for this layout, which generate.py asserts is Manhattan"),
        "3_2_angle table": "same construct, same reason",
        "Seal.k, Seal.l, Seal.m, Seal.n": "seal-ring rules; no EdgeSeal drawn",
        "density.drc": "not part of the deck's own `main` table selection",
    },
}
report["violations_total"] = sum(i["violations"] for i in report["invocations"])
report["rules_executed_total"] = sum(i["rules_executed"] for i in report["invocations"])
pathlib.Path(out).write_text(json.dumps(report, indent=2) + "\n")
print(f"  wrote {pathlib.Path(out).name}: "
      f"{report['rules_executed_total']} rules, "
      f"{report['violations_total']} violations")
PY

say "4. DRC negative control -- a deliberately broken copy must NOT be clean"
python3 - "${GDS}" "${WORK}/broken.gds" <<'PY'
import sys
import klayout.db as kdb
ly = kdb.Layout(); ly.read(sys.argv[1])
top = ly.top_cell()
# Two planted defects, one per deck: a 0.10 um Metal1 stub (min width 0.16,
# rule M1.a / metal1.width.1) and a 0.30 um Cont (Cnt.a fixes the size at
# 0.16 um exactly, min AND max).
m1 = ly.layer(kdb.LayerInfo(8, 0)); cont = ly.layer(kdb.LayerInfo(6, 0))
top.shapes(m1).insert(kdb.Box(-2000, -80000, -1900, -70000))
top.shapes(cont).insert(kdb.Box(-2000, -60000, -1700, -59700))
ly.write(sys.argv[2])
PY
# `klt drc` exits 3 when it finds violations -- which is the point here.
klt drc --deck sg13cmos5l --format json "${WORK}/broken.gds" > "${WORK}/broken_curated.json" || true
python3 - "${WORK}/broken_curated.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  curated deck on the broken copy: {d['status']} {d['rule_counts']}")
sys.exit(0 if d['violation_count'] > 0 else 1)
PY
run_pdk_deck "${WORK}/broken.gds" "${WORK}/broken_full.lyrdb" -rd "tables=${TABLES_FULL}"
test "$(cat "${WORK}/broken_full.lyrdb.count")" -gt 0 || {
  echo "  PDK deck did not flag the planted defect -- the deck is not seeing this layout" >&2
  exit 1; }
echo "  both decks flagged the planted defects: they are really checking this geometry"

say "5. extract"
# Same relative-path discipline as stage 2 -- the extract report names both
# its input GDS and its output netlist, and both belong to this directory.
( cd "${DIR}" && klt extract --deck sg13cmos5l --top "${TOP}" \
    --pins VIN,VOUT,VSS,VREF,IBIAS \
    -o "sg13cmos5l-${CELL}.extracted.spice" --format json \
    "sg13cmos5l-${CELL}.gds" > extract_report.json )
python3 - "${DIR}/extract_report.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  devices: {d['device_counts']}")
print(f"  nets:    {[n['name'] for n in d['nets']]}")
expected = {"pfet": 124, "nfet": 3, "rhigh": 3, "cap_cmomi": 1}
sys.exit(0 if d['device_counts'] == expected else 1)
PY

say "5b. HV-flavour control -- the same layout without its ThickGateOx marker"
# The drawn ThickGateOx (44/0) is what makes these devices the HV flavour.
# `klt extract --pdk` binds each MOS to a real PDK model name, so stripping
# the marker must change every binding from sg13_hv_* to sg13_lv_*: that is
# the direct evidence that the HV flavour is drawn and recognised, not
# assumed.
python3 - "${GDS}" "${WORK}/no_tgo.gds" <<'PY'
import sys
import klayout.db as kdb
ly = kdb.Layout(); ly.read(sys.argv[1])
ly.top_cell().shapes(ly.layer(kdb.LayerInfo(44, 0))).clear()
ly.write(sys.argv[2])
PY
PDK_ROOT="${PDK_ROOT}" klt extract --deck sg13cmos5l --pdk ihp-sg13cmos5l --top "${TOP}" \
  -o "${WORK}/hv.spice" "${GDS}" > /dev/null
PDK_ROOT="${PDK_ROOT}" klt extract --deck sg13cmos5l --pdk ihp-sg13cmos5l --top "${TOP}" \
  -o "${WORK}/lv.spice" "${WORK}/no_tgo.gds" > /dev/null
hv=$(grep -c 'sg13_hv_' "${WORK}/hv.spice" || true)
lv=$(grep -c 'sg13_lv_' "${WORK}/lv.spice" || true)
echo "  as drawn: ${hv} devices bind to sg13_hv_*; without ThickGateOx: ${lv} bind to sg13_lv_*"
test "${hv}" -gt 0 && test "${lv}" -gt 0

say "6. LVS"
cat > "${DIR}/lvs_request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": {
    "netlist": "sg13cmos5l-${CELL}.extracted.spice",
    "top": "${TOP}"
  },
  "reference": {
    "netlist": "sg13cmos5l-${CELL}.lvs_reference.spice",
    "top": "${TOP}"
  },
  "options": {
    "combine_devices": true
  }
}
EOF
( cd "${DIR}" && klt lvs lvs_request.json --format json > lvs_report.json ) || true
python3 - "${DIR}/lvs_report.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  status: {d['status']}")
print(f"  counts: {d['counts']}")
for m in d.get('mismatches', []):
    print(f"  {m['severity']}: {m['category']}: {m['description']}")
sys.exit(0 if d['status'] == 'match' else 1)
PY

say "7. LVS negative controls -- every mutation MUST mismatch"
control() {  # <name> <sed-expression|@drop:REGEX> <what it breaks>
  local name="$1" expr="$2" what="$3"
  if [[ "${expr}" == @drop:* ]]; then
    grep -v "${expr#@drop:}" "${REF}" > "${WORK}/${name}.spice"
  else
    sed "${expr}" "${REF}" > "${WORK}/${name}.spice"
  fi
  cmp -s "${REF}" "${WORK}/${name}.spice" && {
    echo "  ${name}: mutation did not change the netlist -- control is void" >&2; exit 1; }
  cat > "${WORK}/${name}.json" <<EOF
{"schema":"klt.lvs.request/1","engine":"klayout",
 "layout":{"netlist":"${EXTRACTED}","top":"${TOP}"},
 "reference":{"netlist":"${WORK}/${name}.spice","top":"${TOP}"},
 "options":{"combine_devices":true}}
EOF
  klt lvs "${WORK}/${name}.json" --format json > "${WORK}/${name}.out.json" || true
  python3 - "${WORK}/${name}.out.json" "${name}" "${what}" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
cats = sorted({m['category'] for m in d.get('mismatches', []) if m['severity'] == 'error'})
print(f"  {sys.argv[2]} ({sys.argv[3]}): status={d['status']}  {cats}")
sys.exit(0 if d['status'] != 'match' else 1)
PY
}
# Topology mutation: move Mn3's gate off G1 onto N1. Nothing about the drawn
# geometry changes -- only the reference's claim about which net drives it.
control topology-control 's/^MMn3 EAOUT G1 VSS VSS/MMn3 EAOUT N1 VSS VSS/' \
  "Mn3 gate G1 -> N1"
# Parameter mutation: Mpass 1% narrower (2800 -> 2772 um). A 1% error is the
# scale a mis-counted finger row would NOT produce -- it is deliberately
# smaller than one row (25 um = 0.9%) to show the compare is exact, not
# tolerant.
control parameter-control 's/^MMpass \(.*\) W=2800U/MMpass \1 W=2772U/' \
  "Mpass W 2800u -> 2772u"
# The MoM cap is the one device neither side compares *as a device*: `klt
# extract`'s SPICE writer emits it as an `X ... cap_cmomi PARAMS:` card, and
# `klt lvs`'s plain reader turns that into an abstract circuit whose
# parameters are mangled into its NAME (`CAP_CMOMI(L=30,W=0.1K)`). It is
# therefore absent from the report's own device census -- 12 compared devices
# for a 13-device cell -- so "the device count matches" would say nothing
# about it. These three controls are what establish that it is nevertheless
# compared, and on what: presence, connectivity, and (by name equality, not
# by tolerance) its parameters. See klayout-tools#1942 and layout/README.md,
# "LVS: what is compared at device level, and what is not".
control cap-presence-control '@drop:^XCc ' "Cc deleted from the reference"
control cap-topology-control 's/^XCc EAOUT MZ/XCc EAOUT G1/' "Cc MZ -> G1"
control cap-parameter-control 's/^XCc \(.*\)W=100 L=30/XCc \1W=50 L=30/' \
  "Cc W 100u -> 50u"

say "done"
