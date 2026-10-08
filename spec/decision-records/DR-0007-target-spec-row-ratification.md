# DR-0007: Target-spec table — row-by-row ratification record

- **Status**: Proposed. **No row is ratified yet.** The two non-author
  review keys (`RATIFY-KEY: ee`, `RATIFY-KEY: market`) have not posted;
  every disposition below is the PR author's *proposal* to those keys. A
  row becomes ratified only when both verdicts land on this record's PR and
  any request-changes/escalate verdict is resolved (see "Review gates").
- **Date**: 2026-10-08
- **Scope**: Documentation and spec only (issue #54, part of the T1
  gap-to-tier tracker #5). Changes **no** target value, design, simulation,
  layout, or signoff artifact. Does **not** run the corner matrix (#55) or
  Monte Carlo (#56); it defines what they grade.
- **Related**: [`DR-0001`](DR-0001-pass-device-flavor.md) (pass-device
  flavor — a scope input, *not* a ratification of this table),
  [`DR-0002`](DR-0002-sg13cmos5l-device-topology.md) …
  [`DR-0006`](DR-0006-rhigh-family-width-offset-double-count.md),
  `ratification/ee-key/SKILL.md`, `ratification/market-key/SKILL.md`,
  `ratification/market-key/comps/ldo.md`.

## Context

The root `README.md` carried ten target rows labeled DRAFT. Existing
records settle device flavor and topology (DR-0001/0002), `Mpass` sizing and
compensation (DR-0003/0005), and the resistor-corner stability gap
(DR-0004); none ratifies the table, row by row.

### What evidence exists, and where it stops

1. **SG13G2 branch** (`design/ldo_core.sch`): only the bare pass-device
   screen `sim/pass-device-screening/` (DR-0001). The error amplifier is a
   behavioral VCVS placeholder, so there is **no closed-loop evidence on the
   SG13G2 branch** for any row.
2. **SG13CMOS5L branch** (`design/sg13cmos5l/`): the only closed-loop,
   corner-swept evidence in the repo. Its harness states it re-derives this
   same table at the same 3.3 V in / 1.8 V out pair with the same HV devices
   (`sim/ldo-cmos5l-pvt-sweep/README.md` "What this is"; `cornerMOShv.lib` is
   byte-identical between the two PDK trees, `sim/pdk-cmos5l.json`). All
   closed-loop citations below are therefore SG13CMOS5L-branch evidence.
   Reviewers should confirm that treating it as evidence for the shared
   table is acceptable; this record does not claim it as SG13G2-branch
   evidence.

### The evidence base (cited by path and content hash)

Base commit `fc3a5f3177b6115c2941b8785c20e4391c5a719e`.

| Artifact | sha256 |
|---|---|
| `sim/ldo-cmos5l-pvt-sweep/records/20260917-023832-7061e8f.md` | `531ecd3bf8473c657dc2030869ad71cc5b28e337ece46e45a3153a1124a73ffe` |
| `sim/ldo-cmos5l-pvt-sweep/records/20260917-023832-7061e8f.csv` | `cc90f70546403389093f3cc0927a7af06eb04febc9ce378a26be3fdf71c77c8d` |
| `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` | `c6e630e92fe012d16adf71229c99b52d8eb6cc4b85fffbb891108930acf11041` |
| `design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice` | `7982d728a2db933165eedcae69feaa4985dbddf54c269fc68b82d88577c8e38c` |

Record `20260917-023832-7061e8f` (45-point process x temperature x resistor
corner grid, three benches, 214/214 points ran) is the **latest** record. The
netlist under test last changed at commit `1a20b30` (DR-0005, `Cc`
`w=170e-6`, confirmed present in the current erramp netlist); the only later
commit touching `design/sg13cmos5l/` (`d7cede2`) changed schematic comments
only, so the record is not stale against the design. Provenance caveats,
disclosed rather than hidden: the record's git sha `7061e8f` does not resolve
in this clone (squash-merged), and the per-point netlist snapshots `.include`
the design netlist by an absolute worktree path rather than embedding it.
Freshness is therefore established by the `Cc` width and the unchanged
netlist history above, not by a resolvable hash in the record.

Standing caveats on the whole record, taken from the record itself: the
MoM-cap (`Cc`) model has no corner spread at this PDK pin, so every
loop-gain / phase-margin / PSRR result is labeled `insufficient-evidence`
by the record pending its `Cc` value sweeps; the loop-gain and PSRR benches
run at `Cout = 1 uF`, `ESR = 0`, `Iload = 1 mA`, `Vin = 3.30 V` only; the
reference is an ideal 0.90 V source.

## Dispositions

Each row takes exactly one of: **Ratified as written**, **Revised**, **Open**.
Because the review keys have not posted, a row that this author believes is
supported is shown as **Ratified as written (proposed — pending keys)**; it
is *not* ratified until both verdicts land. No row is Revised: no target was
changed, weakened, or strengthened, so the relax-after-measured-FAIL checks
(EE Step 5, market Step 5) do not trigger. The one measured FAIL in this
repo's history (phase margin at `res_bcs`/125 C, DR-0004) was closed by
re-compensating the design (DR-0005), not by moving the target.

Type: **D** = deterministic (decided by a process/temperature/supply corner
matrix); **S** = statistical (accuracy/offset/matching; a corner matrix alone
cannot ratify it — EE Step 2.2).

| # | Row | Current target | Disposition | Type | Evidence / missing evidence |
|---|---|---|---|---|---|
| 1 | Input | 3.3 V ±10 % | **Open** | D | Device flavor is ratified (DR-0001), and the ±10 % window is the supply range used by every sweep. Missing: DR-0001's carried-forward constraint that the (unbuilt) current-limit loop holds \|Vsg\| ≤ 3.3 V at Vin = 3.63 V across PVT under a continuous short — the bare device sees 3.63 V (DR-0001 "\|Vsg\| = 3.63 V vs 3.3 V finding"). No current limiter exists, so the upper end of the row has an unresolved device-rating gate. Also no normal-regulation \|Vgs\| check is recorded. |
| 2 | Output | 1.8 V ±2 % (fixed) | **Open** | **S** | Corner evidence: `vout_no_load_v` 1.80023–1.80066 V over all 45 points (record csv). Not sufficient: output accuracy includes error-amp input offset and divider mismatch, which a corner grid does not exercise (EE Step 2.2, item 6). Missing: Monte Carlo (→ #56). Also missing: a stated definition of the row's scope — the harness uses an ideal `VREF`, so the measurable quantity is regulator-only (excludes reference error, as the gf180 sibling's accuracy row does); the table does not say so. The wording needs a clarifying decision when #56 lands; not done here to avoid editing the target unprompted. |
| 3 | Load | 0–50 mA (no external preload assumed) | **Open** | D | DC regulation at 5 load points (0–50 mA) is swept at all 45 corners (`corners/20260917-023832-7061e8f/dcsweep_*`). Missing: any dynamic evidence at 0 mA — the loop-gain and PSRR benches run at 1 mA only, so "no external preload" stability is unevidenced. Stretch (100 mA) has no evidence and is not ratified. |
| 4 | Dropout @ 50 mA | < 300 mV worst corner | **Ratified as written (proposed — pending keys)** | D | Record csv `dropout_v_50ma`: 0.20–0.24 V over 45 points; binding corners ss/tt/fs at 125 C (0.24 V; +60 mV margin). Dropout is defined at the 1 % VOUT-loss point; 36/45 points sit at the sweep floor (0.20 V, `dropout_v_50ma_floor`), so those values are upper bounds — enough for a "<" row. DC and deterministic; the binding corner is the slow/hot one `spec/porting-plan.md` §1.4 anticipated. Not evidenced: the stretch (< 200 mV) — 9 hot-corner points exceed 0.20 V — so the stretch is not ratified. |
| 5 | Line / load regulation | < 5 mV/V; < 1 % over full load, inside the accuracy window | **Open** | D | Record csv: line 0.162–0.246 mV/V, load 0.0076–0.025 % over 45 points. Missing: both are measured under narrow conditions — line regulation at **no load only**, load regulation at **Vin = 3.63 V only** (record README "Why Vin=3.63V"). The row requires full load span and an in-window result; loaded line regulation and load regulation at 3.30/2.97 V are not reported by any committed record (the raw `dcsweep_*_dc.csv` in the same record would support them, but no committed analysis derives them). → #55. |
| 6 | PSRR | > 50 dB @ 1 kHz, > 20 dB @ 100 kHz | **Open** | D | Record csv: 53.64–57.37 dB @ 1 kHz (worst ss/125C/res_wcs, +3.64 dB), 33.23–37.00 dB @ 100 kHz. Missing: the result rests on the un-cornered `Cc` model (record labels it `insufficient-evidence`; the `Cc` tolerance window x0.65–x1.52 narrows but does not remove this), and PSRR is measured at 1 mA, 1 uF, Vin = 3.30 V only — not at 50 mA or over the Cout window. Margin is thin (3.6 dB) and was spent to close phase margin (DR-0005). Stretch (> 60 dB) is not met by the measured data and is not ratified. |
| 7 | Iq (excl. load) | < 30 uA at no load and at full load | **Open** | D | Record csv `iq_a` (no load): 21.72–24.72 uA over 45 points; margin +5.28 uA. Missing: the full-load half. The latest record does not report it; the earlier #25 record reported 23.05–23.08 uA full-load on a **superseded** netlist (pre-#28 divider, pre-#35 `Cc`), so it is stale. Stretch (< 10 uA) is not met. |
| 8 | Current limit | 65–80 mA brickwall over PVT; short-survivable | **Open** | **S** | Not implemented (record: "not implemented"). No evidence of any kind. The window is built from an on-chip sense threshold (resistor spread, mirror/sense mismatch), so the window-width claim will be statistical; the gf180 sibling's own window needed widening for resistor spread (`spec/porting-plan.md` §1.2). Gate carried from DR-0001 (row 1). Cannot be consumed by #55/#56 until a limiter exists. |
| 9 | Startup | monotonic, controlled ramp, inside ±2 % within 3 ms of enable | **Open** | D | Not implemented: no enable input and no transient testbench exist (record: "not implemented"). |
| 10 | Stability | 0–50 mA, C_out 0.33–4.7 uF effective, ESR 0–500 mΩ; PM ≥ 45°, GM ≥ 10 dB worst corner | **Open** | D | Record csv: PM 53.87–76.94° (worst ss/125C/res_bcs, +8.87°), GM 13.87–29.89 dB (worst ff/-40C/res_wcs, +3.87 dB) over 45 points — the 45° row was a measured FAIL at 5/45 points before DR-0005 and is now met at the grid. Missing: coverage of the row as written — only one (Cout, ESR, load) point of the 0–50 mA × 0.33–4.7 uF × 0–500 mΩ window (1 uF, 0 Ω, 1 mA) is simulated, and `Cc` is un-cornered. A plumbing-grade subset of the row, not the row. |

Tally: **1** proposed-ratified (row 4), **9** Open, **0** Revised. Open rows
remain visibly unratified and must not be treated as passing requirements.

Sibling precedent (EE Step 3): gf180-ldo ratified this same table via its
`DR-0004` (cited in `spec/porting-plan.md` §1.2); that is *method*, not
evidence, and no row above is proposed on sibling parity. Sibling records
were not re-fetched for this record; the plan's citations are relied on only
for what they state about the siblings' reasoning.

## Statistical rows (input to #56)

Surviving statistical rows, i.e. rows that need Monte Carlo to be ratified:

- **Row 2, Output accuracy** — implemented; the Monte Carlo (error-amp input
  pair offset, mirror mismatch, `rhigh` divider ratio mismatch, `Mpass` is not
  accuracy-relevant at DC loop gain ~121–125 dB) can run now against the
  proposed ±2 % bound. Note the `rhigh` double-count (DR-0006) shifts the
  absolute resistance but the divider ratio is set by two identical legs.
- **Row 8, Current limit window** — statistical by construction, but not
  implemented; #56 cannot grade it until a limiter exists. #56 should treat
  it as deferred, not as a pass.

Rows 1, 3, 4, 5, 6, 7, 9, 10 are classified deterministic (corner-decided).
Iq (row 7) and PSRR/stability (6, 10) have a mismatch sensitivity through the
bias mirrors; this record classifies them D because the cited margins are
corner-dominated, and flags the question for the EE key rather than
asserting it.

## Inputs to #55 (deterministic corner verification)

- **Row set**: all ten rows below; the pass/fail gate in
  `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh` still carries hard-coded thresholds
  that equal the unchanged targets here. It labels the table "DRAFT" in
  comments; that is a documentation lag, not a threshold difference.
- **Ratified (pending keys)**: row 4 only. #55 may treat its target as a
  gate once the keys land.
- **Open — must stay informational, not a pass/fail gate**, until closed:
  rows 1, 3, 5, 6, 7, 10 (deterministic, with the missing evidence named
  above, which is #55's scope to produce: full-load Iq, loaded line
  regulation, load regulation at the Vin corners, PSRR and stability over
  the stated load/Cout/ESR window with the `Cc` sensitivity) and rows 8, 9
  (blocked on unimplemented functions). Row 2 is #56's.

## Public competitive evidence (market-key input; no verdict here)

The author holds no market-key standing and gives no competitiveness
verdict. For the market key's convenience only, this is the starting data:
`ratification/market-key/comps/ldo.md` (generated 2026-08-24 from sources
fetched 2026-08-20; 49 days old at this record's date, no staleness flag).
It covers TI TLV70018 and TPS7A02 and Diodes AP7215 and AP2210. Rows with
no comp in that snapshot: Load stability window, current-limit window,
startup time, line/load regulation. The live-source delta check and any
update to the comp data belong to the market reviewer's comment, not to a
hand edit of the generated snapshot (which this PR does not touch). In scope
for the market key by `ratification/market-key/SKILL.md` Step 1: rows 2–10
(externally observable); row 1 (input range) is an interoperability
constant; any process/device-choice question (DR-0001) is EE-key only.

## Review gates

- [ ] `RATIFY-KEY: ee` verdict from a non-author identity, in the installed
  format, per row.
- [ ] `RATIFY-KEY: market` verdict from a non-author identity, in the
  installed format.
- [ ] Any request-changes / escalate verdict resolved before the affected
  row is called ratified.

Until all three are checked, the README renders every row as either
"proposed — pending review" (row 4) or "OPEN — unratified" (all others).
The author (this PR's builder) is not eligible to post either marker and has
not.

## Consequences

- `README.md` replaces the table-wide DRAFT status with per-row status and
  links here; `spec/README.md` describes the populated spec surface.
- Closing an Open row is a new, appended evidence record plus a follow-up
  edit to this table (or a superseding DR) that cites it; targets are not
  edited to match measurements.
- The unresolved `Input` / current-limit gate from DR-0001 is now visible in
  the table instead of only in a decision record.

## References

- Issue #54; downstream #55 (deterministic corner verification), #56
  (Monte Carlo); parent #5.
- `sim/ldo-cmos5l-pvt-sweep/README.md`, records cited above.
- `sim/pass-device-screening/records/20260909-220347-ed18110.{md,csv}`.
- `spec/porting-plan.md` §1.2, §1.4.
