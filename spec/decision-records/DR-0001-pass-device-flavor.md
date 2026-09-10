# DR-0001: Pass-device flavor — `sg13_hv_pmos`, common-source

- **Status**: Accepted, with a carried-forward constraint on the eventual
  current-limit loop (see "Consequences").
- **Date**: 2026-09-09
- **Sequence**: item 1 of `spec/porting-plan.md` §4's ordered decision-record
  list — "the single most consequential record — nearly every other row and
  record below depends on it."

> **Note on shape**: this record follows the Status/Context/Decision/
> Consequences shape below. It is meant to be the SG13G2 analogue of
> `gf180-ldo`'s `DR-0002` and `sky130-ldo`'s `DR-001`/`DR-003` combined
> (per `spec/porting-plan.md` §4 item 1's own framing), but this sandbox
> could not fetch either sibling repo to confirm their section headings
> verbatim — see "Sibling records" below.

## Status

**Accepted.** The `sg13_hv_pmos` common-source pass-device hypothesis
(`spec/porting-plan.md` §2.1) is **confirmed, not rejected**.

## Context

`spec/porting-plan.md` §2.1 proposed `sg13_hv_pmos` (SG13G2's native
3.3 V-class thick-oxide PMOS), common-source, source tied to `VIN`, as the
direct SG13G2 analogue of gf180's `pfet_03v3` — a hypothesis, not a settled
choice, per that section's own framing ("this plan does not treat that
hypothesis as settled... this port owes [a screening deck]... before any
width or Iq number is asserted"). `design/README.md` "Pass device" already
adopted `sg13_hv_pmos` in this configuration for `Mpass` at
inspection/connectivity level ("the hypothesis was not rejected by this
issue's inspection, so no departure record is needed here") but explicitly
deferred the measured confirmation to this decision record.

Issue #13 delivered the measured screening deck this record needed:
`sim/pass-device-screening/` (bare-device characterization of `sg13_hv_pmos`
at `W/L = {1 µm × 0.4/0.5/1.0 µm, 300 µm × 0.5 µm}`, full `{tt, ss, ff, sf,
fs} × {−40, 27, 125} °C` corner grid, 120 simulation points, 120/120 PASS).
This record ratifies the conclusion issue #13's own evidence file already
states, per that issue's own scope ("If the numbers show the hypothesis is
not rejected, say so and leave DR-0001 itself to a follow-up") — it does not
re-run or re-derive any measurement.

**Evidence base** (cited by path, not re-derived):
- `sim/pass-device-screening/records/20260909-220347-ed18110.md` — the
  record's own summary, corner matrix, sanity checks, and links.
- `sim/pass-device-screening/records/20260909-220347-ed18110.csv` — the
  parsed, per-corner/per-temperature/per-device-size measured data
  (`Vth`, `Ron`, `Ron·W`, `Cgate`, implied widths, and the continuous-short
  stress terminal voltages/currents).
- `sim/pass-device-screening/README.md` — the deck's methodology, corner
  grid rationale, and its own "Verdict: `sg13_hv_pmos` hypothesis" and
  "Continuous-short stress: a conservative bound" sections.

## Decision

**Confirm `sg13_hv_pmos`, common-source (source tied to `VIN`, drain tied to
`VOUT`, body tied to `VIN`), as `Mpass`'s flavor and topology.** This is not
a new choice — it ratifies the configuration `design/ldo_core.sch` already
uses (per `design/README.md` "Pass device") and the hypothesis
`spec/porting-plan.md` §2.1 proposed — against measured data rather than
device-menu inspection alone.

### Why: what the measured data shows

1. **Dropout-point behavior is measurable and well-behaved.** At the
   dropout test point (`Vin = 2.10 V`, `Vout = 1.80 V`, gate fully on, per
   `spec/porting-plan.md` §1.4/§2.1), `Ron·W` is measurable across the full
   corner grid at all four screened sizes
   (`sim/pass-device-screening/records/20260909-220347-ed18110.csv`). The
   binding dropout corner is slow-and-hot (`ss`/125 °C), exactly the
   "single easiest sizing trap" both sibling repos' own screening decks
   found and `spec/porting-plan.md` §1.4 anticipated, not a naive
   worst-case-supply corner
   (`sim/pass-device-screening/records/20260909-220347-ed18110.md`
   "Sanity checks": "binding dropout corner (worst Ron*W, w1u_l0.5u):
   ss/125C Ron*W=13013.9 ohm.um").
2. **The `Ron·W` normalization holds at this design's own drawn size.** The
   `W=1 µm`-normalized rows and the `W=300 µm`-as-drawn row (matching
   `design/ldo_core.sch`'s `Mpass`, per `design/README.md` "Pass device")
   agree to within roughly 10–15 % — plausible for a bare-device screen at
   a fixed, non-trivial `Vds` (compare, e.g., the `w1u_l0.5u`/`ss`/125 °C
   `Ron·W = 13013.9 Ω·µm` sanity-check figure against the `w300u_l0.5u`/
   `ss`/125 °C row's own `ron_w_ohm_um = 14103.18` in
   `records/20260909-220347-ed18110.csv`) — so the `Ron·W` scaling law the
   future `Mpass` resizing record will use is empirically grounded for this
   design, not merely assumed.
3. **The extracted `Vth` corroborates the process spec.** The `w1u_l0.4u`
   size (`L = 0.4 µm`, a real characterized test-structure length,
   `VTPHV10x04`/`IDSPHV04` in `libs.doc/doc/SG13G2_os_process_spec.pdf`
   p.9) reports `Vth = 0.6185 V` at `tt`/27 °C
   (`records/20260909-220347-ed18110.csv`), in the same rough neighborhood
   as the process spec's own `VTPHV10x04` target of `−0.65 V`
   (allowing for this deck's `Vds = 0.30 V` extraction bias vs. the
   process spec's near-zero-`Vds` condition, per the record's own
   "Threshold voltage definition" / "Cross-check against the process spec"
   sections) — corroborating the extraction methodology rather than
   contradicting it.
4. **Drain-rating checks clear with margin.** At the continuous-short
   stress point (`Vout = 0 V`, `Vin = 3.63 V`, gate fully on — the Input
   row's own `+10 %` corner), `|Vds| = 3.63 V` for every corner/temperature
   point, comfortably inside the PDK's stated `BVDSSPHV04` breakdown range
   of `5.3–6.3 V`
   (`sim/pass-device-screening/README.md` "Ratings checked, and the
   finding"). This is exactly the check that forced sky130's `DR-001` into
   a different device family for its own pass device (a drain-rating
   disqualification) — SG13G2's `sg13_hv_pmos` does not hit that wall.
5. **The one real caveat is a gate-oxide finding, not a drain-rating or
   `Ron·W` finding** — addressed on its own below, since it is the finding
   this record's ratification most depends on getting right.

### Bipolar pass device — considered, not adopted

Per `spec/porting-plan.md` §2.1's own instruction, this record names and
rules out the bipolar alternative rather than silently picking a winner.
SG13G2's HBTs (`npn13G2` family, `pnpMPA`) were not screened by issue #13's
deck and are not adopted here: a bipolar pass element (a PNP or a
Darlington) draws continuous base current against the Iq budget in a way
`sg13_hv_pmos`'s near-zero gate current does not, and a lateral PNP's
current gain and Early voltage are not expected to compete with a MOS
common-source device for a low-Iq design (`spec/porting-plan.md` §2.1
"Bipolar as a pass-device alternative — deliberately not the primary
hypothesis"). No SG13G2 HBT `beta`/`Early` measurement contradicts this — it
was never run, because the MOS hypothesis was not rejected and did not need
a fallback. Revisiting this would require its own screening deck and its
own decision record, not a reversal of this one.

## The `|Vsg| = 3.63 V` vs. `3.3 V` rating finding — disposition

At the continuous-short stress point, `|Vsg| = 3.63 V` for every
corner/temperature point screened (60/60 points; bias-imposed: gate held at
`0 V`, source at `Vin = 3.63 V` —
`sim/pass-device-screening/records/20260909-220347-ed18110.md`, sanity
check "PASS Vsg at continuous-short stress (|Vsg|=3.63V, bias-imposed)
exceeds the PDK's stated 3.3V max VGS rating at 60/60 points"). This
exceeds `libs.doc/doc/SG13G2_os_process_spec.pdf` p.9's stated `VGS ≤ 3.3 V
(Maximum) @ 27 °C for LG ≥ 0.5 µm` rating by `0.33 V` — 10 %, exactly the
Input row's own `±10 %` tolerance
(`sim/pass-device-screening/README.md` "Ratings checked, and the finding").

**This is a real, quantified finding, not a spec relaxation, and this
record does not wave it away.** But it is a finding about the *bare device
under the most conservative bias this deck could apply*, not about a
circuit that exists yet:

- The stress bench holds the gate at `0 V` (fully on) for the entire corner
  grid because **no current-limit control loop exists in this repo yet**
  (`design/README.md`'s error amplifier is a behavioral placeholder;
  `spec/porting-plan.md` §4 item 6, "Current-limit window," is still open).
  A real current-limit loop, once built, senses the fault current and pulls
  the gate *toward* `Vin` to throttle it — which **reduces** `|Vsg|` below
  this bench's fully-on value, never increases it
  (`sim/pass-device-screening/README.md` "Continuous-short stress: a
  conservative bound"). So the `3.63 V` figure is a conservative upper
  bound on gate-oxide stress at the continuous-short condition, not a claim
  about what the finished, current-limited circuit will actually subject
  the device to.

**Disposition: (a) — the eventual current-limit loop is expected to keep
`|Vsg|` inside the `3.3 V` rating during a real fault, and this record
states that as the constraint the loop must satisfy, rather than adopting a
departure (derating, a different pass-device flavor, or an explicit rating
waiver) now.**

Reasoning for choosing (a) over (b) at this point in the port:

1. **The physics point the right way.** A current-limit loop's entire job
   under a hard fault is to reduce `|Vgs|` from the fully-on value toward
   threshold as it throttles current — the opposite direction from the one
   that would make the `3.63 V` figure worse. There is no plausible
   current-limit topology (brickwall or foldback — and `spec/porting-plan.md`
   §1.2 already commits this port to brickwall, not foldback) whose normal
   operation *increases* gate drive under a continuous short. The `10 %`
   overshoot this record measured is therefore the bare-device ceiling on
   the constraint, not a number the finished circuit is expected to see.
2. **A margin, not a certainty, is what's being asserted.** This record
   does **not** claim the eventual loop will keep `|Vsg|` inside `3.3 V` —
   it commits the loop's own design/verification (`spec/porting-plan.md`
   §4 item 6, sequenced explicitly *after* this record) to demonstrating
   that with its own testbench and its own PVT-corner evidence, the same
   way every other claim in this repo is required to carry a testbench
   (`CLAUDE.md`: "no claim without a testbench"). Item 6's decision record
   inherits this constraint explicitly: **the current-limit loop's
   clamped/steady-state gate drive under a continuous-short fault must keep
   `|Vsg|` at or below the PDK's stated `3.3 V` maximum `VGS` rating, across
   the full PVT corner grid** — not merely "less than the bare-device
   fully-on value."
3. **A departure now would be premature and unfalsifiable.** Choosing (b) —
   derating the device, switching flavor, or writing a rating waiver —
   before the current-limit loop's actual clamped `Vgs` is known would be
   arguing from a bound this record already shows is conservative, not from
   the circuit's real operating point. Both sibling repos' own precedent
   (per `spec/porting-plan.md` §4 item 1's framing, "gf180 `DR-0002`/sky130
   `DR-001` [carry] forward similar 'confirmed, with a caveat the next
   record must address' postures") is to carry the caveat forward as an
   explicit constraint on the next record, not to resolve it preemptively
   in the framing record.
4. **If item 6 finds the loop cannot hold the constraint**, the fallback
   options named above (derating `Mpass`, a different flavor, an explicit
   waiver) remain fully available at that point — this record does not
   foreclose them, it only declines to invoke them on data that does not
   yet show they are needed.

**What would overturn this disposition**: if `spec/porting-plan.md` §4
item 6's own screening/verification shows the current-limit loop's
clamped gate drive under a continuous short still leaves `|Vsg|` above
`3.3 V` at any corner — e.g., because the sense-path delay or the
loop's own gain/bandwidth cannot pull the gate up fast enough before the
device is exposed to the fully-on bias for a non-negligible duration, or
because a foldback-free brickwall limit's steady-state operating point
itself sits at an unsafe `Vgs` — that record must revisit this
disposition and adopt (b) at that point, informed by real data rather
than this record's conservative bound.

## Consequences

- **`Mpass`'s flavor and topology are ratified**: `sg13_hv_pmos`,
  common-source, source at `VIN`, drain at `VOUT`, body at `VIN`. No
  circuit change is required by this record — `design/ldo_core.sch`
  already uses this configuration.
- **`spec/porting-plan.md` §4 item 2** (output capacitor / ESR window,
  sequenced after this record) and **item 6** (current-limit window) can
  now proceed against a ratified pass-device flavor rather than a
  hypothesis.
- **A binding constraint is carried forward to `spec/porting-plan.md` §4
  item 6**: the current-limit loop's clamped/steady-state gate drive under
  a continuous-short fault must keep `|Vsg|` ≤ `3.3 V` across the full PVT
  corner grid. Item 6's own decision record must demonstrate this with its
  own testbench evidence, not assume it from this record's conservative
  bound.
- **Resizing `Mpass`** against the implied-width data
  (`implied_w_um_50ma_300mv` / `implied_w_um_100ma_200mv` columns in
  `sim/pass-device-screening/records/20260909-220347-ed18110.csv`) is
  explicitly out of scope for this record — a separate follow-up, per the
  issue that produced this record.
- **The bipolar pass-device alternative remains formally ruled out**,
  pending no new evidence; revisiting it requires its own screening deck
  and decision record.

## Sibling records

This record is intended as the SG13G2 analogue of `gf180-ldo`'s `DR-0002`
and `sky130-ldo`'s `DR-001`/`DR-003` combined, per
`spec/porting-plan.md` §4 item 1's own framing. **This sandbox could not
clone or fetch `2AMLogic/gf180-ldo` or `2AMLogic/sky130-ldo` to confirm
those records' section headings or structure verbatim** — the shape used
above (Status / Context / Decision / Consequences, plus a dedicated
"Sibling records" note) is a reasonable decision-record shape rather than a
confirmed match to the sibling repos' own template. A future reader with
access to those repos should reconcile this record's shape against theirs
if a closer match is wanted; the numeric content above is independent of
that shape and traces entirely to `sim/pass-device-screening/records/
20260909-220347-ed18110.{md,csv}`.

## References

- `spec/porting-plan.md` §2.1 ("Pass-device choice"), §4 item 1.
- `design/README.md` "Pass device".
- `sim/pass-device-screening/README.md`.
- `sim/pass-device-screening/records/20260909-220347-ed18110.md`.
- `sim/pass-device-screening/records/20260909-220347-ed18110.csv`.
- `libs.doc/doc/SG13G2_os_process_spec.pdf` p.9, "A.f3 HV-PMOS"
  (IHP-Open-PDK v0.3.0).
- `gf180-ldo` `DR-0002`, `sky130-ldo` `DR-001`/`DR-003` (cited by name per
  the issue's own references; not independently fetched — see "Sibling
  records" above).
