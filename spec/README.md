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
  *proposed* or *Open*.
- [`porting-plan.md`](porting-plan.md) — informational port plan from the
  gf180/sky130 siblings; not a spec and not a decision record.

Spec changes go through a decision record. Targets are never relaxed to make
a measured result pass.
