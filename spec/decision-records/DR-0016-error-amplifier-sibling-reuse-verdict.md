# DR-0016: Error amplifier — keep the in-tree OTA; close the `sg13g2-opamp` `evaluate` entry as `kept`

- **Status**: **Proposed.** The operator ratifies. This record authorizes no
  circuit change, no simulation, no layout work and no spec/window change.
  Row 7 (Iq) and every other target-spec row other than row 4 stay **Open**
  in [`DR-0007`](DR-0007-target-spec-row-ratification.md) exactly as they were
  (see [`DR-0015`](DR-0015-sg13cmos5l-dynamic-window-stability-diagnosis.md)).
  No threshold, gate, record or verdict is loosened.
- **Date**: 2026-10-11
- **Scope**: the `reuse.lock.json` entry `{"block": "error amplifier",
  "sibling": "2AMLogic/sg13g2-opamp"}`, bookkept `evaluate` since #47, and the
  adopt-or-keep question `spec/porting-plan.md` deferred. Issue #146. The
  SG13CMOS5L branch's in-tree amplifier (`ldo_erramp_cmos5l`, DR-0002 (b),
  DR-0003) is the amplifier in question. **Zero new simulations were run.**

## Evidence

Sibling-canary figures are pinned to `2AMLogic/sg13g2-opamp` @ `a33ace2`
(2026-09-22), as in `spec/porting-plan.md` section 2.2. The sibling was not
re-read at HEAD; any later figure needs re-dating.

| Axis | `sg13g2-opamp` @ `a33ace2` | This block's in-tree OTA | Gap |
|---|---|---|---|
| Voltage class | 1.2 V LV-only (`sg13_lv_*`); 3.3 V HV flavor is an unopened stretch row `[P]` | 3.3 V-primary loop, built from HV devices | Not usable as-is |
| Iq | <= 119.7 uA worst case **including** its external 10 uA `ibias` | 21.72-24.72 uA total block over 45 PVT points, no load (row 7 table, `DR-0007`) | roughly 5x |
| Offset | +21.9 mV systematic ratified; 46.7 mV mismatch-inclusive, not re-ratified `[P]` | no ratified offset row; regulator-only budget in porting-plan item 1 | Unresolved on both sides |

Row 7 is **Open**: the Iq comparison is the measured Iq against a proposed
< 30 uA target, not against a ratified row, and the in-tree figure is the
no-load half only (full-load measurement is missing, per the row 7 table).

## Decision (proposed)

1. **Verdict: kept in-tree.** The in-tree two-stage HV OTA remains this
   block's error amplifier. `sg13g2-opamp` is not adopted.
2. `reuse.lock.json` entry status moves `evaluate` -> `kept`. The verdict is
   for this tree at this date and does not claim the canary is unsuitable in
   general.
3. The `2am/repos.yml` `consumes` edge is fleet-side bookkeeping and is not
   changed here; flagging it for the operator if the edge should be dropped.

## Reopen conditions

Reopen (new DR) if any of the following holds:

- the canary opens and ratifies an HV (3.3 V) flavor, or this repo adopts and
  records a level-shift/bias scheme for a 1.2 V amplifier;
- row 7 is ratified with an Iq allocation that accommodates the canary's
  ibias-inclusive Iq (or the canary's Iq drops materially);
- the in-tree OTA's offset or Iq fails a ratified row and the canary
  would cure it.

## Consequences

- `spec/porting-plan.md` prose that called `evaluate` open now points here.
- The `status` field of `reuse.lock.json` is free-form: no schema, test, CI or
  signoff check reads the file (verified by search), so `kept` needs no tool
  change.
