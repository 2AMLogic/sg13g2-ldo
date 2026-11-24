# DR-0007: Target-spec table — row-by-row ratification record

- **Status**: Ratified for **row 4 only** (Dropout @ 50 mA, target as
  written; stretch not ratified). The other six rows are **Open** and
  unratified. Rows **2**, **5** and **7** are **proposed** to the two review
  keys as "Ratified as written (proposed — pending keys)" by the PR that
  carries this amendment (issue #318, 2026-11-24); **no row beyond row 4 is
  ratified**, and none becomes ratified by this amendment — that act is the
  two non-author review keys (`RATIFY-KEY: ee`, `RATIFY-KEY: market`)
  posting releasing verdicts on that PR, then the operator. Row 4's
  ratification act was the same keys on pull request #65, the PR that
  carried that status change (issue #54). That PR merged only after both
  keys posted releasing verdicts; had they not, it would have been closed
  unmerged and this record stayed as it merged in PR #61 (Proposed, no row
  ratified). The #318 PR merges only after both keys post releasing
  verdicts on it and the operator ratifies; if they do not, it is closed
  unmerged and rows 2, 5 and 7 revert to Open. See "Ratification note
  (2026-10-08)" and "Proposal note (2026-11-24)" at the end of this record
  for exactly what changed each time.
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
Row 4 was shown as "Ratified as written (proposed — pending keys)" when this
record first merged (PR #61), before either review key had posted; it is
ratified by the two key verdicts on pull request #65. The same pending-keys
vocabulary carries the 2026-11-24 proposal (issue #318): the cells for rows
2, 5 and 7 read "Ratified as written (proposed — pending keys)" while the
two keys are outstanding on that PR, and a proposed row is exactly as
unratified as an Open one. No row is Revised: no target was
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
| 2 | Output | 1.8 V ±2 % (fixed) | **Ratified as written (proposed — pending keys)** | **S** | Monte Carlo (record `sim/ldo-cmos5l-monte-carlo/records/20261012-093854-934dbd7/`): five populations x 400 draws, 2000/2000 inside 1.764–1.836 V; ≥ 99.08 % at 95 % confidence per population (≥ 98.3–98.9 % excluding the 368 recovered-solve draws); normal fit 3.27–3.78 σ from the nearest limit (Cpk 1.09–1.26); deterministic negative control detected. Attribution: MOS mismatch 83 % of variance, `rhigh` 4.540 mV σ alone, RSS ratio 1.02. Proposed scope wording (to the keys; the ±2 % number is not edited): the row is a **regulator-only** accuracy claim — reference error excluded and carried by the reference block's own spec, as the gf180 sibling's accuracy row scopes it. Qualifications: ideal 0.90 V reference; EN tied to VIN; five named corners stand in for global statistical sampling; no `Vin`/load variation; no post-layout evidence; supports a 99 %-class claim, not 3σ. Full hashes in "Proposed evidence (2026-11-24)". |
| 3 | Load | 0–50 mA (no external preload assumed) | **Open** | D | DC regulation at 5 load points (0–50 mA) is swept at all 45 corners (`corners/20260917-023832-7061e8f/dcsweep_*`). Missing: any dynamic evidence at 0 mA — the loop-gain and PSRR benches run at 1 mA only, so "no external preload" stability is unevidenced. Stretch (100 mA) has no evidence and is not ratified. |
| 4 | Dropout @ 50 mA | < 300 mV worst corner | **Ratified as written** | D | Record csv `dropout_v_50ma`: 0.20–0.24 V over 45 points; binding corner ss at 125 C (0.24 V; +60 mV margin), with tt and fs at 125 C at 0.21 V and 0.22 V. Dropout is defined at the 1 % VOUT-loss point; 36/45 points sit at the sweep floor (0.20 V, `dropout_v_50ma_floor`), so those values are upper bounds — enough for a "<" row. DC and deterministic; the binding corner is the slow/hot one `spec/porting-plan.md` §1.4 anticipated. Not evidenced: the stretch (< 200 mV) — 9 hot-corner points exceed 0.20 V — so the stretch is not ratified. |
| 5 | Line / load regulation | < 5 mV/V; < 1 % over full load, inside the accuracy window | **Ratified as written (proposed — pending keys)** | D | Graded `klt sim` envelope `sim/ldo-cmos5l-pvt-sweep/row5-envelope/20261123-213711-06bd6576/`: 45/45 corners pass (the verdict is the tool's own — limits declared in `request.json`, line and load regulation graded as derived expr measurements over `analysis_steps`, never computed by repo Python). Worst line 0.243766 mV/V (`ff`/125 C/`res_wcs`) against 5 mV/V; worst load 0.0241452 % (`ff`/125 C/`res_wcs`) against 1 %. The prior gaps (line at no load only, load at 3.63 V only) are closed by construction: line is graded at Iload 0, 25 and 50 mA, load at Vin 2.97, 3.30 and 3.63 V. Qualifications: ideal 0.90 V reference; **discrete sampling only** (those three loads and three supplies, not a continuous-window claim); the row's "inside the accuracy window" coupling to row 2 is **not demonstrated** by this envelope; schematic level, corner grid only, no Monte Carlo; core without the #190 limiter. Full hashes in "Proposed evidence (2026-11-24)". |
| 6 | PSRR | > 50 dB @ 1 kHz, > 20 dB @ 100 kHz | **Open** | D | Record csv: 53.64–57.37 dB @ 1 kHz (worst ss/125C/res_wcs, +3.64 dB), 33.23–37.00 dB @ 100 kHz. Missing: the result rests on the un-cornered `Cc` model (record labels it `insufficient-evidence`; the `Cc` tolerance window x0.65–x1.52 narrows but does not remove this), and PSRR is measured at 1 mA, 1 uF, Vin = 3.30 V only — not at 50 mA or over the Cout window. Margin is thin (3.6 dB) and was spent to close phase margin (DR-0005). Stretch (> 60 dB) is not met by the measured data and is not ratified. |
| 7 | Iq (excl. load) | < 30 uA at no load and at full load | **Ratified as written (proposed — pending keys)** | D | Graded `klt sim` envelope `sim/ldo-cmos5l-pvt-sweep/row7-envelope/20261121-001957-ed6b0587/`: 45/45 corners pass over the full Input-row supply window at **both** load states — six graded figures (Vin 2.97/3.30/3.63 V x Iload 0/50 mA), all carrying `limits` so the verdict is the tool's own (derived expr measurements over `analysis_steps`; never computed by repo Python). Worst no-load 24.4980 uA (`ss`/125 C/`res_bcs`; margin 5.5020 uA); worst full-load 24.6675 uA (`ff`/125 C/`res_bcs`; margin 5.3325 uA) — the previously missing full-load half. Measurement is \|i(VIN)\| − Iload, the same quantity the legacy base recorded as `iq_a` (includes the 2 uA mirror-reference leg and divider standing current). **#190 limiter disclosure (DR-0017 §5 "Iq")**: the limiter's comparator tail adds ≈ 1 uA typical, up to ≈ 3–4 uA at `VIN` = 3.63 V and `res_bcs`/125 C [C/A]; summed with the worst measured point that is ≈ 28–29 uA [C] against 30 uA — a thin margin from a conservative sum (the two worst corners need not coincide; DR-0017's sum used the then-current 24.72 uA worst point, and this envelope's worst is 24.67/24.50 uA). The PVT records go stale when the limiter is integrated and this evidence is for the present core **without** it; it must be re-run when #190 lands. Other qualifications: ideal 0.90 V reference; ideal 2 uA `IBIAS` sink (the sunk 2 uA itself flows through the core and IS included; no bias-generator current is); corner grid only, no Monte Carlo. Stretch (< 10 uA) is not met and is not proposed. Full hashes in "Proposed evidence (2026-11-24)". |
| 8 | Current limit | 65–80 mA brickwall over PVT; short-survivable | **Open** | **S** | Not implemented (record: "not implemented"). No evidence of any kind. The window is built from an on-chip sense threshold (resistor spread, mirror/sense mismatch), so the window-width claim will be statistical; the gf180 sibling's own window needed widening for resistor spread (`spec/porting-plan.md` §1.2). Gate carried from DR-0001 (row 1). Cannot be consumed by #55/#56 until a limiter exists. |
| 9 | Startup | monotonic, controlled ramp, inside ±2 % within 3 ms of enable | **Open** | D | Not implemented: no enable input and no transient testbench exist (record: "not implemented"). |
| 10 | Stability | 0–50 mA, C_out 0.33–4.7 uF effective, ESR 0–500 mΩ; PM ≥ 45°, GM ≥ 10 dB worst corner | **Open** | D | Record csv: PM 53.87–76.94° (worst ss/125C/res_bcs, +8.87°), GM 13.87–29.89 dB (worst ff/-40C/res_wcs, +3.87 dB) over 45 points — the 45° row was a measured FAIL at 5/45 points before DR-0005 and is now met at the grid. Missing: coverage of the row as written — only one (Cout, ESR, load) point of the 0–50 mA × 0.33–4.7 uF × 0–500 mΩ window (1 uF, 0 Ω, 1 mA) is simulated, and `Cc` is un-cornered. A plumbing-grade subset of the row, not the row. |

Tally: **1** ratified (row 4), **3** proposed-ratified pending keys (rows 2,
5, 7), **6** Open, **0** Revised. Proposed and Open rows alike remain
visibly unratified and must not be treated as passing requirements.

Sibling precedent (EE Step 3): gf180-ldo ratified this same table via its
`DR-0004` (cited in `spec/porting-plan.md` §1.2); that is *method*, not
evidence, and no row above is proposed on sibling parity. Sibling records
were not re-fetched for this record; the plan's citations are relied on only
for what they state about the siblings' reasoning.

## Proposed evidence (2026-11-24): rows 2, 5, 7

The artifacts the three proposed dispositions rest on, cited by path and
content hash. The two graded envelopes' `tb.spice` hashes are the same pins
`signoff/sg13g2-ldo.json` item 5 cites (the grader re-hashes that input);
the `report.json` hashes pin the graded envelopes themselves. All hashes
re-compute against the tree this amendment was written on.

### Row 2 — Output 1.8 V ±2 % (Monte Carlo, record `20261012-093854-934dbd7`)

| Artifact | sha256 |
|---|---|
| `sim/ldo-cmos5l-monte-carlo/records/20261012-093854-934dbd7.md` | `77820f8533f90e64231db5419bddfc3e7d531915819fec8151e656c3e2a4e33f` |
| `sim/ldo-cmos5l-monte-carlo/records/20261012-093854-934dbd7.csv` | `563169ece2536f3b9ccd77370e5d6b35edbbcaa7cab2f878ae52cb5dbde96e50` |
| `sim/ldo-cmos5l-monte-carlo/tb_row2_accuracy_en.spice` (bench, closure-pinned) | `6cc1467a7ba54bab357cd89dd4a47f239c429c516e17c4e379333767e6d26800` |
| `sim/ldo-cmos5l-monte-carlo/runner-preamble.cir` (closure-pinned) | `24a2581f33183c67a7cb530519c44b8637cd339e28ce753aff0e48303a53e4bf` |
| `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` (closure-pinned) | `08a7b857e1fad43dd7af1f575de97853a058e85541601ecc47567fbc28dbae57` |

The five per-population `klt yield` reports this record's results table
summarizes are pinned, with the same hashes, by the item-6 citations in
`signoff/sg13g2-ldo.json` (they are the row-2 citations and predate this
amendment; #225). The record's `environment.netlist_closure` pins the three
closure files above by sha256 and the committed files hash identically, so
the campaign is current against the design and is **not** re-run by this
amendment.

### Row 5 — Line / load regulation (graded envelope `20261123-213711-06bd6576`)

| Artifact | sha256 |
|---|---|
| `sim/ldo-cmos5l-pvt-sweep/row5-envelope/20261123-213711-06bd6576/report.json` | `a517f1baed1174587bc27345448405be0d4e6b533cedc1d82bc1e94e6723ae59` |
| `sim/ldo-cmos5l-pvt-sweep/row5-envelope/20261123-213711-06bd6576/tb.spice` (input the grader re-hashes; the item-5 pin) | `c3cfe8aa41210aae5dff484ee35a3f53bb0e46747e6ff54399301cef3f0b802b` |
| `sim/ldo-cmos5l-pvt-sweep/row5-envelope/20261123-213711-06bd6576/request.json` | `25abf4d965212c1ef41526e3ce3797008638fc035884643f396afb539b19a85c` |

This is the definitive row-5 record (45/45 corners, every coordinate exactly
once, all eight steps ok at every corner, no error-severity diagnostics,
definitive-matrix-claim permitted). The `-probe` record beside it
(`20261123-213537-06bd6576-probe`) is a fleet probe and is never cited.

### Row 7 — Iq excluding load (graded envelope `20261121-001957-ed6b0587`)

| Artifact | sha256 |
|---|---|
| `sim/ldo-cmos5l-pvt-sweep/row7-envelope/20261121-001957-ed6b0587/report.json` | `06ad1829a873421ffe0bc512c57dfd8c8e383725c48fa30a9edbde0699485fd9` |
| `sim/ldo-cmos5l-pvt-sweep/row7-envelope/20261121-001957-ed6b0587/tb.spice` (input the grader re-hashes; the item-5 pin) | `d1101e8225423b91b6f462df3aedfc2b68ec1e2995c7de101662214451baa279` |
| `sim/ldo-cmos5l-pvt-sweep/row7-envelope/20261121-001957-ed6b0587/request.json` | `11d77497c9582d990832321803f87471e58245a648b6849d780e3ae2f33d0a07` |

This is the definitive row-7 record (45/45 corners, all six steps ok at
every corner, no error-severity diagnostics, definitive-matrix-claim
permitted). The `20261123-*` records beside it are the paired
tight-tolerance sensitivity runs (`row7-pair.json`); they quantify observed
solver sensitivity and are not citation candidates. The envelope's input
sha256 list pins the same core and error-amplifier netlist hashes as the
Monte Carlo closure above, so all three proposals rest on one design.

## Statistical rows (input to #56)

Surviving statistical rows, i.e. rows that need Monte Carlo to be ratified:

- **Row 2, Output accuracy** — implemented and measured. The Monte Carlo
  (error-amp input pair offset, mirror mismatch, `rhigh` divider ratio
  mismatch, `Mpass` is not accuracy-relevant at DC loop gain ~121–125 dB)
  has run against the proposed ±2 % bound: record
  `sim/ldo-cmos5l-monte-carlo/records/20261012-093854-934dbd7/` (five
  populations × 400 draws; per-population `klt yield` reports cited under
  T1 item 6 in `signoff/sg13g2-ldo.json` against the still-unratified row).
  Proposed to the keys with the 2026-11-24 amendment, together with the
  row's scope wording: a **regulator-only** accuracy claim, reference error
  excluded and carried by the reference block's own spec (the harness's
  ideal `VREF` makes that the measurable quantity; the gf180 sibling's
  accuracy row scopes it the same way). The ±2 % number is not edited.
  Note the `rhigh` double-count (DR-0006) shifts the
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
- **Ratified**: row 4 only. #55 may treat its target as a gate.
- **Proposed — pending keys (2026-11-24), still informational, not a
  pass/fail gate**: rows 5 and 7 now have graded `klt sim` envelope
  evidence (the records cited in "Proposed evidence (2026-11-24)"); the
  missing evidence this record previously named for them — full-load Iq,
  loaded line regulation, load regulation at the Vin corners — is what
  those envelopes supply. Until both keys release the proposal and the
  operator ratifies, #55 keeps treating rows 5 and 7 as informational.
- **Open — must stay informational, not a pass/fail gate**, until closed:
  rows 1, 3, 6, 10 (deterministic, with the missing evidence named
  above, which is #55's scope to produce: PSRR and stability over
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

- [x] `RATIFY-KEY: ee` verdict from a non-author identity, in the installed
  format, per row: the EE-key review on pull request #65.
- [x] `RATIFY-KEY: market` verdict from a non-author identity, in the
  installed format: the market-key review on pull request #65.
- [x] Any request-changes / escalate verdict resolved before the affected
  row is called ratified.

These three boxes are checked by pull request #65, and they are true only
if that PR merged: it carries the two key reviews and merges only after both
post releasing verdicts. The reviews themselves (verdict tokens, per-row
tables, sources, and the market key's source-freshness check of the comp
snapshot) are on that PR and are not restated here. No author of
this record or of either PR that carried it posted either marker.

### Gates for the 2026-11-24 proposal (rows 2, 5, 7; issue #318)

- [ ] `RATIFY-KEY: ee` verdict from a non-author identity, in the installed
  format (`ratification/ee-key/SKILL.md` "Output format"), per row, on this
  amendment's PR.
- [ ] `RATIFY-KEY: market` verdict from a non-author identity, in the
  installed format (`ratification/market-key/SKILL.md` "Output format"), on
  the same PR.
- [ ] Any request-changes / escalate verdict resolved, and the operator's
  ratification recorded, before any of rows 2, 5, 7 is called ratified.

These boxes are unchecked because no key has posted on the proposal PR. The
PR author posts neither marker (the author is not a non-author identity for
their own proposal). The PR merges only after both keys post releasing
verdicts and the operator ratifies; if that does not happen it is closed
unmerged and rows 2, 5 and 7 revert to Open. Until then the README renders
row 4 as RATIFIED, rows 2, 5 and 7 as "PROPOSED — pending keys", and the
other six rows as "OPEN — unratified".

## Consequences

- `README.md` replaces the table-wide DRAFT status with per-row status and
  links here; `spec/README.md` describes the populated spec surface.
- Closing an Open row is a new, appended evidence record plus a follow-up
  edit to this table (or a superseding DR) that cites it; targets are not
  edited to match measurements.
- The unresolved `Input` / current-limit gate from DR-0001 is now visible in
  the table instead of only in a decision record.

## Ratification note (2026-10-08)

This record first merged in PR #61 with every disposition a proposal and no
row ratified. Pull request #65 (issue #54) is the PR the two review keys
were applied to. It changes this record in four places and nowhere else:

1. **Status** now reads "Ratified for row 4 only". The Status text as first
   merged is preserved here verbatim:

   > **Status**: Proposed. **No row is ratified yet.** The two non-author
   > review keys (`RATIFY-KEY: ee`, `RATIFY-KEY: market`) have not posted;
   > every disposition below is the PR author's *proposal* to those keys. A
   > row becomes ratified only when both verdicts land on this record's PR and
   > any request-changes/escalate verdict is resolved (see "Review gates").

2. **Row 4's disposition** drops the "(proposed — pending keys)" qualifier.
   The target, the stretch entry and the evidence are unchanged, and the
   stretch (< 200 mV) is still not ratified.
3. **Row 4's corner citation is corrected.** The record first said the
   binding corners were "ss/tt/fs at 125 C (0.24 V)". The cited csv
   (`sim/ldo-cmos5l-pvt-sweep/records/20260917-023832-7061e8f.csv`, sha256
   unchanged from the table above) shows that only ss at 125 C reaches
   0.24 V, at all three resistor corners; tt at 125 C is 0.21 V and fs at
   125 C is 0.22 V. The maximum (0.24 V), the +60 mV margin against the
   < 300 mV target, and the count of points above the 0.20 V sweep floor
   (9 of 45) are unaffected.
4. **The "pending keys" wording** in the tally, the #55 input list and the
   review gates is updated to match.

Rows 1–3 and 5–10 keep the dispositions and the named missing evidence they
merged with: all nine stay **Open**. No target value changed, no row was
revised, and no evidence was added, so the relax-after-measured-FAIL checks
still do not trigger.

## Proposal note (2026-11-24)

Issue #318's PR (child of #316, part of #5) proposes rows **2**, **5** and
**7** to the two review keys. It changes this record and nowhere else in
`spec/`:

1. **Status** now reads "Ratified for row 4 only … Rows 2, 5 and 7 are
   proposed … (proposed — pending keys)". Row 4's ratified state, and the
   PR #61 / #65 history, are unchanged.
2. **Rows 2, 5 and 7 dispositions** move from **Open** to **Ratified as
   written (proposed — pending keys)**, with their evidence cells rewritten
   to the records that close the previously named gaps: the row-2 Monte
   Carlo record `20261012-093854-934dbd7` (was "Missing: Monte Carlo"), the
   row-5 graded envelope `20261123-213711-06bd6576` (was "line at no load
   only, load at 3.63 V only"), the row-7 graded envelope
   `20261121-001957-ed6b0587` (was "Missing: the full-load half"). No target
   value or stretch entry is edited. The row-2 scope wording is proposed to
   the keys (regulator-only; reference error excluded and carried by the
   reference block's own spec), not decided here.
3. **"Proposed evidence (2026-11-24)"** is added: per-row artifact/hash
   tables for the three records above, the definitive-vs-probe / sensitivity
   pair distinctions, and the closure verification that keeps the Monte
   Carlo campaign un-re-run.
4. **Tally, "Statistical rows", "#55 inputs" and "Review gates"** are
   updated consistently: 1 ratified, 3 proposed pending keys, 6 Open; rows
   5 and 7 stay informational for #55 until the keys land; three new
   unchecked gate boxes cover this proposal (the #65 boxes stay checked —
   they record what happened, not this PR's state).

No row is ratified by this note. Nothing is Revised; the
relax-after-measured-FAIL checks still do not trigger (no target moved).
`signoff/sg13g2-ldo.json` item 5 additionally cites the two graded
envelopes with `rows` set — every row declaration keeps
`ratified: false`, so the grader still lists rows 2, 5 and 7 under
`unratified_rows` and item 5 stays `unmet` / `partial_coverage` (evidence
against proposed targets is provisional). The stretch entries are not
proposed: row 7's < 10 uA is not met, row 4's < 200 mV stays unratified,
row 2's programmable variants stay deferred.

If the keys do not release the proposal, the PR is closed unmerged and this
record's rows 2, 5 and 7 revert to Open on `main` as this note found them.

## References

- Issue #54; downstream #55 (deterministic corner verification), #56
  (Monte Carlo); parent #5. Proposal of rows 2, 5, 7: issue #318, child of
  #316, with its dependencies #317 (row-7 envelope) and #319 (row-5
  envelope) closed by their records.
- `sim/ldo-cmos5l-pvt-sweep/README.md`, records cited above.
- `sim/ldo-cmos5l-monte-carlo/records/20261012-093854-934dbd7.md` and the
  graded envelopes `sim/ldo-cmos5l-pvt-sweep/row7-envelope/20261121-001957-ed6b0587/`,
  `sim/ldo-cmos5l-pvt-sweep/row5-envelope/20261123-213711-06bd6576/`
  ("Proposed evidence (2026-11-24)").
- `sim/pass-device-screening/records/20260909-220347-ed18110.{md,csv}`.
- `spec/porting-plan.md` §1.2, §1.4.
- [`DR-0017`](DR-0017-sg13cmos5l-current-limiter-plan.md) §5 (the row-7
  limiter/Iq disclosure; #190 open at this note's date).
