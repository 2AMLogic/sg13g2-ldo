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
