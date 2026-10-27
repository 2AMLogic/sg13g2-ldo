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

- **#55**: Corner verification: klt sim corner-matrix envelopes against the ratified spec (T1 item 5)
- **#165**: SG13CMOS5L: implement ldo_ilimit_cmos5l per DR-0017 and instantiate in core

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#165**: SG13CMOS5L: implement ldo_ilimit_cmos5l per DR-0017 and instantiate in core

## In Progress

Issues currently being built (`loom:building`).

- **#183**: Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#55**: Corner verification: klt sim corner-matrix envelopes against the ratified spec (T1 item 5) *(curated)*
- **#56**: Monte Carlo: klt yield evidence for the statistical ratified spec rows (T1 item 6) *(curated)*
- **#64**: sim: parameterise loop-gain/PSRR benches over load, Cout and ESR for rows 3, 6, 10 dynamic coverage *(curated)*
- **#165**: SG13CMOS5L: implement ldo_ilimit_cmos5l per DR-0017 and instantiate in core *(curated)*
- **#183**: Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact) *(curated)*

## Proposed (Architect / Hermit)

_None._

## Epics

- **#5**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers)

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 2 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 5 |
| Architect / Hermit proposals | 0 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
