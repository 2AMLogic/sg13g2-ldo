# ldo-cmos5l-pvt-sweep

Per `CLAUDE.md`: **verification is the product, no claim without a
testbench**, PVT corners on every recorded result, and results here are
**append-only evidence** -- a re-run mints a new, timestamped record; nothing
under `records/`, `netlist-snapshots/` or `corners/` is ever edited or
deleted after it lands. This follows the same per-experiment shape
`sim/README.md` establishes and `sim/pass-device-screening/` already uses on
the SG13G2 branch.

## What this is

The **first circuit-level (closed-loop) PVT verification** in this repo, on
either PDK branch. `sim/pass-device-screening/` characterizes `sg13_hv_pmos`
as a bare device; this experiment instantiates the actual
`design/sg13cmos5l/ldo_core_cmos5l.sch` netlist (issue #20: pass device +
real two-stage Miller-compensated OTA error amp) and verifies it against a
spec table re-derived at SG13CMOS5L's rails -- phase 3/4 of the SG13CMOS5L
port tracked by #12 (issue #21).

**This block sits entirely on the Challenge #6 brief's 3.3V analog rail**
(`design/README.md` "Rails and the Challenge #6 slot budget" -- every
device is an HV, 3.3V-class flavour; there is no 1.2V node anywhere in this
hierarchy), so "re-derived at this PDK's 1.2V/3.3V rails" reduces to
re-deriving the SG13G2-branch DRAFT table (`README.md`) at the same 3.3V
input / 1.8V output pair, on this PDK's own devices -- not a rail
translation.

## Benches

Three testbenches, generated from templates by `run_sweep.sh`:

1. **`testbench/tb_dcsweep_cmos5l.spice.tmpl`** -- closed-loop, whole
   `ldo_core_cmos5l` instantiated directly (no flattening). A single nested
   DC sweep (`Vin` 2.00V-3.63V step 10mV, fast/inner axis; `Iload`
   0/12.5m/25m/37.5m/50m A, 5 evenly-spaced points, slow/outer axis) gives:
   - **Iq**: `|i(vin)|` at the `Iload=0` block, `Vin=3.30V` row.
   - **Dropout @ 50mA**: scan the `Iload=0.05A` block from `Vin=3.63V`
     downward for the first point where `VOUT` falls below 99% of the
     1.8V target; `dropout = that Vin - 1.8V`. If regulation is never lost
     across the whole swept range, dropout is reported as
     `> 1.63V` (worse than the sweep's own floor, `dropout_v_50ma_floor`
     in the CSV) rather than fabricated.
   - **Line regulation**: `Iload=0` block, slope of `VOUT` vs `Vin` over
     the Input row's own `{2.97V, 3.63V}` window -- measured at no load,
     not the light-nonzero-load point an earlier draft of this bench
     planned (see the template header for why: Iq itself is only ~17uA and
     does not meaningfully load the divider/pass device differently).
   - **Load regulation**: `Vin=3.63V` (best-case headroom) rows across all
     five `Iload` points -- see "Why Vin=3.63V for load regulation" below.
2. **`testbench/tb_loopgain_cmos5l.spice.tmpl`** -- loop broken at `FB`
   (the feedback-divider node driving the amp's `INP` pin, a MOSFET gate)
   for an AC phase/gain-margin sweep. See "Loop-gain measurement method"
   below for the full derivation of why a plain series voltage-source break
   is valid here (no inductor/capacitor blocking network needed).
3. **`testbench/tb_psrr_cmos5l.spice.tmpl`** -- closed-loop, whole
   `ldo_core_cmos5l`, 1V AC stimulus on `Vin` (`Vref`'s AC component held
   at 0), `PSRR_dB(f) = -20*log10(|v(vout)/v(vin)|)`.

All three share: `VREF=0.90V` DC (the schematic's own illustrative bias,
`design/README.md` "Reference voltage" -- `Rtop=Rbot=300k` gives
`FB=VOUT/2`, so `0.90V` servos `VOUT` to `1.80V`), `IBIAS` externally sunk
at `2uA` (the bias point `design/README.md`'s "Judgement calls" section 1
assumes: tail=2x, second stage=4x that reference), `Cout=1uF` (a first-cut
point inside the DRAFT table's `0.33-4.7uF` output-cap window, `ESR=0`).

## Loop-gain measurement method

Breaking a feedback loop for a SPICE AC loop-gain measurement normally
needs an L/C blocking network (a large inductor across the break to
preserve the DC operating point, a large capacitor in series with the AC
injection source to avoid disturbing it) -- **not needed here**, because the
break point (`FB` -> the amp's `INP` pin) sits at a MOSFET gate: zero DC or
AC current flows across it, both before and after the break.

Insert an ideal series source `Vbreak` (`0V` DC, `AC=1`) between `FB` (the
real feedback-divider node, resistively determined by `VOUT`) and `FBAMP`
(the node that actually drives the amp's `INP` pin). Because:

- `FBAMP` carries zero current (its only two connections are `Vbreak` and
  a MOSFET gate), the current through `Vbreak`'s branch is zero at both
  ends, so `FB`'s value is unaffected by the break -- `FB = beta * VOUT(s)`
  exactly as in the unbroken circuit (`beta` = the divider ratio); and
- `VOUT(s) = G(s) * FBAMP(s)` for some forward transfer function `G(s)`
  encompassing the whole amp + pass-device path (`VREF`'s AC component is
  held at 0, so it does not contribute),

algebra gives `FB(s) = T(s) * FBAMP(s)` for the identical loop-gain
transfer function `T(s) = beta * G(s)` an unbroken loop would have --
independent of the injection detail. `T(s)` is therefore read directly off
one AC analysis as the ratio of two node voltages:

```
Loop Gain L(s) = -v(fb)/v(fbamp)
```

(sign flipped from the raw `T(s)` so a healthy negative-feedback loop shows
a large **positive** real `L(0)`, phase near 0 degrees at DC, rolling
toward -180 degrees at the unity-gain crossover -- the standard Bode-plot
convention `phase margin = 180 + phase(L)` at the frequency where `|L|=1`
(0dB) is stated against). Verified against a fully independent circuit
simulator run before committing to this method: the closed-loop DC
operating point (`tb_dcsweep_cmos5l`) and the flattened, loop-broken DC
operating point agree to 5 significant figures (`VOUT=1.800208V` both ways
at `tt/27C`, no load), confirming the break does not perturb the bias
point.

`XMpass`/`Rtop`/`Rbot`/`Xamp`'s instantiation lines in
`tb_loopgain_cmos5l.spice.tmpl` are a byte-for-byte mirror of
`ldo_core_cmos5l`'s subckt body in the generated design netlist (`FB` ->
`FBAMP` on `Xamp`'s first pin, plus the inserted `Vbreak`, excepted).
`run_sweep.sh`'s `assert_loopgain_topology_sync()` diffs the two every run
and aborts loudly if a future schematic edit changes that connectivity, so
this bench cannot silently go stale.

## Why Vin=3.63V for load regulation

The schematic's provisional `Mpass` sizing (`w=300u l=0.5u`,
`design/README.md`: "a DC-sanity first cut ... not sized against any
dropout ... target") does **not** hold regulation at 50mA at every `Vin` in
this sweep -- see "Results" below. `Vin=3.63V` (the best-case, max-headroom
supply point) is the *only* point in the grid where the design stays in or
near regulation across the full load range at most corners, so it is the
cleanest available load-regulation measurement; it is not the nominal
3.30V supply datasheets conventionally use, and that departure is
deliberate, not an oversight.

## PDK pin, corner naming, and the resistor/cap corner axes

Pinned SG13CMOS5L revision: [`sim/pdk-cmos5l.json`](../pdk-cmos5l.json)
(commit `607e18d`, re-verified against the installed checkout, matching the
commit issue #21's body cited). `cornerMOShv.lib` at this pin is **byte-for-
byte identical** to `ihp-sg13g2`'s own copy (`diff` clean) -- confirming,
directly against the installed model library rather than by assumption,
that the five-corner naming scheme (`mos_tt`/`mos_ss`/`mos_ff`/`mos_sf`/
`mos_fs`) `spec/porting-plan.md` Sec 1.2 already bound for SG13G2 transfers
unchanged to SG13CMOS5L. This is expected, not coincidental:
`design/README.md` "Install shape is a dispatch hazard" already documents
that this PDK's HV device symbols and model cards are relative symlinks
into a sibling `ihp-sg13g2` checkout.

**`cornerRES.lib` and `cornerCAP.lib` do NOT share this five-corner scheme**
-- both use a three-point `{typ, bcs (best case), wcs (worst case)}` axis,
independent of the MOS process corner. This experiment holds the resistor
corner at `res_typ` and the cap corner at `cap_typ` across the entire main
15-point MOS-corner grid: **no established MOS-corner/R-corner correlation
convention exists yet in this repo** (an `ss`-process-correlates-with-
`res_wcs` mapping would need its own decision record this issue does not
own), so rather than invent one, `Rz`'s own real corner spread is
characterized *separately*, at nominal `tt/27C`, via the
`loopgain_rzsens_{bcs,typ,wcs}` sensitivity points (`records/*.sensitivity.csv`).
This is a first-cut judgement call, flagged as such -- a future phase that
needs a tighter stability bound should replace it with a real correlation
record.

## MoM-cap (Cc) sensitivity sweep

`cornerCAP.lib` at this pin maps **every** `cap_typ`/`cap_typ_mismatch`/
`cap_typ_stat`/`cap_bcs`/`cap_wcs`/`cap_wcs_mismatch` section to the exact
same nominal `cap_cmomi.lib` include (verified directly, not assumed --
see [`sim/pdk-cmos5l.json`](../pdk-cmos5l.json) `pdk_caveats_honoured`).
Per `cap_cmomi.lib`'s own header, this is because the model is **"NOT YET
VALIDATED ON ihp-sg13cmos5l SILICON"**: its coefficients are transferred
from the SG13G2 characterization by layer count, none measured on cmos5l
silicon. A *process-corner* sweep over `Cc` is therefore a no-op by
construction -- `design/README.md`'s own "PDK caveats honoured" table
already anticipated this and said the sweep this issue owes is a **value**
sensitivity sweep, not a corner sweep.

`run_sweep.sh` generates three frozen copies of the design netlist with
`Cc`'s width scaled `{0.5x, 1x (nominal, 30um), 2x}` (capacitance scales
~linearly with area for this device, `l` held fixed) and runs the loop-gain
bench against each, at `tt/27C`. Result (`records/*.sensitivity.csv`,
`sweep=cc_value`): phase margin moves from `0.35deg` (0.5x) to `0.19deg`
(2x) -- **the near-zero phase margin this experiment finds (see "Results")
is not an artifact of the uncharacterized `Cc` value**; it holds across the
full 4x width range tested. Every phase-margin/loop-gain number in
`records/*.csv` is still marked `insufficient-evidence` in the spec table
below per issue #21 acceptance criterion 4 (the *absolute* numbers are not
independently trustworthy pending real silicon characterization), but the
qualitative verdict (this compensation network has essentially no margin)
does not depend on that caveat.

## Results

Record cited throughout: [`records/20260916-083154-7aa1d3f.csv`](records/20260916-083154-7aa1d3f.csv)
(main 15-point PVT grid) and
[`records/20260916-083154-7aa1d3f.sensitivity.csv`](records/20260916-083154-7aa1d3f.sensitivity.csv)
(Cc-value / Rz-corner sensitivity) -- see
[`records/20260916-083154-7aa1d3f.md`](records/20260916-083154-7aa1d3f.md)
for the full run manifest (PDK/ngspice versions, corner matrix, links).
`51/51` simulation points passed (ngspice exit 0, no convergence/model-load
errors); completeness matrix OK.

**Headline finding: the schematic's provisional sizing (both `Mpass` and
the error-amp's `Cc`/`Rz` compensation network, both explicitly flagged as
DC-sanity first cuts, never sized against a target, in `design/README.md`)
does not hold up under closed-loop PVT verification.** This is the expected
outcome of a first verification pass on unratified sizing, not a surprise
finding, and it is recorded here in full per CLAUDE.md's rule that
verification results are never relaxed to pass.

### Spec table, re-derived at this PDK's 3.3V analog rail

Verdict legend: **PASS** (met at every corner in the 15-point grid),
**FAIL** (missed at one or more corners, worst-corner value cited),
**insufficient-evidence** (the PDK caveat this row's own value depends on
has not been resolved yet), **not implemented** (no such circuitry exists
in this schematic increment -- `design/README.md` "Non-goals" / "Known
gaps").

| Parameter | Target (`README.md` DRAFT, port-parity baseline) | Result (this record) | Verdict |
|---|---|---|---|
| Output accuracy | 1.8V +/-2% | 1.80022V-1.80040V no-load, all corners (regulator-only, `VREF` ideal -- port-parity caveat, `spec/porting-plan.md` Sec 1.2) | **PASS** |
| Dropout @ 50mA | < 300mV worst corner | 1.29V-1.83V at 11/15 corners; **never reaches regulation** within the swept `Vin` range (> 1.63V) at `tt/125C`, `ss/27C`, `ss/125C`, `fs/125C` | **FAIL** (every corner; ~4-6x over target even at the best corner) |
| Line regulation | < 5 mV/V | 0.151-0.200 mV/V, no load, all corners | **PASS** (no-load only -- see caveat below) |
| Load regulation | < 1% over full load | 0.021%-248% at `Vin=3.63V` (best-case headroom); 11/15 corners stay under 1% (0.02%-0.63%) with comfortable margin, but the same 4 corners that never reach dropout regulation (`tt/125C`, `ss/27C`, `ss/125C`, `fs/125C`) also fail here (25%-248%) | **FAIL** (4/15 corners; worst-corner value governs the row verdict) |
| Iq, no load | < 30uA | 16.94uA-16.99uA, all corners | **PASS** |
| Iq, full load | < 30uA | not cleanly separable from the load-regulation failure above (several corners never reach a stable 50mA operating point to measure quiescent draw against) | **insufficient-evidence** |
| PSRR @ 1kHz | > 50dB | 65.9dB-69.3dB, all corners | **PASS** |
| PSRR @ 100kHz | > 20dB | 35.8dB-40.6dB, all corners | **PASS** |
| Stability: phase margin | >= 45 deg worst corner | 0.19deg-0.35deg (Cc-value and Rz-corner sensitivity range included), all corners/points tested | **FAIL** (every corner; essentially zero margin) -- **insufficient-evidence** on the exact number (MoM-cap `Cc` caveat), but the FAIL verdict itself does not depend on that caveat (see "MoM-cap sensitivity sweep" above) |
| Stability: gain margin | >= 10dB worst corner | 4.0dB-5.4dB, all corners/points tested | **FAIL** (every corner) -- same insufficient-evidence caveat on the exact number as phase margin |
| Current limit | 65-80mA brickwall | n/a | **not implemented** (`design/README.md` "Known gaps": no current-limit circuit exists on this branch) |
| Startup | monotonic ramp, <2% within 3ms | n/a | **not implemented** (no soft-start circuit) |
| Enable/shutdown | -- | n/a | **not implemented** (no `EN` pin on this branch) |

**Line-regulation caveat**: measured at no load only (see "Benches" above
for why); the DRAFT target does not itself specify a load point for this
row, but a load-dependent line-regulation number cannot be produced
honestly given the load-regulation failure already documented -- this is
noted rather than silently omitted.

### Binding corners

- **Dropout**: worst among the corners that do reach regulation is
  `sf/125C` (1.83V dropout), `fs/27C` (1.82V) close behind; four corners
  never reach regulation at all within the swept range and are strictly
  worse.
  Slow-and-hot corners (matching `sim/pass-device-screening`'s own binding-
  corner finding for the bare `sg13_hv_pmos` device) dominate, as expected.
- **Load regulation**: `ss/125C` is catastrophic (248% -- `VOUT` collapses
  to `-2.67V` at `Vin=3.63V`/`Iload=50mA`, a real consequence of driving an
  ideal current-sink load harder than the pass device can supply at this
  corner, not a simulation artifact -- independently reproduced in a
  standalone `.op` run outside the sweep).
- **Stability**: phase margin is essentially flat (~0.19-0.35 degrees)
  across every corner and every Cc/Rz sensitivity point tested -- this is
  not a corner-dependent marginal case, it is a compensation network with
  no margin budget at any point tested.

## Why this is still a useful record, not a wasted run

Per `spec/porting-plan.md` Sec 1.3's own framing (gf180-ldo's compensation
work took ten decision records of negative results before the loop was
actually stable across PVT), a first verification pass finding real gaps in
unratified, explicitly-provisional sizing is the expected, useful outcome
-- it is the concrete input the next sizing pass needs (implied pass-device
widths from `sim/pass-device-screening`'s own dropout data already
independently predicted this: `sim/pass-device-screening/records/20260909-220347-ed18110.csv`'s
`w1u_l0.5u` rows imply `1135um-2169um` for `300mV`/`50mA`, 4-7x the
schematic's drawn `300um` -- this experiment's closed-loop dropout failure
is consistent with, and adds circuit-level confirmation of, that earlier
bare-device finding).

#25 tracks the resizing pass this evidence motivates (`Mpass` width, and the
`Cc`/`Rz` compensation network) -- see that issue for the next step; it is
out of scope for this verification-only phase.

## CI

**No CI job runs `run_sweep.sh --check-env` for this experiment yet**, unlike
`sim/pass-device-screening-check` (SG13G2 branch). `.github/workflows/ci.yml`
fetches `ihp-sg13g2` via `klayout-tools`' pinned `fetch-ihp-sg13g2.sh`; no
equivalent pinned fetch exists for `ihp-sg13cmos5l` in CI, because (per
`design/README.md` "Known gaps") it is a separate upstream repository
(`IHP-GmbH/ihp-sg13cmos5l`), not a variant directory inside the
IHP-Open-PDK tarball that script downloads -- already filed upstream as
`2AMLogic/klayout-tools#1929`. Until that lands, `--check-env` for this
experiment (like `--check` for the SG13CMOS5L schematic branch generally)
is a local/manual step, verified by this PR's author before submission
(see "Reproducing" below).

## Reproducing

```bash
export PDK_ROOT=/path/to/pdk/parent   # containing BOTH ihp-sg13g2/ and ihp-sg13cmos5l/
PDK=ihp-sg13cmos5l sim/tools/build-osdi.sh   # one-time OSDI build for this PDK
sim/ldo-cmos5l-pvt-sweep/run_sweep.sh
sim/ldo-cmos5l-pvt-sweep/run_sweep.sh --check-env   # syntax-check only, no records written
```

Requires `ngspice >= 46` (OSDI ABI v0.4, see `sim/README.md`) and both
`ihp-sg13g2`/`ihp-sg13cmos5l` installed under the same `PDK_ROOT`
(`design/README.md` "Install shape is a dispatch hazard").
