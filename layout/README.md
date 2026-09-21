# layout/ — GDS, DRC and LVS

Physical verification for this repo. Today it holds **one real layout**: the
full 13-device SG13CMOS5L LDO core, `sg13cmos5l_ldo_core_cmos5l`, drawn from
`design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`, DRC-clean against both the
curated `klt` deck and the PDK's own deck, and LVS-matching against a reference
netlist mechanically derived from the schematic export.

```bash
layout/run_flow.sh            # regenerate, verify, refresh the committed reports
layout/run_flow.sh --check    # verify the committed artifacts reproduce, byte for byte
```

A full run takes about 15 seconds and prints one block per stage:

```
=== 1. generate            11856 shapes, 163.10 x 281.18 um
=== 2. DRC -- klt's curated sg13cmos5l deck      clean, 0 violations
=== 3. DRC -- the PDK's own ihp-sg13cmos5l deck  222 rules, 0 violations
=== 4. DRC negative control                      both decks flag a planted defect
=== 5. extract                                   pfet 124, nfet 3, rhigh 3, cap_cmomi 1
=== 5b. HV-flavour control                       127 bind sg13_hv_*, 127 bind sg13_lv_* without ThickGateOx
=== 6. LVS                                       match
=== 7. LVS negative controls                     5 mutations, 5 mismatches
```

Exit status is 0 only if every stage passed, including every control.

## What is here

```
layout/
  common_sg13cmos5l.py                      CMOS5L drawing primitives (layer table,
                                            MOS row, well/substrate ties, meandered
                                            rhigh, cap_cmomi, routing helpers)
  lvs_reference.py                          schematic export -> LVS reference netlist
  run_flow.sh                               the one command (see "The seven stages")
  sg13cmos5l-ldo_core_cmos5l/
    generate.py                             the floorplan: this cell's layout, as code
    sg13cmos5l-ldo_core_cmos5l.gds          the committed stream
    sg13cmos5l-ldo_core_cmos5l.lvs_reference.spice   schematic side of LVS (generated)
    sg13cmos5l-ldo_core_cmos5l.extracted.spice       layout side of LVS (extracted)
    drc_report.json                         curated `klt drc --deck sg13cmos5l`
    drc_pdk_deck_report.json                the PDK's own deck, both invocations
    extract_report.json                     `klt extract --deck sg13cmos5l`
    lvs_request.json / lvs_report.json      `klt lvs`
    erc-supply-spec.json                    T1 item 11 supply spec (`klt erc`, #43)
    erc_supply_report.json                  the `klt erc` run against the committed GDS
```

The directory is named `sg13cmos5l-<cell>` to match `sim/`'s own per-PDK prefix
convention, and holds a `<dirname>.gds`.

Everything in it is **generated**. Nothing here is hand-drawn geometry or a
hand-written netlist: `generate.py` draws the layout, `lvs_reference.py`
derives the schematic side from `design/`'s own committed export, and
`run_flow.sh --check` re-runs both and demands the committed artifacts
reproduce byte for byte before it will re-verify the reports.

> **Reproducibility detail worth knowing.** GDSII stores a modification and an
> access timestamp in its `BGNLIB`/`BGNSTR` records, and KLayout fills them
> from the wall clock. `Builder.write` therefore writes with
> `gds2_write_timestamps = False`; without it, two runs of the identical
> generator produce two different files and the committed `.gds` could never be
> checked against the code that claims to draw it.

## Getting the tools

| Tool | Version used here | Why |
| --- | --- | --- |
| `klt` | 0.4.0 (was 0.5.0 through #28) | curated DRC deck, device extraction, LVS compare |
| KLayout Python module | 0.30.10 (was 0.30.12 through #28) | pulled in by `klt`; also what `generate.py` draws with |
| standalone `klayout` | 0.28.16 | runs the PDK's **own** DRC-DSL deck (stage 3) |
| `ihp-sg13cmos5l` | pin `607e18d4` (`sim/pdk-cmos5l.json`) | the deck, the layer table, the PCell sources every constant is cited from |

`PDK_ROOT` defaults to `~/share/pdk`; override it in the environment. Install
`ihp-sg13cmos5l` **next to** an `ihp-sg13g2` checkout under the same
`PDK_ROOT` — see `design/README.md`, "Install shape is a dispatch hazard".

> **The `klt`/KLayout versions moved *down* between #28 and #35, and the
> committed reports say so.** #28's reports were produced on `klt` 0.5.0 /
> KLayout 0.30.12; the host #35 re-ran the flow on carries `klt` 0.4.0 /
> KLayout 0.30.10. Every report's `provenance` block records the versions
> that actually produced it, so this shows up as a `[DRIFT]` line in
> `run_flow.sh --check` rather than being silently normalised. It is not a
> deliberate downgrade and nothing in the *results* depends on it: DRC is
> 0 violations on both decks either way, LVS matches either way, and all
> five negative controls mismatch either way. Two cosmetic differences to
> expect in a diff of the artifacts: 0.4.0 writes a `metrics` block into
> the DRC/extract reports that 0.5.0 did not, and it emits `L=`/`W=` on
> extracted `rhigh` cards. Re-running on a 0.5.0 host will move them back.

There is no CI job for this flow, for the same reason there is none for
`design/netlist.py --design sg13cmos5l --check`: no checksum-pinned fetch
script exists for this PDK yet (`2AMLogic/klayout-tools#1929`).

## SG13CMOS5L layer numbers

Read off the resolved technology's own
`libs.tech/klayout/tech/sg13cmos5l.lyp` by matching its `<name>` / `<source>`
element pairs — not inherited from SG13G2 by analogy, and not copied from
another repo's module. `common_sg13cmos5l.py` carries the same table as
constants.

| Layer | GDS | Role in this layout |
| --- | --- | --- |
| `Activ.drawing` | 1/0 | MOS source/drain/channel diffusion, well and substrate ties |
| `GatPoly.drawing` | 5/0 | MOS gates; the `rhigh` conductor (body **and** heads) |
| `GatPoly.pin` | 5/2 | deck's `poly_label` (unused by this cell) |
| `Cont.drawing` | 6/0 | contacts, 0.16 µm fixed by `Cnt.a` (min **and** max) |
| `nSD.drawing` | 7/0 | n+ implant: n-taps, and (with `pSD`) what makes a poly resistor `rhigh` rather than `rppd` |
| `Metal1.drawing` | 8/0 | device-local buses, resistor/cap terminal pads |
| `Metal1.pin` | 8/2 | deck's `metal_labels[0]` — net naming |
| `Metal2.drawing` | 10/0 | drain escape; every vertical riser to the routing channel |
| `Metal2.pin` | 10/2 | deck's `metal_labels[1]` |
| `pSD.drawing` | 14/0 | p+ implant (PMOS, p-taps, resistor heads) |
| `Via1.drawing` | 19/0 | Metal1 ↔ Metal2 |
| `SalBlock.drawing` | 28/0 | silicide block over the resistor body |
| `Via2.drawing` | 29/0 | Metal2 ↔ Metal3 |
| `Metal3.drawing` | 30/0 | the horizontal per-net trunks in the routing channel |
| `Metal3.pin` | 30/2 | deck's `metal_labels[2]` — where each net gets its name |
| `NWell.drawing` | 31/0 | PMOS wells (three: pass array on `VIN`, bias group on `VIN`, diff pair on `TAIL`) |
| `NWell.pin` | 31/2 | deck's `well_label` — gives a PMOS body terminal a real net |
| `ThickGateOx.drawing` | 44/0 | the HV flavour marker; every MOS here is inside one |
| `TEXT.drawing` | 63/0 | human-readable annotation; read by nothing in the flow |
| `Recog.mom` | 99/39 | `cap_cmomi` recognition marker |
| `EXTBlock.drawing` | 111/0 | poly-resistor marker (shared by `rhigh`/`rppd`) |
| `PolyRes.drawing` | 128/0 | poly-resistor body marker |

Net names are carried by **texts** on the `.pin` layers, not boxes: the PDK's
own `Pin.*` rules check that every *polygon* on a `.pin` layer is covered by
its drawing layer, and a text carries no polygon. The single exception is
`draw_cap_cmomi`, whose extractor requires two real `Metal1.pin` port polygons;
those are drawn strictly inside a `Metal1.drawing` pad, so `Pin.e` holds by
construction.

## The layout

`sg13cmos5l_ldo_core_cmos5l`, one flat cell, **163.10 × 281.18 µm**
(≈ 45.9 × 10³ µm²), 11 856 axis-aligned boxes, on the PDK's own 5 nm grid
(`techParams['grid']`) at `dbu = 0.001` (`sg13cmos5l.lyt`'s own `<dbu>`).

Three horizontal bands with a routing channel between them:

```
y >= 0          active band    Mpass array | error-amp devices | Cc
-70 < y < -50   routing channel  one horizontal Metal3 track per net
y <= -80        passive band   Rz, Rtop, Rbot (the three rhigh meanders)
```

That split is what makes the routing checkable by inspection: a riser is
vertical Metal2, a trunk is horizontal Metal3, and the only place the two meet
is a deliberate `Via2`. Everything else that crosses is on different levels
with no via — a real crossing in this deck's connectivity, not a drawing
convention. (The curated deck models the full `Metal1..TopMetal1` stack with
its vias only as of `klayout-tools#1417`; before that this PDK's curated deck
had one metal and no via at all, and a two-level layout like this one could not
have been verified against it.)

**The two devices that set the floorplan** — the two the issue that ordered
this work called out as "not a defensible layout" if drawn literally:

- **`Mpass`, `sg13_hv_pmos w=2800u l=0.5u`.** A single 2800 µm finger is not a
  layout. Drawn as **4 rows × 28 fingers × 25 µm**, interdigitated with shared
  source/drain diffusions inside one common NWell on a 31 µm row pitch.
  4 × 28 × 25 = 2800 µm exactly: the row/finger split is a layout decision, the
  total is the schematic's, and `run_flow.sh`'s parameter control (below) is
  what proves a mis-counted row would be caught.
- **`Rz`, `rhigh`.** A 1.2 mm straight bar is not a layout either. The
  schematic now declares `w=1u l=28.81u b=39` — 40 stripes — and the layout
  draws exactly 40. `b` is **not** a free layout choice: it is the PDK PCell's
  own bend count and it is electrically real (the PDK model computes
  `leff = (b+1)·l + (2/kappa·weff + ps)·b`), so the drawn stripe count must
  equal the declared one. Same for the divider's `b=7` eight-stripe legs.

The divider legs (`Rtop`/`Rbot`) were behavioural `res.sym` 300 kΩ primitives
until this phase — SPICE `R` cards that extraction cannot see as devices at
all. They are now real `rhigh` instances, which is what makes the divider
LVS-visible; `design/README.md` had that gap flagged as blocking this phase.

**A third device now shares that billing: `Cc`.** Issue #35 widened the
Miller cap from `w=100u` to `w=170u` (the compensation change that closes
the `res_bcs`/125 °C phase-margin gap — see
`spec/decision-records/DR-0005-sg13cmos5l-cc-recompensation.md`). It is
drawn on the same origin, so it grows upward only and no riser corridor,
well or trunk moved; but at 170 µm it is now the **tallest object in the
active band** — the `Mpass` array tops out at 118 µm — and it is what sets
this cell's bounding box in Y. That is a 22 % area increase (37.7 → 45.9 ×
10³ µm²) bought deliberately, for the cap-value tolerance `DR-0005`
decision (b) argues for; a future area-constrained phase that wants it back
should re-open that decision knowingly rather than shrink the cap here.

**Area is not optimised.** The bands are laid out for verifiability, not
density: the routing channel is mostly air, and a real block would fold the
passive band under the pass array and tighten the OTA row. Nothing in this
phase claims a competitive area number.

## The seven stages

**1. Generate.** `generate.py` draws the cell and asserts two properties
directly from the database before writing: every shape is an axis-aligned box
(`assert_manhattan`), and no two riser corridors are closer than
`RISER_MIN_DX`. The second is not decoration — the first run of this floorplan
put a resistor-terminal riser 0.25 µm from an NMOS source riser and merged
`VOUT` into `VSS`.

**2. DRC — `klt drc --deck sg13cmos5l`.** The agent-facing, JSON-contracted
inner-loop check. **Clean, 0 violations.** See "Coverage, honestly" below for
what that does and does not cover.

**3. DRC — the PDK's own `ihp-sg13cmos5l.drc`.** **222 rules executed, 0
violations**, across two invocations. This is the DRC number worth quoting.

**4. DRC negative control.** A copy of the GDS with two planted defects — a
0.10 µm Metal1 stub (min width is 0.16) and a 0.30 µm contact (`Cnt.a` fixes
contacts at 0.16 µm, min *and* max). Both decks must flag them, and do. A deck
that registers no rules against a layout's actual layers produces an empty
report indistinguishable from a clean one; this is what rules that out.

**5. Extract — `klt extract --deck sg13cmos5l`.** 131 raw devices: `pfet` 124,
`nfet` 3, `rhigh` 3, `cap_cmomi` 1. The 124 is the finger count, not the
schematic count — 112 pass-array fingers plus 12 error-amp PMOS fingers.

**5b. HV-flavour control.** Every MOS in this design is the thick-oxide HV
flavour (DR-0002), and the thing that makes it so is the drawn `ThickGateOx`
(44/0). Extracting the same layout twice — once as drawn, once with that layer
cleared — flips all 127 MOS bindings from `sg13_hv_*` to `sg13_lv_*`. That is
direct evidence the HV flavour is *drawn and recognised*, not assumed. (The
curated deck grew HV MOS recognition in `klayout-tools#1416`; before that a
thick-oxide device silently extracted as its LV counterpart.)

**6. LVS — `klt lvs`.** **Match.** 12 devices, 11 nets, 5 pins.

**7. LVS negative controls.** Five mutations of the reference, every one of
which must mismatch:

| Control | Mutation | What a match would mean |
| --- | --- | --- |
| topology | `Mn3` gate moved from `G1` to `N1` | connectivity is not being compared |
| parameter | `Mpass` W 2800 → 2772 µm (1 %, deliberately *less* than one 25 µm row) | device parameters are not compared, or are compared with a tolerance |
| cap presence | `Cc` deleted from the reference | the MoM cap is not compared at all |
| cap topology | `Cc` moved from `MZ` to `G1` | ditto, for connectivity |
| cap parameter | `Cc` W 170 → 85 µm | ditto, for parameters |

The three cap controls exist because the cap is the one device that does *not*
appear in the LVS report's device census — see the next section. Without them,
"12 devices matched" would be silently saying nothing about the 13th.

## T1 item 11 — the ERC supply check (#43)

The T1 checklist grew an eleventh item on 2026-09-17
([`klayout-tools`#2025](https://github.com/2AMLogic/klayout-tools/issues/2025)):
**power delivery, structural** — "is the supply actually connected to what it
powers" — graded, per block kind, from a [`klt
erc`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/cli/erc.md)
supply-spec run. This is the fleet's first ERC supply spec for an IHP
SG13-family PDK. Two artifacts in this directory:

- `erc-supply-spec.json` — the declaration. Every GDS layer/datatype is
  SG13CMOS5L's own, read from the PDK's `sg13cmos5l.lyp` and cross-checked
  against the curated `sg13cmos5l` extraction deck (`EXTRACTION_DECK`'s
  `poly`/`active`/`contact`/`metals`/`vias`/`metal_labels`) — transcribed from
  neither gf180mcu's nor sky130's spec. The three power rails `VIN`, `VOUT`,
  `VSS` are declared `kind: "supply"` and checked on the routing stack they
  actually use: GatPoly → Metal1 → Metal2 → Metal3 bridged by `Cont`, `Via1`,
  `Via2`, with text labels on the `.pin` layers of all three metals.
  `VREF`/`IBIAS` are control inputs by DR-0002, not power rails, so they are
  not declared.
- `erc_supply_report.json` — the committed run. Its `provenance.input.
  content_hash` is the committed GDS's own sha256
  (`f0f01392735616cbdb45166467972f8e4456426fd1cf794e3380d1713eabc062`,
  byte-verified), and its `provenance.spec.content_hash` pins the spec the
  verdict was graded against.

Read the three verdicts precisely in that report:

- **One island per supply, and no supply shorts.** `erc_status: "clean"`:
  zero `erc.unconnected_net` (each of VIN, VOUT, VSS resolves to exactly one
  electrical island) and zero `erc.supply_short` (every declared-supply pair
  resolves to *distinct* islands — VIN↔VOUT separated by the pass device,
  VOUT↔VSS by the feedback divider's resistors, VIN↔VSS by everything else).
  This is the item-11 question answered on the rails' real routing stack.
- **Why `devices[]` is declared.** `klt erc`'s connectivity model traces
  declared conductor layers as wires with no device recognition, so the three
  `rhigh` meanders — drawn on GatPoly like everything else in this PDK's poly
  — would chain the divider string `VOUT—Rtop—FB—Rbot—VSS` into one island
  and report a **false `erc.supply_short`** against an LVS-matched layout:
  exactly the gap [`klayout-tools`#2183](https://github.com/2AMLogic/klayout-tools/issues/2183)
  filed for supply-sensing analog blocks. The spec declares the carve-out that
  closes it — this deck's own `rhigh` recognition marker, PolyRes (128/0),
  subtracted from the GatPoly role — and the report's
  `provenance.devices[].body_area_um2` (1568.82 µm²) is the cross-check that
  the carve-out actually removed geometry. `Cc` needs no declaration: its
  interdigitated plates never touch, and bridging `EAOUT`↔`MZ` would not be a
  declared-supply pair anyway.
- **`erc.missing_tie` is NOT computed.** The spec deliberately declares no
  `ties[]` (per this issue's curation: the ties[] reading was the
  false-positive class of `klayout-tools`#2169 on real routed layouts, since
  fixed upstream), so `erc.missing_tie` is never computed by this run — the
  report's own `erc_coverage` carries that as
  `inapplicable: erc.missing_tie / no_ties_declared`, which is an **absence of
  evidence, not evidence of absence**. The well-tie evidence that stands in,
  all against this same GDS: (1) the three drawn, contacted Activ tie bars —
  the pass array's NWell tie (VIN, whose Metal1 strap also ties every row's
  source bus into one rail), the diff pair's TAIL NWell tie, and the substrate
  tie (VSS) — are extracted and compared by `klt lvs` (status `match`; well
  nets named by the NWell.pin texts, tap geometry derived by the deck's
  `tap_nplus`/`tap_pplus`, #1414), with `VIN`/`VOUT`/`VSS` all carried as
  pins in `net_correspondence` — item 11's Analog-column requirement; (2) the
  PDK deck's own latch-up rule (LU.b — every N+ implant within 20 µm of a
  substrate tie) ran clean over this GDS; (3) the PG pin labels themselves sit
  on the rails' `.pin` layers at every level they touch. Declaring a *checked*
  tie in the spec (now that #2169's fix is upstream) is follow-up work, not a
  silent gap.

Two contract notes for anyone re-running it:

- The command exits **4** with `status: "not_checked"` — that is the
  *antenna* half of the report, which cannot be graded on this PDK (`klt`
  has a real antenna-ratio table only for sky130), and antenna is not item
  11's subject ([`klayout-tools`#1994](https://github.com/2AMLogic/klayout-tools/issues/1994)).
  The structural verdict item 11 grades is the separate `erc_status` field:
  `clean`. Gate on that, not on the exit code.
- Released `klayout-tools` 0.5.0 — what pip/uv installs and what this host's
  `klt` currently resolves to — predates both the `status`/`provenance`
  envelope (#1968) and `devices[]` (#2183), so it can produce neither the
  content-hash pin nor the carve-out. This report was made with an
  upstream-main source build (version `0.5.0+gb15edf5e3a2e`, recorded in
  `provenance.klt_version`); the one-line command in the spec's `_comment`
  reproduces it verbatim once a klayout-tools release carrying those changes
  is installed:

```
klt erc layout/sg13cmos5l-ldo_core_cmos5l/sg13cmos5l-ldo_core_cmos5l.gds \
  layout/sg13cmos5l-ldo_core_cmos5l/erc-supply-spec.json --format json
```

## Coverage, honestly

Two DRC numbers, never conflated:

| | Rules | Result |
| --- | --- | --- |
| `klt drc --deck sg13cmos5l` (curated) | **16 executed** of the deck's 27 | clean, 0 violations |
| `ihp-sg13cmos5l.drc` (the PDK's own) | **222 executed** | 0 violations |

**The curated deck is a 27-rule starter subset** — width, space and enclosure
on `Activ`, `GatPoly`, `Metal1..Metal4`, `Via1..Via3`, `TopVia1`, `TopMetal1`,
covering 8 rule-category sections of the design rule manual (5.5, 5.8, 5.16,
5.17, 5.19, 5.20, 5.21, 5.22). 11 of its 27 rules do not run here because this
layout draws nothing above Metal3 — that is a property of the layout, not a
gap. What the curated deck has **no rules for at all** is the larger fact: no
implant rules, no well rules, no contact rules, no latch-up, no density, no
antenna, no thick-oxide rules. `klt drc: clean` and "DRC clean" are different
claims and this repo will not conflate them.

The report also records, for this layout, 14 layers present in the stream that
the curated deck has no rules for, and a voltage-domain warning for `44/0`: the
deck models `ThickGateOx` for *extraction* (it is what binds the HV flavour)
but still applies general-case thresholds for DRC regardless of it — the
channel-length-specific `Gat.a1`/`Gat.a2` rules that do read it are not
transcribed there.

### DRC: what actually ran (the PDK deck, and why it takes two invocations)

The PDK's own deck **cannot run end to end** against KLayout 0.28.16: several
of its rules use `with_angle(45, absolute)`, a DRC-DSL construct this build
does not provide, and the deck aborts at the first one it reaches. A naive
`main` run therefore executes **183 rules and then dies** — and, because the
deck has already written its report file by then, the surviving report is short
but valid.

`run_flow.sh` runs the deck in two invocations instead: every table that
contains no such rule at full strength (183 rules), then the three that do
(`gatpoly`, `metal1`, `metaln`) in the deck's **own** reduced `precheck_drc`
mode, which skips exactly those sub-blocks and keeps each table's width and
space rules (39 more). **222 rules, 0 violations.** The split recovers 39 rules
a naive run silently drops.

What stays unrun, and why each is not load-bearing here:

| Skipped | Why it is skipped | Why that is acceptable |
| --- | --- | --- |
| `Gat.g`, `M1.g`, `M1.i`, `Mn.g`, `Mn.i`, `Seal.k`, the whole `3_2_angle` table | `with_angle(45, absolute)` is unavailable on this KLayout build | all are 45°-geometry rules, and `generate.py` asserts from the database that every shape is an axis-aligned box |
| `Gat.a1`, `Gat.a2` | 1.2 V (LV) FET channel-length rules | this design has no LV FET (DR-0002) |
| `Seal.k`/`l`/`m`/`n` | seal-ring rules | no `EdgeSeal` is drawn |
| `density.drc` | not in the deck's own `main` table selection | matches what the PDK's own runner does |

> **This is exactly the shape of failure `klt` cannot currently see.** Hand the
> aborting `main` run to `klt drc --engine klayout` and it reports
> `status: "clean", violation_count: 0` and exits 0 — it never inspects
> klayout's exit status (1) or the two `ERROR:` lines on its stdout; its only
> failure check is "no report file was produced at all". Filed upstream as
> [klayout-tools#1941](https://github.com/2AMLogic/klayout-tools/issues/1941)
> with a 10-line generic repro. Stage 3 therefore shells out to `klayout`
> directly and checks both signals itself.

### LVS: what is compared at device level, and what is not

The report says 12 devices on each side. The cell has **13**. The missing one
is `Cc`, and it is missing for a tooling reason, not a drawing one.

`klt extract` recognises `cap_cmomi` as its own device class
(`MomCapacitorDevice`, `klayout-tools#1466`) — `extract_report.json` counts it.
But KLayout has no SPICE element letter for a custom `GenericDeviceExtractor`
class, so the writer emits it as a subcircuit call:

```
XD_$128 EAOUT MZ cap_cmomi PARAMS: W=170 L=30
```

and `klt lvs`'s plain `NetlistSpiceReader` reads that back as an abstract
circuit whose parameters are mangled into its **name**:
`CAP_CMOMI(L=30,W=0.1K)`. So the cap is compared by circuit-name string
equality, on both sides, and never reaches device-level compare.

Measured consequences (all three are standing controls in stage 7, not
assumptions):

- presence, connectivity **and** parameters *are* compared — every mutation
  mismatches;
- but `options.parameter_tolerance` never reaches it: a 0.001 % width
  difference hard-fails under a 10 % tolerance, while every other device in the
  same run honours it;
- and every failure degrades to the same unattributed
  `topology: circuit could not be matched to a counterpart`, three times, with
  no device, parameter or net named.

Filed upstream as
[klayout-tools#1942](https://github.com/2AMLogic/klayout-tools/issues/1942).
Until it lands, `lvs_reference.py` must emit the identical `X ... PARAMS:` card
and rely on the two sides mangling identically — which is why that special case
is written down in its docstring rather than left as a quirk of the generator.

### Three more things LVS here does not establish

**Pin order.** Verified, not assumed: swapping `VREF` and `IBIAS` in the
reference's `.SUBCKT` port list still reports a **match**. The compare is
structural, and the two nets are already distinguishable by connectivity, so
reordering the declaration changes no graph. **"LVS match" therefore says
nothing about whether the block's pinout is right.** In this repo the thing
that checks that is `design/netlist.py --design sg13cmos5l --check`, which
asserts the ratified port list and order and that every symbol's pins match its
schematic's ports.

**Resistance.** The reference states each `rhigh`'s resistance in the *curated
deck's own* first-order model (`R = L/W · 1360 Ω/□` over the drawn meander),
not the PDK ngspice model's value, and prints both in a comment on the line:

| Device | Deck model | PDK ngspice model | Δ |
| --- | --- | --- | --- |
| `Rtop`, `Rbot` | 278 392 Ω | 300 444 Ω | +7.9 % |
| `Rz` | 1 576 811 Ω | 1 700 012 Ω | +7.8 % |

The gap is real physics the curated deck's single-coefficient model does not
carry — the line-width delta (`weff = w − 0.04 µm`, +4.2 %) and a measured
corner-crowding term per bend (+2.9 %). Stating the deck figure keeps the LVS
compare geometry-against-geometry rather than one resistance model against a
different one. Neither number is "the" resistance; the device's identity on
both sides is its drawn `w`/`l`/`b`. The *simulation* evidence in `sim/` uses
the PDK model, as it must.

**Capacitance.** `draw_cap_cmomi` draws the recognition marker and the two port
polygons exactly — those three shapes are the entire input to device
recognition, and the extractor computes no capacitance at all (the real
device's `C` comes from its Verilog-A model). The *interior* is a coarse
interdigitated comb on a 2 µm row pitch rather than the PCell's own 0.89 µm
lattice of 0.21 µm bars, which at 30 × 170 µm would be ~107 000 rectangles this
phase has no way to verify. So the footprint occupies the right area and
extracts as the right device with the right `W`/`L`, but its **drawn** fringe
capacitance is not the PCell's ≈ 5.5 pF. It is a placeholder for a real
`cap_cmomi` PCell instance, not a substitute for one.

## What this layout is, and is not

Every device here is a **simplified representative footprint**: correct layer
stack, correct device-defining dimensions, correct terminal and contact
structure, drawn to the PDK's own DRC rule values — but not a
re-implementation of each PCell's full geometry. Concretely, not drawn:

- each PCell's contact-packing loops, dogbone and asymmetric-contact special
  cases, and thermal pseudo-layers;
- `cap_cmomi`'s unit-cell lattice (above);
- dummy/filler devices, guard rings beyond the ties extraction needs, and any
  deliberate matching structure (common-centroid, edge dummies) for the
  differential pair or the mirror;
- a seal ring, pads, or anything above Metal3.

The right end state is instantiating the PDK's own PCells, which is what makes
the geometry correct by construction; that is a larger piece of work than this
phase and is not claimed here.

## Friction filed upstream

Per `CLAUDE.md`'s friction protocol, gaps this phase hit are filed generically
against [klayout-tools](https://github.com/2AMLogic/klayout-tools):

- [#1941](https://github.com/2AMLogic/klayout-tools/issues/1941) — `klt drc
  --engine klayout` reports a partially-executed deck as clean: the klayout
  exit status and its `ERROR:` output are both ignored when a report file
  exists. **A false clean.** Stage 3 works around it by driving `klayout`
  directly.
- [#1942](https://github.com/2AMLogic/klayout-tools/issues/1942) — a
  custom-extractor device class round-trips through `klt extract` → `klt lvs`
  as a name-mangled abstract subcircuit, so it never reaches device-level
  compare. This is why the MoM cap needs three negative controls of its own.

Closed gaps this layout depends on, recorded because it would not have been
verifiable without them:
[#1415](https://github.com/2AMLogic/klayout-tools/issues/1415) (poly
resistors), [#1416](https://github.com/2AMLogic/klayout-tools/issues/1416) (HV
MOS flavour), [#1417](https://github.com/2AMLogic/klayout-tools/issues/1417)
(the metal stack and its vias),
[#1466](https://github.com/2AMLogic/klayout-tools/issues/1466) (`cap_cmomi`
recognition) — and, for the ERC supply check above,
[#2183](https://github.com/2AMLogic/klayout-tools/issues/2183) (the `devices[]`
carve-out, without which the divider string false-shorts VOUT to VSS) and
[#1968](https://github.com/2AMLogic/klayout-tools/issues/1968) (`klt erc`'s
`status`/`provenance`, without which the report could not pin its input). Still open and still shaping this flow:
[#1927](https://github.com/2AMLogic/klayout-tools/issues/1927) (`klt extract`
drops a drawn resistor's `L`/`W`, which is why the reference states `R` rather
than geometry), [#1928](https://github.com/2AMLogic/klayout-tools/issues/1928)
(no request-level parameter scoping),
[#1929](https://github.com/2AMLogic/klayout-tools/issues/1929) (no pinned fetch
script for this PDK, which is why there is no CI job).
