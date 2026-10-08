# signoff/ — klt signoff block manifest and the T1 verdict of record

This directory is this repo's machine-graded **gap-to-T1** state (#44). Issue
#5's hand-maintained checkbox list is retired: the **committed block manifest
is the input**, the **committed tier report is the verdict of record**, and
both are regenerated and gated in CI — so the state cannot go silently stale
the way a hand-read checklist does.

| File | What it is |
| --- | --- |
| `sg13g2-ldo.json` | The **block manifest** for `klt signoff --manifest`: `block: sg13g2-ldo`, `kind: analog`, and one pinned evidence citation per T1 item this repo can honestly cite. |
| `sg13g2-ldo.t1-report.json` | The **verdict of record**: the exact `klt signoff --manifest sg13g2-ldo.json --format json` output, committed. `t1_item_count: 11, t1_met_count: 3, tier: null` — this block is **not T1 yet**, and the report says so per item with a `reason`. |

## Reading the report

Today's honest read is **3/11 met**:

- **met — item 3 (DRC clean)**: `layout/sg13cmos5l-ldo_core_cmos5l/drc_report.json`, `status: clean`, 0 violations, citation verified against the committed GDS (`input_verified: true`).
- **met — item 4 (LVS clean)**: `layout/sg13cmos5l-ldo_core_cmos5l/lvs_report.json`, `status: match`, 0 errors / 0 mismatches, citation verified against the committed extracted netlist it compared.
- **met — item 8 (characterization report)**: `sim/characterization/characterization-envelope.json`, a hand-rolled `kind: generic` envelope (the one evidence kind item 8 accepts) with `t1_item: 8`, pinned by `content_hash` to the sha256 of the committed aggregate report. **What `met` means here, and what it does not**: the envelope verdict is *artifact completeness and freshness* — every one of the ten target-spec rows appears exactly once with an explicit state, every selected source record matches its sha256 pin, the 45-point PVT grid is whole, and the record is current against the design netlists. It is **not** a claim that the circuit meets its spec: the report lists failing/ambiguous/unmeasured/unimplemented/unratified rows as such (today: 1 not measured, 5 partial-coverage passes, 1 full-coverage pass on the one ratified row, 1 ambiguous, 2 not implemented), and no post-layout performance evidence exists. `klt signoff` does **not** inspect the envelope's `source`, nor re-hash the report (`input_verified: null` for generic envelopes); the content and freshness are verified by this repo's generator and its CI `--check` gate (`python3 sim/characterization/generate.py --check`), which is what makes the pin trustworthy. Other T1 items are not touched by this citation.
- **unmet — item 11 (power delivery, structural)**: `supply_spec_incomplete` — the `klt erc` supply run is clean on all three supply islands (VIN/VOUT/VSS, zero `erc.supply_short`), but the spec carries no `ties[]` declaration. That omission is deliberate and recorded: the current `klt erc` cannot express this PDK's well/substrate-tie convention (klayout-tools#2169, filed from this repo by #43), so this row stays `unmet` with that exact reason rather than a green row resting on an unchecked condition. The standing-in well-tie evidence is named in `layout/README.md`; a checked tie declaration (once expressible upstream) is what closes it.
- **unmet — items 1, 2, 9, 10 (`no_evidence`)**: the grader contract is explicit that these four name no `klt` verb and cannot be graded for topical relevance, and that leaving them uncited is the honest default ([`docs/design-evidence-tiers.md`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/design-evidence-tiers.md) → "Not every item has a tool behind it"). This repo follows that default deliberately: a met row here would only mean "some passing envelope was cited", not that the claim was checked.
- **unmet — item 5 (`no_evidence`; deliberately uncited, #55)**: no `klt sim` envelope exists for the ratified deterministic row (DR-0007 row 4, dropout), so none is cited. This is a tool/host limit, not an omission: the SG13CMOS5L DC bench needs OSDI models under ngspice >= 46, `klt sim`'s batch/remote backends refuse `ihp-sg13cmos5l` (existing upstream gap [klayout-tools#2727](https://github.com/2AMLogic/klayout-tools/issues/2727)), and local multi-corner grids are not permitted on the dispatch host. Hand-wrapping the committed CSVs into a sim-shaped envelope would be a synthesized success and is refused. What exists instead is **qualified, non-gating evidence** under [`sim/ldo-cmos5l-pvt-sweep/evidence/20260917-023832-7061e8f/`](../sim/ldo-cmos5l-pvt-sweep/evidence/20260917-023832-7061e8f/): a ten-row coverage inventory (`coverage-inventory.{json,md}`) and informational DC summaries (`dc-informational-summary.csv`), regenerated and byte-checked by `python3 sim/ldo-cmos5l-pvt-sweep/item5_evidence.py --check` (CI). **If a sim envelope is cited here later, read the grade carefully:** `klt signoff` accepts any `status: pass` sim envelope for item 5 and does not know which spec rows are ratified or Open, nor the SG13G2/SG13CMOS5L branch split. A green item 5 would mean "one cited corner run passed", not that the shared spec is verified: nine of ten rows are Open (DR-0007), the dropout definition is unresolved (#70), and the SG13G2 branch has no closed-loop evidence (#71). The inventory, not the grade, is the coverage statement.
- **unmet — items 6, 7 (`no_evidence`)**: item 6 needs `klt yield` Monte Carlo (#56) and item 7 needs `klt pex` (post-layout re-simulation, #57). Those envelopes will be cited as they are produced — never fabricated to turn a row green.

## Claim disclosures the grader cannot make for us

`klt signoff` reports (not grades) the conditions below; the claim is
incomplete unless they are stated alongside it. Both are part of this
directory's verdict-of-record statement.

- **Item 3's DRC deck coverage** — quoted verbatim from the cited envelope's
  own `coverage` block. The `status: clean` is measured strictly inside
  this scope:
  - `layers_in_stream_without_rules` (14 layers this layout draws that this
    deck carries no rule for): `6/0, 7/0, 8/2, 10/2, 14/0, 28/0, 30/2, 31/0,
    31/2, 44/0, 63/0, 99/39, 111/0, 128/0`
  - `rules_skipped` (11 rules, every one on metal levels above this
    layout's Metal1/Metal2/Metal3 + Via1/Via2 stack, none of which it
    draws): `metal3.enclosing.via3.1, metal4.enclosing.topvia1.1,
    metal4.space.1, metal4.width.1, topmetal1.enclosing.topvia1.1,
    topmetal1.space.1, topmetal1.width.1, topvia1.space.1,
    topvia1.width.1, via3.space.1, via3.width.1`
  - `deck_scope` (which DRM chapters the deck transcribes at all, 8):
    `5.16 Metal1, 5.17 Metaln, 5.19 Via1, 5.20 Vian, 5.21 TopVia1,
    5.22 TopMetal1, 5.5 Activ, 5.8 GatPoly`
- **Item 7 has no citation today, so no `body_bias` statement is attached** —
  exactly as the contract requires: an absent `body_bias` would mean "this
  artifact made no body-bias statement", and with no pex evidence there is
  no post-layout number to qualify.

## Item 8 pin refresh (#55)

The item-8 `content_hash` had gone stale on `main`: `characterization-report.json` pins the root `README.md`'s sha256, which moved in the documentation-guide update (#72) after the pin was written, so the pinned grading build rendered item 8 `unmet / stale_evidence` and `sim/characterization/generate.py --check` failed. This PR regenerated the characterization artifact (a one-line change: the README pin), updated the manifest pin to the new envelope input hash, and regenerated the report (the item returns to `met`; `t1_met_count` is 3 again). No measurement or verdict content changed.

## Regenerating

Item 8 first (its envelope is an input to the manifest's `content_hash` pin;
regenerate it whenever the selected record, `README.md`'s target table, or
DR-0007 changes — see [`sim/characterization/README.md`](../sim/characterization/README.md)):

```bash
python3 sim/characterization/generate.py          # then update the item-8 content_hash in sg13g2-ldo.json
python3 sim/characterization/generate.py --check  # what CI runs
```

Then the tier report:

From the repo root, with the pinned grading build installed (below):

```bash
klt signoff --manifest signoff/sg13g2-ldo.json --format json \
  > signoff/sg13g2-ldo.t1-report.json
```

Exit `0` means every T1 item met (`tier: "T1"`). Exit `3` is a successful,
honest **non-T1** run — the committed record carries code 3's shape today
and that is correct, not a failure. Exit `1` (error envelope) or a drift
between the regenerated and committed file is the rot this directory exists
to catch: regenerate, re-read this README's disclosures, and commit both in
the same PR as whatever moved the evidence.

The citations pin a `content_hash` — the input artifact each cited check
actually ran against (DRC/ERC: the committed GDS; LVS: the committed
extracted netlist) — and the report catches rot on two independent axes:

- **manifest pin vs the envelope's own recorded input hash** — a citation
  whose envelope ran against a different revision than the pin renders
  `unmet` / `stale_evidence`, never a pass.
- **the grader independently re-hashes the input itself** (`input_verified`
  on every met citation, #2196): an artifact whose bytes changed since the
  cited run flips that field to `false`, the regenerated report then
  differs from the committed record, and the CI gate fails — a passing
  report against a since-changed GDS or netlist cannot silently grade
  green. That drift path was verified by a planted-artifact negative
  control during #44 (tamper the GDS → `input_verified: false` → report
  drift → gate failure).

## The pinned grading build

The report's `build` block names the exact `klt` that graded it. The
envelope-grading rules this report depends on — the `erc` evidence kind,
compound item 11 grading, and input-artifact verification (`input_verified`,
which re-hashes the cited input rather than trusting the envelope's say-so)
— shipped upstream **after** the v0.5.0 release, so the manifest is graded
with the pinned post-release commit whose version stamp the ERC envelope
already records:

```bash
uv venv /tmp/klt-signoff-venv
uv pip install --python /tmp/klt-signoff-venv/bin/python \
  "klayout-tools @ git+https://github.com/2AMLogic/klayout-tools@b15edf5e3a2e56467a3406c98a2555eb1a5ae45c"
```

Bump the pin deliberately — in the same PR as the regenerated report —
when a `klt` release ships the item-11 grading rules; CI (the
`signoff-t1-report` job) fails on any drift between the pinned build's
output and the committed record, including that pin moving. The three layout
envelopes cited here were refreshed under this same build (see
`layout/README.md`'s drift note) so all cited evidence carries one uniform,
current-deck vintage with populated input hashes.

## Where the fleet reads this

`klt signoff --fleet` (2AMLogic/2am#956) discovers each block's manifest by
this convention; `block: sg13g2-ldo` is the row identity in the fleet
roll-up. `klt signoff --manifest signoff/sg13g2-ldo.json` (text format)
gives the human rendering of the same grade.
