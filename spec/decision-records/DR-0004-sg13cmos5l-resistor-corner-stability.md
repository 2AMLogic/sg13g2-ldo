# DR-0004: SG13CMOS5L port — the resistor corner is a first-class PVT axis, and the loop misses PM ≥ 45° at `res_bcs`/125 °C

- **Status**: Proposed (this PR is the ratification act — see "Status" below).
- **Date**: 2026-09-16
- **Scope**: The **SG13CMOS5L branch only** (issue #31, phase 4b of the
  SG13CMOS5L port tracked by #12, Epic `2AMLogic/2am#542` Phase 5A). This
  record narrows the *stability verdict* `DR-0003` recorded; it does not
  revisit `DR-0002`'s device-flavour or topology decisions, does not change
  any sizing, and does not touch the SG13G2 branch (`design/ldo_core.sch`).
- **Related**: [`DR-0003`](DR-0003-sg13cmos5l-mpass-resize-and-compensation.md)
  (the `Mpass` resize and `Cc`/`Rz` compensation network whose PASS verdict
  this record narrows), [`DR-0002`](DR-0002-sg13cmos5l-device-topology.md),
  issue #28 (the `rhigh` feedback-divider conversion this issue was filed to
  verify), issues #21 / #25 (the pre-conversion PVT evidence),
  `sim/ldo-cmos5l-pvt-sweep/README.md` (the harness and all evidence cited
  here), root `README.md` (the DRAFT spec table this record refuses to
  relax).

## Status

**Proposed.** Per the fleet's standing ratification policy
(`2AMLogic/2am#357`: "a builder drafts the ratification/DR as a PR on the
evidence, and the operator's PR approval is the ratification act"), this
record is drafted as a PR on the evidence gathered below. **Operator
approval of that PR is what moves this record to Accepted** — there is no
separate ratification step.

## Context

### Why this run happened at all

Issue #28 (phase 4a) replaced the SG13CMOS5L feedback divider's two
behavioural `res.sym` 300 kΩ resistors with real PDK `rhigh` instances
(`w=1u l=25.43u b=7`) so that extraction and LVS could see the divider as a
device. That was a device-model swap, not a topology change — but the
behavioural pair was **corner-independent by construction**, and a PDK
`rhigh` is not: `cornerRES.lib` spreads `rsh_rhigh` over 1020 / 1360 /
1700 Ω/□ across `res_bcs` / `res_typ` / `res_wcs`, on top of a
`tc1 = −2300e-6` temperature coefficient.

Every closed-loop result under `sim/ldo-cmos5l-pvt-sweep/` predates that
swap. Issue #31 exists because this repo's rule is that no claim stands
without a testbench, and "the conversion is harmless" was, until this run,
an assumption. The expected answer was "harmless". That answer is
confirmed — **and the run that confirmed it also found something else.**

### Evidence

Record: [`sim/ldo-cmos5l-pvt-sweep/records/20260916-210331-9d3ace1.md`](../../sim/ldo-cmos5l-pvt-sweep/records/20260916-210331-9d3ace1.md)
(`.csv`, `.sensitivity.csv`, `.delta.csv`, `.divider-attribution.csv`).
186/186 simulation points passed; completeness matrix OK. Grid:
`{tt,ss,ff,sf,fs} × {−40,27,125}°C × {res_typ,res_bcs,res_wcs}` = 45 points
× 3 benches, plus the `Cc`-value and resistor-corner sensitivity points and
a 45-point divider-attribution sweep.

**Finding 1 — the `rhigh` divider conversion is harmless, as #28 predicted.**
Measured directly rather than argued: the loop-gain bench was re-run at
every one of the 45 grid points with the divider swapped back to the
pre-#28 behavioural 300 kΩ pair and *everything else* — MOS corner,
temperature, resistor section, `Cc` — held identical, so `Rz`'s corner
spread is common to both sides and cancels. Across all 45 points the
divider conversion's own contribution is:

| Metric | Worst contribution of the conversion |
| --- | --- |
| Phase margin | −0.53° (at `ff`/−40 °C/`res_wcs`); ≥ −0.31° at `res_typ` |
| Gain margin | ±1.16 dB |
| DC loop gain | −0.19 dB |
| PSRR @ 1 kHz | −0.00 dB at `res_typ` (below display resolution) |

At the five points that miss the phase-margin spec (below), the
conversion's contribution is **+0.00° to +0.01°** — it is not a
contributor there at all.

What the divider conversion *does* change is its own standing current, and
only that: a corner-independent 3.00 µA before (an ideal 600 kΩ across
1.8 V) becomes 1.97 µA–4.82 µA across the PVT × resistor grid. Total
no-load `Iq` moves from 21.87–22.98 µA to 21.72–24.72 µA — still under the
30 µA spec at every point, with 5 µA of headroom.

**Finding 2 — the loop misses PM ≥ 45° at `res_bcs`/125 °C, at all five MOS
corners.** This is the finding that forces this record:

| MOS corner @ 125 °C | `res_bcs` | `res_typ` | `res_wcs` |
| --- | --- | --- | --- |
| `tt` | **43.93°** | 54.91° | 62.87° |
| `ss` | **43.35°** | 54.35° | 62.42° |
| `ff` | **44.48°** | 55.45° | 63.31° |
| `sf` | **44.19°** | 55.18° | 63.09° |
| `fs` | **43.65°** | 54.64° | 62.65° |

Five of 45 points miss the ratified `PM ≥ 45°` row, by 0.5°–1.7°. Every
other spec row — gain margin, `Iq`, PSRR at both frequencies, line and load
regulation, dropout, output accuracy — is met at every one of the 45
points. Gain margin is in fact *best* at exactly the failing corner
(29.76 dB at `ss`/125 °C/`res_bcs`), which is the signature of a zero that
has moved rather than a loop that has lost gain.

### Why no earlier record caught this, and why that was not negligence

`#21` and `#25` held the resistor axis at `res_typ` across their main
15-point grid and swept `res_bcs`/`res_typ`/`res_wcs` **only at `tt`/27 °C**,
as a separate "Rz corner sensitivity" experiment. That was a defensible
judgement call at the time and is documented as one: the divider was
behavioural, `Rz` was the loop's only `rhigh`, and this repo had (and still
has) no ratified MOS-corner/R-corner correlation convention, so inventing
one was refused in favour of characterising `Rz` separately.

The gap is that the separate experiment ran at **27 °C only**. At 27 °C,
`res_bcs` costs 8.4° of phase margin (68.41° → 59.98°) and still passes
comfortably — which is exactly what `#25` recorded and reasonably read as
"checked". The failure needs the resistor corner *and* 125 °C together, and
no record before this one ran that combination. Crossing the axes in full,
which issue #31 required for the divider's sake, is what surfaced it.

### Mechanism

`Rz` is a PDK `rhigh` (`l=28.81u b=39`, 1.700 MΩ nominal). Two effects
compound at `res_bcs`/125 °C:

- sheet rho: `1020/1360` = 0.75× at `res_bcs`;
- temperature: `1 + tc1·ΔT + tc2·ΔT²` with `tc1 = −2300e-6`,
  `tc2 = 2.1e-6`, `ΔT = 98 K` ⇒ 0.795×.

Together ≈ 0.60×, putting `Rz` near 1.01 MΩ. The nulling zero `Rz`
provides moves up in frequency roughly as `1/Rz`, so it arrives too late to
supply its phase boost at the unity-gain crossover — phase margin falls
while gain margin rises. `res_wcs` moves the same knob the other way and
*improves* phase margin (62.4°–63.3° at 125 °C), confirming the direction.
The divider is not part of this mechanism, as Finding 1 measures directly.

## Decision

1. **The ratified `PM ≥ 45°, GM ≥ 10 dB worst corner` spec row stands,
   unrelaxed and unqualified.** No threshold is moved, no corner is
   declared out of scope, and no "worst corner" is redefined to exclude the
   failing points. CLAUDE.md is explicit that agents do not relax the
   ratified spec to make results pass, and this record does not.

2. **`DR-0003`'s stability verdict is narrowed, not overturned.** Its
   evidence remains valid for what it measured. The SG13CMOS5L branch's
   stability claim is restated as: *PASS at `res_typ` and `res_wcs` across
   the full MOS × temperature grid; FAIL at `res_bcs`/125 °C at all five MOS
   corners, by 0.5°–1.7°.* `DR-0003` is not superseded — the `Mpass` resize
   and the `Cc`/`Rz` topology it ratified are unchanged and still correct
   for every other point in the grid.

3. **The resistor corner is a first-class axis of
   `sim/ldo-cmos5l-pvt-sweep` from this record onward.** `run_sweep.sh`
   crosses `cornerRES.lib`'s three sections with the full MOS × temperature
   grid, every point id and CSV row names its own section, and the
   `tt`/27 °C-only sensitivity experiment is retained as a cross-check
   rather than as the primary resistor evidence. A future record that holds
   the resistor axis at nominal is a regression against this record.

4. **Re-compensation is deferred to its own issue, deliberately not
   attempted here.** Issue #31 is a verification issue. Changing `Cc` or
   `Rz` inside it would mean the run that found the gap and the run that
   claims to close it share no common baseline, and would amend `DR-0003`'s
   sizing without its own PVT evidence. The follow-up owns: re-deriving the
   compensation network against the `res_bcs`/125 °C corner, re-running this
   same harness, and amending `DR-0003` with the result.

5. **The gap is disclosed wherever the PASS verdict was previously
   stated** — `sim/ldo-cmos5l-pvt-sweep/README.md`'s Results section,
   `design/README.md`, and the generated record itself, which now evaluates
   the spec table mechanically against its own CSV so no future record can
   assert a PASS its data contradicts.

## Options considered and rejected

- **Relax `PM ≥ 45°` to `≥ 43°`.** Rejected outright. The margin exists to
  absorb exactly the modelling error this PDK's own caveats already flag
  (the `cap_cmomi` MoM model is explicitly "NOT YET VALIDATED ON
  ihp-sg13cmos5l SILICON"); spending it to make a simulation pass inverts
  the purpose of the number, and CLAUDE.md forbids it regardless.
- **Declare `res_bcs`/125 °C non-physical by correlating the resistor corner
  to the MOS corner** (e.g. "`res_bcs` only co-occurs with `ff`"). Rejected.
  No evidence for such a correlation exists in this PDK's libraries —
  `cornerRES.lib` is a standalone axis with no MOS coupling — and inventing
  a correlation whose only effect is to delete the failing points is the
  relaxation of option 1 wearing a different hat. If a correlation is ever
  established, it belongs in its own decision record, argued on foundry
  data, not derived from which answer is convenient.
- **Re-compensate inside issue #31.** Rejected on evidence-integrity
  grounds (decision 4 above), not on effort.
- **Record nothing, on the grounds that the divider conversion — this
  issue's actual subject — came back clean.** Rejected. The run is the
  evidence; suppressing half of what it found because the other half was
  the part that was asked for is precisely the failure mode "verification
  is the product" exists to prevent.

## Consequences

- The SG13CMOS5L branch is **not** PVT-stable across the full corner space
  as previously claimed, and no downstream phase may cite `DR-0003`'s
  "every spec row passes at every corner" without this record's
  qualification.
- Layout work already completed under #28 is unaffected: nothing here
  changes a device size, so the drawn `Mpass`, `Rz` and divider geometry all
  remain valid. A re-compensation follow-up that changes `Rz`'s length
  *would* invalidate the drawn `Rz`, which is a cost that follow-up owns and
  should weigh — it is cheaper to change `Cc` than `Rz` for this reason.
- The harness is ~3.5× larger per run (186 points vs 51) and still
  completes in well under a minute, so the cost of the wider grid is not a
  reason to narrow it back.

## Separate observation, recorded here rather than lost

The PDK's `rhigh` **symbol value expression and its simulation model
disagree by 4.35 %**, and this record is the first place in this repo with
the measurement to say so.

`design/sg13cmos5l/ldo_core_cmos5l.sch`'s header derives 300.44 kΩ per
divider leg from `rhigh.sym`'s own `value` expression
(`rspec·leff/weff + rzspec/w`, with `weff = w − 0.04µm`). The simulated
device is **313.5 kΩ** at `res_typ`/27 °C (measured: `r_divider_leg_ohm` in
this record's CSV). The difference is exactly the width offset applied
twice: `resistors_mod.lib`'s `rhigh` subckt narrows the width once
(`weff = w − 0.04e-6`) and passes `W=weff` to the `r3_cmc` model card,
whose own `xw=-0.04` narrows it again. `1360·211.965µm/0.92µm + 160` =
313.5 kΩ reproduces the simulated value to four figures; the same formula
at 0.96 µm reproduces the symbol's 300.44 kΩ.

Consequences, stated so they are not assumed away:

- Every `rhigh` on this branch is affected, including `Rz` — its nominal is
  1.700 MΩ by the symbol expression and ≈1.774 MΩ as simulated. This is
  **not** a change introduced by anything in this issue: it was equally
  true of the `#21` and `#25` records, so no prior result moves.
- The divider ratio is untouched (both legs are the same drawn device), so
  `FB = VOUT/2` and the 1.8 V output are unaffected — which is why this
  surfaced as a 2.87 µA measured vs 3.0 µA documented standing current and
  nothing else.
- The schematic header's arithmetic has been corrected to state both
  numbers and which is which.

Whether the double-count is a PDK bug or an intentional convention is not
something this repo can settle from the installed tree alone; it is filed as
its own follow-up so it is chased upstream rather than silently normalised.
