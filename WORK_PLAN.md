# Work Plan

This roadmap is generated from the repository's current Loom label state.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#190**: SG13CMOS5L: integrate ldo_ilimit_cmos5l into the core with refreshed PVT/startup/loop-gain and layout/LVS evidence *(held)*

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

- **#389**: Clean up regenerated traces after the loop-gain reproducibility check

## In Progress

Issues currently being built (`loom:building`).

- **#318**: DR-0007 amendment PR proposing rows 2, 5, 7 for the two review keys (child of #316)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#56**: Monte Carlo: klt yield evidence for the statistical ratified spec rows (T1 item 6) *(curated)* *(held)*
- **#64**: sim: parameterise loop-gain/PSRR benches over load, Cout and ESR for rows 3, 6, 10 dynamic coverage *(curated)* *(held)*
- **#190**: SG13CMOS5L: integrate ldo_ilimit_cmos5l into the core with refreshed PVT/startup/loop-gain and layout/LVS evidence *(curated)* *(held)*
- **#313**: sim: replay one loop-gain deck at DR-0015 point P3 on the current batch runner, and retire batch_backend.py's deck-side pre_osdi preamble if it is the cause (klayout-tools#5766 hold on #218 and #219) *(curated)* *(held)*
- **#318**: DR-0007 amendment PR proposing rows 2, 5, 7 for the two review keys (child of #316) *(curated)*
- **#343**: Run the strict row-7 Iq evidence pair for PR #322 on a batch-enabled worker *(curated)* *(held)*

## Proposed (Architect / Hermit)

_None._

## Epics

- **#5**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers) *(held)*

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 1 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 6 |
| Architect / Hermit proposals | 0 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
