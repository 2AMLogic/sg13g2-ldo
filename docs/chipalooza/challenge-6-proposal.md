# Chipalooza Challenge #6 — sign-off proposal: SG13CMOS5L low-dropout regulator

**Status: schematic captured, electrical spec table fully PVT-verified and
passing; physical implementation (layout / DRC / LVS) not started.** This
document covers phases 2/4-3/4 of the SG13CMOS5L port tracked by #12 (Epic
`2AMLogic/2am#542`, Phase 5A): device-topology decision + schematic capture
(#20, ratified by
[`DR-0002`](../../spec/decision-records/DR-0002-sg13cmos5l-device-topology.md)),
PVT-cornered closed-loop verification (#21), and the `Mpass` resize plus
error-amp re-compensation that verification motivated (#25, ratified by
[`DR-0003`](../../spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md)).
**Every spec row in section 4 currently passes at every one of the 15 PVT
corners swept.** The Challenge #6 brief's full sign-off bar (schematic +
pre-layout sim -> layout + post-layout sim over PVT -> DRC/LVS-clean GDS,
open-source-EDA-verifiable) is **not yet fully met**: this repo's `layout/`
directory is empty as of this writing, and DRC/LVS sign-off has not
happened — that work is tracked separately in #28 (split from the same
parent issue, #22, as this document) and is explicitly **not** a
prerequisite for this document (see section 5). This document proposes the
block and reports what has been verified so far, honestly bounded by what
has not — no claim without a testbench, per `CLAUDE.md`.

Block-only document: no personal or institutional detail below, per the
epic's (`2AMLogic/2am#542`) Tier 1 disclosure scope.

## 1. Block type and positioning

**This is a fixed-output, 1.8 V linear voltage regulator (LDO)** — a
closed-loop analog macro that regulates a 3.3 V analog-rail input down to a
1.8 V output over a 0–50 mA load range, for local on-die supply generation
(e.g. powering a lower-voltage sub-block from the shared 3.3 V analog rail
without a separate off-chip regulator). It is not a slot-filling novelty:
the block closes real negative feedback around a sized pass device and a
real two-stage Miller-compensated OTA error amplifier (not a behavioral
placeholder — see section 3), and it is offered with a PVT-cornered
closed-loop verification record behind every spec-table row, not just a
schematic.

The core regulation loop is verified against the full
`{tt, ss, ff, sf, fs} x {-40, 27, 125} degC` process/temperature grid (15
corners), across three independent closed-loop testbenches (DC sweep, loop
gain, PSRR) — 51/51 simulation points passing (`sim/ldo-cmos5l-pvt-sweep/`,
record
[`20260916-112842-c25ff53`](../../sim/ldo-cmos5l-pvt-sweep/records/20260916-112842-c25ff53.csv)).
That is offered as the block's positioning argument: a small, closed-loop,
fully-PVT-verified regulator macro with a real evidence trail, distinct
from an unsized or PVT-unverified schematic.

This block has **no on-chip bandgap** — `VREF` is an external, ideal
reference input by design decision
([`DR-0002`](../../spec/decision-records/DR-0002-sg13cmos5l-device-topology.md),
carried from the SG13G2 branch's own port-parity default) — so it is
positioned as consuming, not supplying, whatever bandgap-referenced
voltage/current the Challenge #6 harness already provides, rather than
competing with it.

## 2. I/O mapped to the Challenge #6 slot budget

The assembled block (`design/sg13cmos5l/ldo_core_cmos5l.sch`, top cell
`ldo_core_cmos5l`) exposes exactly five pins today, in netlist port order
(`design/README.md` "`ldo_core_cmos5l` pinout"):

| Pin | Direction | Role |
|---|---|---|
| `VIN` | inout | 3.3 V analog-rail supply (see section 4 caveats for why this rail, not the brief's 1.2 V digital rail) |
| `VOUT` | inout | Regulated 1.8 V output — the block's functional deliverable |
| `VSS` | inout | Ground |
| `VREF` | in | External ideal reference input — no on-chip bandgap (`DR-0002`) |
| `IBIAS` | inout | External bias-current input, mirrored on-block (`design/README.md` "Error amplifier" judgement call 1) |

Mapped against the brief's slot budget (per `2AMLogic/2am#542`'s own
reading of the published rules: <=24 digital control inputs, <=12 digital
test outputs, <=4 shared analog lines, 0-4 dedicated pads, template wrapper
cell):

| Budget category | Used | Notes |
|---|---|---|
| Digital control inputs | **0 / 24** | No enable, trim, or mode pin exists in the current schematic (`design/README.md` "Known gaps" — no `EN`, current limit, or soft-start circuitry on this branch either). |
| Digital test outputs | **0 / 12** | No digital status/flag signal exists. |
| Dedicated pads (preferred) | **up to 3 / 4** | `VOUT`, `VREF`, and `IBIAS` each need external analog access beyond the shared supply/ground rails — see reconciliation below. Dedicated pads are the preferred routing for `VOUT` in particular (a shared analog mux bus would add switch loading on a low-impedance regulator output whose load-regulation spec this block's own PVT record is sensitive to; that loading is not characterized against this block's output impedance). |
| Shared analog lines (fallback) | **up to 3 / 4** | If dedicated pads are oversubscribed by other participants, `VOUT`/`VREF`/`IBIAS` degrade gracefully to 3 of the brief's 4 shared analog lines instead. |

`VIN`/`VSS` are assumed supplied from the harness's shared global 3.3 V
analog rail and ground, the same assumption the sibling bandgap block's own
Challenge #2 proposal makes for its `vdd`/`vss`
(`2AMLogic/sg13g2-bandgap` `docs/chipalooza/challenge-2-proposal.md`
section 2) — **an assumption, not a fact confirmed against the brief
text**, which does not detail per-block power delivery; flagged here as an
open question for harness integration, not asserted as settled.

**Reconciling against `design/README.md`'s own slot-budget note**:
`design/README.md` ("Rails and the Challenge #6 slot budget") states this
block "presents `VIN`/`VOUT`/`VSS` plus two analog lines (`VREF`,
`IBIAS`)" — a summary written for a different purpose (total pin count
versus the SG13G2 placeholder branch's four-pin interface), not a
pin-by-pin mapping into the brief's specific budget categories. Doing that
finer-grained mapping directly against the brief's own categories (as this
issue's acceptance criteria ask): `VIN` and `VSS` are pure supply/ground,
assumed harness-provided exactly as above; `VOUT`, `VREF`, and `IBIAS` are
each a signal an external tester or the harness's own reference/bias
infrastructure must reach, so each consumes one analog-line/dedicated-pad
slot — **three** analog-line/pad-consuming pins, not two. This resolves to
the same total pin count and the same zero digital-I/O count
`design/README.md` already states; it only refines which pins the brief's
specific "analog line" category actually counts.

Total slot-budget usage proposed: **0 digital control inputs, 0 digital
test outputs, 3 shared analog lines or up to 3 dedicated pads** — well
inside every ceiling the brief sets.

## 3. Functional description

`design/sg13cmos5l/ldo_core_cmos5l.sch` (`design/README.md` "SG13CMOS5L
branch" has the full account; summarized here):

- **`Mpass`** — `sg13_hv_pmos`, common-source, source at `VIN`, drain at
  `VOUT`, body at `VIN` (`DR-0002` Decision (a)). Resized by #25
  (`w=300u` -> `w=2800u`, `l=0.5u` unchanged) against the closed-loop
  dropout evidence #21 produced — see `DR-0003` for the full derivation.
- **`Xamp` (`ldo_erramp_cmos5l.sch`)** — a real two-stage,
  Miller-compensated, single-ended-output OTA, not a behavioral
  placeholder: a `sg13_hv_pmos` tail current source (`Mtail`), a
  `sg13_hv_pmos` input pair (`Minp`=`FB`, `Minn`=`VREF`, non-inverting /
  inverting), an `sg13_hv_nmos` first-stage mirror (`Mn1`/`Mn2`), a single
  `sg13_hv_nmos` second-stage common-source device (`Mn3`) loaded by a
  `sg13_hv_pmos` current-source (`Mload2`), and a `Cc`/`Rz` Miller
  compensation network (`OUT` back to the first-stage output `G1`).
  Bias-mirror ratios and the `Cc`/`Rz` network were both re-derived by #25
  against #21's closed-loop PVT evidence (`DR-0003`) — the resistor
  nulling element `Rz` in particular grew ~226x in length to place a
  deliberate phase-lead zero near the loop's unity-gain crossover, the
  technique that actually closed the phase-margin gap (`DR-0003` "What
  actually closes the gap").
- **Feedback divider** — `Rtop`/`Rbot` (300 k-ohm each, `FB = VOUT/2`),
  still behavioral `res.sym`, not yet a PDK resistor flavor (a known gap
  for the layout phase, #28 — see section 5).
- **Bias scheme** — an external `IBIAS` current input, mirrored on-block
  via a diode-connected `Mb0`; `Mtail` (`m=3`) and `Mload2` (`m=6`) mirror
  from it, so an external sink of `Iref` sets tail = `3*Iref` and second
  stage = `6*Iref` (`design/README.md` "Error amplifier" judgement call
  1). Chosen over a `VBIAS` voltage port (would not track the mirror's
  `Vsg` over PVT) and over an on-block resistor self-bias (would make Iq a
  direct function of supply, bad PSRR in a regulator).
- **Reference** — `VREF` stays an external port; no on-chip bandgap
  (`DR-0002`).

Polarity, re-derived directly from `Mpass`'s own device physics in the
schematic header (`design/README.md`): `FB` rises -> `Minp` conducts less
-> the `VREF` leg takes more tail current -> `G1` falls -> `Mn3` conducts
less -> `Mload2` pulls `OUT` up -> `Mpass`'s `|Vsg|` shrinks -> `VOUT`
falls. Negative feedback.

No enable, current-limit, soft-start, or loop-break test point exists in
this schematic increment (`design/README.md` "Known gaps") — the same
scope boundary the SG13G2 branch's own placeholder-amp schematic states.

## 4. Spec table

Every row below is re-derived directly from `sim/`'s closed-loop PVT
evidence at SG13CMOS5L's own rails, not copied from the SG13G2 branch's
DRAFT table without independent re-verification. **This block sits
entirely on the Challenge #6 brief's 3.3 V analog rail** — every device in
the hierarchy is an HV, 3.3 V-class flavor, and there is no 1.2 V node
anywhere in it (`sim/ldo-cmos5l-pvt-sweep/README.md`, `design/README.md`
"Rails and the Challenge #6 slot budget"), so the 1.2 V digital-rail row is
marked `N/A` below, not `unmet` or omitted.

Record cited throughout:
[`sim/ldo-cmos5l-pvt-sweep/records/20260916-112842-c25ff53.csv`](../../sim/ldo-cmos5l-pvt-sweep/records/20260916-112842-c25ff53.csv)
(main 15-point PVT grid, 45 points across 3 benches) and
[`.../20260916-112842-c25ff53.sensitivity.csv`](../../sim/ldo-cmos5l-pvt-sweep/records/20260916-112842-c25ff53.sensitivity.csv)
(`Cc`-value / `Rz`-corner sensitivity, 6 points), full manifest in
[`.../20260916-112842-c25ff53.md`](../../sim/ldo-cmos5l-pvt-sweep/records/20260916-112842-c25ff53.md).
51/51 points PASS (ngspice exit 0, no convergence/model-load errors);
completeness matrix OK. "Min"/"Typ"/"Max" below are the measured
best-corner / `tt`-process-27degC / worst-corner values across the 15-point
grid — not a statistical distribution (only 15 discrete corners were
swept, no Monte Carlo) — flagged as such rather than presented as a
continuous min/typ/max the evidence does not support.

| Parameter | Target | Min (best corner) | Typ (`tt`/27degC) | Max (worst corner) | Status | Evidence |
|---|---|---|---|---|---|---|
| Output accuracy | 1.8 V +/-2% (1.764-1.836 V) | 1.80023 V | 1.80030 V | 1.80064 V | **PASS**, all 15 corners | `vout_no_load_v` column |
| Dropout @ 50 mA | < 300 mV worst corner | 0.200 V (`tt`/-40degC, floors at the bench's discretization step — see `sim/ldo-cmos5l-pvt-sweep/README.md` "Benches") | 0.200 V | 0.240 V (`ss`/125degC) | **PASS**, all 15 corners now reach regulation | `dropout_v_50ma` column |
| Line regulation | < 5 mV/V (no-load only — see caveat below) | 0.162 mV/V (`ss`/-40degC) | 0.179 mV/V | 0.245 mV/V (`ff`/125degC) | **PASS** | `line_reg_mv_per_v` column |
| Load regulation | < 1% over full load, measured at `Vin`=3.63 V (best-case headroom — see `sim/ldo-cmos5l-pvt-sweep/README.md` "Why Vin=3.63V for load regulation") | 0.0076% (`sf`/-40degC) | 0.0095% | 0.0248% (`ff`/125degC) | **PASS**, all 15 corners | `load_reg_pct` column |
| Iq, no load | < 30 uA | 21.87 uA (`ff`/125degC) | 22.97 uA | 22.98 uA (`fs`/-40degC) | **PASS** | `iq_a` column |
| Iq, full load (50 mA) | < 30 uA | -- | -- | 23.05-23.08 uA (range across the 15-point grid; not separately broken out by corner in the merged CSV — see `sim/ldo-cmos5l-pvt-sweep/README.md` "Results (issue #25...)") | **PASS** | per-corner raw sweep CSVs, `sim/ldo-cmos5l-pvt-sweep/corners/20260916-112842-c25ff53/` |
| PSRR @ 1 kHz | > 50 dB | 58.21 dB (`ss`/125degC) | 60.28 dB | 61.85 dB (`ff`/-40degC) | **PASS** | `psrr_db_1khz` column |
| PSRR @ 100 kHz | > 20 dB | 33.82 dB (`ff`/27degC) | 33.86 dB | 35.17 dB (`ff`/-40degC) | **PASS** | `psrr_db_100khz` column |
| Stability: phase margin | >= 45 deg worst corner | 54.40 deg (`ss`/125degC) | 68.57 deg | 72.72 deg (`ss`/-40degC) | **PASS** | `phase_margin_deg` column |
| Stability: gain margin | >= 10 dB worst corner | 17.07 dB (`ff`/-40degC) | 20.76 dB | 25.87 dB (`ss`/125degC) | **PASS** | `gain_margin_db` column |
| Supply operating range, 3.3 V analog rail | 2.97-3.63 V (+/-10%) | -- | -- | -- | **Met** — every spec row above is swept across this full `Vin` range (`sim/ldo-cmos5l-pvt-sweep/testbench/tb_dcsweep_cmos5l.spice.tmpl`) | same record |
| Supply operating range, 1.2 V digital rail | -- | -- | -- | -- | **N/A** — analog-only block, instantiates no device against the LV digital rail (`design/README.md` "Rails and the Challenge #6 slot budget": every transistor is HV, no 1.2 V node exists in the hierarchy) | n/a |
| Current limit | 65-80 mA brickwall | -- | -- | -- | **not implemented** — no current-limit circuit exists on this branch (`design/README.md` "Known gaps") | n/a |
| Startup | monotonic ramp, < 2% within 3 ms | -- | -- | -- | **not implemented** — no soft-start circuit | n/a |
| Enable/shutdown | -- | -- | -- | -- | **not implemented** — no `EN` pin on this branch | n/a |

**Stability-row caveat (do not read past this)**: `cornerCAP.lib` at this
PDK's pinned revision maps every corner/mismatch/stat section to the same
nominal `cap_cmomi` model — the Miller cap `Cc`'s value has **no
characterized process-corner spread on this PDK** (per
`sim/ldo-cmos5l-pvt-sweep/README.md` "MoM-cap (Cc) sensitivity sweep": the
model is explicitly "NOT YET VALIDATED ON ihp-sg13cmos5l SILICON"). Every
exact phase-margin/gain-margin/PSRR number above is therefore
`insufficient-evidence` in the strict sense pending real CMOS5L MoM-cap
silicon characterization — but the **qualitative PASS verdict itself does
not depend on that caveat**: a `Cc`-value sensitivity sweep (0.5x-2x
nominal) and an `Rz`-corner sensitivity sweep (`res_bcs`/`res_typ`/
`res_wcs`), both re-run at the current sizing
(`records/20260916-112842-c25ff53.sensitivity.csv`), give phase margin
56.9-76.4deg and gain margin 18.6-23.5dB across the full sensitivity
range tested — still comfortably inside target at every point. This
mirrors the same caveat `DR-0002`/#21 already established for the
*opposite* (FAIL) verdict before the #25 resize, applied here to the
current PASS result.

**Line-regulation caveat**: measured at no load only
(`sim/ldo-cmos5l-pvt-sweep/README.md` "Benches" — Iq itself is only
~17-23 uA and does not meaningfully load the divider/pass device
differently at other load points), unchanged from the pre-resize record.

No spec row above required relaxation to reach a PASS verdict, per
`CLAUDE.md`'s rule that verification results are never relaxed to pass. If
a future re-verification pass — for example, post-layout parasitic
extraction once #28 lands — finds a regression in any row above, that row
must be marked unmet here, not silently omitted; nothing in section 5
below should be read as pre-committing to that outcome either way.

## 5. Sign-off status against the brief

| Brief stage | Status |
|---|---|
| Schematic + pre-layout sim | **Done.** `design/sg13cmos5l/ldo_core_cmos5l.sch` (+ `ldo_erramp_cmos5l.sch`) captured and ratified (#20, `DR-0002`); resized and re-compensated against closed-loop PVT evidence (#25, `DR-0003`). Three PVT-cornered pre-layout testbenches (DC sweep, loop gain, PSRR) land 51/51 PASS across the full 15-corner grid plus sensitivity sweeps (#21, #25, section 4 above). |
| Layout + post-layout sim over PVT | **Not started.** `layout/` is empty in this repo as of this writing (`layout/README.md`: "Empty until the first work lands here"). No post-layout parasitic-extraction re-simulation exists yet. Tracked in #28 (the sibling sub-issue split from the same parent, #22, as this document) — this document has **no dependency** on #28's completion (see the note at the top of this document and #29's own "No dependency on the layout half" note); re-check #28's actual status before relying on the sentence above if you are reading this after #28 has progressed. |
| DRC/LVS-clean GDS, in-repo, open-source-EDA-verifiable | **Not started**, for the same reason: no layout exists yet to run DRC or LVS against. `Mpass` (`w=2800u`, still `ng=1 m=1`) and `Rz` (`l=1200u` at the PDK's `rhigh` minimum width, an implied ~1.2-1.7 MOhm, 1200:1 aspect ratio) are both large, schematic-level-only draws #25 sized purely against electrical targets and flagged explicitly as a known gap for the layout phase (`DR-0003` "Consequences", `design/README.md` "Known gaps") — neither has been floorplanned. The feedback divider is also still behavioral `res.sym`, not a PDK resistor flavor, and needs to become one before LVS can see it (`design/README.md` "Known gaps"). |

**This document does not claim manufacturability the design has not yet
earned.** The brief's full sign-off bar requires all three stages; only
the first is landed. Section 4's PASS verdicts are schematic-level,
pre-layout electrical verification only — real, PVT-cornered, and honestly
reported, but not a substitute for the DRC/LVS-clean, post-layout-verified
GDS the brief's deliverable gate ultimately requires. This mirrors
`CLAUDE.md`'s "no claim without a testbench" rule applied to a process
claim (implementation status), not just to a spec-row claim.

## 6. Known gaps carried into any future layout pass

Restated here from `design/README.md`/`DR-0003` so a reader of this
proposal does not have to cross-reference them to understand what #28
still has to resolve:

- **`Mpass` (`w=2800u`) and `Rz` (`l=1200u`) are both large,
  schematic-level-only draws.** `Mpass` needs multi-finger/multi-row
  layout (`ng`/`m` are both still `1`); `Rz` needs the PDK's own `rhigh`
  PCell meandering (`b` bends parameter, currently `0`) to fit a
  practical die footprint.
- **The feedback divider is behavioral `res.sym`, not a PDK resistor
  flavor** — needs a real `rsil`/`rppd`/`rhigh` divider before LVS can see
  it.
- **No CI job** runs `--design sg13cmos5l --check` or the PVT sweep for
  this branch yet; both are local/manual steps
  (`sim/ldo-cmos5l-pvt-sweep/README.md` "CI",
  `2AMLogic/klayout-tools#1929`).
- **The MoM-cap (`Cc`) model has no characterized process-corner spread on
  this PDK** (see section 4's stability-row caveat) — resolving this
  needs real CMOS5L silicon characterization, out of scope for any
  schematic- or layout-level phase of this port.

None of these block this document's own spec-table claims (section 4),
which are pre-layout, schematic-level PVT results and are reported as
such — they are listed here as the concrete input the layout phase (#28)
needs, consistent with this repo's practice of surfacing costs rather than
leaving them implicit.

## References

- `design/README.md` "SG13CMOS5L branch" — schematic capture account
  (#20), pinout, slot-budget note, and the full device table.
- [`spec/decision-records/DR-0002-sg13cmos5l-device-topology.md`](../../spec/decision-records/DR-0002-sg13cmos5l-device-topology.md)
  — device-flavor and topology decision.
- [`spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md`](../../spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md)
  — `Mpass` resize and error-amp re-compensation decision, with the full
  before/after PVT evidence.
- [`sim/ldo-cmos5l-pvt-sweep/README.md`](../../sim/ldo-cmos5l-pvt-sweep/README.md)
  — the three PVT-cornered testbenches this document's spec table draws
  from (#21, #25), including the loop-gain measurement method and the
  MoM-cap sensitivity sweep this document's stability-row caveat cites.
- `layout/README.md` — current (empty) state of this repo's layout tree.
- [`2AMLogic/2am` `docs/pdk/sg13cmos5l.md`](https://github.com/2AMLogic/2am/blob/main/docs/pdk/sg13cmos5l.md)
  — the fleet's SG13CMOS5L PDK notes.
- [`2AMLogic/2am#542`](https://github.com/2AMLogic/2am/issues/542) — Epic
  #542, Phase 5A, tracking the SG13CMOS5L port across this repo.
- Issue #12 (this repo's own tracking issue for the SG13CMOS5L port), #20
  (schematic capture), #21 (PVT verification), #25 (resize +
  re-compensation), #22 (parent issue this document and #28 were split
  from), #28 (sibling layout + DRC/LVS sub-issue), #29 (this document's
  own tracking issue).
- Precedent: `2AMLogic/sg13g2-bandgap`
  [`docs/chipalooza/challenge-2-proposal.md`](https://github.com/2AMLogic/sg13g2-bandgap/blob/main/docs/chipalooza/challenge-2-proposal.md)
  — the analogous proposal-doc phase for the sibling bandgap block, whose
  structure (I/O slot-budget table, spec table with explicit
  insufficient-evidence/not-implemented rows, sign-off-status-against-the-brief
  table) this document follows.
