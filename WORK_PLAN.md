# Work Plan

This roadmap is generated from the repository's current Loom label state.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#317**: Row 7 Iq envelope: shared row-envelope module and klt sim record (child of #316)

## Important

`loom:important`; taken before unlabelled work.

- **#190**: SG13CMOS5L: integrate ldo_ilimit_cmos5l into the core with refreshed PVT/startup/loop-gain and layout/LVS evidence *(held)*
- **#312**: Post-layout slice 2: klt pex schematic-vs-extracted delta for ratified row 4 (dropout) and the T1 item 7 citation *(held)*

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#313**: sim: replay one loop-gain deck at DR-0015 point P3 on the current batch runner, and retire batch_backend.py's deck-side pre_osdi preamble if it is the cause (klayout-tools#5766 hold on #218 and #219)
- **#317**: Row 7 Iq envelope: shared row-envelope module and klt sim record (child of #316)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#321**: batch backend: drop the deck-side pre_osdi preamble, verify runner-applied osdi_preload (#313)

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#56**: Monte Carlo: klt yield evidence for the statistical ratified spec rows (T1 item 6) *(curated)* *(held)*
- **#64**: sim: parameterise loop-gain/PSRR benches over load, Cout and ESR for rows 3, 6, 10 dynamic coverage *(curated)* *(held)*
- **#190**: SG13CMOS5L: integrate ldo_ilimit_cmos5l into the core with refreshed PVT/startup/loop-gain and layout/LVS evidence *(curated)* *(held)*
- **#218**: sim: run the two-injection loop-gain bench at DR-0015 point P3 (experiment E2) *(curated)* *(held)*
- **#219**: sim: f_ug-vs-Cc probe at heavy load, DR-0015 point P3 (experiment E3) *(curated)* *(held)*
- **#312**: Post-layout slice 2: klt pex schematic-vs-extracted delta for ratified row 4 (dropout) and the T1 item 7 citation *(curated)* *(held)*
- **#313**: sim: replay one loop-gain deck at DR-0015 point P3 on the current batch runner, and retire batch_backend.py's deck-side pre_osdi preamble if it is the cause (klayout-tools#5766 hold on #218 and #219) *(curated)*
- **#317**: Row 7 Iq envelope: shared row-envelope module and klt sim record (child of #316) *(curated)*

## Proposed (Architect / Hermit)

- **#228**: Remove the placeholder root package.json: five dead scripts that steer agent build-gate detection to a Node toolchain this repo does not have *(hermit)* *(held)*
- **#229**: Twenty-seven unused module-level constants — four of them claim behaviour they do not have (the dimension #226's scan did not cover) *(hermit)* *(held)*
- **#323**: Install the pinned klt release once per netlist and screening CI job *(hermit)* *(held)*

## Epics

- **#5**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers) *(held)*

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 1 |
| Important | 2 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 0 |
| In Progress (`loom:building`) | 2 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 0 |
| Curated | 8 |
| Architect / Hermit proposals | 3 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
