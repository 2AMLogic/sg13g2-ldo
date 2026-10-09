# signoff/ — klt signoff block manifest and the T1 verdict of record

This directory is this repo's machine-graded **gap-to-T1** state (#44). Issue
#5's hand-maintained checkbox list is retired: the **committed block manifest
is the input**, the **committed tier report is the verdict of record**, and
both are regenerated and gated in CI — so the state cannot go silently stale
the way a hand-read checklist does.

| File | What it is |
| --- | --- |
| `sg13g2-ldo.json` | The **block manifest** for `klt signoff --manifest`: `block: sg13g2-ldo`, `kind: analog`, and one pinned evidence citation per T1 item this repo can honestly cite. |
| `sg13g2-ldo.t1-report.json` | The **verdict of record**: the exact `klt signoff --manifest sg13g2-ldo.json --format json` output, committed. `t1_item_count: 11, t1_met_count: 4, tier: null` — this block is **not T1 yet**, and the report says so per item with a `reason`. |

## Reading the report

Today's honest read is **4/11 met**:

- **met — item 3 (DRC clean)**: `layout/sg13cmos5l-ldo_core_cmos5l/drc_report.json`, `status: clean`, 0 violations, citation verified against the committed GDS (`input_verified: true`).
- **met — item 4 (LVS clean)**: `layout/sg13cmos5l-ldo_core_cmos5l/lvs_report.json`, `status: match`, 0 errors / 0 mismatches, citation verified against the committed extracted netlist it compared.
- **met — item 8 (characterization report)**: `sim/characterization/characterization-envelope.json`, a hand-rolled `kind: generic` envelope (the one evidence kind item 8 accepts) with `t1_item: 8`, pinned by `content_hash` to the sha256 of the committed aggregate report. **What `met` means here, and what it does not**: the envelope verdict is *artifact completeness and freshness* — every one of the ten target-spec rows appears exactly once with an explicit state, every selected source record matches its sha256 pin, the 45-point PVT grid is whole, and the record is current against the design netlists. It is **not** a claim that the circuit meets its spec: the report lists failing/ambiguous/unmeasured/unimplemented/unratified rows as such (today: 1 not measured, 5 partial-coverage passes, 1 full-coverage pass on the one ratified row, 1 ambiguous, 2 not implemented), and no post-layout performance evidence exists. `klt signoff` does **not** inspect the envelope's `source`, nor re-hash the report (`input_verified: null` for generic envelopes); the content and freshness are verified by this repo's generator and its CI `--check` gate (`python3 sim/characterization/generate.py --check`), which is what makes the pin trustworthy. Other T1 items are not touched by this citation.
- **met — item 11 (power delivery, structural)**: `layout/sg13cmos5l-ldo_core_cmos5l/erc_supply_report.json` (with item 4's LVS report as the second part), `input_verified: true`. VIN/VOUT/VSS each resolve to one island, zero `erc.supply_short`, zero `erc.missing_tie` from three **checked** ties (`nwell_tie_VIN`, `nwell_tie_TAIL`, `substrate_tie_VSS`; `erc_coverage.skipped` empty, nothing `degenerate_*`). **What `met` means here, and what it does not** (the claimant-side disclosures the grader does not enforce): every tie rests on a *caller assertion* — the report's `power_delivery` block lists all three under both `ties_checked_by_assertion` (tap boxes) and `ties_checked_by_well_assertion` (the well side: `well_requires_boxes` selects which NWell each n-tie is about, and the substrate tie sits in native substrate, so its region is asserted via `well_layer: null` + `well_boxes`). The boxes are not hand-typed: they are the generator's own `draw_tap_bar` calls (`layout/sg13cmos5l-ldo_core_cmos5l/erc-tap-boxes.json`, verified against the spec by `layout/erc_ties.py --check` in `layout/run_flow.sh`), and the n-ties are additionally layer-narrowed (`tap_requires` nSD), which this stream can express because it draws implants. The substrate tie's asserted region is the tap bar grown by 20 µm (the PDK deck's LU.b reach), so `erc_coverage.well_assertion_coverage` reports `uncovered_tap_fraction ≈ 0.977`: tap geometry elsewhere in the layout (every n+ source/drain contact is Activ too) was never examined by that tie, only the NMOS-group region was. `erc_coverage.layers_in_stream_without_declaration` is `28/0, 31/2, 44/0, 63/0, 99/39, 111/0` (marker/label layers carrying no routing). A tie-box mutation control (one tap box moved off its tap) MUST raise `erc.missing_tie`; `layout/run_flow.sh` stage 8b runs it. Connectivity of the taps beyond "a contacted tap reaches the net" is `klt lvs`'s job (item 4).
- **unmet — items 1, 2, 9, 10 (`no_evidence`)**: the grader contract is explicit that these four name no `klt` verb and cannot be graded for topical relevance, and that leaving them uncited is the honest default ([`docs/design-evidence-tiers.md`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/design-evidence-tiers.md) → "Not every item has a tool behind it"). This repo follows that default deliberately: a met row here would only mean "some passing envelope was cited", not that the claim was checked.
- **unmet — item 5 (`no_evidence`; deliberately uncited, #55)**: no `klt sim` envelope exists for the ratified deterministic row (DR-0007 row 4, dropout), so none is cited. This is a tool/host limit, not an omission: the SG13CMOS5L DC bench needs OSDI models under ngspice >= 46, `klt sim`'s batch/remote backends refuse `ihp-sg13cmos5l` (existing upstream gap [klayout-tools#2727](https://github.com/2AMLogic/klayout-tools/issues/2727)), and local multi-corner grids are not permitted on the dispatch host. Hand-wrapping the committed CSVs into a sim-shaped envelope would be a synthesized success and is refused. What exists instead is **qualified, non-gating evidence** under [`sim/ldo-cmos5l-pvt-sweep/evidence/20260917-023832-7061e8f/`](../sim/ldo-cmos5l-pvt-sweep/evidence/20260917-023832-7061e8f/): a ten-row coverage inventory (`coverage-inventory.{json,md}`) and informational DC summaries (`dc-informational-summary.csv`), regenerated and byte-checked by `python3 sim/ldo-cmos5l-pvt-sweep/item5_evidence.py --check` (CI). **If a sim envelope is cited here later, read the grade carefully:** `klt signoff` accepts any `status: pass` sim envelope for item 5 and does not know which spec rows are ratified or Open, nor the SG13G2/SG13CMOS5L branch split. A green item 5 would mean "one cited corner run passed", not that the shared spec is verified: nine of ten rows are Open (DR-0007), the dropout definition is unresolved (#70), and the SG13G2 branch has no closed-loop evidence (#71). The inventory, not the grade, is the coverage statement.
- **unmet — item 6 (`no_evidence`), with real but deliberately uncited evidence.** See "Item 6 coverage statement" below.
- **unmet — item 7 (`no_evidence`)**: item 7 needs `klt pex` (post-layout re-simulation, #57). That envelope will be cited when it is produced — never fabricated to turn a row green.

## Item 6 coverage statement

T1 item 6 covers **every** statistical row of the target spec. DR-0007 classifies two:

| Row | Ratification | Monte Carlo evidence | Status for item 6 |
|---|---|---|---|
| 2 — Output 1.8 V ±2 % | **Open** (unratified) | `sim/ldo-cmos5l-monte-carlo/` (issue #56): SG13CMOS5L, regulator-only accuracy (ideal 0.90 V reference, reference error excluded), Vin 3.30 V, no load. PDK MOS + `rhigh` mismatch at five process/temperature corners, N = 400 each, fixed seeds, deterministic negative control, per-population `klt yield` reports. Results are in that experiment's record. | Evidence against a **proposed** window, not a ratified one |
| 8 — Current limit 65–80 mA | **Open** | none: no limiter exists (#63) | **Deferred**, not "no statistical row" |

**Why item 6 stays uncited.** The pinned grading build marks item 6 `met` as soon as one cited `klt yield` envelope has `status` `pass` or `reported` (`signoff.py` at `b15edf5e`: `passed = envelope.get("status") in ("pass", "reported")`). A manifest entry carries only `file`/`command`/`cwd`/`content_hash`. There is no way to tell the grader that the block has two statistical rows, that the citation covers only one, or that its target is unratified. Citing a row-2 yield report would therefore publish item 6 as satisfied while row 8 has no evidence and row 2's target is Open. That presents partial coverage as full, which #56's acceptance criteria rule out. Uncited, the item reads `no_evidence`. That is also inaccurate (the row-2 evidence exists), and this statement exists to correct it. The tool gap is filed as klayout-tools#2908.

The campaign is ready to cite once item 6 can be graded honestly, i.e. once row 2 is ratified, row 8 has its own campaign, and the grader can express row coverage. Its per-population `klt yield` reports sit beside their sample-set documents, so each report's `samples` field resolves relative to the report itself. That is the input the grader re-hashes for a yield citation's `content_hash`. The experiment's record shows what a citation would grade to today, plus a tamper check on a copy.

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

The item-8 `content_hash` had gone stale on `main`: `characterization-report.json` pins the root `README.md`'s sha256, which moved in the documentation-guide update (#72) after the pin was written, so the pinned grading build rendered item 8 `unmet / stale_evidence` and `sim/characterization/generate.py --check` failed. This PR also edits a second pinned source, `sim/ldo-cmos5l-pvt-sweep/README.md` (the `superseded_evidence_statement`; it gains the item-5 evidence section). The characterization artifact was therefore regenerated *after* the last edit to either file, and exactly two source pins changed, one line each in `characterization-report.{json,md}`:

- `target_table` `README.md`: `3d8f46e2…` → `29c85891…` (#72)
- `superseded_evidence_statement` `sim/ldo-cmos5l-pvt-sweep/README.md`: `073e2f4e…` → `56db1791…` (#55)

The envelope's `provenance.input.content_hash`, the manifest's item-8 `content_hash` and the cited `content_hash` in `sg13g2-ldo.t1-report.json` all moved from `sha256:5c1393fa…` to `sha256:3db06e10…` (the sha256 of the regenerated report). The tier report was regraded with the pinned build `0.5.0+gb15edf5e3a2e` (exit 3, item 8 `met`, `t1_met_count` 3). No measurement, row state or verdict content changed. Any later edit to a pinned source (see `characterization-report.json` → `sources`) needs the same regeneration in the same order: `generate.py`, then the manifest pin, then the tier report.

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
  "klayout-tools @ git+https://github.com/2AMLogic/klayout-tools@b82427b30c9604b53b2dce64850409841cc38bde"
```

Bump the pin deliberately — in the same PR as the regenerated report —
when a `klt` release ships the item-11 grading rules; CI (the
`signoff-t1-report` job) fails on any drift between the pinned build's
output and the committed record, including that pin moving. **Pin bump (#59).** The pin moved from `b15edf5e3a2e` to `b82427b30c96` (`0.7.0+gb82427b30c96`) because the item-11 tie declaration needs `ties[].well_layer: null` + `well_boxes` (klayout-tools#2255) and `ties[].well_requires_boxes` (#2540), which the old build rejects at spec-parse. Regrading the unchanged manifest under the new build changed no item's status (items 3, 4, 8 stay met); only the build block, the grader's item text and `grading_ruleset_id` moved, plus item 11 flipping to met. The new build also rejects unrecognised spec keys (#2243), so the free-form `_comment` array the ERC spec used to carry is gone: its rationale now lives in `layout/sg13cmos5l-ldo_core_cmos5l/erc-supply-spec.md`. **The item 3/4 envelopes were deliberately NOT regenerated**: re-running `layout/run_flow.sh` under the new build changes the `klt extract` netlist dialect (`X... cap_cmomi`/`X... rhigh r=` cards instead of `XD_`/`R` cards), which the committed LVS reference no longer matches, so stages 2-7 of the flow are not reproducible with the pinned-new build until the reference writer is updated. The root `README.md` status line (3 -> 4 of 11) is a pinned item-8 source, so `sim/characterization/generate.py` was re-run and the item-8 pin moved to `sha256:0593923a…`. That is separate work; item 3/4 evidence keeps its original vintage and still grades `met` with `input_verified: true`.

The DRC and LVS
envelopes cited here were refreshed under the previous build (see
`layout/README.md`'s drift note) and carry populated input hashes; the ERC
envelope is from the current build.

## Where the fleet reads this

`klt signoff --fleet` (2AMLogic/2am#956) discovers each block's manifest by
this convention; `block: sg13g2-ldo` is the row identity in the fleet
roll-up. `klt signoff --manifest signoff/sg13g2-ldo.json` (text format)
gives the human rendering of the same grade.
