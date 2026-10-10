# spec

The specification surface for this block. Nothing here is ratified merely by
being present; ratification state is stated per row.

- [`decision-records/`](decision-records/) — numbered decision records.
  `DR-0001` (pass-device flavor), `DR-0002`–`DR-0006` (SG13CMOS5L branch
  topology, sizing, compensation, resistor corners, PDK `rhigh` finding).
  [`DR-0007`](decision-records/DR-0007-target-spec-row-ratification.md) is the
  row-by-row ratification record for the target table in the root
  [`README.md`](../README.md): one disposition per row (Ratified as written /
  Revised / Open), evidence citations, deterministic-vs-statistical
  classification, and the inputs handed to #55 (corner verification) and
  #56 (Monte Carlo). A row is ratified only after both non-author review
  keys (`ratification/ee-key/`, `ratification/market-key/`) have posted and
  any request-changes/escalate verdict is resolved; until then rows are
  *proposed* or *Open*. Current state: row 4 (dropout @ 50 mA) is ratified,
  by the two key reviews on pull request #65; the other nine rows are Open.
- [`DR-0012`](decision-records/DR-0012-row4-dropout-measurement.md)
  (**proposed**, not ratified) defines how row 4 (dropout @ 50 mA) is
  measured: 1 % loss against the corner's own regulated output, interpolated
  crossing, `VIN - VOUT(actual)`, 5 mV grid down to 1.70 V. It keeps the
  `< 300 mV` target unchanged and does not alter `DR-0007`; the row-4 wording
  there stays as is until both review keys release the proposal.
  *Alias:* it was drafted as "DR-0009". Artifacts under
  `sim/ldo-cmos5l-pvt-sweep/` named or labelled `DR-0009` (the dropout
  testbench template, the netlist snapshots and record of run
  `20261010-111618-19e8e39`, `test_dropout_dr0009.py`, `dropout_metrics.py`,
  `dropout_campaign.py`) belong to `DR-0012`, not to
  [`DR-0009`](decision-records/DR-0009-sg13cmos5l-startup-measurement-methodology.md)
  (startup measurement methodology).
- [`porting-plan.md`](porting-plan.md) — informational port plan from the
  gf180/sky130 siblings; not a spec and not a decision record.

Spec changes go through a decision record. Targets are never relaxed to make
a measured result pass.
