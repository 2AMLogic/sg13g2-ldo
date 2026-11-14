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
#   sim/ldo-cmos5l-pvt-sweep/run_sweep.sh --doe-generate --batch   # issue #64
#     dynamic DoE (load x Cout x ESR) on the batch fleet; README.md
#     "Dynamic DoE" (refinement: --doe-extra/--doe-only-extra/--doe-base).
#
#   sim/ldo-cmos5l-pvt-sweep/run_sweep.sh --batch --loopgain-ac-max=10g   # issue #128
#     loop-gain AC sweep ceiling (default 100meg; also SWEEP_LOOPGAIN_AC_MAX;
#     exact power of ten, 20 points/decade, 1 Hz floor -- ac_sweep.py).
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
CHECK_GUARD=0
CHECK_TOPOLOGY=0
DOE_GENERATE=0
DOE_EXTRA=""
DOE_ONLY_EXTRA=0
DOE_BASE=""
# --batch (PR #87): run every point on the EDA batch fleet through
# `klt sim --backend batch` (batch_backend.py) instead of a local
# `ngspice -b` per point. Dispatch hosts must not run SPICE grids locally.
# The per-point decks, the screening and the post-processing are the same
# in both modes; only the step that runs the simulator changes. See
# batch_backend.py's docstring and README.md "Batch backend".
BATCH=0
# --loopgain-ac-max=<f> (issue #128): upper end of the loop-gain AC sweep,
# default 100meg (the historical `ac dec 20 1 100meg`). Also settable as
# SWEEP_LOOPGAIN_AC_MAX. Must be an exact power of ten (ac_sweep.py); the
# floor (1 Hz) and 20 points/decade are fixed. It is rendered into
# tb_loopgain_cmos5l.spice.tmpl and sets the loop-gain completeness row
# count. The PSRR bench is unaffected.
LOOPGAIN_AC_MAX="${SWEEP_LOOPGAIN_AC_MAX:-100meg}"
for arg in "$@"; do
  case "${arg}" in
    --check-env) CHECK_ENV=1 ;;
    --check-topology-guard) CHECK_GUARD=1 ;;
    --check-topology) CHECK_TOPOLOGY=1 ;;
    --doe-generate) DOE_GENERATE=1 ;;   # issue #64: netlists + manifest only, no simulation
    --doe-extra=*) DOE_EXTRA="${arg#--doe-extra=}" ;;
    --doe-only-extra) DOE_ONLY_EXTRA=1 ;;   # with --doe-extra: simulate only the refinement points
    --doe-base=*) DOE_BASE="${arg#--doe-base=}" ;;   # record id whose corners/ the analysis also reads
    --batch) BATCH=1 ;;
    --loopgain-ac-max=*) LOOPGAIN_AC_MAX="${arg#--loopgain-ac-max=}" ;;
    -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "run_sweep.sh: unknown argument '${arg}'" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Validate and canonicalise the loop-gain ceiling before anything else runs.
LG_AC_MAX="$(python3 "${SCRIPT_DIR}/ac_sweep.py" ceiling "${LOOPGAIN_AC_MAX}")" || {
  echo "run_sweep.sh: invalid --loopgain-ac-max / SWEEP_LOOPGAIN_AC_MAX '${LOOPGAIN_AC_MAX}'." >&2
  exit 2
}
if [[ ${DOE_GENERATE} -eq 1 && "${LG_AC_MAX}" != "100meg" ]]; then
  echo "run_sweep.sh: --loopgain-ac-max other than the default is not supported with --doe-generate" >&2
  echo "run_sweep.sh: (dynamic_doe.py expects the default sweep)." >&2
  exit 2
fi
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"

DESIGN_NETLIST="${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"

# --- Sync-check: tb_loopgain_cmos5l.spice.tmpl flattens ldo_core_cmos5l one
# level (to insert the loop-gain break at FB, a high-impedance node -- see
# that template's header for the full derivation) by hand-mirroring its
# XMpass/XRtop/XRbot/Xamp/XMen/XMbdis instantiation lines (XMen, XMbdis:
# the enable pull-ups, issue #67). If a future schematic edit changes that connectivity,
# this bench would silently go stale -- so BOTH (a) the generated netlist
# and (b) the template's own mirrored copy are compared against the
# expected body baked in below, every run. (a) catches a schematic edit
# that this script was not updated for; (b) catches a template that was not
# migrated (an omitted or miswired enable device). The one intentional
# difference -- FB -> FBAMP on Xamp's first pin, behind Vbreak -- is
# normalised before (b) compares, and Vbreak's own connectivity is
# asserted separately, so the loop break cannot silently move or vanish.
# This block deliberately needs neither a PDK nor ngspice, so
# --check-topology-guard (the negative controls) runs anywhere.
# Since issue #89 Xamp carries EN as its seventh pin (the amplifier's own G1
# disable pull-down, DR-0008 addendum), so the expected body and both
# copies name EN on Xamp too; a template that still instantiates the
# six-pin amplifier is rejected by the negative controls below. ---
LOOPGAIN_MIRRORED_RE='^(XMpass|XRtop|XRbot|Xamp|XMen|XMbdis) '
LOOPGAIN_EXPECTED_BODY='XMpass VOUT EAOUT VIN VIN sg13_hv_pmos w=2800u l=0.5u ng=1 m=1
XRtop VOUT FB VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7
XRbot FB VSS VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7
Xamp FB VREF EAOUT VIN VSS IBIAS EN ldo_erramp_cmos5l
XMen EAOUT EN VIN VIN sg13_hv_pmos w=40u l=0.5u ng=1 m=1
XMbdis IBIAS EN VIN VIN sg13_hv_pmos w=5u l=0.5u ng=1 m=1'

# topology_sync_problem <netlist> <template> [variant]: prints a diagnostic
# and returns 1 on any mismatch, 0 when every comparison agrees. variant
# selects the loop-break assertion: "vbreak" (default -- the series-break
# benches tb_loopgain_cmos5l and, since issue #135, its circuit-identical
# twin tb_loopgain2v) or "shunt" (tb_loopgain2i's intact-loop shunt
# injection, also issue #135).
topology_sync_problem() {
  local netlist="$1" template="$2" variant="${3:-vbreak}" body mirrored breaks vmeas iinx
  body="$(awk '/^\.subckt ldo_core_cmos5l /,/^\.ends/' "${netlist}" | grep -E "${LOOPGAIN_MIRRORED_RE}" || true)"
  if [[ "${body}" != "${LOOPGAIN_EXPECTED_BODY}" ]]; then
    echo "run_sweep.sh: generated netlist ${netlist}: ldo_core_cmos5l's top-level instantiation lines differ from the expected body." >&2
    diff <(echo "${LOOPGAIN_EXPECTED_BODY}") <(echo "${body}") >&2 || true
    return 1
  fi
  # The enable port must also be in the subckt header, last.
  if ! grep -qE '^\.subckt ldo_core_cmos5l VIN VOUT VSS VREF IBIAS EN$' "${netlist}"; then
    echo "run_sweep.sh: generated netlist ${netlist}: .subckt ldo_core_cmos5l header is not 'VIN VOUT VSS VREF IBIAS EN'." >&2
    return 1
  fi
  mirrored="$(grep -E "${LOOPGAIN_MIRRORED_RE}" "${template}" | sed -E 's/^(Xamp) FBAMP /\1 FB /' || true)"
  if [[ "${mirrored}" != "${LOOPGAIN_EXPECTED_BODY}" ]]; then
    echo "run_sweep.sh: ${template}: flattened copy differs from the exported core (after undoing the FB->FBAMP break)." >&2
    diff <(echo "${LOOPGAIN_EXPECTED_BODY}") <(echo "${mirrored}") >&2 || true
    return 1
  fi
  case "${variant}" in
    vbreak)
      # The series-break benches: exactly one ideal AC source between FB and
      # FBAMP. (tb_loopgain2v's circuit is byte-identical to tb_loopgain's;
      # only its .control export differs -- see the template headers.)
      if ! grep -qE '^Xamp FBAMP ' "${template}"; then
        echo "run_sweep.sh: ${template}: Xamp is not driven from FBAMP (loop break missing)." >&2
        return 1
      fi
      breaks="$(grep -cE '^Vbreak FB FBAMP 0 ac 1$' "${template}" || true)"
      if [[ "${breaks}" != "1" ]]; then
        echo "run_sweep.sh: ${template}: expected exactly one 'Vbreak FB FBAMP 0 ac 1' loop break, found ${breaks}." >&2
        return 1
      fi
      ;;
    shunt)
      # tb_loopgain2i (issue #135): the loop is INTACT -- a 0 V ammeter
      # Vmeas bridges FB to FBAMP and a shunt AC current source Iinx injects
      # into the driven side (FBAMP), so both the source and the load
      # impedance are seen. A series AC source here would be a second,
      # unintended injection: explicitly rejected.
      if ! grep -qE '^Xamp FBAMP ' "${template}"; then
        echo "run_sweep.sh: ${template}: Xamp is not driven from FBAMP (measurement point missing)." >&2
        return 1
      fi
      vmeas="$(grep -cE '^Vmeas FB FBAMP 0 dc 0$' "${template}" || true)"
      if [[ "${vmeas}" != "1" ]]; then
        echo "run_sweep.sh: ${template}: expected exactly one 'Vmeas FB FBAMP 0 dc 0' ammeter, found ${vmeas}." >&2
        return 1
      fi
      iinx="$(grep -cE '^Iinx 0 FBAMP dc 0 ac 1$' "${template}" || true)"
      if [[ "${iinx}" != "1" ]]; then
        echo "run_sweep.sh: ${template}: expected exactly one 'Iinx 0 FBAMP dc 0 ac 1' shunt injection, found ${iinx}." >&2
        return 1
      fi
      if grep -qE '^Vbreak ' "${template}"; then
        echo "run_sweep.sh: ${template}: the current-injection bench must NOT break the loop (found a Vbreak line)." >&2
        return 1
      fi
      ;;
    *)
      echo "run_sweep.sh: unknown topology variant '${variant}'" >&2
      return 1
      ;;
  esac
  return 0
}

assert_loopgain_topology_sync() {
  local tmpl variant rc=0
  for tmpl in loopgain loopgain2v loopgain2i e1op; do
    case "${tmpl}" in
      loopgain2i) variant=shunt ;;
      *)          variant=vbreak ;;
    esac
    if ! topology_sync_problem "${DESIGN_NETLIST}" \
        "${SCRIPT_DIR}/testbench/tb_${tmpl}_cmos5l.spice.tmpl" "${variant}"; then
      echo "run_sweep.sh: FATAL -- tb_${tmpl}_cmos5l bench topology is out of sync with ldo_core_cmos5l." >&2
      echo "run_sweep.sh: update tb_${tmpl}_cmos5l.spice.tmpl's flattened copy (and LOOPGAIN_EXPECTED_BODY) to match, then re-run." >&2
      rc=1
    fi
  done
  [[ ${rc} -eq 0 ]] || exit 4
}

# Negative controls for the guard above: each mutation of the real netlist or
# template MUST be rejected. Run with --check-topology-guard. Three suites:
# tb_loopgain_cmos5l (the series-break bench, issues #21/#67/#89),
# tb_loopgain2v (issue #135: circuit-identical twin, its own file guarded)
# and tb_loopgain2i (issue #135: the intact-loop shunt-injection variant).
# Each mutation line is "name<TAB>sed-expression<TAB>target(netlist|template)".
check_topology_guard() {
  local tmp rc=0
  tmp="$(mktemp -d)"
  guard_suite() {
    local tmpl_base="$1" variant="$2"
    local tmpl="${SCRIPT_DIR}/testbench/tb_${tmpl_base}_cmos5l.spice.tmpl"
    if ! topology_sync_problem "${DESIGN_NETLIST}" "${tmpl}" "${variant}" 2>"${tmp}/base.err"; then
      echo "run_sweep.sh: --check-topology-guard: the UNMUTATED ${tmpl_base} pair is already rejected:" >&2
      cat "${tmp}/base.err" >&2
      rc=1
      return 0
    fi
    echo "run_sweep.sh: guard accepts the real ${tmpl_base} netlist/template pair."
    neg() { # name sed-expr target(netlist|template)
      local name="$1" expr="$2" target="$3" n="${tmp}/ldo.spice" t="${tmp}/tb.tmpl"
      cp "${DESIGN_NETLIST}" "${n}"
      cp "${tmpl}" "${t}"
      if [[ "${target}" == netlist ]]; then sed -i -E "${expr}" "${n}"; else sed -i -E "${expr}" "${t}"; fi
      if cmp -s "${n}" "${DESIGN_NETLIST}" && cmp -s "${t}" "${tmpl}"; then
        echo "run_sweep.sh: NEGATIVE CONTROL INEFFECTIVE (${tmpl_base}; mutation changed nothing): ${name}" >&2
        rc=1
      elif topology_sync_problem "${n}" "${t}" "${variant}" 2>/dev/null; then
        echo "run_sweep.sh: NEGATIVE CONTROL NOT REJECTED (${tmpl_base}): ${name}" >&2
        rc=1
      else
        echo "run_sweep.sh: rejected (${tmpl_base}, as required): ${name}"
      fi
    }
    local name expr target
    while IFS=$'\t' read -r name expr target; do
      [[ -n "${name}" ]] || continue
      neg "${name}" "${expr}" "${target}"
    done
  }

  # --- tb_loopgain_cmos5l: the series-break bench (issues #21/#67/#89) ---
  guard_suite loopgain vbreak <<'MUTATIONS'
template omits XMen	/^XMen /d	template
template XMen gate (EN) tied to VSS	s/^XMen EAOUT EN /XMen EAOUT VSS /	template
template XMen drain moved to FB	s/^XMen EAOUT /XMen FB /	template
template XMen body moved to VSS	s/^(XMen EAOUT EN VIN) VIN /\1 VSS /	template
template XMen width changed	s/^(XMen .* w=)40u/\130u/	template
template omits XMbdis	/^XMbdis /d	template
template XMbdis drain moved to FB	s/^XMbdis IBIAS /XMbdis FB /	template
template XMbdis gate (EN) tied to VIN	s/^XMbdis IBIAS EN /XMbdis IBIAS VIN /	template
netlist omits XMbdis	/^XMbdis /d	netlist
template Xamp loop break removed	s/^Xamp FBAMP /Xamp FB /	template
template Vbreak removed	/^Vbreak /d	template
netlist omits XMen	/^XMen /d	netlist
netlist XMen gate moved to VIN	s/^XMen EAOUT EN /XMen EAOUT VIN /	netlist
netlist EN port dropped from header	s/^(\.subckt ldo_core_cmos5l .*) EN$/\1/	netlist
template Xamp EN pin dropped (six-pin amp)	s/^(Xamp FBAMP VREF EAOUT VIN VSS IBIAS) EN /\1 /	template
template Xamp EN pin tied to VIN	s/^(Xamp FBAMP VREF EAOUT VIN VSS IBIAS) EN /\1 VIN /	template
netlist Xamp EN pin dropped	s/^(Xamp FB VREF EAOUT VIN VSS IBIAS) EN /\1 /	netlist
MUTATIONS

  # --- tb_loopgain2v (issue #135): circuit-identical twin of the break bench;
  # the same connectivity mutations must be rejected against ITS file too,
  # plus the break-amplitude mutation the reconstruction relies on. ---
  guard_suite loopgain2v vbreak <<'MUTATIONS'
template Xamp loop break removed	s/^Xamp FBAMP /Xamp FB /	template
template Vbreak removed	/^Vbreak /d	template
template Vbreak AC amplitude changed	s/^Vbreak FB FBAMP 0 ac 1$/Vbreak FB FBAMP 0 ac 2/	template
template omits XMen	/^XMen /d	template
template omits XMbdis	/^XMbdis /d	template
MUTATIONS

  # --- tb_loopgain2i (issue #135): the intact-loop shunt-injection bench. ---
  guard_suite loopgain2i shunt <<'MUTATIONS'
template ammeter removed (loop left open)	/^Vmeas /d	template
template ammeter given an AC injection	s/^Vmeas FB FBAMP 0 dc 0$/Vmeas FB FBAMP 0 dc 0 ac 1/	template
template shunt injection removed	/^Iinx /d	template
template shunt injection moved to the divider side	s/^Iinx 0 FBAMP dc 0 ac 1$/Iinx 0 FB dc 0 ac 1/	template
template shunt injection polarity flipped	s/^Iinx 0 FBAMP dc 0 ac 1$/Iinx FBAMP 0 dc 0 ac 1/	template
template ammeter nodes swapped	s/^Vmeas FB FBAMP 0 dc 0$/Vmeas FBAMP FB 0 dc 0/	template
template Vbreak smuggled in	s/^Vmeas FB FBAMP 0 dc 0$/Vbreak FB FBAMP 0 ac 1/	template
template omits XMen	/^XMen /d	template
template omits XMbdis	/^XMbdis /d	template
netlist omits XMbdis	/^XMbdis /d	netlist
template Xamp EN pin dropped (six-pin amp)	s/^(Xamp FBAMP VREF EAOUT VIN VSS IBIAS) EN /\1 /	template
MUTATIONS

    rm -rf "${tmp}"
  return ${rc}
}
if [[ ${CHECK_GUARD} -eq 1 ]]; then
  check_topology_guard
  exit $?
fi

# --check-topology (issue #135): the POSITIVE assertion only (every
# loop-gain bench template still mirrors ldo_core_cmos5l), no PDK, no
# ngspice, no mutations. run_loopgain2.sh calls this before rendering.
if [[ ${CHECK_TOPOLOGY} -eq 1 ]]; then
  assert_loopgain_topology_sync
  echo "run_sweep.sh: all loop-gain bench templates are in sync with ldo_core_cmos5l."
  exit 0
fi


export PDK=ihp-sg13cmos5l
# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"
# shellcheck source=/dev/null
source "${SIM_DIR}/tools/preflight.sh"

if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_sweep.sh: no resolvable ${PDK} install -- see sim/env.sh output above." >&2
  exit 3
fi

OSDI_DIR="${SG13G2_OSDI_DIR}"

if [[ ${BATCH} -eq 1 && ${CHECK_ENV} -eq 0 ]]; then
  # Batch mode: the OSDI binaries are staged to the fleet and loaded by the
  # runner's ngspice 46. They do not need to load in this host's ngspice
  # (the host may have none, or an older one that rejects OSDI ABI v0.4).
  # They only need to exist here.
  for m in psp103 psp103_nqs mosvar r3_cmc cap_cmomi cap_cmomf; do
    [[ -f "${OSDI_DIR}/${m}.osdi" ]] || {
      echo "run_sweep.sh: --batch: ${OSDI_DIR}/${m}.osdi missing -- run PDK=${PDK} sim/tools/build-osdi.sh first." >&2
      exit 3
    }
  done
  command -v klt >/dev/null 2>&1 || { echo "run_sweep.sh: --batch: klt not on PATH." >&2; exit 3; }
  NGSPICE_VERSION="(set from the batch runner after submission)"
else
  if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
    echo "run_sweep.sh: OSDI models missing/unloadable -- run PDK=${PDK} sim/tools/build-osdi.sh first:" >&2
    "${SIM_DIR}/tools/build-osdi.sh" --check || true
    exit 3
  fi

  command -v ngspice >/dev/null 2>&1 || { echo "run_sweep.sh: ngspice not on PATH." >&2; exit 3; }
  NGSPICE_VERSION="$(ngspice -v 2>&1 | sed -n '2p')"
fi

if [[ ! -f "${DESIGN_NETLIST}" ]]; then
  echo "run_sweep.sh: ${DESIGN_NETLIST} not found -- regenerate it first:" >&2
  echo "run_sweep.sh:   python3 design/netlist.py --design sg13cmos5l" >&2
  exit 3
fi

assert_loopgain_topology_sync

# Expected output-row counts, per bench, for the POSITIVE completeness
# check in run_ngspice below (and the --check-env output validation, #91). Derived from the templates' own analysis
# statements, not guessed: the DC bench's nested sweep is Vin
# 2.00..3.63 step 0.01 (164 rows) x 5 Iload blocks = 820; the two AC
# benches are `ac dec 20 1 100meg` = 20 points/decade x 8 decades + 1 = 161.
# If a template's analysis statement is ever changed without updating
# these, every point fails loudly -- the same "fail loudly rather than go
# silently stale" posture assert_loopgain_topology_sync() takes above.
EXPECT_ROWS_DC=820
EXPECT_ROWS_AC=161      # psrr bench (ac dec 20 1 100meg)
# Loop-gain bench: derived from the configured ceiling (issue #128) and
# cross-checked against the rendered template line below, so a template and
# a count that drift apart fail loudly here instead of at every point.
EXPECT_ROWS_LG="$(python3 "${SCRIPT_DIR}/ac_sweep.py" rows "${LG_AC_MAX}")"
LG_AC_LINE="$(python3 "${SCRIPT_DIR}/ac_sweep.py" line "${LG_AC_MAX}")"
if ! grep -qxF "ac dec 20 1 @@LG_AC_MAX@@" "${SCRIPT_DIR}/testbench/tb_loopgain_cmos5l.spice.tmpl"; then
  echo "run_sweep.sh: tb_loopgain_cmos5l.spice.tmpl no longer has 'ac dec 20 1 @@LG_AC_MAX@@'; update ac_sweep.py/EXPECT_ROWS_LG with it." >&2
  exit 3
fi
if [[ ${LG_AC_MAX} == 100meg && ${EXPECT_ROWS_LG} -ne ${EXPECT_ROWS_AC} ]]; then
  echo "run_sweep.sh: default loop-gain row count ${EXPECT_ROWS_LG} != ${EXPECT_ROWS_AC}." >&2
  exit 3
fi

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
      -e "s|@@LG_AC_MAX@@|${LG_AC_MAX}|g" \
      -e "s|@@CC_W@@|nominal (--check-env)|g" \
      -e "s|@@LOAD_A@@|0.001|g" \
      -e "s|@@COUT_F@@|1u|g" \
      -e "s|@@COUT_BOTTOM@@|0|g" \
      -e "s|@@ESR_LINE@@|* ESR=0 (--check-env)|g" \
      -e "s|@@DESIGN_NETLIST@@|${DESIGN_NETLIST}|g" \
      -e "s|@@DC_CSV@@|${tmp}/${bench}_check_dc.csv|g" \
      -e "s|@@AC_CSV@@|${tmp}/${bench}_check_ac.csv|g" \
      "${template}" > "${netlist}"
    log="${tmp}/${bench}_check.log"
    case "${bench}" in
      dcsweep)  vargs=(--wrdata "${tmp}/${bench}_check_dc.csv:8:${EXPECT_ROWS_DC}") ;;
      loopgain) vargs=(--wrdata "${tmp}/${bench}_check_ac.csv:4:${EXPECT_ROWS_LG}" --marker LOOPGAIN_VOUT_OP) ;;
      psrr)     vargs=(--wrdata "${tmp}/${bench}_check_ac.csv:2:${EXPECT_ROWS_AC}") ;;
    esac
    preflight_bench_ok "${bench}" "${netlist}" "${log}" "${vargs[@]}" || rc=1
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
#
# RE-BASELINED BY #67 (PR #87), from the #31 record to the #35 one
# (20260917-023832-7061e8f). That is the last record before the EN
# interface (DR-0008), run against the pre-#67 netlist (sha256 c6e630e9...).
# It uses the same benches (EN tied to VIN reproduces the pre-#67
# connectivity) and the same full 45-point grid, so the delta table isolates
# what the enable devices change.
#
# RE-BASELINED BY #89, from the #35 record to the #67 one
# (20261010-025634-60a3e81, PR #87). That is the last main-grid record
# before the G1 disable pull-down (DR-0008 addendum), run on the batch fleet
# against the six-pin-Xamp netlist (core sha256 7953b25b...222cc1). Same
# benches (EN tied to VIN), same full 45-point grid, so the delta table
# isolates what the three added amplifier devices change in the enabled
# state.
BASELINE_CSV="${RECORDS_DIR}/20261010-025634-60a3e81.csv"
# The newest committed main-grid record (issue #67, EN design, batch fleet).
# The dynamic DoE (issue #64) compares its legacy 1 mA / 1 uF / 0 ohm point
# against BOTH this and the pre-EN #35 record. #89 moved BASELINE_CSV to the
# #67 record, so the DoE keeps naming the #35 record explicitly (its
# comparison is unchanged by that re-baselining).
CURRENT_RECORD_CSV="${RECORDS_DIR}/20261010-025634-60a3e81.csv"
DOE_LEGACY_BASELINE_CSV="${RECORDS_DIR}/20260917-023832-7061e8f.csv"

total=0
passed=0
failed_points=()

# ESR as a series element with Cout. Prints "<cout-bottom-node> <esr-line>".
# ESR of exactly 0 wires Cout to ground and emits a comment instead of a
# zero-valued resistor, which ngspice versions treat differently.
esr_netlist_parts() {
  local esr="$1"
  if [[ "${esr}" == "0" ]]; then
    echo "0 * ESR=0: Cout wired directly to ground, no series resistor"
  else
    echo "COUT_ESR Resr COUT_ESR 0 ${esr}"
  fi
}

gen_netlist() {
  local bench="$1" point_id="$2" mos_section="$3" res_section="$4" cap_section="$5" temp="$6" design_netlist="$7" cc_w_desc="$8"
  # Optional operating point (issue #64); defaults are the legacy 1mA / 1uF /
  # 0 ohm point, so every pre-#64 call site renders the same Iload/Cout.
  # $9 load [A], $10 effective Cout [F], $11 ESR [ohm], all in ngspice number
  # syntax. Validation/canonicalisation lives in dynamic_doe.py.
  local load_a="${9:-0.001}" cout_f="${10:-1u}" esr_ohm="${11:-0}"
  local cout_bottom esr_line
  read -r cout_bottom esr_line < <(esr_netlist_parts "${esr_ohm}")
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
    -e "s|@@LG_AC_MAX@@|${LG_AC_MAX}|g" \
    -e "s|@@CC_W@@|${cc_w_desc}|g" \
    -e "s|@@DESIGN_NETLIST@@|${design_netlist}|g" \
    -e "s|@@LOAD_A@@|${load_a}|g" \
    -e "s|@@COUT_F@@|${cout_f}|g" \
    -e "s|@@COUT_BOTTOM@@|${cout_bottom}|g" \
    -e "s|@@ESR_LINE@@|${esr_line}|g" \
    "${extra_sed[@]}" \
    "${template}" > "${netlist}"
  echo "${netlist}"
}


recoverable_warning_points=()

if [[ ${BATCH} -eq 1 ]]; then
  # Scratch space for the requests and the returned rawfiles (~1 MB per
  # corner). Only the reduced *_dc/_ac.csv files, the logs and the request
  # and report provenance are copied into corners/<id>/.
  BATCH_WORK="$(mktemp -d "${TMPDIR:-/tmp}/ldo-cmos5l-pvt-batch.XXXXXX")"
  BATCH_QUEUE="${BATCH_WORK}/queue.tsv"
  : > "${BATCH_QUEUE}"
fi
BATCH_EXTRA_ARGS=()

run_ngspice() {
  local point_id="$1" netlist="$2"
  local rc=0
  if [[ ${BATCH} -eq 1 ]]; then
    # Deferred: batch_backend.py runs every queued point on the fleet, then
    # screen_point screens each one exactly as below (see the --batch block
    # after the loops).
    printf '%s\t%s\n' "${point_id}" "${netlist}" >> "${BATCH_QUEUE}"
    return 0
  fi
  ngspice -b "${netlist}" > "${CORNERS_OUT}/${point_id}.log" 2>&1 || rc=$?
  screen_point "${point_id}" "${rc}"
}

screen_point() {
  local point_id="$1" rc="$2"
  local log="${CORNERS_OUT}/${point_id}.log"
  local out_csv expect_rows got_rows
  case "${point_id}" in
    dcsweep_*) out_csv="${CORNERS_OUT}/${point_id}_dc.csv"; expect_rows=${EXPECT_ROWS_DC} ;;
    loopgain_*) out_csv="${CORNERS_OUT}/${point_id}_ac.csv"; expect_rows=${EXPECT_ROWS_LG} ;;
    *)         out_csv="${CORNERS_OUT}/${point_id}_ac.csv"; expect_rows=${EXPECT_ROWS_AC} ;;
  esac
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

  # Loop-gain traces must also span exactly the configured floor..ceiling
  # (issue #128): the row count alone would accept a wrong-range sweep.
  if [[ "${point_id}" == loopgain_* ]] \
     && ! python3 "${SCRIPT_DIR}/ac_sweep.py" check-trace "${out_csv}" "${LG_AC_MAX}"; then
    echo "run_sweep.sh: FAILED ${point_id} -- loop-gain trace does not match the configured ${LG_AC_LINE}" >&2
    failed_points+=("${point_id}")
    return 1
  fi

  if grep -qiE "^[[:space:]]*Warning: singular matrix" "${log}"; then
    recoverable_warning_points+=("${point_id}")
  fi
  passed=$((passed + 1))
  return 0
}

# Run every queued point on the fleet, then screen each one (shared by the
# main grid and the --doe-generate --batch campaign, issue #64).
# SWEEP_BATCH_CONCURRENCY (default 2) bounds how many klt sim requests are
# in flight at once; it is fleet-side work, the submitting host only waits.
# SWEEP_BATCH_REUSE_WORK=<earlier batch work dir> (issue #89) reuses the
# completed fleet report of any group whose request there is byte-identical
# (batch_backend.py --reuse-work), so a run whose client was interrupted
# after most jobs finished does not resubmit them. Reused groups are listed
# in corners/<id>/_batch/reused-reports.tsv. Nothing ever runs locally.
run_batch_queue() {
  # Run every queued point on the fleet. batch_backend.py writes the same
  # <point_id>.log and *_dc/_ac.csv files the local loop writes. A failed
  # submission leaves its points without output, and screen_point then
  # fails them. Nothing here ever falls back to a local ngspice run.
  batch_rc=0
  python3 "${SCRIPT_DIR}/batch_backend.py" run \
    --queue "${BATCH_QUEUE}" --corners-out "${CORNERS_OUT}" \
    --work "${BATCH_WORK}" --osdi-dir "${OSDI_DIR}" \
    --submit-concurrency "${SWEEP_BATCH_CONCURRENCY:-2}" \
    "${BATCH_EXTRA_ARGS[@]}" \
    ${SWEEP_BATCH_REUSE_WORK:+--reuse-work "${SWEEP_BATCH_REUSE_WORK}"} \
    ${SWEEP_BATCH_PLAN_ONLY:+--plan-only} || batch_rc=$?
  if [[ -n "${SWEEP_BATCH_PLAN_ONLY:-}" ]]; then
    echo "run_sweep.sh: SWEEP_BATCH_PLAN_ONLY set -- plan printed, nothing submitted;" >&2
    echo "run_sweep.sh: delete ${SNAPSHOTS_OUT} and ${CORNERS_OUT} by hand." >&2
    exit "${batch_rc}"
  fi
  if [[ ${batch_rc} -ne 0 ]]; then
    echo "run_sweep.sh: batch_backend.py exited ${batch_rc}; the affected points are screened as FAILED below." >&2
  fi
  if [[ -f "${CORNERS_OUT}/_batch/backend.env" ]]; then
    # shellcheck source=/dev/null
    source "${CORNERS_OUT}/_batch/backend.env"
    NGSPICE_VERSION="${BATCH_NGSPICE_VERSION} (EDA batch fleet runner, klt ${BATCH_RUNNER_KLT})"
  fi
  while IFS=$'\t' read -r point_id _netlist; do
    rc=0
    [[ -f "${CORNERS_OUT}/${point_id}.log" ]] || rc=1
    screen_point "${point_id}" "${rc}" || true
  done < "${BATCH_QUEUE}"
}

# --- Dynamic DoE (issue #64). Renders every planned load x Cout x ESR x PVT
# netlist through the SAME gen_netlist as the main grid and writes a
# provenance manifest. Without --batch it stops there (generate-only; it
# never launches a local ngspice grid). With --batch it sends every point to
# the EDA batch fleet through the same run_batch_queue/batch_backend.py path
# as the main grid, screens each point, and runs dynamic_doe.py analyse +
# refine into records/<id>.dynamic-doe.*. The matrix, validation and ID
# rules are dynamic_doe.py's; --doe-extra=FILE appends refinement points,
# --doe-only-extra simulates only those, and --doe-base=<record id> names
# the earlier record whose corners/ the analysis reads for the rest. ---
if [[ ${DOE_GENERATE} -eq 1 ]]; then
  if [[ ${DOE_ONLY_EXTRA} -eq 1 && ( -z "${DOE_EXTRA}" || -z "${DOE_BASE}" ) ]]; then
    echo "run_sweep.sh: --doe-only-extra needs --doe-extra=FILE and --doe-base=<record id>." >&2
    exit 2
  fi
  if [[ -n "${DOE_BASE}" && ! -d "${EXPERIMENT_DIR}/corners/${DOE_BASE}" ]]; then
    echo "run_sweep.sh: --doe-base: ${EXPERIMENT_DIR}/corners/${DOE_BASE} not found." >&2
    exit 2
  fi
  MANIFEST="${RECORDS_DIR}/${RECORD_ID}.dynamic-doe.manifest.tsv"
  plan_args=(plan)
  [[ -n "${DOE_EXTRA}" ]] && plan_args+=(--extra "${DOE_EXTRA}")
  [[ ${DOE_ONLY_EXTRA} -eq 1 ]] && plan_args+=(--only-extra)
  # The DoE decks differ only in their Iload/Cout/Resr lines (the bench
  # body is otherwise identical), so batch_backend.py moves exactly those
  # lines into each point's own corners.lib section and runs each bench as
  # ONE klt sim request instead of one per operating point. Each fleet job
  # costs minutes of overhead for seconds of simulation; see README.md
  # "Dynamic DoE" for the measured numbers and the cross-check.
  # SWEEP_BATCH_MAX_POINTS caps the points per request (default: no cap),
  # so one Spot interruption holds up only that slice of the grid.
  BATCH_EXTRA_ARGS=(--variant-lines '^(Iload|Cout|Resr) ')
  [[ -n "${SWEEP_BATCH_MAX_POINTS:-}" ]] && BATCH_EXTRA_ARGS+=(--max-points-per-request "${SWEEP_BATCH_MAX_POINTS}")
  doe_rows=()
  while IFS=$'\t' read -r bench pid mos res temp load cout esr; do
    netlist="$(gen_netlist "${bench}" "${pid}" "${mos}" "${res}" cap_typ "${temp}" "${DESIGN_NETLIST}" "170u (nominal)" "${load}" "${cout}" "${esr}")"
    doe_rows+=("${bench}"$'\t'"${pid}"$'\t'"${mos}"$'\t'"${res}"$'\t'"${temp}"$'\t'"${load}"$'\t'"${cout}"$'\t'"${esr}"$'\t'"${netlist}")
    [[ ${BATCH} -eq 1 ]] && run_ngspice "${pid}" "${netlist}"
  done < <(python3 "${SCRIPT_DIR}/dynamic_doe.py" "${plan_args[@]}")
  if [[ ${#doe_rows[@]} -eq 0 ]]; then
    echo "run_sweep.sh: --doe-generate: the plan is empty." >&2
    exit 2
  fi
  [[ ${BATCH} -eq 1 ]] && run_batch_queue
  printf 'bench\tpoint_id\tmos\tres\ttemp_c\tload_a\tcout_f\tesr_ohm\tnetlist\tnetlist_sha256\tinvocation\tgit_sha\tpdk\tngspice\n' > "${MANIFEST}"
  for row in "${doe_rows[@]}"; do
    IFS=$'\t' read -r bench pid mos res temp load cout esr netlist <<< "${row}"
    if [[ ${BATCH} -eq 1 ]]; then
      group="$(awk -F'\t' -v p="${pid}" '$1 == p {print $2}' "${CORNERS_OUT}/_batch/points.tsv" 2>/dev/null || true)"
      invocation="klt sim --backend batch corners/${RECORD_ID}/_batch/${group:-UNSUBMITTED}/request.json (batch_backend.py; corner ${mos}__${res}__cap_typ @ ${temp}C)"
    else
      invocation="ngspice -b ${netlist#"${REPO_ROOT}/"}"
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "${bench}" "${pid}" "${mos}" "${res}" "${temp}" "${load}" "${cout}" "${esr}" \
      "${netlist#"${REPO_ROOT}/"}" "$(sha256sum "${netlist}" | cut -d' ' -f1)" \
      "${invocation}" "${REPO_GIT_SHA}" "${PDK}" "${NGSPICE_VERSION}" >> "${MANIFEST}"
  done
  echo "run_sweep.sh: --doe-generate: ${#doe_rows[@]} netlists -> ${SNAPSHOTS_OUT}; manifest ${MANIFEST}"
  if [[ ${BATCH} -eq 0 ]]; then
    echo "run_sweep.sh: no simulation was run (see README.md 'Dynamic DoE')."
    exit 0
  fi
  echo "run_sweep.sh: --doe-generate --batch: ${passed}/${total} points passed screening; failed: ${failed_points[*]:-none}"
  doe_dirs=("${CORNERS_OUT}")
  [[ -n "${DOE_BASE}" ]] && doe_dirs+=("${EXPERIMENT_DIR}/corners/${DOE_BASE}")
  doe_args=()
  [[ -n "${DOE_EXTRA}" ]] && doe_args+=(--extra "${DOE_EXTRA}")
  doe_rc=0
  python3 "${SCRIPT_DIR}/dynamic_doe.py" analyse "${doe_dirs[@]}" "${doe_args[@]}" \
    --legacy-record "${DOE_LEGACY_BASELINE_CSV}" \
    --legacy-record "${CURRENT_RECORD_CSV}" \
    --out-prefix "${RECORDS_DIR}/${RECORD_ID}.dynamic-doe" || doe_rc=$?
  python3 "${SCRIPT_DIR}/dynamic_doe.py" refine "${doe_dirs[@]}" "${doe_args[@]}" \
    --out "${RECORDS_DIR}/${RECORD_ID}.dynamic-doe.refine.json"
  echo "run_sweep.sh: summary ${RECORDS_DIR}/${RECORD_ID}.dynamic-doe.md (analyse exit ${doe_rc}: non-zero = matrix incomplete)"
  exit "${doe_rc}"
fi

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

if [[ ${BATCH} -eq 1 ]]; then
  run_batch_queue
fi

if [[ ${passed} -eq 0 ]]; then
  echo "run_sweep.sh: no points passed -- refusing to write a summary." >&2
  exit 1
fi

# --- Post-process everything into the record CSVs + the before/after/delta
# markdown fragment that gets inlined into the record below ---
CMP_MD_FRAGMENT="${CORNERS_OUT}/_before_after_delta.md"
# Axes go over as repeatable flags (issue #223): one flag per corner /
# temperature / resistor section / Cc width, so a reordered or dropped axis
# value is a parse error rather than a silently mis-attributed column.
REPORT_AXES=()
for corner in "${CORNERS[@]}"; do REPORT_AXES+=(--corner "${corner}"); done
for temp in "${TEMPS[@]}"; do REPORT_AXES+=(--temp "${temp}"); done
for rlabel in "${RES_LABELS[@]}"; do REPORT_AXES+=(--res-label "${rlabel}"); done
for w in "${CC_TOL_WIDTHS[@]}"; do REPORT_AXES+=(--cc-tol-width "${w}"); done
python3 "${SCRIPT_DIR}/sweep_report.py" \
         --corners-dir "${CORNERS_OUT}" \
         --csv-out "${CSV_OUT}" \
         --sens-csv-out "${SENS_CSV_OUT}" \
         --baseline-csv "${BASELINE_CSV}" \
         --delta-csv-out "${DELTA_CSV_OUT}" \
         --cmp-md-out "${CMP_MD_FRAGMENT}" \
         --cc-nominal-w "${CC_NOMINAL_W}" \
         "${REPORT_AXES[@]}"

# Fold invalid-DC-grid points (#120) into the failed-point accounting.
DC_GRID_ERRORS_TSV="${CORNERS_OUT}/_dc_grid_errors.tsv"
DC_GRID_ERROR_LINES=()
if [[ -s "${DC_GRID_ERRORS_TSV}" ]]; then
  while IFS=$'\t' read -r _pid _err; do
    DC_GRID_ERROR_LINES+=("${_pid}: ${_err}")
    if [[ " ${failed_points[*]-} " != *" ${_pid} "* ]]; then
      failed_points+=("${_pid}")
    fi
  done < "${DC_GRID_ERRORS_TSV}"
fi

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
  echo "  closes the res_bcs/125C phase-margin gap #31 found), or #67 (the"
  echo "  active-high \`EN\` interface, DR-0008, run with EN tied to VIN)."
  # Installed-revision provenance is READ from the install (issue #155): the
  # fetcher's .fetched-version marker, else a git checkout's HEAD, else
  # "not recorded" -- never a hard-coded commit string.
  pdk_installed="not recorded (no .fetched-version marker, not a git checkout)"
  if [[ -f "${PDK_ROOT}/${PDK}/.fetched-version" ]]; then
    pdk_installed="$(cat "${PDK_ROOT}/${PDK}/.fetched-version") (read from ${PDK}/.fetched-version)"
  elif git -C "${PDK_ROOT}/${PDK}" rev-parse HEAD >/dev/null 2>&1; then
    pdk_installed="$(git -C "${PDK_ROOT}/${PDK}" rev-parse HEAD) (git rev-parse HEAD)"
  fi
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned revision: see"
  echo "  \`sim/pdk-cmos5l.json\`. Installed revision as read from the install:"
  echo "  \`${pdk_installed}\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by"
  echo "  \`PDK=${PDK} sim/tools/build-osdi.sh\`."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  if [[ ${BATCH} -eq 1 ]]; then
    echo "- **Backend**: \`run_sweep.sh --batch\`. Every point ran on the EDA batch"
    echo "  fleet through \`klt sim --backend batch\` (\`batch_backend.py\`), not on"
    echo "  the submitting host: ${BATCH_JOB_COUNT:-?} klt sim requests (job ids,"
    echo "  requests, generated decks and klt reports under"
    echo "  \`corners/${RECORD_ID}/_batch/\`). The OSDI binaries listed above were"
    echo "  staged byte-for-byte with each job and loaded from the job's \`inputs/\`."
    echo "  Their sha256 is printed in every per-point log and listed in"
    echo "  \`corners/${RECORD_ID}/_batch/backend.json\`. The model libraries were"
    echo "  staged from the PDK install above. Reduction from the runner's ASCII"
    echo "  rawfile to the \`wrdata\` CSV layout was validated byte-for-byte against"
    echo "  local ngspice-46 output (README.md \"Batch backend\")."
  fi
  echo "- **Design netlist sha256**: \`ldo_core_cmos5l.spice\` $(sha256sum "${DESIGN_NETLIST}" | cut -c1-64),"
  echo "  \`ldo_erramp_cmos5l.spice\` $(sha256sum "${REPO_ROOT}/design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice" | cut -c1-64)."
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
  echo "  ${EXPECT_ROWS_LG} per loopgain point, ${EXPECT_ROWS_AC} per psrr point)."
  echo "- **Loop-gain AC sweep** (issue #128): \`${LG_AC_LINE}\` (ceiling"
  echo "  \`${LG_AC_MAX}\`, floor 1 Hz, 20 points/decade, ${EXPECT_ROWS_LG} rows per"
  echo "  loopgain trace) in every loopgain deck, requested through"
  echo "  \`--loopgain-ac-max\` / \`SWEEP_LOOPGAIN_AC_MAX\`. The psrr bench is"
  echo "  \`ac dec 20 1 100meg\`."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  for _l in "${DC_GRID_ERROR_LINES[@]-}"; do
    [[ -n "${_l}" ]] && echo "- **Invalid DC grid** (#120): ${_l}"
  done
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
