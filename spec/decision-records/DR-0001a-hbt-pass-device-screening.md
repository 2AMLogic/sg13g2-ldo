# DR-0001a: HBT pass-device screening — addendum to DR-0001

- **Status**: **Proposed (evidence addendum).** Nothing here is ratified, and
  nothing here edits DR-0001's ratified text. DR-0001's "Bipolar pass device —
  considered, not adopted" ruling stands until the operator decides otherwise.
- **Date**: 2026-10-11
- **Issue**: #139
- **Scope**: supplies the screening deck and decision record that DR-0001
  ("revisiting it requires its own screening deck and decision record") named
  as the prerequisite for revisiting the bipolar alternative. Evidence only: no
  change to the spec, the ratified rows, or the MOS design.
- **Evidence**: `sim/pass-device-screening-hbt/records/20261011-145941-ccb529c8.{md,csv}`
  derived from `.../raw/*.sim.json`, 72 `klt sim --backend batch` units
  (4 devices x 2 benches x `hbt_{bcs,typ,wcs}` x {-40, 27, 125} C). Method and
  caveats: `sim/pass-device-screening-hbt/README.md`.

## Result: confirms DR-0001's ruling, on grounds that differ in part from the ones it stated

DR-0001 gave two reasons: a bipolar pass element draws continuous base current
against the Iq budget, and a PNP's current gain and Early voltage are not
expected to compete. The measurement supports the ruling (no contradiction was
found, so nothing is escalated as a reversal), but not uniformly on those two
reasons:

1. **Base current vs the Iq budget — confirmed for the NPNs at the worst
   corner, and not at the best.** Total base current to carry 50 mA (100 mA)
   at Vce = 1.5 V, against DR-0007 row 7's 30 uA (Iq excluding load):
   - `npn13G2`: 26.6 uA (53 uA) at bcs/-40C to 317 uA (634 uA) at wcs/125C;
     worst corner 10.6x (21.1x) the budget.
   - `npn13G2l`: 10.7 uA (21.5 uA) at bcs/-40C to 317 uA (635 uA) at wcs/125C;
     worst corner 10.6x (21.2x).
   - `npn13G2v`: 259 uA (518 uA) at bcs/125C to 4.5 mA (9.0 mA) at wcs/-40C;
     worst corner 150x (300x). beta is only 11-193.
   Across the PDK's own corners the base drive alone exceeds the whole row-7
   allowance in the worst case; at the best corner `npn13G2l` at 50 mA uses
   about 0.36x of it. Whether base current counts as "Iq" is a definition
   question this record does not settle: in an emitter-follower the base
   current is delivered to the load node, but it must be sourced from a
   supply above Vin (point 3), and that supply's own quiescent draw is not
   modelled.
2. **PNP — confirmed strongly.** `pnpMPA` (model `bf` about 1.1; collector is
   the substrate) never delivered the target current in any of the 9 corners:
   at Vce = 1.5 V with the base current clamped at 1.5x the load current it
   reached 0.31-0.97 of the 50 mA target, and 0.30 V of Vce was never enough
   (0/9 corners). Its `vcesweep` needed Vce = 0.94 V at forced beta = 1 and
   reached the target in only 2 of 9 corners; at forced beta of 10, 20 or 50
   it reached 0/9. As modelled, it is not a pass element.
3. **Not anticipated by DR-0001 — headroom and rating, which weigh against
   the NPNs independently of Iq.** A high-side NPN is an emitter follower;
   with the base limited to Vin, regulation needs Vin - Vout >= Vbe. Measured
   Vbe at the target current (Vce = 1.0 V) is 0.864-1.037 V (`npn13G2`),
   0.797-0.956 V (`npn13G2l`) and 0.836-1.034 V (`npn13G2v`). The ratified
   dropout differential is 0.30 V (Vin 2.10 V, Vout 1.80 V), so the base
   needs 0.66-0.74 V above Vin, i.e. a boosted supply, which the current
   design does not have. Separately, the model cards state `vce_max` = 1.6 V
   (`npn13G2`, `npn13G2l`) and 2.2 V (`npn13G2v`): the 1.83 V regulating
   headroom at Vin_max exceeds the first two, and the 3.63 V continuous short
   exceeds all three.
4. **What the measurement does not support from DR-0001's wording.** The
   Early-voltage extrapolation (beta ratio at 1.5 V vs 1.0 V, same Ic) is
   22-313 V for `npn13G2`, 0.5-24.6 V for `npn13G2l`, and negative or about
   zero for `npn13G2v`; and beta of the NPNs at the 50 mA point is 158-1880
   (`npn13G2`) and 157-4650 (`npn13G2l`). Those are not poor numbers.
   DR-0001's "gain and Early voltage are not expected to compete" is a PNP
   statement and is borne out for the PNP; for the NPNs it is not the
   operative reason. Likewise device-level dropout is not the obstacle:
   `npn13G2l` at 50 mA needs only 0.13-0.18 V of Vce at forced beta 10-50
   (worst corner), and `npn13G2` 0.29-0.34 V. The operator may wish to
   reword DR-0001's rationale; that is a separate decision and is not done
   here.

## Limits of this evidence

- Isothermal (`selft=0`): the PDK default `selft=1` thermally ran away in the
  DC solve with an ideal current-driven base, so junction heating at
  50-100 mA x 1.5 V is not shown.
- The 0.30 V group lies outside the VBIC model's stated valid `Vce` range
  (0.4-2.0 V), and 1.83 V exceeds `vce_max` on two of three NPNs; the
  simulator does not enforce either.
- Device sizing is a screening choice (Nx = 10, m = 2 / 4), not a layout.
- No mismatch/Monte Carlo, AC, transient, noise, closed-loop circuit, layout
  or LVS-level feasibility. A bipolar pass device in a regulator loop (base
  drive, boosted supply, compensation) was not designed.
- `npn13G2v` reached the target current at 0.30 V in 5 of 9 corners only.
- The fleet runner runs klt 0.5.0 while the client is 0.7.0
  (`runner_compatibility: mismatch`, as for other batch records in this repo).
- `pnpMPA`'s servo deck sets `.options gminsteps=0` (ngspice's dynamic-gmin
  homotopy failed at two 125 C corners; source stepping reached the same
  point, printed measurements identical). The option is not used for the
  NPNs, where it makes the solve fail.

## Decision requested of the operator

None required: the result does not contradict DR-0001. If the operator wants
to revisit the bipolar alternative anyway, the open items are the base-current
accounting for Iq (point 1), a boosted base supply (point 3), `vce_max`
(point 3), and self-heating.

## Sibling records

- [`DR-0001`](DR-0001-pass-device-flavor.md) — the ruling this record
  supplies evidence for.
- [`DR-0007`](DR-0007-target-spec-row-ratification.md) — rows 4 and 7 (the
  dropout and Iq references used above).
