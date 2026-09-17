# DR-0005: SG13CMOS5L port — closing the `res_bcs`/125 °C phase-margin gap on `Cc` alone, and centring `Cc` in its own measured pass window

- **Status**: Proposed (this PR is the ratification act — see "Status" below).
- **Date**: 2026-09-17
- **Scope**: The **SG13CMOS5L branch only** (issue #35, the re-compensation
  `DR-0004` deferred; phase 4c of the SG13CMOS5L port tracked by #12, Epic
  `2AMLogic/2am#542` Phase 5A). This record **supersedes `DR-0004`'s
  narrowed stability verdict** and **amends `DR-0003`'s `Cc` sizing**. It
  does not revisit `DR-0002`'s device-flavour or topology decisions, does
  not change `Mpass`, `Rz`, the bias mirrors or any other device, and does
  not touch the SG13G2 branch (`design/ldo_core.sch`).
- **Related**:
  [`DR-0004`](DR-0004-sg13cmos5l-resistor-corner-stability.md) (the record
  that found the gap, named the mechanism, and deferred the fix here),
  [`DR-0003`](DR-0003-sg13cmos5l-mpass-resize-and-compensation.md) (the
  `Mpass` resize and the `Cc`/`Rz` phase-lead-zero compensation this record
  re-sizes one value of),
  [`DR-0002`](DR-0002-sg13cmos5l-device-topology.md),
  `sim/ldo-cmos5l-pvt-sweep/README.md` (the harness and all evidence cited
  here), root `README.md` (the DRAFT spec table this record does not
  relax).

## Status

**Proposed.** Per the fleet's standing ratification policy
(`2AMLogic/2am#357`: "a builder drafts the ratification/DR as a PR on the
evidence, and the operator's PR approval is the ratification act"), this
record is drafted as a PR on the evidence gathered below. **Operator
approval of that PR is what moves this record to Accepted** — there is no
separate ratification step.

## Context

### The gap this record closes

`DR-0004` recorded that the SG13CMOS5L loop misses the ratified
`PM ≥ 45°` row at `res_bcs`/125 °C at all five MOS corners, by 0.5°–1.7°,
and that every other spec row passes at all 45 grid points:

| MOS corner @ 125 °C | `res_bcs` | `res_typ` | `res_wcs` |
| --- | --- | --- | --- |
| `tt` | **43.93°** | 54.91° | 62.87° |
| `ss` | **43.35°** | 54.35° | 62.42° |
| `ff` | **44.48°** | 55.45° | 63.31° |
| `sf` | **44.19°** | 55.18° | 63.09° |
| `fs` | **43.65°** | 54.64° | 62.65° |

(`sim/ldo-cmos5l-pvt-sweep/records/20260916-210331-9d3ace1.csv`.)

`DR-0004`'s mechanism, restated because this record's whole argument turns
on it: `Rz` is a PDK `rhigh`, and at `res_bcs`/125 °C its sheet rho
(`1020/1360` = 0.75×) and its temperature coefficient (`tc1 = −2300e-6`
over 98 K ⇒ 0.795×) compound to ≈0.60×. The nulling resistor's LHP
phase-lead zero sits at `f_z ≈ 1/(2π·Rz·Cc)`, so a 0.60× `Rz` moves it
1.67× **up** in frequency — out of the crossover region where
`DR-0003`'s compensation deliberately placed it. Gain margin is *best* at
exactly the failing point, which is the signature of a zero that moved
rather than a loop that lost gain.

`DR-0004` also measured, directly, that the #28 `rhigh` feedback-divider
conversion contributes `+0.00°`–`+0.01°` at the five failing points. It is
not part of the mechanism and nothing in this record touches it.

### What this record had to settle

1. Which knob to move: `Cc`, `Rz`, the bias mirrors, or a combination.
2. What value to move it to — and on what principle, given that the one
   device involved (`Cc`, a `cap_cmomi` MoM cap) has a model this PDK
   explicitly flags as **"NOT YET VALIDATED ON ihp-sg13cmos5l SILICON"**
   and a `cornerCAP.lib` that maps every corner/mismatch/stat section to
   the same nominal model, so there is no cap corner to sweep.
3. Whether the fix costs anything on a row that was previously passing —
   and if so, to say so in the same breath as the win, the standard
   `DR-0003`'s own "PSRR trade-off" section set.

## The lever study

All three candidate knobs were swept over the **full 45-point grid**
(`{tt,ss,ff,sf,fs} × {−40,27,125}°C × {res_typ,res_bcs,res_wcs}`), with
both the loop-gain and PSRR benches run at every point, using the existing
`sim/ldo-cmos5l-pvt-sweep` templates unmodified. Worst-case over all 45
points is what is reported; the binding corner is named in each cell.

### Knob 1 — `Rz` (the knob that moved): works for PM, breaks GM

| `Rz` `leff` | worst PM | worst GM | worst PSRR@1kHz | verdict |
| --- | --- | --- | --- | --- |
| 1200 µm (`DR-0003`, as-is) | 43.35° (`ss`/125/`bcs`) | **13.83 dB** (`ff`/−40/`wcs`) | 58.20 dB | PM fails at 5/45 |
| 1400 µm | 49.39° | 12.18 dB | 58.20 dB | passes, 2.2 dB GM margin |
| 1600 µm | 54.69° | 10.66 dB | 58.19 dB | passes, 0.7 dB GM margin |
| 1800 µm | 59.24° | **9.27 dB** | 58.18 dB | **GM fails at 5/45** |
| 2000 µm | 61.69° | 8.00 dB | 58.18 dB | GM fails at 5/45 |

Enlarging `Rz` does move the zero back down and does fix phase margin.
It also raises the loop's **high-frequency gain floor** — above the zero,
`Rz` passes `Cc`'s current straight through, so the compensation branch
stops rolling the loop off and starts feeding it forward — and gain margin
is measured right in that band (≈0.8 MHz). The cost lands at the
*opposite* resistor corner (`res_wcs`, where `Rz` is largest) and at cold,
which is exactly the "fix one corner by eating another" failure mode issue
#35's own Test Plan flagged. At 1600 µm the design would be inside spec
with 0.7 dB of gain-margin margin — real, but not margin anyone should
want to defend. Rejected.

There is a second, weaker reason to leave `Rz` alone, and it is recorded as
secondary on purpose: `Rz` is drawn in layout (#28) as a forty-stripe
`rhigh` meander, and any `l`/`b` change invalidates that draw.
`DR-0004`'s Consequences section flagged this as a cost the follow-up
should weigh. It was weighed, and it did not decide anything — the gain
margin table above did.

### Knob 2 — the bias mirrors: a negative result

`DR-0003` established that more bias current buys back the 1 kHz loop gain
(and therefore the PSRR) that a large `Rz`/`Cc` pair costs — it saw
worst-corner PSRR@1kHz go from 46.2–50.1 dB to 59.9 dB when both mirrors
were doubled (`m=2/m=4` → `m=4/m=8`). So raising the mirrors again was the
obvious way to buy headroom for a larger `Cc`. **At the notch size this
block's Iq budget can afford, it buys nothing.**

The budget is the binding constraint. Iq is `Iref·(1 + m_tail + m_load2)`
plus the divider's own current, measured at 21.72–24.72 µA against a
ratified `< 30 µA` row. `Mtail` `m=3→4` or `Mload2` `m=6→7` each add 2 µA;
both together add 4 µA; `m=4`/`m=8` — `DR-0003`'s own PSRR-restoring
point — adds 6 µA and would put the worst corner at ≈30.7 µA, **over
spec**. So only single notches were admissible. Measured, at `Cc` = 160e-6:

| Bias | worst PM | worst GM | worst PSRR@1kHz | Iq cost | grid points with a 2nd 0 dB crossing |
| --- | --- | --- | --- | --- | --- |
| `m=3`/`m=6` (as-is) | 52.58° | 13.87 dB | 54.20 dB | — | 15/45 |
| `Mload2` `m=7` | 52.69° | 14.05 dB | **54.21 dB** | +2 µA | 15/45 |
| `Mtail` `m=4` | 56.21° | 12.47 dB | 55.91 dB | +2 µA | **27/45** |

`Mload2 m=7` moves worst-corner PSRR by **+0.01 dB** for 2 µA — i.e.
nothing, at four decimal places of the thing it was supposed to buy.
`Mtail m=4` does buy +1.7 dB of PSRR, but pays 1.4 dB of gain margin, 2 µA
of Iq, and nearly doubles the number of grid points whose loop gain crosses
0 dB a second time near the top of the swept band. Both rejected: `Cc`
alone reaches the target with more margin on every row and no Iq cost at
all.

This is a genuine negative result against a lever a previous record
endorsed, and it is recorded as one rather than quietly dropped. It also
rhymes with the sibling fleet: `gf180-ldo`'s `DR-0013`/`DR-0014` are
likewise negative results that ruled out its bias and fixed-`Rz` levers
before its compensation work converged.

### Knob 3 — `Cc`: works for PM at no gain-margin cost, bounded above by PSRR

| `Cc` `w` | worst PM | worst GM | worst PSRR@1kHz | worst PSRR@100kHz |
| --- | --- | --- | --- | --- |
| 100e-6 (`DR-0003`, as-is) | **43.35°** | 13.83 dB | 58.20 dB | 32.57 dB |
| 110e-6 | 45.15° | 13.84 dB | 57.41 dB | 32.72 dB |
| 130e-6 | 48.50° | 13.86 dB | 55.95 dB | 32.95 dB |
| 170e-6 (**this record**) | 53.87° | 13.87 dB | 53.64 dB | 33.23 dB |
| 200e-6 | 57.06° | 13.87 dB | 52.27 dB | 33.37 dB |
| 250e-6 | 61.41° | 13.85 dB | 50.35 dB | 33.53 dB |
| 260e-6 | 62.21° | 13.85 dB | **49.99 dB** | 33.55 dB |
| 320e-6 | 65.96° | 13.83 dB | 48.21 dB | 33.66 dB |

Two things to read off this table.

**Gain margin is flat.** Across a 3.2× `Cc` range it moves 13.83 → 13.87 →
13.83 dB. This is the property that makes `Cc` the right knob and `Rz` the
wrong one: both move `f_z = 1/(2π·Rz·Cc)`, but only `Rz` moves the HF gain
floor that sets gain margin. The loop is zero-dominated well below
crossover here, so a larger `Cc` lowers the zero without meaningfully
lowering the unity-gain frequency (89.6 kHz → 86.0 kHz for a 2× `Cc` at
`tt`/27 °C) — the phase boost arrives earlier relative to crossover, and
phase margin rises.

**PSRR@1kHz is the upper bound, and it is a real cost.** A larger `Cc`
pushes the Miller-split dominant pole down, which is also the loop gain
that rejects supply ripple at 1 kHz. The `PSRR@1kHz > 50 dB` row is
therefore the constraint from above, and it binds at the *same* corner
family (125 °C) as the phase-margin row binds from below.

## Decision

### (a) `Cc`: `w=100e-6` → `w=170e-6` (`l=30e-6` unchanged), and nothing else moves

| Device | `DR-0003` (#25) | This record (#35) | Change |
|---|---|---|---|
| `Cc` (`cap_cmomi`) | `w=100µm, l=30µm` (≈3.2 pF) | `w=170µm, l=30µm` (≈5.5 pF) | 1.70× |
| `Rz` (`rhigh`) | `w=1µm, l=28.81µm, b=39` | unchanged | — |
| `Mtail` / `Mload2` | `m=3` / `m=6` | unchanged | — |
| `Mpass` | `w=2800µm, l=0.5µm` | unchanged | — |
| every other device | — | unchanged | — |

Capacitance is by the PDK's own display helper
(`libs.tech/xschem/sg13cmos5l_pr/cap_cmomi.tcl`, which reproduces
`cap_cmomi.va`'s low-frequency C): 3.21 pF at `w=100µm`, 5.47 pF at
`w=170µm`.

### (b) The value is the **geometric centre of the measured pass window**, not a first value that passed

This is the part of the decision that is a decision rather than a number.
`Cc` is bounded on both sides by ratified spec rows, and both bounds were
measured over the full grid rather than argued:

- **from below**, `PM ≥ 45°` fails at `res_bcs`/125 °C once `Cc`'s width
  drops under ≈110e-6 (44.99° at 109e-6, `ss`/125 °C/`res_bcs`);
- **from above**, `PSRR@1kHz > 50 dB` fails once it exceeds ≈259e-6
  (49.99 dB at 260e-6, `ss`/125 °C/`res_bcs`).

`sqrt(110e-6 · 259e-6) = 168.8e-6`. **170e-6 is that geometric centre**,
rounded: ×0.65 of nominal reaches the lower edge and ×1.52 reaches the
upper one, i.e. the *multiplicative* error tolerance is as close to
symmetric as a round value gets.

Centring is the right rule here specifically because of the MoM-cap
caveat. `cornerCAP.lib` offers no corner spread to sweep — every section
maps to the same nominal model — and `cap_cmomi.lib`'s own header says the
model is not validated on CMOS5L silicon, with coefficients transferred
from SG13G2 by layer count. **Tolerance to a wrong cap value is the only
robustness that caveat can be given**, and a multiplicative modelling error
is the shape such an error would take. Picking the smallest `Cc` that
passes, or the largest, would spend that entire tolerance on one side of a
number nobody has measured.

### (c) The harness now measures that window, at the corners that bind it

`sim/ldo-cmos5l-pvt-sweep/run_sweep.sh` already ran a `Cc`-value
sensitivity sweep `{0.5×, 1×, 2×}` at `tt`/27 °C. Those three points are
**kept**, unchanged in name and shape, so the sensitivity CSV stays
row-comparable back to the #21 record — but they are no longer load-bearing
for the "the verdict does not depend on the uncharacterized cap value"
claim, and this record says so plainly. They were a fair test while
`tt`/27 °C was near the worst case. Since #31 crossed the resistor corner
it is not: at `tt`/27 °C every row passes with tens of degrees and dB to
spare, so those points would report PASS at `0.5×` **while `0.5×` in fact
fails `PM ≥ 45°` at `res_bcs`/125 °C**. Reporting that as evidence of
robustness would be a hollow claim of exactly the kind "verification is the
product" exists to prevent.

So `run_sweep.sh` gains a **`Cc` value-tolerance experiment**: `Cc`'s width
swept across `{85, 110, 130, 170, 220, 259, 340}e-6` at `ss`/125 °C against
**both** resistor sections that hold a worst case (`res_bcs` for phase
margin, `res_wcs` for gain margin), with **both** the loop-gain and PSRR
benches run at every point, written to a new
`records/<id>.cc-tolerance.csv` and tabulated in the record. Measured
(`records/20260917-023832-7061e8f.cc-tolerance.csv`):

| `Cc` `w` | × nominal | `res_bcs`: PM / GM / PSRR@1kHz | `res_wcs`: PM / GM / PSRR@1kHz | every row met |
| --- | --- | --- | --- | --- |
| 85e-6 | 0.50× | **40.29°** / 29.68 / 59.61 | 59.39° / 23.53 / 59.59 | **no** (PM) |
| 110e-6 | 0.65× | 45.15° / 29.79 / 57.42 | 64.08° / 23.59 / 57.41 | yes |
| 130e-6 | 0.76× | 48.50° / 29.84 / 55.96 | 66.96° / 23.61 / 55.95 | yes |
| **170e-6** | **1.00×** | **53.87° / 29.89 / 53.65** | **71.01° / 23.63 / 53.64** | **yes** |
| 220e-6 | 1.29× | 58.98° / 29.92 / 51.43 | 74.27° / 23.62 / 51.43 | yes |
| 259e-6 | 1.52× | 62.14° / 29.92 / 50.02 | 76.05° / 23.61 / 50.03 | yes |
| 340e-6 | 2.00× | 67.03° / 29.90 / **47.67** | 78.53° / 23.58 / **47.69** | **no** (PSRR) |

The two failing widths are in the sweep on purpose. A tolerance window with
no measured ends is not a tolerance window.

### (d) `DR-0004`'s narrowed verdict is superseded; `DR-0003`'s `Cc` value is amended

- **`DR-0004` decision 2** restated the branch's stability claim as *"PASS
  at `res_typ` and `res_wcs` across the full MOS × temperature grid; FAIL
  at `res_bcs`/125 °C at all five MOS corners."* **That narrowing is
  superseded by this record.** The claim is now: *PASS at all 45 points of
  the `{tt,ss,ff,sf,fs} × {−40,27,125}°C × {res_typ,res_bcs,res_wcs}` grid,
  on every spec row,* on the evidence below. `DR-0004`'s other three
  decisions stand unchanged and are **not** superseded — in particular
  decision 1 (the spec row is not relaxed), decision 3 (the resistor corner
  is a first-class axis of this experiment; a future record that holds it
  at nominal is a regression) and its "Separate observation" on the
  `rhigh` symbol-vs-model 4.35 % disagreement all remain in force.
- **`DR-0003`'s Decision (b)** is amended in exactly one value: `Cc`
  `w=100µm` → `w=170µm`. Its `Mpass` resize, its `Mtail`/`Mload2` mirror
  ratios, its `Rz` sizing and — importantly — its *approach* (use the
  nulling resistor's zero as a deliberate phase-lead element near
  crossover, rather than only as an RHP-zero canceller) are all unchanged
  and still correct. This record does not overturn `DR-0003`; it re-sizes
  one of its four numbers against a corner `DR-0003` never ran.

### (e) The spec is not relaxed

No threshold moved, no corner was declared out of scope, no "worst corner"
was redefined. The record's own mechanical spec gate evaluates the root
`README.md` table against its own CSV and reports **0 failing points on all
nine rows across all 45 points**.

## Evidence: before / after PVT re-verification

Re-run of `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh`, benches unmodified
(`tb_dcsweep_cmos5l.spice.tmpl`, `tb_loopgain_cmos5l.spice.tmpl`,
`tb_psrr_cmos5l.spice.tmpl`). **214/214 points passed**; completeness
matrix OK.

- **After**: `records/20260917-023832-7061e8f.{md,csv,sensitivity.csv,cc-tolerance.csv,delta.csv,divider-attribution.csv}`
- **Before**: `records/20260916-210331-9d3ace1.csv` (the #31 record —
  `DR-0004`'s evidence, and the last run before this change)

The before/after is like-for-like at every one of the 45 points: same
benches, same PDK pin, same ngspice build, and the **same resistor section
on both sides** (`run_sweep.sh`'s delta table was re-baselined from the #25
record to the #31 one and re-keyed on `(corner, temperature, res_section)`
for exactly this reason — the #25 record has no `res_bcs`/`res_wcs` rows to
compare against).

| Parameter | Target | Before (#31) | After (#35, this record) | Verdict |
|---|---|---|---|---|
| Output accuracy | 1.8 V ±2 % | 1.80023–1.80066 V | 1.80023–1.80066 V | **PASS** (unchanged) |
| Dropout @ 50 mA | < 300 mV | 0.20–0.24 V | 0.20–0.24 V | **PASS** (unchanged) |
| Line regulation | < 5 mV/V | 0.162–0.246 mV/V | 0.162–0.246 mV/V | **PASS** (unchanged) |
| Load regulation | < 1 % | 0.0076 %–0.025 % | 0.0076 %–0.025 % | **PASS** (unchanged) |
| Iq, no load | < 30 µA | 21.72–24.72 µA | 21.72–24.72 µA | **PASS** (unchanged) |
| PSRR @ 1 kHz | > 50 dB | 58.20–61.87 dB | 53.64–57.37 dB | **PASS**, margin reduced — see below |
| PSRR @ 100 kHz | > 20 dB | 32.57–36.81 dB | 33.23–37.00 dB | **PASS** (slightly improved) |
| DC loop gain | (not a spec row) | 121.42–124.70 dB | 121.42–124.70 dB | unchanged |
| **Stability: phase margin** | **≥ 45° worst corner** | **43.35°–73.25° (FAIL, 5/45)** | **53.87°–76.94°** | **PASS** (was FAIL) |
| Stability: gain margin | ≥ 10 dB worst corner | 13.83–29.76 dB | 13.87–29.89 dB | **PASS** (unchanged) |

"Unchanged" on the first five rows is meant literally, and that is a result
rather than a coincidence: `Cc` sits in series with `Rz` between two nodes
and carries no DC current, so the DC-sweep bench's metrics (Iq, dropout,
line and load regulation, output accuracy) and the loop's DC gain are
analytically invariant under any change to it. Checked rather than
asserted, comparing the two CSVs cell by cell: `vout_no_load_v`,
`dropout_v_50ma`, `line_reg_mv_per_v`, `load_reg_pct`, `i_divider_a` and
`r_divider_leg_ohm` are **byte-identical** at all 45 points; `iq_a` differs
by at most `1e-13 A` (0.1 fA) and DC loop gain by at most `0.0004 dB`,
which is the DC solve's own numerical noise, not an effect. The sweep
confirms the analysis rather than the other way round — had any of those
rows moved by a physically meaningful amount, something other than `Cc`
would have changed.

**The one cost, stated next to the win.** Worst-corner PSRR @ 1 kHz drops
4.56 dB, from 58.20 dB to 53.64 dB, against a 50 dB row — from 8.2 dB of
margin to 3.6 dB. (Per point the largest single change is −4.57 dB; the
effect is nearly uniform across the grid.) This is the direct, expected
consequence of the lever:
a larger Miller cap lowers the dominant pole, and the loop gain at 1 kHz
*is* what rejects supply ripple there. It is not a side effect that was
discovered late; it is the upper bound that set the value in decision (b),
and it is why the value is 170e-6 and not the 220e-6 or 260e-6 that would
have bought a further 5–8° of phase margin. `DR-0003` recorded the same
trade in the opposite direction, and this record holds to the same
standard: a design pass that fixes one row while silently eating another is
the failure mode `CLAUDE.md`'s "PVT corners on every recorded result" rule
exists to catch.

**Worst-corner summary, all 45 points:**

| Row | Worst value | Binding point | Margin to spec |
|---|---|---|---|
| Phase margin | 53.87° | `ss`/125 °C/`res_bcs` | +8.87° |
| Gain margin | 13.87 dB | `ff`/−40 °C/`res_wcs` | +3.87 dB |
| PSRR @ 1 kHz | 53.64 dB | `ss`/125 °C/`res_wcs` | +3.64 dB |
| PSRR @ 100 kHz | 33.23 dB | `ff`/27 °C/`res_bcs` | +13.23 dB |
| Iq, no load | 24.72 µA | `ss`/125 °C/`res_bcs` | +5.28 µA |
| Dropout @ 50 mA | 0.24 V | `ss` @ 125 °C | +60 mV |

**The `res_wcs` edge case explicitly checked.** Issue #35's own Test Plan
asked for confirmation that the improvement is not bought at `res_wcs`'s
expense. It is not: phase margin improves at `res_wcs` too (e.g. `tt`/125:
62.87° → 71.30°), and gain margin — the row `res_wcs`/cold holds the worst
case on — moves from 13.83 dB to 13.87 dB, i.e. improves marginally. The
mechanical spec gate covers `res_wcs` on the same footing as the other two
sections, so a trade of one resistor corner for another would have failed
it rather than passing quietly.

### Layout

`Cc` is drawn in `layout/sg13cmos5l-ldo_core_cmos5l/generate.py` and is
re-drawn at `w=170µm` — the only geometry change. It grows upward from the
same origin, so no riser corridor, well or trunk moves; at 170 µm it
becomes the tallest object in the active band (the `Mpass` array tops out
at 118 µm) and sets the cell's bounding box in Y. Cell bbox grows from
163.10 × 231.28 µm to 163.10 × 281.18 µm, area from 37.7k to 45.9k µm².
`layout/run_flow.sh` re-run end to end: curated deck **0 violations**, PDK
deck **222 rules / 0 violations**, extraction 131 devices / 11 nets, LVS
**match**, and all five negative controls (topology, `Mpass` parameter, and
the three `Cc` controls) still mismatch as they must. `Rz`'s forty-stripe
meander from #28 is untouched and did not need re-verification, though it
got it anyway as part of the same flow.

## Options considered and rejected

- **Enlarge `Rz` instead of `Cc`.** Rejected on the gain-margin table in
  "Knob 1": it works for phase margin and costs gain margin at the opposite
  resistor corner, breaking the `GM ≥ 10 dB` row outright at `leff` 1800 µm
  and leaving only 0.7 dB of margin at 1600 µm.
- **Raise the bias mirrors to buy PSRR headroom for a larger `Cc`.**
  Rejected on the measurement in "Knob 2": the only notches the Iq budget
  admits buy +0.01 dB (`Mload2 m=7`, for 2 µA) or buy 1.7 dB while costing
  1.4 dB of gain margin and 2 µA (`Mtail m=4`). `DR-0003`'s 2× bias step,
  which did work, would put worst-corner Iq at ≈30.7 µA — over the ratified
  row.
- **Pick the smallest `Cc` that passes** (≈120e-6, 1.2× the old value).
  Rejected. It reaches `PM ≥ 45°` with 1.8° to spare at the binding point
  and leaves essentially no tolerance to the uncharacterized cap value on
  the low side — a −10 % modelling error on a cap the PDK says is not
  silicon-validated would take the design back out of spec. The whole point
  of decision (b) is that "it passes" is not the same claim as "it passes
  robustly", and only the second one is worth ratifying here.
- **Pick the largest `Cc` that passes** (≈250e-6), maximising phase margin.
  Rejected symmetrically: it leaves 0.35 dB of PSRR@1kHz margin and spends
  the entire cap-value tolerance on the high side.
- **Replace the fixed `Rz` with the gm-tracking triode-MOS refinement**
  `DR-0002`/`DR-0003` both flag as available. Not rejected — **deferred**,
  and deliberately not attempted here. It is a topology change that needs
  its own record and its own evidence, it substitutes a MOS-corner
  dependence for the resistor-corner dependence this record just
  characterised (which is a different trade, not obviously a better one),
  and it is not needed: a one-parameter change reaches every ratified row
  with margin on all of them. `gf180-ldo` reached for its adaptive `Rz`
  (`DR-0015`) only after a fixed-`Rz` lever was proved insufficient for a
  far wider cap × load envelope; this branch's envelope is a fixed 1 µF
  `Cout` at one load point, and the fixed lever suffices.
- **Relax `PM ≥ 45°`.** Never on the table. `CLAUDE.md` forbids it,
  `DR-0004` already rejected it explicitly, and this record needed no such
  relief.

## Consequences

- The SG13CMOS5L branch **is** PVT-stable across the full 45-point corner
  space, on every ratified spec row, at the sizing this record fixes. No
  downstream phase needs `DR-0004`'s qualification any more — but it should
  cite *this* record for the claim, not `DR-0003`, because `DR-0003`'s own
  evidence never ran `res_bcs`/125 °C.
- **PSRR @ 1 kHz is now the second-tightest row on the block** (3.64 dB of
  margin, behind only gain margin's 3.87 dB). Any future change that
  lowers the dominant pole further — a larger `Cc`, a smaller bias current,
  a heavier load on the amplifier's output — has to be checked against this
  row first. Before this record the tightest rows were gain margin and
  phase margin; the ordering has changed and downstream work should know.
- `design/sg13cmos5l/ldo_erramp_cmos5l.sch` and its regenerated netlists
  carry the new `Cc`; the schematic's header records the lever study above
  in short form, including both negative results, so a reader of the
  schematic alone is not left thinking `Rz` and the mirrors were untried.
- `layout/sg13cmos5l-ldo_core_cmos5l/generate.py` draws the wider cap; the
  cell's area grows 22 %. For a canary block that is an acceptable price
  for the robustness in decision (b), and it is stated rather than buried:
  a future area-constrained phase that wants it back should re-open
  decision (b) knowingly, and the tolerance window table is exactly the
  data it would need.
- `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh` grew a fourth experiment and a
  fifth record artifact (`.cc-tolerance.csv`). Point count per run goes
  186 → 214; runtime is still under 30 s.
- The `Cc` MoM-cap **insufficient-evidence caveat is not resolved** — it
  cannot be without real CMOS5L silicon characterization. What this record
  changes is that the caveat now has a *measured* tolerance attached
  (×0.65–×1.52) instead of a qualitative "the verdict does not depend on
  it". If characterization ever lands and `cap_cmomi`'s true value is
  outside that band, this record's sizing is what has to move.
- This record does **not** touch the SG13G2 branch
  (`design/ldo_core.sch`, `design/ldo_erramp_placeholder.sch`).

### What would overturn parts of this

- **Real CMOS5L MoM-cap characterization** putting `cap_cmomi`'s actual
  value outside ×0.65–×1.52 of the model used here. That is a re-sizing of
  `Cc` (the window shifts with it), not a re-derivation of the approach.
- **A corrected `rhigh` model.** `DR-0004`'s "Separate observation" records
  that this PDK's `rhigh` symbol expression and its simulation model
  disagree by 4.35 % (a doubly-applied width offset). Every number here is
  taken from the *simulated* device, so the record is self-consistent — but
  if the model is fixed upstream, `Rz` moves ≈4 % and both edges of the
  `Cc` window move with it. The window is wide enough (×2.35 end to end)
  that a 4 % shift cannot invalidate the choice, which is itself an
  argument for having centred it.
- **A ratified MOS-corner/R-corner correlation convention.** If foundry
  data ever establishes that `res_bcs` cannot co-occur with some MOS
  corners, the binding point of the `PM ≥ 45°` row moves and the lower edge
  of the `Cc` window relaxes. `DR-0004` already rejected inventing such a
  correlation, and nothing here depends on one existing.
- **A change to the 1 µF `Cout` or the single load point** the loop-gain
  bench runs at. This branch has never swept an output-cap or load
  envelope; `gf180-ldo` needed ten decision records to converge on one, and
  if this branch ever ratifies a range, the fixed-`Cc` answer here is the
  first thing that should be re-tested against it.

## References

- Issue #35 (this record's tracking issue) and its dependency, issue #31.
- `sim/ldo-cmos5l-pvt-sweep/records/20260917-023832-7061e8f.md` — the
  after record, its mechanical spec gate, its before/after table against
  the #31 record, and the `Cc` tolerance window.
- `sim/ldo-cmos5l-pvt-sweep/records/20260916-210331-9d3ace1.md` — the
  before record (#31), `DR-0004`'s evidence.
- `sim/ldo-cmos5l-pvt-sweep/README.md` — harness, the loop-gain measurement
  derivation, and the Results history.
- `DR-0004` (the gap and its mechanism), `DR-0003` (the compensation
  approach this record re-sizes one value of), `DR-0002` (topology and the
  MoM-cap caveat), `DR-0001` (the carried-forward `|Vsg| ≤ 3.3 V`
  constraint, untouched).
- `spec/porting-plan.md` §1.3 and `gf180-ldo`'s `DR-0013`–`DR-0016` — the
  sibling-fleet precedent for recording compensation *negative* results
  (bias and fixed-`Rz` levers) rather than only the lever that worked.
