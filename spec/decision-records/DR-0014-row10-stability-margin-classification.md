# DR-0014: Row 10 stability-margin measurement and classification (multi-crossing PM, no -180 deg crossing GM)

> **Numbering note.** DR-0014 is the next free number. DR-0010, DR-0011 and
> DR-0013 stay skipped for the reason given in
> [`DR-0012`](DR-0012-row4-dropout-measurement.md): `spec/porting-plan.md`
> cites those numbers. No open pull request or remote branch carries a
> DR-0014 (checked against `origin` on 2026-10-11).

- **Status**: **Proposed.** Nothing in this record is ratified. Row 10
  (Stability) stays **Open** in [`DR-0007`](DR-0007-target-spec-row-ratification.md)
  and in the root `README.md`. The targets `PM >= 45 deg` and `GM >= 10 dB worst corner`
  are unchanged. No gate, threshold or verdict is loosened.
- **Date**: 2026-10-11
- **Scope**: *How* the row-10 phase and gain margins are read from a
  loop-gain trace, and how each committed trace is classified. Issue #126.
  The record only makes the existing numbers decidable. Whether the design
  needs a compensation change is a separate study (#125), and this record does
  not change the load/Cout/ESR coverage question (#64).
- **Related**: `DR-0009` (startup) and `DR-0012` (dropout) set the precedent of
  one measurement-methodology record per row. Evidence: the committed
  loop-gain traces under `sim/ldo-cmos5l-pvt-sweep/corners/`, classified
  offline into `sim/ldo-cmos5l-pvt-sweep/evidence/<record-id>/row10-margins.*`.

## Problem

`sim/ldo-cmos5l-pvt-sweep/ac_metrics.py:loopgain_metrics` reports PM at the
**first** 0 dB crossing and GM at the **first** -180 deg crossing. Two trace
shapes then have no defined margin:

1. **More than one 0 dB crossing.** The characterization report listed these
   points as `ambiguous` with first-crossing PM 74 to 77 deg and a recorded
   `phase_margin_worst_deg` of about -158 to -166 deg. It did not say what
   would resolve them.
2. **No -180 deg crossing in the sweep.** The #64 combined analysis marks these
   rows `failed`: "gain margin unmeasured". Counting them as misses and
   counting them as infinite margin are both unjustified without a rule.

**Verified counts** (`main` at `38e359a`, 2026-10-11, recounted from the
committed CSVs, not copied from the issue):

| set | source | count |
|---|---|---|
| legacy points with more than one 0 dB crossing | `records/20261010-025634-60a3e81.csv`, `n_0db_crossings != 1` | **15 of 45** (all have exactly 2) |
| #64 rows with `status = failed` | `records/20261010-101245-6df50fd.dynamic-doe.csv` | **46 of 536**; all 46 carry the single failure `loopgain: no -180 degree crossing (gain margin unmeasured)` |

The 46 rows are at 0 mA (29), 0.5 mA (10) and 1 mA (7), all with ESR > 0, as
`sim/ldo-cmos5l-pvt-sweep/README.md` states (that paragraph now sits at line
1045, not 1043).

## What the committed traces show

Every trace is the `tb_loopgain_cmos5l` bench output: 1 Hz to 100 MHz,
20 points per decade, 161 points, `L = -v(fb)/v(fbamp)` with phase near 0 at
DC. All 581 traces (45 legacy and 536 #64 rows, the latter read from their own
`source` corners directory) were examined. Numbers are from
`row10-margins.json` of each record.

1. **The loop gain rises again over the last decade in every trace.** At
   100 MHz it is between -1.17 and +0.53 dB, and it grew by 5.3 to 12.9 dB
   over 10 to 100 MHz. No trace ends below unity by a margin, and none is
   still falling at the ceiling.
2. **The second crossing at the 15 points is that rise.** It is a *rising*
   0 dB crossing at 59 to 98 MHz with unwrapped phase -338 to -346 deg, which
   is +14 to +22 deg modulo 360. That crossing is 158 to 166 deg away from the
   critical point. The recorded `phase_margin_worst_deg` (-158 to -166) is
   `180 + unwrapped phase`, an unwrapping artefact and not a margin.
3. **The 15 / 30 split is not physical.** The 30 single-crossing points end at
   -1.17 to -0.02 dB, rising 7.0 to 12.5 dB over the last decade. They have the
   same rise and simply had not reached 0 dB by 100 MHz. The first-crossing
   convention scored them as passes only because the ceiling cut the trace
   off.
4. **The 46 `failed` rows** turn back up before reaching -180 deg (their
   lowest unwrapped phase is -164 to -173 deg). They end in the same
   unbounded rise (-1.17 to +0.53 dB at 100 MHz).
5. **Hypothesis, not used by the rule and not tested here.** The bench breaks
   the loop with a single voltage injection at a MOSFET gate and assumes zero
   AC gate current (`README.md`, "Loop-gain measurement method"). At tens of
   MHz the gate capacitance makes that assumption weak, and a rising
   high-frequency `|L|` is what a voltage-only injection shows when it does.
   Whether the rise is circuit or bench needs a two-injection (Middlebrook or
   Tian) bench or a higher sweep ceiling. Both need new simulation.

## Decision (methodology, for review)

The rule is implemented once, in `ac_metrics.classify_margins` (it leaves
`loopgain_metrics`, which minted the records, unchanged).

**P0, open-loop stability (premise, stated and not tested).** The broken loop
is assumed to have no right-half-plane poles. Every Bode PM/GM reading,
including the first-crossing one, already assumes this. An AC trace cannot
check it, and this record does not claim it.

1. **Trace validity.** At least 4 points, all values finite, frequency
   strictly increasing. Otherwise both margins are `ambiguous`
   (`invalid_trace`).
2. **Low-end premise P1.** The loop gain at the sweep floor is above 0 dB and
   non-increasing over the first decade. Then, with `L(0)` real and positive
   (the loop regulates, as the DC benches show), no critical-phase crossing
   above unity happens below the floor. The encirclement count starts at zero.
   If P1 fails, nothing that depends on the count can pass or fail on sign
   (`low_end_premise_failed`).
3. **PM: every 0 dB crossing counts (minimum, signed by encirclement).** Each
   crossing's margin is the angular distance of its interpolated phase from
   the critical point, `180 - |wrap(phase)|` with `wrap` into (-180, 180]. For
   phase in (-180, 0] this equals the classic `180 + phase`, so a
   single-crossing trace keeps its recorded value. The margin is made
   **negative** when the running count of critical-line crossings made
   **above unity** since the floor is not zero, that is, when the curve has
   already passed the critical point. **The scored PM is the minimum over all
   crossings.**
   *Why both parts.* Of the two options in the issue, the minimum over
   crossings alone, with `180 + phase`, turns the 15 harmless rising crossings
   into -162 deg. The angular distance alone would turn the #64 point
   ff/-40C/res_wcs, 50 mA, 0.33 uF, 0 ohm, which encircles (it crosses -180 deg
   at +3.9 dB), into +52.7 deg instead of its recorded -52.7 deg. Signing by
   the encirclement count is the Nyquist check, read from the Bode data, and
   it keeps that miss a miss.
4. **GM: every -180 deg (mod 360) crossing counts (minimum).** Each critical
   crossing's margin is minus its interpolated gain. **The scored GM is the
   minimum over all crossings.** A crossing above unity has a negative margin.
5. **Ceiling premise P2.** The loop gain at the sweep ceiling is at most
   **-10 dB** and has been non-increasing over the last decade. Under P2 the
   gain above the ceiling is taken to stay at or below its ceiling value. So
   any crossing above the ceiling has a GM of at least 10 dB, and no further
   0 dB crossing exists. The floor equals the GM bound, so P2 is enough for
   both margins. Sensitivity: no committed trace meets the non-increasing
   clause, so no outcome below depends on the -10 dB value.
6. **GM with no -180 deg crossing in the sweep.** This is **never a miss on
   absence alone and never infinite margin**. With P2 it passes, reported as
   the lower bound `-L(ceiling) >= 10 dB`. Without P2 it is `ambiguous`
   (`ceiling_unbounded`).
7. **Verdicts** (per margin, per point):
   - **fail**: some in-sweep crossing has an interpolated margin below the
     bound (for PM: its distance, or with P1 its signed margin). More
     bandwidth can only add crossings and can never raise a minimum, so a miss
     inside the sweep is a miss whatever happens above the ceiling.
   - **pass**: every crossing's whole sample bracket clears the bound, P1 and
     P2 hold, and (for PM) no critical-line crossing is at or above unity.
   - **ambiguous**: everything else, with its reasons (`ceiling_unbounded`,
     `low_end_premise_failed`, `resolution_limited`, `no_zero_db_crossing`,
     `critical_crossing_at_or_above_unity`, `invalid_trace`).
8. **Near-threshold (sampling resolution).** Each crossing carries the bracket
   given by its two neighbouring samples. A bracket that straddles the bound
   blocks a pass (`resolution_limited`). It never turns an interpolated miss
   into anything else, so the recorded interpolation convention keeps every
   recorded miss. The same applies to the encirclement count: whether a
   critical crossing is above unity follows the interpolated gain, as the
   records do. If its two samples straddle 0 dB, the crossing blocks a pass
   and the Nyquist class, but it does not move a miss.
9. **Nyquist bookkeeping** is reported per point: `stable`, `unstable`,
   `conditionally_stable`, or `undetermined` when P1 or P2 fails or a critical
   crossing's gain bracket contains 0 dB. It is informational. The verdicts
   follow items 7 and 8.
10. **Validity range.** A claim under this record holds for the stated bench
    conditions and sweep (1 Hz to 100 MHz, 20 points per decade), at the
    sampled operating points only. It says nothing above the ceiling except
    through P2, and nothing between sampled operating points.

## Applied to the committed evidence (offline, no new simulation)

`python3 sim/ldo-cmos5l-pvt-sweep/row10_margins.py` reclassifies every
committed trace. Each trace is first cross-checked against the record minted
from it (0 dB crossing count, first-crossing PM, recorded worst-crossing PM,
first -180 deg GM). A **no-loosening guard** then requires that every point the
record shows below 45 deg or 10 dB classifies as `fail`. Any disagreement is a
hard error. No historical record was edited. The outputs are new evidence
files.

**The 15 legacy multi-crossing points** (`evidence/20261010-025634-60a3e81/row10-margins.*`):

| margin | outcome | in-sweep numbers |
|---|---|---|
| PM | **ambiguous 15** (`ceiling_unbounded`) | scored PM 74.34 to 76.80 deg (the first crossing). The second crossing is 158 to 166 deg from the critical point |
| GM | **ambiguous 15** (`ceiling_unbounded`) | one -180 deg crossing each, 13.85 to 20.29 dB |

They are no longer *unexplained*: in the sweep both margins clear their
bounds, and the second crossing is far from the critical point. They stay
`ambiguous` because the loop gain is above unity and rising at 100 MHz
(+0.03 to +0.53 dB). A further crossing above the ceiling cannot be excluded
from these traces.

**The 46 #64 `failed` rows** (`evidence/20261010-101245-6df50fd/row10-margins.*`):

| margin | outcome |
|---|---|
| GM | **ambiguous 46** (`ceiling_unbounded`). No -180 deg crossing in the sweep, loop gain -1.17 to +0.53 dB and rising at 100 MHz, so no lower bound can be stated. Neither a miss nor a pass. |
| PM | **fail 39** (scored PM 9.5 to 41.5 deg, inside the sweep). **ambiguous 7**: 6 `ceiling_unbounded` (PM 47.5 to 57.1 deg in the sweep) and 1 `resolution_limited` plus `ceiling_unbounded` (ss/125C/res_wcs, 0.5 mA, 4.7 uF, 500 mohm: 46.07 deg). |

**Everything else, for completeness** (the same rule, applied uniformly):

- Legacy, all 45 points: PM ambiguous 45 and GM ambiguous 45, all
  `ceiling_unbounded`. Before this record the characterization report scored
  PM 30 pass / 15 ambiguous and GM 45 pass. The 30 PM passes and 45 GM passes
  rested on the same unbounded ceiling as the 15 points, so they become
  `ambiguous`. This is a tightening. The row-10 verdict was already
  `ambiguous` and stays `ambiguous`. P1 holds at all 45 points.
- #64, all 536 rows: PM fail 210 / ambiguous 326, GM fail 90 / ambiguous 446,
  no pass. The fails equal the per-corner miss tables in
  `sim/ldo-cmos5l-pvt-sweep/README.md` exactly (PM 77+41+49+43, GM
  63+10+2+15). Under the guard, no recorded miss changes class.
- 148 of the 536 rows have two 0 dB crossings. Eleven rows cross -180 deg
  above unity, all at ff/-40C/res_wcs with 13 to 50 mA and 0.33 to 1 uF. They
  fail both margins. Their GM is the recorded value (-9.20 to -0.81 dB). Their
  first crossing keeps its recorded PM (-52.70 to -4.40 deg). Their scored PM,
  the minimum, is the rising crossing near 59 MHz at about -162 deg, which
  equals the record's own `phase_margin_worst_deg` there: after an in-band
  encirclement every later crossing is negative. Only the sign of such a
  number means anything. Its size is not a robustness figure.

**What would resolve the ambiguous points** (new simulation, outside this
record): extend the loop-gain sweep ceiling until P2 holds, or replace the
single voltage injection with a two-injection bench and show whether the
high-frequency rise is the circuit or the bench. Either one turns every
`ceiling_unbounded` point into a pass or a fail under these same rules.

## Implementation

- `sim/ldo-cmos5l-pvt-sweep/ac_metrics.py`: `classify_margins`,
  `classify_margins_trace`, `critical_distance_deg`, `wrap180`, `ceiling_bounded`.
  `loopgain_metrics` is unchanged.
- `sim/ldo-cmos5l-pvt-sweep/row10_margins.py`: offline reclassification of both
  records with cross-checks and the no-loosening guard. `--check` byte-compares
  (CI).
- `sim/ldo-cmos5l-pvt-sweep/test_ac_metrics.py`, `test_row10_margins.py`:
  multi-crossing, no-crossing, near-threshold, encirclement, premise and
  committed-trace cases, each with a negative control.
- `sim/characterization/generate.py`: row 10 reads the pinned classification
  of the selected record (`selection.json` → `row10_margin_evidence`). It
  validates it fail-closed: pins, traces, classifier bytes, bounds,
  verdict-versus-number consistency and the no-loosening guard. The
  first-crossing reading is kept as labelled, superseded context.

## What this does not claim

- No ratification. Row 10 stays Open and the target text is unchanged.
- No new simulation. No historical `sim/` record was edited.
- No claim that the design is stable or unstable above 100 MHz, between
  sampled operating points, or with Cc, layout parasitics or the reference
  error included.
- No claim that the high-frequency rise is a bench artefact (item 5 above is
  a hypothesis).
