# sg13g2-ldo roadmap

A 3.3 V in, 1.8 V out, 0–50 mA low-dropout regulator ported to IHP SG13G2 / SG13CMOS5L to exercise the open flow (xschem, ngspice, klayout-tools) and surface its gaps upstream.

**Status as of 2026-11-13, `main` @ `41a8294b`.**

This file is the reasoned plan. [`WORK_PLAN.md`](../WORK_PLAN.md) is the generated view of issue labels and [`WORK_LOG.md`](../WORK_LOG.md) is the merge history; neither is restated here. The graded state lives in [`signoff/`](../signoff/README.md), and that directory wins over anything below if they disagree.

## Where it stands

**T1 evidence: 8 of 11 items met, no tier awarded** ([`signoff/sg13g2-ldo.t1-report.json`](../signoff/sg13g2-ldo.t1-report.json), graded with klayout-tools 0.8.0 and re-graded in CI). All of it is the SG13CMOS5L implementation.

| Item | State | Evidence or gap |
|---|---|---|
| 1 Design sources, 2 Layout, 9 Testbenches, 10 Repo hygiene | met | Inventory envelopes under `signoff/evidence/`; items 1, 9, 10 are repo-made inventories, not `klt signoff --attest` (#199) |
| 3 DRC clean, 4 LVS clean | met | `layout/sg13cmos5l-ldo_core_cmos5l/{drc,lvs}_report.json`; deck coverage limits are disclosed in `signoff/README.md` |
| 5 Corner verification vs a ratified spec | unmet, `no_evidence` | No `klt sim` corner-matrix envelope for the one ratified row (#55) |
| 6 Monte Carlo for statistical rows | unmet, `no_evidence` | Row-2 campaign exists (`sim/ldo-cmos5l-monte-carlo/`) but is deliberately uncited; row 8 has no campaign (#56) |
| 7 Post-layout verification | unmet, `no_evidence` | `pex_report.json` is extraction only, `status: not_checked` (slice 1, #172); no re-simulation yet |
| 8 Characterization report | met | `sim/characterization/`; "met" means complete and fresh, not that the circuit meets spec |
| 11 Power delivery (structural) | met | `erc_supply_report.json`, three asserted ties |

**Spec: 1 of 10 rows ratified** (row 4, dropout @ 50 mA; [DR-0007](../spec/decision-records/DR-0007-target-spec-row-ratification.md)). The other nine are Open. What the committed evidence says about the Open rows on SG13CMOS5L:

- **Row 10 stability and row 6 PSRR miss inside the dynamic window.** The load x Cout x ESR campaign (536 operating points, `sim/ldo-cmos5l-pvt-sweep/README.md`, "Dynamic DoE") samples phase margin down to -52.70 deg and PSRR @ 1 kHz down to 43.55 dB. [DR-0015](../spec/decision-records/DR-0015-sg13cmos5l-dynamic-window-stability-diagnosis.md) (Proposed) diagnoses three miss classes and ranks a load-tracking compensation family first; its experiment E1 is measured, E2 is run only at the legacy 1 mA / 1 uF point, E3 and E4 are open.
- **Row 9 startup fails 135 of 135 grid points** on overshoot and monotonicity under the proposed methodology ([DR-0009](../spec/decision-records/DR-0009-sg13cmos5l-startup-measurement-methodology.md)); the core has an enable input but no soft start.
- **Row 8 current limit: a standalone cell exists, not integrated.** `ldo_ilimit_cmos5l` and a one-point nominal smoke record landed in PR #179 per [DR-0017](../spec/decision-records/DR-0017-sg13cmos5l-current-limiter-plan.md); the core netlist does not instantiate it.
- **Row 2 output accuracy** has Monte Carlo evidence against the proposed window (five corners, N = 400 each); the row is still Open.

**The SG13G2 branch is a placeholder.** `design/netlist/ldo_core.spice` has a `w=300u` pass device behind a behavioural amplifier, no layout, and no closed-loop evidence ([DR-0018](../spec/decision-records/DR-0018-row4-branch-status-clarification.md)). HBT pass-device screening and an HBT extraction/LVS probe are recorded (DR-0001a, `layout/hbt-probe/`).

## Now

Can start today; each is one PR.

1. **Item 5: cite a `klt sim` corner-matrix envelope for row 4** (#55). Done when `signoff/sg13g2-ldo.json` carries an item-5 citation with the envelope's real `content_hash`, the T1 report is regenerated with the pinned grader, and the Open-row qualifications in `signoff/README.md` stay in place. The tool blocker (klayout-tools#2727, batch backend refusing `ihp-sg13cmos5l`) is closed. The issue is curated but waits for a maintainer to adopt it before the fleet may draw it.
2. **Artifact store for new sim evidence** (#183, PR #184). Done when PR #184 merges with CI green: manifests in git, bytes through `klt artifact`. The PR conflicts with `main`; the two failures it was parked on (#185, #186) are closed, so it needs a rebase onto `main` and a fresh CI run, not new design.
3. **DR-0015 E2 at point P3** (no issue; seed 1). `run_loopgain2.sh` hard-codes the legacy operating point. Done when the two-injection bench runs at P3 (ff / -40 C / res_wcs, 50 mA, 0.33 uF, 0 ohm), a new append-only record is committed, and a DR-0015 addendum states whether the P3 verdicts stay `fail` or become decidable.
4. **DR-0015 E3: `f_ug`-vs-`Cc` probe at P3** (no issue; seed 2). Done when three runs (`Cc` at 0.5x, 1x, 2x) are recorded and an addendum states which node owns the class-2 third pole, or that the probe cannot tell.
5. **Row 9: a startup remedy plan** (no issue; seed 3). Done when a Proposed decision record names the cause of the overshoot from committed traces, compares candidate remedies, and lists the benches and records a follow-up must refresh. No core edit, no row change; the same shape DR-0017 gave row 8.

## Next

Unblocked by a named item above or by an upstream fix.

- **DR-0015 E4: divider / `Cc` probe at P5**, four runs. After E2 and E3 per the record's own priority order. Done when an addendum says whether rows 3, 6, 7 and 10 are jointly satisfiable at 0 mA for this topology; if not, that is a two-key ratification question, not a design PR.
- **Compensation prototype screen (DR-0015 family B)**, at most 72 AC runs. Only if E1–E4 leave family B standing. Done when each candidate has a verdict at the six recorded points; a candidate that does not clear every recorded `fail` stops there.
- **Item 7 slice 2: post-layout re-simulation.** After #55, so the row-4 bench exists as a `klt sim` request to re-run on `sg13cmos5l-ldo_core_cmos5l.pex.spice`. Done when `pex_report.json` carries delta rows instead of `nothing_checked` and is cited under item 7. No issue yet.
- **Dynamic-coverage close-out** (#64). The parameterised benches and one refinement round are on `main`; the issue stays blocked on an approved refinement stopping rule. Done when the rule is written into `sim/ldo-cmos5l-pvt-sweep/README.md` and the issue is closed or re-scoped against it.
- **Bump the klayout-tools pin** (#210). After klayout-tools#5334 (`klt erc` substrate continuity) ships. Done when `layout/run_flow.sh` stage 8 passes unchanged with `erc.supply_short` evaluated and every `layout/` report and the T1 report are regenerated. A reported short is a layout finding to fix here.
- **Tool-made attestations for items 1, 9, 10** (#199). Needs an attesting host where `design/netlist.py --check` passes (xschem 3.4.7, as CI builds) and the cold-start commands run. Done when the three envelopes come from `klt signoff --attest` and `--check` gates them in CI.
- **Delegate xschem export to `klt netlist`** (#176). After klayout-tools#4952 and #4953. Done when the regenerated netlists are byte-identical to the committed ones.

## Later

Direction; each needs its question answered first.

- **Ratify more rows.** Each Open row needs evidence over its full window and two independent review keys (`ratification/`). Question: which rows can be evidenced as written, and which need the E4 answer first?
- **Item 6 citation.** Question: can the grader express partial row coverage (klayout-tools#2908)? Until it can, and until row 2 is ratified and row 8 has a campaign, citing the row-2 reports would overstate coverage.
- **SG13G2 (BiCMOS) implementation.** Resized pass device, transistor-level amplifier, closed-loop dropout bench. Question: is the SG13G2 branch carried to parity with SG13CMOS5L, and with which pass device, given DR-0001 and the HBT screen in DR-0001a?
- **Layout for whatever the compensation and startup work changes**, then the full `signoff/README.md#regenerating` order. Question: which candidate survives screening?
- **Shuttle seat and measured silicon**, the last two rungs of the README's maturity ladder. `measurements/` is empty. Question: none worth asking before T1.

## Blocked and waiting

- **Limiter integration is parked on an operator decision** (#190): authorising the batch campaign and layout rework that instantiating `ldo_ilimit_cmos5l` in the core requires. #164, #166, #167, #168 and the row-8 half of #56 all wait behind it.
- **#210** waits on klayout-tools#5334; **#176** on klayout-tools#4952 / #4953; **#56**'s citation on klayout-tools#2908.
- **The T1 tracker (#5)** rests until #55 and #56 close.
- **Dispatchable today, as the tracker reads:** nothing is drawable without a hand. #55 needs adoption, #183 has a conflicting open PR, and items 3–5 above have no issue yet.

## Not planned

- An on-chip reference: `VREF` is an external port (`spec/porting-plan.md` §1.2).
- A capless or programmable-output variant: recorded as stretch or a separate fork in the README's target table.
- Relaxing a target, gate or verdict to turn an item green, or hand-wrapping committed CSVs into a passing envelope (`CLAUDE.md`, `signoff/README.md`).
- Adopting a sibling error amplifier: kept in-tree by DR-0016 (`reuse.lock.json`).
