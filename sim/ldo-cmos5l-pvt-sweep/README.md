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
   - **Feedback-divider standing current** (since issue #31):
     `|i(vdivsense)|` at the `Iload=0` block, `Vin=3.30V` row, plus the
     per-leg resistance it implies. Read off a non-invasive replica of the
     divider -- an ideal unity-gain VCVS copy of `VOUT` driving a
     byte-identical pair of `rhigh` legs through a 0V ammeter -- because
     ngspice cannot report a branch current inside a subcircuit instance
     whose device is an OSDI `r3_cmc`. The replica draws nothing from
     `VOUT` and sits on a disjoint node set, so `Iq` and every other
     measured quantity stay directly comparable to the #21/#25 records.
2. **`testbench/tb_loopgain_cmos5l.spice.tmpl`** -- loop broken at `FB`
   (the feedback-divider node driving the amp's `INP` pin, a MOSFET gate)
   for an AC phase/gain-margin sweep. See "Loop-gain measurement method"
   below for the full derivation of why a plain series voltage-source break
   is valid here (no inductor/capacitor blocking network needed).
3. **`testbench/tb_psrr_cmos5l.spice.tmpl`** -- closed-loop, whole
   `ldo_core_cmos5l`, 1V AC stimulus on `Vin` (`Vref`'s AC component held
   at 0), `PSRR_dB(f) = -20*log10(|v(vout)/v(vin)|)`.

All three share: `VREF=0.90V` DC (the schematic's own illustrative bias,
`design/README.md` "Reference voltage" -- `Rtop=Rbot` by construction gives
`FB=VOUT/2`, so `0.90V` servos `VOUT` to `1.80V`; since #28 both legs are
the same drawn PDK `rhigh`, so that ratio is exactly 1/2 independent of
sheet rho and therefore of the resistor corner), `IBIAS` externally sunk at
`2uA` (the bias point `design/README.md`'s "Judgement calls" section 1
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

`XMpass`/`XRtop`/`XRbot`/`Xamp`'s instantiation lines in
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
independent of the MOS process corner.

**Resistor corner: crossed in full since issue #31.** Every `(MOS corner,
temperature)` point is run against all three of `res_typ`/`res_bcs`/
`res_wcs`, giving a 45-point main grid. The axis is swept *independently* of
the MOS corner rather than correlated to it: **no established
MOS-corner/R-corner correlation convention exists in this repo** (an
`ss`-process-correlates-with-`res_wcs` mapping would need its own decision
record, argued on foundry data), and crossing the axes in full reports every
combination instead of inventing one. `DR-0004` ratifies this as the
experiment's standing policy -- a future record that holds the resistor axis
at nominal is a regression against it.

*Why it was not always so, and what that cost:* the `#21` and `#25` records
held the main grid at `res_typ` and characterised the resistor spread
separately at `tt/27C` only, via `loopgain_rzsens_{bcs,typ,wcs}`. That was
defensible when `Rz` was the loop's only `rhigh` and the feedback divider
was a corner-independent behavioural 300k pair -- but the separate
experiment ran at one temperature, and the loop's phase-margin failure needs
`res_bcs` *and* `125C` together. Crossing the axes surfaced it immediately.
The `tt/27C` sensitivity experiment is retained (renamed `res_corner`, since
since #28 it moves the divider as well as `Rz`) as a cross-check on the main
grid's new axis, not as the primary resistor evidence.

**Cap corner** is still held at `cap_typ`, for the different and stronger
reason below: selecting a cap corner on this PDK is a literal no-op.

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
`Cc`'s width scaled `{0.5x, 1x (nominal), 2x}` (capacitance scales
~linearly with area for this device, `l` held fixed) and runs the loop-gain
bench against each, at `tt/27C` (`records/*.sensitivity.csv`,
`sweep=cc_value`). These three points are retained unchanged, and are
row-comparable back to the #21 record -- at #21 they showed phase margin
moving only from `0.35deg` (0.5x) to `0.19deg` (2x), i.e. that the
*near-zero* margin of the original compensation was not an artifact of the
uncharacterized `Cc` value.

**Since issue #35 they are no longer the load-bearing evidence for the
robustness claim, and the `Cc` value-tolerance sweep below is.** They run
at `tt/27C`, which was near this loop's worst case until #31 crossed the
resistor corner and found `res_bcs`/125C (DR-0004). At `tt/27C` every spec
row now passes with tens of degrees and dB to spare, so a `{0.5x,1x,2x}`
sweep there would report PASS at `0.5x` while `0.5x` in fact misses
`PM >= 45deg` at `res_bcs`/125C. Reporting that as evidence of robustness
would be a hollow claim.

### `Cc` value-tolerance window (issue #35)

What the uncharacterized-cap caveat actually needs is a measured answer to
"how wrong may the cap value be, in either direction, before a ratified row
fails" -- so `run_sweep.sh` measures exactly that. `Cc`'s width is swept
across `{85, 110, 130, 170, 220, 259, 340}e-6` at **`ss`/125C**, against
**both** resistor sections that hold a worst case (`res_bcs` for phase
margin, `res_wcs` for gain margin), with **both** the loop-gain and PSRR
benches run at every point. Output:
`records/*.cc-tolerance.csv`, plus a table in the record itself.

`Cc` is bounded on both sides by ratified spec rows, which is why both ends
have to be measured:

- **too small** and the `Rz*Cc` phase-lead zero lands above crossover at
  `res_bcs`/125C (where `Rz` has shrunk to `~0.60x`), failing `PM >= 45deg`;
- **too large** and the Miller-split dominant pole -- and with it the 1 kHz
  loop gain that sets PSRR there -- drops far enough to fail
  `PSRR@1kHz > 50dB`.

At the current `w=170e-6` nominal the measured window is
`110e-6`-`259e-6`, i.e. **x0.65 to x1.52** of nominal with every spec row
still met at both binding corners; `85e-6` (x0.50) fails on phase margin
and `340e-6` (x2.00) on PSRR. Both failing widths are kept in the sweep on
purpose -- a tolerance window with no measured ends is not a tolerance
window. `DR-0005` uses this measurement to place the nominal at the
*geometric centre* of the window rather than at the first value that
passed.

Every phase-margin/loop-gain number in `records/*.csv` is still marked
`insufficient-evidence` per issue #21 acceptance criterion 4 -- the
*absolute* numbers are not independently trustworthy pending real silicon
characterization -- but the qualitative verdict does not depend on that
caveat, and now has a measured tolerance band attached to it rather than an
assertion.

## Results (issue #35, `Cc` re-compensation -- current)

**Every ratified spec row is met at every one of the 45 grid points.** The
`res_bcs`/125C phase-margin gap #31 found is closed by a single-parameter
change to the error amplifier's Miller cap -- `Cc` `w` `100e-6` ->
`170e-6`, with `Rz`, both bias mirrors, `Mpass` and every other device
unchanged. Full lever study (including the two rejected levers, `Rz` and
the bias mirrors, both measured over the full grid), the derivation of the
value from the measured `Cc` pass window, and the one row that pays for it:
[`spec/decision-records/DR-0005-sg13cmos5l-cc-recompensation.md`](../../spec/decision-records/DR-0005-sg13cmos5l-cc-recompensation.md).

Record cited: [`records/20260917-023832-7061e8f.md`](records/20260917-023832-7061e8f.md),
with [`.csv`](records/20260917-023832-7061e8f.csv) (45-point PVT x resistor
grid), [`.sensitivity.csv`](records/20260917-023832-7061e8f.sensitivity.csv),
[`.cc-tolerance.csv`](records/20260917-023832-7061e8f.cc-tolerance.csv) (new
-- see "`Cc` value-tolerance window" above),
[`.delta.csv`](records/20260917-023832-7061e8f.delta.csv) and
[`.divider-attribution.csv`](records/20260917-023832-7061e8f.divider-attribution.csv).
`214/214` simulation points passed; completeness matrix OK.

### Spec table at this record

Before/after is against the #31 record at the **same** `(MOS corner,
temperature, resistor section)` on both sides -- same benches, same PDK
pin, same ngspice build -- so the deltas isolate the `Cc` change and
nothing else.

| Parameter | Target | #31 (before) | #35 (this record) | Verdict |
|---|---|---|---|---|
| Output accuracy | 1.8V +/-2% | 1.80023V-1.80066V | 1.80023V-1.80066V | **PASS** (unchanged) |
| Dropout @ 50mA | < 300mV worst corner | 0.20V-0.24V | 0.20V-0.24V | **PASS** (unchanged) |
| Line regulation | < 5 mV/V | 0.162-0.246 mV/V | 0.162-0.246 mV/V | **PASS** (unchanged, no-load only -- see caveat) |
| Load regulation | < 1% over full load | 0.0076%-0.025% | 0.0076%-0.025% | **PASS** (unchanged) |
| Iq, no load | < 30uA | 21.72uA-24.72uA | 21.72uA-24.72uA | **PASS** (unchanged) |
| PSRR @ 1kHz | > 50dB | 58.20dB-61.87dB | 53.64dB-57.37dB | **PASS**, margin down 4.56dB -- the cost, see below |
| PSRR @ 100kHz | > 20dB | 32.58dB-36.81dB | 33.23dB-37.00dB | **PASS** (slightly improved) |
| Stability: phase margin | >= 45 deg worst corner | 43.35deg-73.25deg (**FAIL** 5/45) | 53.87deg-76.94deg | **PASS** (was FAIL) |
| Stability: gain margin | >= 10dB worst corner | 13.83dB-29.76dB | 13.87dB-29.89dB | **PASS** (unchanged) |
| Current limit | 65-80mA brickwall | n/a | n/a | **not implemented** |
| Startup | monotonic ramp, <2% within 3ms | n/a | n/a | **not implemented** |
| Enable/shutdown | -- | n/a | n/a | **not implemented** |

"Unchanged" on the first five rows is meant literally, and that is a result
rather than luck: `Cc` carries no DC current, so every DC-sweep metric (Iq,
dropout, line and load regulation, output accuracy) and the loop's DC gain
are analytically invariant under any change to it. Checked cell by cell
against the #31 CSV: `vout_no_load_v`, `dropout_v_50ma`,
`line_reg_mv_per_v`, `load_reg_pct`, `i_divider_a` and `r_divider_leg_ohm`
are byte-identical at all 45 points, while `iq_a` differs by at most
`1e-13 A` and DC loop gain by at most `0.0004 dB` -- the DC solve's own
numerical noise. Had any of them moved by a physically meaningful amount,
something other than `Cc` would have changed.

### The one row that pays

Worst-corner PSRR @ 1kHz falls `4.56dB`, from `58.20dB` to `53.64dB`
against a `50dB` row -- from `8.2dB` of margin to `3.6dB`. A larger Miller
cap lowers the dominant pole, and the loop gain at 1 kHz *is* what rejects
supply ripple there. This is not a late discovery: it is the bound that set
the value (`DR-0005` decision (b)), and it is why `Cc` is `170e-6` rather
than the `220e-6`-`259e-6` that would have bought another 5-8 degrees of
phase margin. **PSRR @ 1kHz is now the second-tightest row on this block**,
behind gain margin's `3.87dB`; anything that lowers the dominant pole
further has to be checked against it first.

### Worst-corner summary, all 45 points

| Row | Worst value | Binding point | Margin |
|---|---|---|---|
| Phase margin | 53.87deg | `ss`/125C/`res_bcs` | +8.87deg |
| Gain margin | 13.87dB | `ff`/-40C/`res_wcs` | +3.87dB |
| PSRR @ 1kHz | 53.64dB | `ss`/125C/`res_wcs` | +3.64dB |
| PSRR @ 100kHz | 33.23dB | `ff`/27C/`res_bcs` | +13.23dB |
| Iq, no load | 24.72uA | `ss`/125C/`res_bcs` | +5.28uA |
| Dropout @ 50mA | 0.24V | `ss` @ 125C | +60mV |

`res_wcs` was checked explicitly, because a fix that trades one resistor
corner for another is the obvious way to pass this gate dishonestly: phase
margin improves at `res_wcs` too (`tt`/125C: `62.87deg` -> `71.30deg`), and
gain margin -- the row `res_wcs`/cold holds the worst case on -- improves
marginally rather than degrading.

### What changed in the harness

- **New `Cc` value-tolerance experiment** (see above): 7 widths x
  `{res_bcs,res_wcs}` x `{loopgain,psrr}` = 28 points at `ss`/125C, written
  to `records/*.cc-tolerance.csv`. Point count per run goes `186` -> `214`.
- **Before/after/delta re-baselined** from the #25 record to the #31 one,
  and re-keyed on `(corner, temperature, res_section)`. The #25 record held
  the resistor axis at `res_typ`, so it has no `res_bcs`/`res_wcs` rows to
  compare against -- and `res_bcs`/125C is precisely the point at issue.
  The metric list also widened from five metrics to every spec row.
- **`Cc`'s nominal width is now a single `CC_NOMINAL_W` variable**, used by
  both the sensitivity substitution and its FATAL guard, so the two cannot
  drift apart when the value moves again.

## Results (issue #31, PDK `rhigh` divider + full resistor-corner cross -- superseded in part by #35 above)

> **Superseded in part.** This record's Finding 1 (the `rhigh` divider
> conversion is harmless) stands unchanged and is not re-litigated. Its
> Finding 2 -- `PM < 45deg` at `res_bcs`/125C -- is the gap issue #35
> closed; see "Results (issue #35)" above and `DR-0005`. The tables below
> are what this run measured and are not retro-edited.

**The `rhigh` divider conversion is harmless, as #28 predicted. Crossing the
resistor corner, which this run did for the first time, found something
else: phase margin misses the ratified `>= 45deg` row at `res_bcs`/125C, at
all five MOS corners.** Full argument, mechanism, options considered and the
decision not to relax the spec:
[`spec/decision-records/DR-0004-sg13cmos5l-resistor-corner-stability.md`](../../spec/decision-records/DR-0004-sg13cmos5l-resistor-corner-stability.md).

Record cited: [`records/20260916-210331-9d3ace1.md`](records/20260916-210331-9d3ace1.md)
(run manifest, before/after/delta tables, the mechanical spec gate, and the
divider-attribution table), with
[`records/20260916-210331-9d3ace1.csv`](records/20260916-210331-9d3ace1.csv)
(45-point PVT x resistor grid),
[`.sensitivity.csv`](records/20260916-210331-9d3ace1.sensitivity.csv),
[`.delta.csv`](records/20260916-210331-9d3ace1.delta.csv) and
[`.divider-attribution.csv`](records/20260916-210331-9d3ace1.divider-attribution.csv).
`186/186` simulation points passed; completeness matrix OK.

### What changed in the harness

This is the first run against the post-#28 design netlist, and the first to
sweep `cornerRES.lib` across the whole grid rather than holding it at
`res_typ`:

- **Resistor corner crossed in full**: `{tt,ss,ff,sf,fs} x {-40,27,125}C x
  {res_typ,res_bcs,res_wcs}` = 45 points x 3 benches. Every point id, every
  snapshot filename and every CSV row names its own section, so no reader
  has to infer which corner produced a number. The axis is swept
  *independently* of the MOS corner, not correlated to it -- this repo still
  has no ratified correlation convention, and crossing in full reports every
  combination rather than inventing one.
- **Divider standing current measured per point**, from a non-invasive
  replica in `tb_dcsweep_cmos5l.spice.tmpl`: an ideal unity-gain VCVS copy
  of `VOUT` driving a byte-identical pair of `rhigh` legs through a 0V
  ammeter. It loads neither `VOUT` nor `i(vin)`, so `Iq` stays directly
  comparable to the #21/#25 records.
- **Divider attribution sweep**: the loop-gain bench re-run at all 45 points
  with the divider swapped *back* to the pre-#28 behavioural 300k pair and
  everything else held identical, so `Rz`'s corner spread cancels and what
  is left is the conversion's own contribution.
- **Mechanical spec gate**: the record now evaluates the root `README.md`
  spec table against its own CSV, so a record cannot claim a PASS its data
  contradicts.
- **`Warning: singular matrix` is no longer treated as a failure.** ngspice
  emits it while walking its own convergence-aid ladder and then reports
  `Dynamic gmin stepping completed` and a converged result; 9 of this grid's
  points do so (the #21/#25 runs never did -- the `rhigh` divider adds
  internal nodes to the DC solve). They are counted and named in the record
  rather than discarded. To keep this from being a net loosening, the pass
  criterion also gained a *positive* check it never had: every point must
  have written exactly the row count its own analysis statement implies.

### Finding 1: the divider conversion itself is harmless

Measured, not argued -- the attribution sweep above, across all 45 points:

| Metric | Worst contribution of the `rhigh` conversion |
|---|---|
| Phase margin | `-0.53deg` (at `ff`/-40C/`res_wcs`); `>= -0.31deg` at `res_typ` |
| Gain margin | `+/-1.16dB` |
| DC loop gain | `-0.19dB` |
| PSRR @ 1kHz | below display resolution at `res_typ` |

At the five points that miss the phase-margin spec, the conversion's
contribution is `+0.00deg` to `+0.01deg` -- it is not a contributor there.

What the conversion does change is the divider's own standing current: a
corner-independent `3.00uA` before (an ideal 600k across 1.8V) becomes
`1.97uA`-`4.82uA` across the PVT x resistor grid. Total no-load `Iq` moves
from `21.87-22.98uA` to `21.72-24.72uA` -- still inside the `30uA` spec at
every point.

### Finding 2: PM < 45deg at `res_bcs`/125C

| MOS corner @ 125C | `res_bcs` | `res_typ` | `res_wcs` |
|---|---|---|---|
| `tt` | **43.93deg** | 54.91deg | 62.87deg |
| `ss` | **43.35deg** | 54.35deg | 62.42deg |
| `ff` | **44.48deg** | 55.45deg | 63.31deg |
| `sf` | **44.19deg** | 55.18deg | 63.09deg |
| `fs` | **43.65deg** | 54.64deg | 62.65deg |

Five of 45 points, short by `0.5deg`-`1.7deg`. Every other spec row passes
at all 45 points. `Rz` -- not the divider -- is the mechanism: at
`res_bcs`/125C its sheet rho (`1020/1360` = `0.75x`) and its temperature
coefficient (`tc1=-2300e-6` over `98K` => `0.795x`) compound to `~0.60x`,
moving its nulling zero up in frequency so the phase boost arrives too late
at crossover. Gain margin is *best* at exactly that point (`29.76dB`),
which is the signature of a zero that moved rather than a loop that lost
gain; `res_wcs` moves the same knob the other way and improves phase margin.

No earlier record could have caught this: #21/#25 held the main grid at
`res_typ` and swept the resistor corner at `tt`/27C only, where `res_bcs`
costs `8.4deg` and still passes comfortably (`59.98deg`). The failure needs
the resistor corner *and* 125C together.

**The spec is not relaxed.** Per CLAUDE.md, the `PM >= 45deg` row stands as
ratified; DR-0004 records the narrowed verdict and defers re-compensation to
its own issue rather than changing `Cc`/`Rz` inside a verification run.

### Spec table at this record

| Parameter | Target | #25 (pre-conversion, `res_typ` only) | #31 (this record, 45-point grid) | Verdict |
|---|---|---|---|---|
| Output accuracy | 1.8V +/-2% | 1.80023V-1.80064V | 1.80023V-1.80066V | **PASS** |
| Dropout @ 50mA | < 300mV worst corner | 0.20V-0.24V | 0.20V-0.24V | **PASS** |
| Line regulation | < 5 mV/V | 0.162-0.245 mV/V | 0.162-0.246 mV/V | **PASS** (no-load only -- see caveat) |
| Load regulation | < 1% over full load | 0.0076%-0.025% | 0.0076%-0.025% | **PASS** |
| Iq, no load | < 30uA | 21.87uA-22.98uA | 21.72uA-24.72uA | **PASS** |
| Divider standing current | (not a spec row; part of Iq) | 3.00uA, corner-independent by construction | 1.97uA-4.82uA | n/a (newly measurable) |
| PSRR @ 1kHz | > 50dB | 58.21dB-61.85dB | 58.20dB-61.87dB | **PASS** |
| PSRR @ 100kHz | > 20dB | 33.82dB-35.28dB | 32.58dB-36.81dB | **PASS** |
| Stability: phase margin | >= 45 deg worst corner | 54.40deg-72.72deg | 43.35deg-73.25deg | **FAIL** at 5/45 points, all `res_bcs`/125C -- see DR-0004 |
| Stability: gain margin | >= 10dB worst corner | 17.07dB-25.87dB | 13.83dB-29.76dB | **PASS** |
| Current limit | 65-80mA brickwall | n/a | n/a | **not implemented** |
| Startup | monotonic ramp, <2% within 3ms | n/a | n/a | **not implemented** |
| Enable/shutdown | -- | n/a | n/a | **not implemented** |

The MoM-cap (`Cc`) `insufficient-evidence` caveat below still applies to
every loop-gain and margin number in this table, unchanged: `cornerCAP.lib`
maps every section to the same nominal `cap_cmomi` model at this PDK's pin.
The `Cc`-value sensitivity sweep was re-run at this record
(`sweep=cc_value`: phase margin `56.72deg`-`76.24deg` at `tt`/27C over the
`0.5x`-`2x` width range), and, as before, the qualitative verdict does not
depend on that caveat.

### PDK observation: `rhigh`'s symbol expression and its model disagree by 4.35%

This record's directly-measured per-leg divider resistance is **313.5 kOhm**
at `res_typ`/27C. `rhigh.sym`'s own `value` expression -- the source of the
`300.44 kOhm` figure `design/sg13cmos5l/ldo_core_cmos5l.sch`'s header and
`design/README.md` both quote -- gives `300.44 kOhm`. The difference is the
width offset applied twice: `resistors_mod.lib`'s `rhigh` subckt narrows the
width once (`weff = w - 0.04e-6`) and hands `W=weff` to the `r3_cmc` model
card, whose own `xw=-0.04` narrows it again. Every `rhigh` on this branch is
affected, `Rz` included (1.700 MOhm by the expression, `~1.774 MOhm` as
simulated). It is **not** a change introduced here -- the #21/#25 records
simulated the same model -- so no earlier result moves; see DR-0004's
"Separate observation" section.

## Results (issue #25, post-resize -- superseded in part by #31 above)

> **Superseded in part.** This section's evidence remains valid for what it
> measured -- the `res_typ` slice of the grid, against the pre-#28
> behavioural divider. Its "every spec row passes at every corner" headline
> does **not** survive the resistor-corner cross issue #31 ran: see
> "Results (issue #31)" above and DR-0004. The sizing and compensation
> topology DR-0003 ratified are unchanged and still correct everywhere
> except `res_bcs`/125C.

**Every spec row now passes at every corner.** Issue #25 resized `Mpass`
and re-derived the error-amp's `Cc`/`Rz` compensation network and bias
currents against the pre-resize evidence below (full derivation:
[`spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md`](../../spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md)),
then re-ran this same unmodified harness against the resized schematic.

Record cited: [`records/20260916-112842-c25ff53.csv`](records/20260916-112842-c25ff53.csv)
(main 15-point PVT grid) and
[`records/20260916-112842-c25ff53.sensitivity.csv`](records/20260916-112842-c25ff53.sensitivity.csv)
(Cc-value / Rz-corner sensitivity) -- see
[`records/20260916-112842-c25ff53.md`](records/20260916-112842-c25ff53.md)
for the full run manifest. `51/51` simulation points passed (ngspice exit
0, no convergence/model-load errors); completeness matrix OK.

| Parameter | Target | Before (#21, pre-resize) | After (#25, this record) | Verdict |
|---|---|---|---|---|
| Output accuracy | 1.8V +/-2% | 1.80022V-1.80040V | 1.80023V-1.80064V | **PASS** |
| Dropout @ 50mA | < 300mV worst corner | 1.29V-1.83V, 4/15 corners never regulate | 0.20V-0.24V (worst `ss/125C`), all corners regulate | **PASS** (was FAIL) |
| Line regulation | < 5 mV/V | 0.151-0.200 mV/V | 0.162-0.245 mV/V | **PASS** (no-load only -- see caveat below) |
| Load regulation | < 1% over full load | 0.021%-248%, 4/15 corners fail | 0.0076%-0.025% | **PASS** (was FAIL) |
| Iq, no load | < 30uA | 16.94uA-16.99uA | 21.87uA-22.98uA | **PASS** (higher due to raised bias currents, still well under target) |
| Iq, full load | < 30uA | not separable from the dropout failure | 23.05uA-23.08uA | **PASS** (newly measurable and passing) |
| PSRR @ 1kHz | > 50dB | 65.9dB-69.3dB | 58.21dB-61.85dB | **PASS** (reduced margin -- see DR-0003 "PSRR trade-off") |
| PSRR @ 100kHz | > 20dB | 35.8dB-40.6dB | 33.82dB-35.28dB | **PASS** |
| Stability: phase margin | >= 45 deg worst corner | 0.19deg-0.35deg | 54.40deg-72.72deg | **PASS** (was FAIL) |
| Stability: gain margin | >= 10dB worst corner | 4.0dB-5.4dB | 17.07dB-25.87dB | **PASS** (was FAIL) |
| Current limit | 65-80mA brickwall | n/a | n/a | **not implemented** (`design/README.md` "Known gaps": no current-limit circuit exists on this branch) |
| Startup | monotonic ramp, <2% within 3ms | n/a | n/a | **not implemented** (no soft-start circuit) |
| Enable/shutdown | -- | n/a | n/a | **not implemented** (no `EN` pin on this branch) |

Cc-value (`0.5x`-`2x` nominal) / Rz-corner (`res_bcs`/`res_typ`/`res_wcs`)
sensitivity, re-swept at the new nominal, `tt/27C`: phase margin
56.9deg-76.4deg, gain margin 18.6dB-23.5dB across both sweeps -- the PASS
verdict holds across the full sensitivity range tested, mirroring the
same "verdict does not depend on the uncharacterized `Cc` value" reasoning
the pre-resize FAIL verdict established (`cornerCAP.lib` still maps every
corner/mismatch/stat section to the same nominal `cap_cmomi` model at this
PDK's pin, so the *exact* numbers above remain `insufficient-evidence`
pending real CMOS5L MoM-cap silicon characterization, even though the
qualitative PASS verdict does not depend on that caveat).

**Line-regulation caveat**: measured at no load only (see "Benches" above
for why) -- unchanged from the pre-resize record.

No spec row required relaxation to reach this result, per CLAUDE.md's rule
that verification results are never relaxed to pass.

## Results (issue #21, pre-resize -- historical, kept for evidence provenance)

**This section is preserved unmodified as the append-only record of the
first verification pass** (`sim/` results are append-only evidence per
CLAUDE.md) -- the sizing it describes no longer matches the current
schematic; see "Results (issue #25, post-resize)" above for the current
state.

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

#25 is the resizing pass this evidence motivated (`Mpass` width, and the
`Cc`/`Rz` compensation network) -- see "Results (issue #25, post-resize)"
above for the outcome; it was out of scope for this original
verification-only phase, and is captured in full in
[`DR-0003`](../../spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md).

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
