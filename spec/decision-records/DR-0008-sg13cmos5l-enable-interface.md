# DR-0008: SG13CMOS5L enable interface — topology, valid levels, bias handling, stress, and off-state measurement conditions

- **Status**: Proposed (a builder-drafted record; operator approval of the PR
  that carries it is the acceptance act, per the fleet ratification policy
  `DR-0006` quotes). **No target-spec row is ratified, relaxed or changed by
  this record. Row 9 (startup) stays Open.**
- **Date**: 2026-10-10
- **Scope**: The electrical **interface** of the SG13CMOS5L core
  (`design/sg13cmos5l/ldo_core_cmos5l.sch`): a sixth, active-high `EN` port
  and the two transistors behind it. Issue #67, child of #62. It does **not**
  implement startup characterization (#69), layout (#68), output discharge,
  soft start or a current limit (#63), and it adds no SG13G2-branch change.
- **Related**: [`DR-0002`](DR-0002-sg13cmos5l-device-topology.md) (HV-only
  device flavor and the `VGS <= 3.3 V` rating this record is graded against),
  [`DR-0003`](DR-0003-sg13cmos5l-mpass-resize-and-compensation.md),
  [`DR-0007`](DR-0007-target-spec-row-ratification.md) (row ratification;
  row 9 Open). Evidence: `sim/ldo-cmos5l-enable/` (record
  `20261010-023648-4d45f5d`).

## Decision

1. **Port.** `EN`, active high, appended after `IBIAS`:
   `VIN VOUT VSS VREF IBIAS EN`. `EN = VIN` regulates; `EN` low holds the
   pass device off. The SG13G2 core keeps its four-port invariant.
2. **Topology** (two `sg13_hv_pmos`, `l = 0.5 u`, source and body at `VIN`,
   gate at `EN`, so both are **off** when `EN = VIN` and **on** when `EN` is
   low):

   | Device | `w` | Drain | Job |
   |---|---|---|---|
   | `Men` | 40 u | `EAOUT` | Pulls the pass gate to `VIN`: `Vsg(Mpass) ~ 0`, whatever the amplifier drives. |
   | `Mbdis` | 5 u | `IBIAS` | Pulls the amplifier's bias-mirror node to `VIN`, turning off the tail and second-stage load PMOS so the amplifier stops conducting and cannot fight `Men`. |

   The pass device is **not** held off by disabling the amplifier alone.
   With `VOUT = 0` the loop drives `EAOUT` *low* (FB below VREF), so a quiet
   amplifier is the wrong state to rely on; `Men` is what holds `Mpass` off.
   An intermediate build with `Men` alone worked for the pass device but
   left the amplifier output stage pulling `Men` (about 1.1 mA of supply
   current while disabled in that run, discarded and not committed); `Mbdis`
   removes that fight. `Mbdis` is **supporting**, not what makes the pass
   device safe.
3. **No output discharge, no soft start.** With `EN` low `VOUT` decays only
   through the feedback divider and the load.

## Valid levels, bias handling, stress

- **EN levels.** `EN` is a `VIN`-domain signal. It must swing rail to rail
  (`EN` close to `0` for off, close to `VIN` for on). A 1.2 V digital `EN`
  does **not** turn `Men`/`Mbdis` off at `VIN = 3.3 V` and needs a level
  shifter that this record does not add. The transition region is **not
  characterized**: in a DC sweep at `VIN = 3.30 V` (Rload 1.8 k) the loop was
  off for `EN` up to 2.4 V, regulating at 2.5 V, off again at 2.6 V and
  regulating from 2.7 V up (a DC-solver / bistability artifact, not a
  threshold). No hysteresis, threshold or EN-edge behaviour is claimed.
- **Bias handling.** The external `IBIAS` sink keeps being serviced while
  disabled: `Mbdis` conducts the sink's current (2 uA in the benches) from
  `VIN`, so the `IBIAS` node sits at about `VIN` when disabled. The source
  feeding `IBIAS` must tolerate that compliance (an ideal current sink does).
  `VREF` is untouched.
- **Device stress.** `Vsg(Men) = Vsg(Mbdis) = VIN - EN`, up to `VIN`. At the
  Input-row top of 3.63 V with `EN = 0` that is **3.63 V, above the 3.3 V
  `VGS` rating** (`DR-0002` ratings table, `LG >= 0.5 u`). So the *rated*
  EN-low level is `EN >= VIN - 3.3 V` (>= 0.33 V at `VIN = 3.63 V`); `EN`
  at hard 0 V at 3.63 V is an over-rating condition, recorded here rather
  than hidden. The same 3.63 V `Vsg` applies to the existing amplifier and
  pass devices at the top of the Input row; this record does not fix it.
  `Mpass` itself is benign when disabled: `Vsg` is 8-14 mV and
  `Vsd = VIN - VOUT <= 3.63 V`.
- **Enable-on stress.** With `EN = VIN` the two devices see `Vgs = 0`. Their
  drains sit on `EAOUT` and `IBIAS`, both at normal operating levels.

## Off-state measurement conditions (defined before simulating)

No shutdown-current or leakage **target** exists and none is invented.
Measurements are defined as follows, at tt / 27 C unless stated:

- **Pass leakage.** `EN = 0`, `VOUT` clamped to 0 V by a 0 V source
  (worst-case `Vds(Mpass) = VIN`), `VIN` in {2.97, 3.30, 3.63} V, `IBIAS`
  2 uA sink, `VREF` 0.90 V. Leakage is the current into the clamp. Here
  `Rtop` carries no current (`VOUT = 0`).
- **Disabled supply current.** Same conditions with `VOUT` floating (no
  load) and with a 1.8 k load; reported as the `VIN` source current. It
  includes the 2 uA bias sink and a floating-node contribution (below), so it
  is a measurement, not a spec.
- **Discharge.** Not measured: no discharge feature exists.

## Results (tt, 27 C, schematic-level, single corner)

All numbers are from `sim/ldo-cmos5l-enable/records/20261010-023648-4d45f5d/`
(`summary.csv`, `derived.txt`), run on the 2AM batch fleet (ngspice 46).
They are a smoke check at **one** process/temperature corner. They are **not**
a PVT sweep and do not supersede `sim/ldo-cmos5l-pvt-sweep` records.

| Quantity (EN = 0) | 2.97 V | 3.30 V | 3.63 V |
|---|---|---|---|
| Pass leakage, `VOUT` = 0 V clamp | 0.32 nA | 0.63 nA | 1.24 nA |
| `Vsg(Mpass)` | 8.4 mV | 10.7 mV | 13.7 mV |
| `EAOUT` (= `VIN` - `Vsg`) | 2.9616 V | 3.2893 V | 3.6163 V |
| Supply current, `VOUT` floating | 53.7 uA | 73.2 uA | 99.6 uA |
| `VOUT`, floating (leakage into divider) | 0.20 mV | 0.39 mV | 0.78 mV |

- **Disabled supply current is not clean.** Of the 73 uA at 3.30 V only
  about 2 uA is the bias sink. The rest is conduction in the amplifier output
  NMOS `Mn3`, whose gate (`G1`) floats at DC once the bias is cut; `Men`
  sinks it (hence the 10-14 mV `Vsd`). That current depends on a floating
  node's DC solution, so treat it as an indicative value, not a
  characterized shutdown current. Removing it needs a pull-down inside
  `ldo_erramp_cmos5l`, which this change deliberately does not touch.
- **Off-state is robust to that.** The pass device stays off even when the
  output stage fights `Men` hard (the discarded `Men`-only run held
  `Vsg(Mpass)` to about 0.17 V and gave `VOUT` = 13 uV into 1.8 k).
- **EN high restores regulation, identical to before.** Against the pre-#67
  netlist (kept as `sim/ldo-cmos5l-enable/baseline/`, sha256
  `c6e630e9...f11041`), same fleet/ngspice/model files:
  - DC (Vin 2.97/3.30/3.63 V x 0 / 50 mA): `VOUT`, `EAOUT`, `FB`, `Vsg(Mpass)`
    differ by at most 1e-10 V; supply current by at most 3.1e-13 A.
    `VOUT` at 3.30 V: 1.800306 V no load, 1.800145 V at 50 mA (both designs).
  - PSRR (1 mA, 1 uF): 75.6317 / 55.7529 / 34.2420 dB at 10 Hz / 1 kHz /
    100 kHz (baseline) vs 75.6317 / 55.7529 / 34.2413 dB (EN design): at
    most 0.0007 dB, at 100 kHz.
  - Loop gain: dc gain 123.796 dB both; unity-gain frequency 84956.2 Hz vs
    84955.9 Hz; phase margin 74.653 vs 74.647 deg (-0.006 deg).
  - **Caveat on the AC numbers.** The fleet runner image has no `cap_cmomi`
    model, so the AC decks replace `Cc` with a **linear 5.47 pF capacitor**
    in *both* designs. The delta is like-for-like; the absolute phase margin
    and unity-gain frequency are **not** comparable to the
    `sim/ldo-cmos5l-pvt-sweep` records. Gain margin was not extracted.
  - No regression was found at this single corner; this is not a statement
    about the 45-point grid.

## What this does not claim

- **Evidence is schematic-only.** No layout, DRC, LVS or extraction exists
  for the EN-bearing design (#68). The committed DRC/LVS/ERC reports under
  `layout/` remain historical evidence for their **old** hashes; this record
  makes no current-design claim from them and cites no fresh signoff.
- The characterization report and the item-5 coverage inventory pin the old
  netlist hashes. They are now **stale against the design** and say so; a
  new full-grid record on the EN design is separate work.
- No startup, soft-start, current-limit or discharge claim, and no
  shutdown-current target. Rows are unchanged (row 4 ratified, the other
  nine Open, row 9 Open).
- Single corner only. Process, temperature and resistor corners of the EN
  states are **not** run (the host policy sends grids to the batch fleet; this
  change ran only the smoke points above).
- The Monte Carlo bench `sim/ldo-cmos5l-monte-carlo/tb_row2_accuracy.spice`
  instantiates the five-port core and is **not** migrated (its committed
  record and DR-0007 cite the old netlist bytes); it will not elaborate
  against the new netlist until that is done deliberately.

## Consequences

- `design/netlist.py`'s SG13CMOS5L port invariant is six wide. The three
  `ldo-cmos5l-pvt-sweep` templates tie `EN` to `VIN`; the loop-gain template's
  flattened copy carries `XMen` and `XMbdis`, and `run_sweep.sh`
  (`assert_loopgain_topology_sync`) now compares **both** the generated
  netlist and the template copy against an expected body that includes them,
  keeps the single `FB -> FBAMP` break, and ships `--check-topology-guard`
  negative controls for an omitted or miswired enable device.
- Historical records under `sim/` are unchanged.

## Addendum: enabled-state 45-point grid (PR #87 review follow-up)

The Judge's review of PR #87 asked for the stale characterization evidence to
be replaced inside the PR. The sections above are left as written. This
addendum supersedes two of their bullets: "stale against the design" and
"single corner only", but only for the enabled state.

- **Record.** `sim/ldo-cmos5l-pvt-sweep/records/20261010-025634-60a3e81`
  covers the full process x temperature x resistor grid on the EN design
  (core sha256 `7953b25b...222cc1`), with `EN` tied to `VIN`: 214/214
  points, run with `run_sweep.sh --batch` on the EDA batch fleet. Unlike the
  smoke decks above, the AC benches use the real `cap_cmomi` model. Its OSDI
  binary is staged with each job, so the absolute phase margin and
  unity-gain frequency are comparable with the earlier pvt-sweep records.
- **No regression.** Against the pre-EN record `20260917-023832-7061e8f`,
  same point by point, the largest changes are: phase margin -0.015 deg,
  gain margin -0.023 dB, PSRR at most -0.001 dB, Iq -0.43 nA and no-load
  VOUT -0.46 uV. Dropout, line regulation and load regulation are unchanged.
  The binding corners have not moved.
- **Re-selected evidence.** The item-8 characterization report and the
  item-5 coverage inventory now cite this record and are current against
  the design again. This is a statement about artifact freshness, not spec
  compliance. Row 4 is still the only ratified row, and row 9 stays Open.
- **Still not claimed.** The disabled state is covered only at the single
  smoke corner above. There is still no layout, DRC, LVS or extraction for
  the EN-bearing design (#68), and the item 3/4/11 citations stay historical
  for the old GDS. The Monte Carlo bench migration is #88, and the floating
  `Mn3` gate behind the disabled supply current is #89.

## Addendum: Monte Carlo bench migration (#88)

This addendum supersedes the "What this does not claim" bullet on the Monte
Carlo bench. It covers the bench migration only.

- **Versioned, not edited.** `sim/ldo-cmos5l-monte-carlo/tb_row2_accuracy.spice`
  keeps its bytes (sha256 `b994dbb0…dbd45`) as the historical five-port deck
  of record `20261009-003009-3ee8306`. The new file `tb_row2_accuracy_en.spice`
  ties `EN` to `VIN` (`Xtop VIN VOUT 0 VREF IBIAS VIN ldo_core_cmos5l`), the
  same tie the pvt-sweep templates use, and all live `request-row2-*.json`
  select it. `run_campaign.sh check` never hashes the deck, so an in-place
  edit would have passed CI while making that record's provenance statement
  false. `test_deck_versioning.py` now guards the split in CI.
- **Smoke only.** One batch-fleet unit (tt_nom, 27 °C, MC off, job
  `klt-sim-ec04a78c8228`) elaborates and completes at 1.800306041 V, the same
  value the historical probe gives at that point. That solve needed dynamic
  gmin stepping, which the historical probe did not. See
  `sim/ldo-cmos5l-monte-carlo/evidence/20261010-193208-028a3f8-en-smoke/`.
- **No row-2 claim changes.** Row 2 stays Open. Its Monte Carlo evidence is
  still the pre-EN record until a new campaign record exists on the EN design.

## Addendum: G1 disable pull-down inside the error amplifier (#89)

This addendum supersedes the "Disabled supply current is not clean" bullet
of the Results section and the disabled-state half of the PR #87 addendum's
"Still not claimed" bullet. The sections above are left as written. **No
target-spec row is ratified, relaxed or added: there is still no
shutdown-current row, and the numbers below are measurements, not targets.**

### Problem

With `EN` low, `Mbdis` cuts the bias, so `Mtail` carries no current and
nothing defines the amplifier's first-stage output `G1` at DC. `G1` is the
gate of the second-stage NMOS `Mn3`. Its value came from the DC solution of a
floating node, so `Mn3` conducted from `EAOUT` into `VSS` by an amount the
solver chose, and `Men` supplied it: 53.7 / 73.2 / 99.6 uA at 2.97 / 3.30 /
3.63 V (tt, 27 C, DC smoke record `20261010-023648-4d45f5d`). The same
quantity in the transient startup bench of record `20261010-104827-91e92aa`
(end of the 1 ms off state, before the `EN` edge) was 2.00 uA to 358 uA
across the 135 points, and 2.61 uA at tt / 27 C / 3.30 V. The two benches
disagree at the same corner, which is what a floating node does.

### Decision

**Option 1 of #89: a new `EN` pin on `ldo_erramp_cmos5l` with a local
inverter driving a small NMOS pull-down on `G1`.**

- Port list: `INP INN OUT VDD VSS IBIAS EN` (`EN` appended last, so the first
  six pins keep their positions). The core connects its own `EN` port to it:
  `Xamp FB VREF EAOUT VIN VSS IBIAS EN ldo_erramp_cmos5l`. The core's six-port
  interface is unchanged.
- Topology, all three devices inside the amplifier:

  | Device | Type | `w` / `l` | D | G | S / B | Job |
  |---|---|---|---|---|---|---|
  | `Minvp` | `sg13_hv_pmos` | 1 u / 1 u | `ENB` | `EN` | `VDD` | inverter pull-up |
  | `Minvn` | `sg13_hv_nmos` | 1 u / 1 u | `ENB` | `EN` | `VSS` | inverter pull-down |
  | `Mpd` | `sg13_hv_nmos` | 1 u / 1 u | `G1` | `ENB` | `VSS` | holds `G1` at `VSS` when `EN` is low |

- **Sizing.** With `EN` low the tail is off, so `Mpd` only has to sink
  leakage into `G1`; the smallest regular device is enough. `l = 1 u` keeps
  the amplifier's own "L >= 1 um on every device" rule and gives a lower
  off-state leakage on `G1` (enabled state) than the `l = 0.5 u` the core's
  enable devices use. The inverter drives one gate, so it is minimum size
  too. No device is sized for speed: the `EN` edge behaviour stays
  uncharacterized (DR-0008, #62).
- **Enabled state.** `EN = VIN` gives `ENB = VSS`: `Mpd` sits at `Vgs = 0`
  and adds only its drain junction and overlap capacitance (fF, against the
  ~5.5 pF Miller `Cc` on the same node) and its off-state leakage to `G1`.
  The inverter draws only leakage (`Minvn` on, `Minvp` off).
- **Stress.** `EN` is still a `VIN`-domain, rail-to-rail signal. `Vsg(Minvp)`
  with `EN = 0`, `Vgs(Minvn)` with `EN = VIN`, and `Vgs(Mpd)` (= `ENB` = `VIN`)
  with `EN = 0` all reach `VIN`, i.e. 3.63 V at the top of the Input row,
  over the 3.3 V `VGS` rating. That is the same condition this record
  already states for `Men`/`Mbdis`; it is recorded, not fixed here.

### Options not taken

- **Option 2 (`ENB` port, inverter in `ldo_core_cmos5l`).** Same device
  count and the same pull-down, but it splits one function across two
  cells: the amplifier's disabled state would depend on a complement that
  every other instantiation (an amplifier-only bench, or any later reuse)
  has to generate correctly. It also puts two more devices in the core
  body, which the loop-gain bench's hand-flattened core copy, its topology
  guard (`run_sweep.sh`) and the layout's core-level floorplan would all
  have to mirror. With option 1 the only core-level change is one pin on
  `Xamp`, so the flattened copies change by one token.
- **Option 3 (series switch in `Mn3`'s source).** Rejected on analysis, not
  measured. A switch in the second stage's source degenerates `Mn3`
  (lower `gm3`, so lower second-stage gain, loop gain and PSRR) and costs
  `Vds` headroom on the node that must pull `EAOUT` low enough to drive
  `Mpass` at full load and dropout. It also does not define `G1`: it removes
  the current path but leaves the node floating.
- **Gating a pull-down from `IBIAS`.** Not used and not measured. When
  enabled `IBIAS` sits one `Vsg(Mb0)` below `VIN`, i.e. about 2 V above
  `VSS`, well above an NMOS threshold, so an `IBIAS`-gated NMOS would conduct
  in the enabled state.

### Results: disabled state (`EN = 0`)

DC smoke record `sim/ldo-cmos5l-enable/records/20261011-031743-df3f802/`
(batch fleet, ngspice 46, tt / 27 C, `IBIAS` 2 uA sink, `VREF` 0.90 V,
`VOUT` floating unless stated). Same decks and conditions as the
`20261010-023648-4d45f5d` figures in the Results section above, so each row
is a like-for-like replacement:

| Quantity (EN = 0, tt / 27 C) | 2.97 V | 3.30 V | 3.63 V |
|---|---|---|---|
| Supply current, `VOUT` floating (was 53.7 / 73.2 / 99.6 uA) | 2.0003 uA | 2.0006 uA | 2.0012 uA |
| Supply current, 1.8 k load | 2.0003 uA | 2.0006 uA | 2.0012 uA |
| `V(G1)` = `Vgs(Mn3)` | 3.2 nV | 7.0 nV | 14.3 nV |
| `V(ENB)` | 2.97 V | 3.30 V | 3.63 V |
| `EAOUT` | 2.97 V | 3.30 V | 3.63 V |
| `Vsg(Mpass)` (was 8.4 / 10.7 / 13.7 mV) | 31 pV | 33 pV | 35 pV |
| `VOUT`, floating (was 0.20 / 0.39 / 0.78 mV) | 0.19 mV | 0.38 mV | 0.77 mV |
| Pass leakage, `VOUT` = 0 V clamp (was 0.32 / 0.63 / 1.24 nA) | 0.30 nA | 0.61 nA | 1.23 nA |

- `G1` now has a DC path to `VSS` through `Mpd`, and `Mn3` is off: its gate
  sits within 15 nV of its source. Of the ~2.0006 uA at 3.30 V, 2 uA is the
  external bias sink serviced through `Mbdis`; the remainder (0.3 to 1.2 nA
  across the three supplies) is leakage. `Men` no longer sinks anything, so
  `Vsg(Mpass)` drops from about 11 mV to picovolts.
- **Across PVT** (not a new simulation; read from the committed traces of
  the new startup record `20261011-031426-df3f802`, `EN = 0`, 1.8 k load,
  1 uF, at t = 1 ms just before the `EN` edge, with
  `python3 sim/ldo-cmos5l-pvt-sweep/startup_offstate.py <run id>`): 2.000 uA
  to 2.264 uA over all 135 process x temperature x resistor x Vin points
  (median 2.0012 uA; maximum at ff / 125 C / 3.63 V). The same read-out of
  the previous record gives 2.000 uA to 358 uA (median 32.3 uA).
- That record's own `off_supply_current_a` column is not an off-state value:
  `startup_eval.py` samples it at the last point before the `EN = VIN/2`
  crossing, which lies inside the 1 us edge. For this design it therefore
  includes the inverter's crowbar current during the edge (6.0 to 28.3 uA in
  the column). The evaluator and the column are left unchanged (pinned
  methodology); the fix is #130.
- The `EN` sweep at `VIN = 3.30 V` (1.8 k, DC) is still not a characterized
  threshold. It now regulates from `EN = 2.5 V` up with no off-again point,
  and with `EN` between about 1.0 and 2.4 V the supply current includes the
  inverter's through-current (13 uA at 1.0 V, 78 uA at 2.0 V). No threshold,
  hysteresis or edge behaviour is claimed.

### Results: enabled state

Record `sim/ldo-cmos5l-pvt-sweep/records/20261011-051956-eda9285` (full
process x temperature x resistor grid plus the Cc and resistor sensitivity
points, `EN` tied to `VIN`, 214/214 points, completeness OK,
`run_sweep.sh --batch` on the EDA batch fleet, real `cap_cmomi` model).
Its delta table (`.delta.csv`, 540 rows, and per-metric tables in the record
`.md`) compares every one of the 45 points against record
`20261010-025634-60a3e81` (the #67 record), same point on both sides.
Extremes over the 45 points, per metric that record reports:

| Metric (direction that is worse) | Worst case, #67 -> #89 (point) | Per-point delta range | Points worse / better / equal |
|---|---|---|---|
| Phase margin (lower) | 53.8710 -> 53.8708 deg (ss/125C/res_bcs) | -0.0021 .. -0.0002 deg | 45 / 0 / 0 |
| Gain margin (lower) | 13.8526 -> 13.8449 dB (ff/-40C/res_wcs) | -0.0086 .. -0.0060 dB | 45 / 0 / 0 |
| Unity-gain frequency | 39111.28 -> 39111.29 Hz (min); 172879.7 -> 172887.7 Hz (max) | +0.009 .. +8.0 Hz | n/a |
| DC loop gain (lower) | 121.41929 -> 121.41927 dB (ff/125C/res_bcs) | -2.0e-5 .. +1.2e-5 dB | 19 / 1 / 25 |
| PSRR @ 1 kHz (lower) | 53.642887 -> 53.642879 dB (ss/125C/res_wcs) | -1.1e-5 .. +7.1e-5 dB | 44 / 1 / 0 |
| PSRR @ 100 kHz (lower) | 33.23419 -> 33.23409 dB (ff/27C/res_bcs) | -1.6e-4 .. -4.8e-5 dB | 45 / 0 / 0 |
| Iq, no load (higher) | 24.722161 -> 24.722172 uA (ss/125C/res_bcs) | 0 .. +0.043 nA | 33 / 0 / 12 |
| Dropout @ 50 mA (higher) | 0.24 -> 0.24 V (ss/125C/res_wcs) | 0 | 0 / 0 / 45 |
| Line regulation (higher) | 0.2457576 -> 0.2457727 mV/V (ff/125C/res_wcs) | -1.5e-5 .. +1.5e-5 mV/V | 3 / 8 / 34 |
| Load regulation (higher) | 0.02537509 -> 0.02537566 % (ff/125C/res_wcs) | -5.6e-7 .. +5.7e-7 % | 13 / 4 / 28 |
| VOUT, no load (further from 1.8 V) | 1.80065464 -> 1.80065381 V (ff/125C/res_wcs) | -0.84 uV .. 0 | 0 / 15 / 30 |
| Divider standing current | 4.8168367 -> 4.8168344 uA (max) | -2.2e-6 uA .. 0 | n/a |

- **This is not a zero delta, and it is not reported as one.** Phase margin,
  gain margin and PSRR @ 100 kHz are lower at every point, and no-load Iq is
  higher or unchanged at every point. That is the expected direction for a
  device added to `G1` (its drain capacitance and leakage) and an inverter on
  the supply (its leakage). The largest adverse move on each row is -0.0021
  deg of PM, -0.0086 dB of GM, -1.6e-4 dB of PSRR @ 100 kHz, -1.1e-5 dB of
  PSRR @ 1 kHz and +0.043 nA of Iq. Each is more than two orders of magnitude
  below that row's worst-case margin to its target (PM 8.87 deg, GM 3.84 dB,
  PSRR 3.64 / 13.23 dB, Iq 5.28 uA). The closest is gain margin, where the
  shift is 0.22 % of the margin.
- **What "no regression" means here.** #89 asks for no regression on every
  metric the record reports. This addendum reads that the way the PR #87
  addendum above did. There, phase margin -0.015 deg and gain margin
  -0.023 dB against `7061e8f` were called "no regression" because no
  verdict, pass count or binding corner moved. It does not mean a zero
  delta. The deltas here are smaller than the #87 ones (PM about 7x, GM
  about 3x), and the same invariants hold, as the next bullet lists. The
  adverse direction is still reported as adverse, as above.
- **What does not change.** These are two separate readings, and neither
  changes.
  - *The record's own spec comparison* (the legacy single-crossing scalars
    in `20261011-051956-eda9285.md`): all 45 points meet every row there,
    as before. That includes PM >= 45 deg and GM >= 10 dB read from the first
    crossing.
  - *The characterization report under DR-0014 (proposed)*: row 10 is not a
    pass. Phase margin and gain margin are each **0/45 pass, 0 fail,
    45 ambiguous**. Every point has the reason `ceiling_unbounded`, because
    no trace bounds the 100 MHz sweep ceiling. That is the same result as for
    `20261010-025634-60a3e81`, from
    `sim/ldo-cmos5l-pvt-sweep/evidence/20261011-051956-eda9285/row10-margins.*`
    (written by `row10_record.py`, which runs `row10_margins.py`'s unchanged
    classifier on this record).
  - The same 15 points have more than one 0 dB crossing. Under DR-0014 they
    classify exactly as before, with the same per-point verdicts and reasons.
  - Each row's worst case is at the same (corner, temperature, resistor)
    point.
  - The `Cc` tolerance window is unchanged at `110e-6`..`259e-6`
    (x0.65..x1.52), and dropout is identical at every point.
  - In the characterization report, no row's verdict, coverage or freshness
    state changes. Row 10 stays `ambiguous`, and DR-0007 keeps it Open.

  The full-load Iq worst case moves by one 1e-10 A
  quantization step (24.8873 -> 24.8874 uA), and the 2.97 V load-regulation
  worst case improves slightly (0.0228482 -> 0.0228476 %).
- **Smoke cross-check** (tt / 27 C, linear 5.47 pF `Cc` stand-in, against the
  pre-#67 baseline, record `20261011-031743-df3f802`): phase margin -0.0067
  deg (was -0.0062 deg for the #67 design alone), PSRR @ 100 kHz -8.1e-4 dB
  (was -6.9e-4 dB), DC operating point within 1 nV / 0.21 pA.
- **Provenance note.** The first submission of this grid lost its client after
  21 of its 22 fleet requests had completed: one request never returned, and
  the submitting process was stopped at its wall-clock limit. No record was
  written. The grid was then re-run in full through `run_sweep.sh --batch`.
  Four requests whose decks were byte-identical to completed requests of the
  first run (the main-grid DC and loop-gain groups, the `res_bcs`
  resistor-sensitivity group and the divider-attribution group) reuse those fleet reports through the new
  `SWEEP_BATCH_REUSE_WORK` / `batch_backend.py --reuse-work` option, listed
  in `corners/20261011-051956-eda9285/_batch/reused-reports.tsv`. The other
  18 were submitted afresh. Nothing ran on the dispatch host.

### Startup campaign

The startup bench drives `EN` low for the first millisecond, so the pull-down
changes what it measures and the previous startup record is stale against the
new netlist. It was re-run in full on the batch fleet (`startup_campaign.py`
grid stage, 135 points in 15 jobs): record `20261011-031426-df3f802`, 135/135
evaluated. The verdicts are unchanged in kind. All 135 points fail on
overshoot and the 1 mV monotonicity check, as before, because there is still
no soft start (start peak 1.858 to 2.339 V, was 1.868 to 2.339 V). Every
start still settles inside the band within 3 ms (28 to 441 us). Row 9 stays
Open, and the methodology is still DR-0009's proposal.

### Layout

The layout is regenerated with the three devices drawn (`layout/README.md`):
`Minvp` in the enable NWell (body `VIN`), `Minvn` and `Mpd` beside it with a
second substrate tie bar, and a new `ENB` track. Both DRC decks are clean,
LVS matches with 17 compared devices (the MoM cap is compared by name, as
before), all six LVS negative controls mismatch (new: `Mpd` deleted from the
reference), and the ERC supply check is clean with three checked ties. This
is schematic-equals-layout evidence only. There is no extraction-based
(post-layout) performance claim.

### What this does not claim

- No shutdown-current or leakage target. The disabled supply current is a
  measurement at the stated conditions.
- The disabled state is measured at tt / 27 C in DC, and across PVT only as
  the off-state sample of the startup bench (1.8 k load). No disabled-state
  DC sweep across PVT and no `EN`-edge characterization was run.
- Monte Carlo row-2 evidence is unchanged and still pre-EN (#88).
  `tb_row2_accuracy_en.spice` instantiates only the core, whose ports did
  not change, so it needed no edit. It was not re-run, and no new Monte
  Carlo campaign exists on this design.
- Layout parasitics: none. The layout evidence is DRC/LVS/ERC only.
