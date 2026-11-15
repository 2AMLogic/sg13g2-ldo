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

- **#250**: Gate layout/run_flow.sh's klt + KLayout engine pins against ci.yml (no drift check today)

## In Progress

Issues currently being built (`loom:building`).

- **#176**: Simplify design/netlist.py: delegate xschem export to klt netlist
- **#199**: T1 grading: attest items 1, 9, 10 with klt signoff --attest instead of hand-rolled inventory envelopes
- **#226**: sim/ldo-cmos5l-pvt-sweep: four never-called helpers — adopt complex_rawfile as read_raw's missing test, drop corner_key
- **#232**: Remove four never-read bindings in the hash-pinned item-9 testbench modules — the only members of this scan CI's byte-reproduction gates allow removing
- **#240**: row_7_iq duplicates its provenance entry when called twice (shared mutable RowContext.sources)
- **#245**: A ninth @@TOKEN@@ render site survived #236: row4_envelope.py tb_text() has no leftover-@@ guard
- **#248**: signoff: record klayout-tools#5786 in the Monte Carlo campaign's upstream-issues list
- **#251**: evidence_store: narrow gaps in the documented fail-closed contract
- **#252**: docs/chipalooza/challenge-6-proposal.md still says layout is empty and DRC/LVS not started — refresh or delete

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#255**: sim: drop four never-read bindings in item-9 testbench modules
- **#264**: docs: record klayout-tools#5786 in the campaign's upstream-issues list and date the item-6 0.8.0 verdict

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#242**: test: cover read_raw via complex_rawfile; drop dead corner_key
- **#257**: fix: evidence writer's fail-closed contract is now literal (StoreError, rollback, pinned schema)
- **#259**: refactor(design): delegate netlist.py's xschem export to klt netlist
- **#260**: docs: refresh stale layout/DRC/LVS status in challenge-6 proposal
- **#263**: fix(characterization): move superseded-statement provenance into _row_context so row_7_iq is pure

## Proposed

Issues carrying `loom:curated`.

- **#56**: Monte Carlo: klt yield evidence for the statistical ratified spec rows (T1 item 6) *(curated)*
- **#64**: sim: parameterise loop-gain/PSRR benches over load, Cout and ESR for rows 3, 6, 10 dynamic coverage *(curated)*
- **#176**: Simplify design/netlist.py: delegate xschem export to klt netlist *(curated)*
- **#190**: SG13CMOS5L: integrate ldo_ilimit_cmos5l into the core with refreshed PVT/startup/loop-gain and layout/LVS evidence *(curated)*
- **#199**: T1 grading: attest items 1, 9, 10 with klt signoff --attest instead of hand-rolled inventory envelopes *(curated)*
- **#218**: sim: run the two-injection loop-gain bench at DR-0015 point P3 (experiment E2) *(curated)*
- **#219**: sim: f_ug-vs-Cc probe at heavy load, DR-0015 point P3 (experiment E3) *(curated)*
- **#232**: Remove four never-read bindings in the hash-pinned item-9 testbench modules — the only members of this scan CI's byte-reproduction gates allow removing *(curated)*
- **#240**: row_7_iq duplicates its provenance entry when called twice (shared mutable RowContext.sources) *(curated)*
- **#245**: A ninth @@TOKEN@@ render site survived #236: row4_envelope.py tb_text() has no leftover-@@ guard *(curated)*
- **#246**: signoff item-9 inventory pins test_e1_oppoints.py but not test_row4_envelope.py *(curated)*
- **#248**: signoff: record klayout-tools#5786 in the Monte Carlo campaign's upstream-issues list *(curated)*
- **#250**: Gate layout/run_flow.sh's klt + KLayout engine pins against ci.yml (no drift check today) *(curated)*
- **#251**: evidence_store: narrow gaps in the documented fail-closed contract *(curated)*
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
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 9 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 5 |
| Curated | 15 |
| Architect / Hermit proposals | 2 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
