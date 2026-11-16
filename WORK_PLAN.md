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

- **#190**: SG13CMOS5L: integrate ldo_ilimit_cmos5l into the core with refreshed PVT/startup/loop-gain and layout/LVS evidence

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#199**: T1 grading: attest items 1, 9, 10 with klt signoff --attest instead of hand-rolled inventory envelopes
- **#245**: A ninth @@TOKEN@@ render site survived #236: row4_envelope.py tb_text() has no leftover-@@ guard
- **#248**: signoff: record klayout-tools#5786 in the Monte Carlo campaign's upstream-issues list
- **#250**: Gate layout/run_flow.sh's klt + KLayout engine pins against ci.yml (no drift check today)
- **#252**: docs/chipalooza/challenge-6-proposal.md still says layout is empty and DRC/LVS not started — refresh or delete

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#264**: docs: record klayout-tools#5786 in the campaign's upstream-issues list and date the item-6 0.8.0 verdict

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#260**: docs: refresh stale layout/DRC/LVS status in challenge-6 proposal
- **#261**: refactor(sim): route row4_envelope tb_text through render_deck

## Proposed

Issues carrying `loom:curated`.

- **#56**: Monte Carlo: klt yield evidence for the statistical ratified spec rows (T1 item 6) *(curated)*
- **#64**: sim: parameterise loop-gain/PSRR benches over load, Cout and ESR for rows 3, 6, 10 dynamic coverage *(curated)*
- **#190**: SG13CMOS5L: integrate ldo_ilimit_cmos5l into the core with refreshed PVT/startup/loop-gain and layout/LVS evidence *(curated)*
- **#199**: T1 grading: attest items 1, 9, 10 with klt signoff --attest instead of hand-rolled inventory envelopes *(curated)*
- **#218**: sim: run the two-injection loop-gain bench at DR-0015 point P3 (experiment E2) *(curated)*
- **#219**: sim: f_ug-vs-Cc probe at heavy load, DR-0015 point P3 (experiment E3) *(curated)*
- **#221**: spec: proposed decision record for a row-9 startup remedy on SG13CMOS5L (plan only) *(curated)*
- **#245**: A ninth @@TOKEN@@ render site survived #236: row4_envelope.py tb_text() has no leftover-@@ guard *(curated)*
- **#248**: signoff: record klayout-tools#5786 in the Monte Carlo campaign's upstream-issues list *(curated)*
- **#250**: Gate layout/run_flow.sh's klt + KLayout engine pins against ci.yml (no drift check today) *(curated)*
- **#254**: spec: DR-0017 line 632 still says "Item 6 stays uncited" — stale after #225 cited the row-2 campaign *(curated)*
- **#262**: evidence_store: preflight's uri-scheme probe can still escape as a traceback (residual #251 item-1 site) *(curated)*

## Proposed (Architect / Hermit)

- **#228**: Remove the placeholder root package.json: five dead scripts that steer agent build-gate detection to a Node toolchain this repo does not have *(hermit)*
- **#229**: Twenty-seven unused module-level constants — four of them claim behaviour they do not have (the dimension #226's scan did not cover) *(hermit)*

## Epics

- **#5**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers)

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 5 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 2 |
| Curated | 12 |
| Architect / Hermit proposals | 2 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
