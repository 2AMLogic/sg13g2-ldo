# Work Plan

This roadmap is generated from the repository's current Loom label state.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs stuck under a `loom:operator` merge-risk hold — implementation work is done, only a human merge decision is missing.

_None._

## Operator Priority

Issues the operator starred (`loom:operator-priority`); land these first.

_None._

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#64**: sim: parameterise loop-gain/PSRR benches over load, Cout and ESR for rows 3, 6, 10 dynamic coverage
- **#70**: spec: define how dropout is measured for row 4 (worst corner is 0.255 V at 1 % loss, a 45 mV margin)

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
- **#57**: Post-layout: klt pex extraction of the LDO core and spec re-run on the extracted netlist (T1 item 7) *(curated)*
- **#63**: SG13CMOS5L current limiter: topology and sizing design plan for row 8 *(curated)*
- **#64**: sim: parameterise loop-gain/PSRR benches over load, Cout and ESR for rows 3, 6, 10 dynamic coverage *(curated)*
- **#70**: spec: define how dropout is measured for row 4 (worst corner is 0.255 V at 1 % loss, a 45 mV margin) *(curated)*

## Proposed (Architect / Hermit)

- **#62**: SG13CMOS5L startup: add enable input and transient testbench for spec row 9 *(architect)*
- **#63**: SG13CMOS5L current limiter: topology and sizing design plan for row 8 *(architect)*
- **#101**: CI: run layout/run_flow.sh --check so committed layout reports cannot go stale *(architect)*
- **#102**: CI: enforce the append-only rule for sim/ evidence records *(architect)*

## Epics

- **#5**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers)
- **#62**: SG13CMOS5L startup: add enable input and transient testbench for spec row 9

## Backlog Balance

| Tier | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Operator priority | 0 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 2 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 6 |
| Architect / Hermit proposals | 4 |
| Active epics | 2 |
<!-- guide:plan-body:end -->
