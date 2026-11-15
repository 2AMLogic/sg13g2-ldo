# DR-0018: Row 4 (dropout @ 50 mA) — target ratification versus per-branch compliance

- **Status**: **Clarification only.** This is a follow-on record to
  [`DR-0007`](DR-0007-target-spec-row-ratification.md). It changes no target,
  no row disposition, no threshold, no gate, no record and no verdict. Row 4's
  `< 300 mV` target stays **ratified** and its stretch (`< 200 mV`) stays not
  ratified; rows 1-3 and 5-10 stay **Open**. DR-0007 is deliberately left
  byte-for-byte unchanged: the append-only item-5 evidence pins its sha256, so
  the branch note lives here instead of as an edit to that record.
- **Date**: 2026-10-24 (evidence snapshot: `origin/main` `028a3f8`,
  2026-10-10)
- **Scope**: issue #71. Documentation only. No schematic, netlist or
  simulation record is touched and **zero new simulations were run.**

## Why this record exists

DR-0007 ratified row 4's *target* for the shared table and says the SG13G2
branch has no closed-loop evidence and that SG13CMOS5L evidence is not claimed
as SG13G2 evidence. It does not state the implementation difference between
the two branches next to the ratified status, so the row can be misread as
saying both branches meet it. PR #65's engineering-key review ruled that the
target applies to both branches and that the row is met only by the
SG13CMOS5L branch.

## Branch difference (snapshot `028a3f8`, 2026-10-10)

| | SG13CMOS5L | SG13G2 |
|---|---|---|
| Netlist | `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` | `design/netlist/ldo_core.spice` |
| Pass device | `w=2800u` | `w=300u` (provisional) |
| Error amplifier | transistor-level | behavioural VCVS placeholder |
| Row 4 evidence | closed-loop PVT sweep that ratified the row | none; the ratifying sweep is not SG13G2 evidence |
| Status | **meets the target at schematic level** | **not evidenced; predicted to miss with the committed sizing** |

The SG13G2 prediction is PR #65's screening-derived estimate from the
committed bare-device screen: about 47 ohm (about 2.35 V at 50 mA), with an
implied width of 2169-2351 um. It is **not** a closed-loop SG13G2
measurement and must not be cited as one.

## Decision

1. **Target ratification and branch compliance are separate claims.** Row 4's
   `< 300 mV` target is ratified for the shared table. That is not a statement
   that either implementation meets it.
2. SG13CMOS5L: meets the target at schematic level (2800 um pass device,
   transistor-level amplifier, closed-loop sweep).
3. SG13G2: no qualifying closed-loop evidence; the provisional 300 um sizing
   is predicted to miss. Resizing the pass device, a transistor-level
   amplifier and a closed-loop dropout bench under the DR-0012 definition are
   future work with their own decision and scope. They are not part of this
   record.
4. DR-0007's ratification verdict and all of its evidence and provenance
   caveats are preserved as written.

## References

- Issue #71; PR #65 (EE-key and market-key reviews); parent #54.
- [`DR-0007`](DR-0007-target-spec-row-ratification.md),
  [`DR-0012`](DR-0012-row4-dropout-measurement.md).
- `README.md` target table and "Row 4 branch note"; `spec/README.md`.
