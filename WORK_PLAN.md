# Work Plan

This roadmap is generated from the repository's current Loom label state.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#277**: chore(loom): resync installed Loom to v0.19.1302

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#190**: SG13CMOS5L: integrate ldo_ilimit_cmos5l into the core with refreshed PVT/startup/loop-gain and layout/LVS evidence

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#56**: Monte Carlo: klt yield evidence for the statistical ratified spec rows (T1 item 6)
- **#272**: evidence_store: put_files' private temp dir can still escape as a non-StoreError (residual of the #262 class)

## In Progress

Issues currently being built (`loom:building`).

- **#199**: T1 grading: attest items 1, 9, 10 with klt signoff --attest instead of hand-rolled inventory envelopes
- **#267**: Gate sim/pdk-cmos5l.json's pinned_tarball_url SHA against its own pinned_commit
- **#275**: sim/pdk-cmos5l.json's fetch_method cites a stale KLAYOUT_TOOLS_REF (159527a5, ci.yml says 046ba746)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#277**: chore(loom): resync installed Loom to v0.19.1302
- **#288**: feat: gate the intra-file PDK pin copies and ci.yml's SG13G2 version

## Proposed

Issues carrying `loom:curated`.

- **#56**: Monte Carlo: klt yield evidence for the statistical ratified spec rows (T1 item 6) *(curated)*
- **#64**: sim: parameterise loop-gain/PSRR benches over load, Cout and ESR for rows 3, 6, 10 dynamic coverage *(curated)*
- **#190**: SG13CMOS5L: integrate ldo_ilimit_cmos5l into the core with refreshed PVT/startup/loop-gain and layout/LVS evidence *(curated)*
- **#199**: T1 grading: attest items 1, 9, 10 with klt signoff --attest instead of hand-rolled inventory envelopes *(curated)*
- **#218**: sim: run the two-injection loop-gain bench at DR-0015 point P3 (experiment E2) *(curated)*
- **#219**: sim: f_ug-vs-Cc probe at heavy load, DR-0015 point P3 (experiment E3) *(curated)*
- **#254**: spec: DR-0017 line 632 still says "Item 6 stays uncited" — stale after #225 cited the row-2 campaign *(curated)*
- **#267**: Gate sim/pdk-cmos5l.json's pinned_tarball_url SHA against its own pinned_commit *(curated)*
- **#272**: evidence_store: put_files' private temp dir can still escape as a non-StoreError (residual of the #262 class) *(curated)*
- **#275**: sim/pdk-cmos5l.json's fetch_method cites a stale KLAYOUT_TOOLS_REF (159527a5, ci.yml says 046ba746) *(curated)*

## Proposed (Architect / Hermit)

- **#228**: Remove the placeholder root package.json: five dead scripts that steer agent build-gate detection to a Node toolchain this repo does not have *(hermit)*
- **#229**: Twenty-seven unused module-level constants — four of them claim behaviour they do not have (the dimension #226's scan did not cover) *(hermit)*
- **#270**: Remove check_artifact_manifests.py verify subcommand: hand-rolled twin of klt artifact verify *(hermit)*

## Epics

- **#5**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers)

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`) | 2 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 2 |
| Curated | 9 |
| Architect / Hermit proposals | 3 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
