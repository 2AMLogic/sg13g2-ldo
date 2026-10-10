# DR-0009: SG13CMOS5L startup measurement methodology (proposed)

- **Status**: Proposed (a builder-drafted record; operator approval of the PR
  that carries it is the acceptance act). **No target-spec row is ratified,
  relaxed or changed. `DR-0007` row 9 (startup) stays Open.**
- **Date**: 2026-10-10
- **Scope**: How startup of the EN-bearing SG13CMOS5L core is measured and
  graded in `sim/ldo-cmos5l-pvt-sweep/` (issue #69, child of #62). It does not
  add a soft start, a discharge path or a current limit (#63), and it makes
  no layout or post-layout claim (#68).
- **Related**: [`DR-0007`](DR-0007-target-spec-row-ratification.md) (row 9),
  [`DR-0008`](DR-0008-sg13cmos5l-enable-interface.md) (the EN interface and its
  "no soft start, no discharge" statement),
  [`DR-0002`](DR-0002-sg13cmos5l-device-topology.md) (3.3 V VGS reference).
  Evidence: `sim/ldo-cmos5l-pvt-sweep/records/20261010-104827-91e92aa-startup-*`.
- **Not this record**: the row-4 dropout artifacts under
  `sim/ldo-cmos5l-pvt-sweep/` labelled `DR-0009` (`tb_dropout_cmos5l.spice.tmpl`,
  `test_dropout_dr0009.py`, run `20261010-111618-19e8e39`) belong to
  [`DR-0012`](DR-0012-row4-dropout-measurement.md), which was drafted as DR-0009.

## Decision (methodology, for review)

1. **Row 9 is read as two checks and both are reported.** (a) *Timing*:
   VOUT inside 1.764-1.836 V within 3 ms of enable and staying there for the
   rest of a >= 5 ms observation. (b) *Controlled ramp*: monotonic rise.
   First band entry and settling are different quantities: settling is the
   last re-entry after which the trace stays in the band.
2. **Time zero** is the `EN = VIN/2` crossing of a finite 1 us edge, after
   1 ms disabled. The disabled operating point is solved with `EN = 0`, no UIC,
   `VOUT` not forced.
3. **Monotonic** is operationalised as: no downward excursion from the running
   maximum above **1 mV** from time zero until settling. 1 mV is a numerical
   tolerance, not a physical claim; raw excursions and reversal counts at
   0.1 / 1 / 10 mV are published so it cannot hide a physical reversal. The
   recovery from an overshoot counts as a reversal.
4. **Overshoot is reported separately.** A peak above 1.836 V fails the +/-2 %
   envelope reading. This is recorded as an interpretation for review, not
   silently adopted as the meaning of "controlled ramp".
5. **Off state.** A cold-start resistive load must show no sustained
   regulator-driven output: max `|VOUT|` <= 50 mV (proposed bound). `VOUT` and
   supply current are published. A disable/re-enable case is run; instant
   discharge is not required.
6. **Loads are resistive** (1.8 V / I). A current sink would pull a disabled
   output negative. A load of 0 leaves the output open; its limits are
   stated in the results.
7. **Timestep.** Max step 1 us (equal to the edge); binding points rerun at
   0.5 us and compared.
8. **Fail closed.** Missing or non-finite data, gaps above the step cap, a
   window under 5 ms, a missing EN edge, or a non-converged run is
   *insufficient*, never a pass. Incomplete coverage is reported as such.
9. **Cc tolerance stays unverified**; no Cc axis is added here.

## What the first evidence shows (schematic-level)

Not a ratification. At 135 of 135 requested PVT/supply points (and the
3 + 24 follow-up points) the startup **fails the overshoot and monotonic
checks** (peak 1.87-2.34 V at the 1 mA / 1 uF / 0 ohm point) while the timing
check is met (settling in 37-440 us). Overshoot magnitudes are not
step-converged (0.5 us changes them by up to 0.15 V) although the verdicts did
not change at the three binding points. Details and limits:
`sim/ldo-cmos5l-pvt-sweep/README.md` "Startup campaign (issue #69)".

## What this does not claim

- No row 9 ratification and no relaxation of the 1.8 V +/-2 % target.
- No claim that the three binding points bound the design, or that the
  bounded load/Cout/ESR set covers every interior point.
- No constant-current load, no soft-start/discharge variants, no layout.
