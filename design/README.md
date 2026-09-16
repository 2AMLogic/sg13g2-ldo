# design/ — xschem sources and netlist export

Schematic entry for the LDO core, in xschem. This directory is the source of
truth for the block's electrical interface — a future `sim/` harness and
`layout/` LVS flow will both consume the netlists exported from here.

**There are two PDK branches, in two directories, with no shared cells:**

| Branch | Directory | PDK variant | Top cell | Issue |
| ------ | --------- | ----------- | -------- | ----- |
| SG13G2 | `design/` | `ihp-sg13g2` | `ldo_core` | #6 |
| SG13CMOS5L | `design/sg13cmos5l/` | `ihp-sg13cmos5l` | `ldo_core_cmos5l` | #20 |

Everything from here down to ["SG13CMOS5L branch"](#sg13cmos5l-branch-designsg13cmos5l)
describes the **SG13G2** branch. `design/netlist.py --design sg13cmos5l`
selects the other one; `--design sg13g2` is the default, so every command in
this file that omits the flag means the SG13G2 branch.

> **Status (issue #6, T1 item 1 of the bronze evidence ladder — #5): sources
> exist and are reproducible, nothing is corner-verified.** This is a
> forward-designed, clean-room schematic for SG13G2's own device menu — not
> a copy or mechanical translation of `2AMLogic/gf180-ldo`'s or
> `2AMLogic/sky130-ldo`'s `design/*.sch` (see "Clean-room provenance"
> below). Two sub-blocks are explicitly provisional stand-ins, not final
> answers: `Mpass`'s sizing (see "Pass device") and the error amplifier
> (see "Error amplifier" — a behavioral placeholder, not a real amp). No
> `sim/` evidence exists yet for any spec row; nothing here is claimed to be
> corner-verified, PVT-swept, or even DC-operating-point-simulated —
> `xschem netlist -erc`'s own connectivity check is the only verification
> this issue performs.

## Cells

```
ldo_core                          top level — issue #6
└── ldo_erramp_placeholder        behavioral placeholder error amp — issue #6
```

## `ldo_core` pinout (established by issue #6, in netlist port order)

| Pin    | Dir   | Meaning |
| ------ | ----- | ------- |
| `VIN`  | inout | Supply, 3.3 V nominal (`README.md`'s DRAFT target row) |
| `VOUT` | inout | Regulated output, 1.8 V nominal (`README.md`'s DRAFT target row) |
| `VSS`  | inout | Ground |
| `VREF` | in    | External reference input — see "Reference voltage" below |

`python3 design/netlist.py --check` asserts this exact port list (and that
each cell's `.sym` pin order matches its `.sch` port order) so a schematic
edit that drifts from this interface fails loudly instead of quietly
shipping.

No `EN`, no current-limit or soft-start ports, no loop-break points. Those
are real gaps against where the block eventually needs to land (mirroring
`gf180-ldo`'s own decomposition of pass-device/divider, error amp, current
limit, and soft start across separate issues) — this issue's acceptance
criteria scope it to the core regulation loop plus a placeholder amp only;
everything else is explicit future-issue territory, not a silent omission.

## Clean-room provenance

`ldo_core.sch` was authored without opening `gf180-ldo/design/ldo_core.sch`
or `sky130-ldo/design/ldo_3v3in_1v8out.sch` in this session — only each
sibling's *decision records* and `spec/porting-plan.md`'s synthesis of them
were read. Every device instance in this schematic is an `ihp-sg13g2`
symbol (`sg13g2_pr/sg13_hv_pmos.sym`) or a generic xschem device
(`devices/res.sym`, `devices/vcvs.sym`), sized and wired independently for
this PDK. The one deliberate exception is *naming*, not circuit content:
this issue's own acceptance criteria ask the placeholder amplifier to
"mirror gf180-ldo's `ldo_erramp_placeholder` pattern", so this repo's
placeholder cell reuses that name — there is no gain stage, bias network,
or compensation in either placeholder to have copied.

## Pass device

`Mpass` is `sg13_hv_pmos` (thick-oxide, 3.3 V-class), common-source, source
tied to `VIN`, drain tied to `VOUT`, body tied to `VIN` (the source) — the
standard PMOS body-to-highest-potential practice for a device whose source
rides at the supply rail. This confirms `spec/porting-plan.md` §2.1's
starting hypothesis on device-menu grounds (SG13G2 has a native 3.3 V-class
PMOS, unlike sky130, which forced its own `DR-001` into a 5 V-flavor
device): the hypothesis was **not rejected** by this issue's inspection, so
no departure record is needed here.

**Sizing is a DC-sanity stand-in, not a final answer**: `L=0.5 µm`,
`W=300 µm`, `ng=1`, `m=1` (300 µm total width) — a modest first-cut size
chosen to close the loop for connectivity/ERC purposes, not sized against
any dropout, current-limit, or area target. Do not read this width as a
dropout- or area-sized value; it mirrors how `gf180-ldo`'s own first
design-source issue (#8) flagged its pass-device width as "2 mm, #8's
DC-sanity simplification of the ratified ~4 mm sizing" rather than
presenting it as final.

The confirming screening deck `spec/porting-plan.md` §4 item 1 calls for
has now been run: [`sim/pass-device-screening/`](../sim/pass-device-screening/README.md)
(issue #13) measures `Ron·W`, `Vth` and `Cgate` at the `Vin = 2.10 V` /
`Vout = 1.80 V` dropout point, and terminal voltage/current stress at the
`Vout = 0 V` / `Vin = 3.63 V` continuous-short condition, across the full
`{tt,ss,ff,sf,fs} × {-40,27,125}°C` grid. **Verdict: the `sg13_hv_pmos`
hypothesis is not rejected** — `Ron·W` and the dropout/drain-rating checks
clear with margin — **with one quantified caveat**: at the bare-device,
gate-fully-on worst case (no current-limit loop exists yet to relieve it),
`|Vsg|` reaches `3.63 V` during the continuous-short condition, 10% past the
PDK's stated `3.3 V` maximum `VGS` rating (`libs.doc/doc/SG13G2_os_process_spec.pdf`
p.9) — see that experiment's README for the full finding, the conservative-
bound argument for why this is a bound on the eventual current-limit design
rather than a verdict on a finished circuit, and the implied pass-device
width data (`records/*.csv`) the eventual `Mpass` resizing decision record
will need. Ratifying a decision record (DR-0001) from this finding, and
resizing `Mpass` itself, are both out of scope for issue #13 and are left to
a follow-up.

## Error amplifier

`Xamp` (`ldo_erramp_placeholder.sch`/`.sym`) is a single ideal
voltage-controlled voltage source (`E1`, xschem's generic
`devices/vcvs.sym` — a native SPICE `E` element, not a PDK device),
`OUT = 100000 * (INP - INN)`, referenced to an explicit `VSS` pin (not an
implicit global-ground alias). `INP` is wired to `FB` (non-inverting) and
`INN` to `VREF` (inverting) — the polarity a PMOS common-source pass
device's negative-feedback loop requires: as `Mpass`'s gate (`EAOUT`) rises,
its `Vsg` shrinks and `VOUT` falls, so when `FB` rises above `VREF`, `EAOUT`
must rise to correct `VOUT` back down. This polarity was re-derived directly
from `Mpass`'s own device physics in this schematic, not read off either
sibling's amplifier.

A full amplifier topology decision — bipolar vs. CMOS input stage, on-chip
bandgap vs. external `VREF` — is explicitly out of scope for this issue
(`spec/porting-plan.md` §2.2, §4 item 5). The placeholder's 4-pin interface
(`INP INN OUT VSS`, no `VDD`: an ideal VCVS has no supply/bias dependence to
model) is not a ratified contract — a real amplifier will very likely need a
`VDD` pin (and possibly `EN`), and that pin-list change will be made and
documented when the real amp lands, not assumed here.

That prediction has since been borne out on the *other* branch: the
SG13CMOS5L amplifier's pin list is `INP INN OUT VDD VSS IBIAS` — see
["Error amplifier"](#error-amplifier-1) under "SG13CMOS5L branch". It does
**not** settle anything for SG13G2: DR-0002 binds the SG13CMOS5L branch
only, and `spec/porting-plan.md` §4 item 5 remains open here.

## Reference voltage

`VREF` is a top-level port of `ldo_core` — an external, ideal input, not an
on-chip bandgap (`spec/porting-plan.md` §1.2/§2.2's port-parity default: no
sibling designs or assumes an on-chip reference either). No value is fixed
inside this schematic; a future testbench supplies it.

The feedback divider (`Rtop`=300 kΩ, `VOUT`→`FB`; `Rbot`=300 kΩ, `FB`→`VSS`,
both plain behavioral `res.sym`, not a PDK resistor flavor — deferred to
whichever future issue needs a layout-matched divider, the same allowance
`gf180-ldo` issue #8 made for its own first-cut divider) gives `FB =
VOUT/2`. Assuming an illustrative `VREF = 0.9 V` (chosen only to exercise
the loop; not a spec commitment — `spec/target-spec.md` does not exist yet
in this repo, see "Non-goals" below), this divider ratio would servo `VOUT`
to `1.8 V`, matching `README.md`'s DRAFT output target. The divider's
900 kΩ total holds its own standing current at `1.8 V / 900 kΩ = 2 µA`,
inside the DRAFT `< 30 µA` Iq row. Both the ratio and the assumed `VREF`
value are provisional first-cut choices, not derived from any measurement.

## Non-goals (explicitly out of scope for this issue)

- **Verification.** No `sim/` testbench exists yet; no spec row is
  corner-verified, PVT-swept, or even DC-operating-point-simulated by this
  issue. `xschem netlist -erc`'s connectivity check is the only
  verification performed here.
- **`spec/target-spec.md`.** Drafting a ratified target spec is not this
  issue's job (per this issue's own curator note) — the `README.md` DRAFT
  table is the only spec surface referenced above, and only as an
  illustrative target, not a ratified one.
- **Enable/shutdown, current limit, soft start, compensation network,
  loop-break test points.** None of these exist in `ldo_core` yet. This
  mirrors how `gf180-ldo` decomposed the same pieces across separate issues
  (#9 error amp, #11 current limit + enable, #38 soft start) rather than a
  single all-in-one schematic.
- **Layout, DRC, LVS, PVT corners, Monte Carlo, PEX.** T1 items 2–10 per the
  gap tracker (#5); this issue is item 1 only.
- **The pass-device and error-amp decision records** `spec/porting-plan.md`
  §4 lists as future work (items 1 and 5) — this issue's schematic marks
  both choices as provisional per the sections above, but does not file or
  resolve either record.

## SG13CMOS5L branch (`design/sg13cmos5l/`)

Schematic capture for the SG13CMOS5L port, against the `ihp-sg13cmos5l` PDK
(issue #20, phase 2/4 of the port tracked by #12, Epic `2AMLogic/2am#542`
Phase 5A).

> **Status: PVT-verified and re-sized (issues #21 and #25, phase 3/4) —
> every spec row now passes.** #21's first closed-loop PVT sweep (the full
> `{tt,ss,ff,sf,fs} × {-40,27,125}°C` grid) found the phase-2 provisional
> sizing this section originally documented missed dropout by 4–7× and
> never reached regulation at all at 4/15 corners, with phase margin
> ≈0.2–0.35° (target 45°) essentially independent of `Cc`/`Rz` sensitivity.
> #25 resized `Mpass` (`300u`→`2800u`) and re-derived the error amp's
> `Cc`/`Rz` compensation and bias currents against that evidence; the
> re-run sweep now **passes every spec row at every corner** — dropout
> 0.20–0.24V (worst `ss/125°C`), load regulation ≤0.025%, phase margin
> 54.4–72.7° worst-case, gain margin 17.1–25.9dB worst-case, PSRR
> 58.2–61.9dB @ 1kHz / 33.8–35.3dB @ 100kHz, Iq 21.9–23.1µA (no load and
> full load both), output accuracy 1.80023–1.80064V. Full spec table,
> before/after evidence, and the pole/zero re-derivation:
> [`sim/ldo-cmos5l-pvt-sweep/README.md`](../sim/ldo-cmos5l-pvt-sweep/README.md),
> [`spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md`](../spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md).
> Layout/DRC/LVS is phase 4 (#22).

### Cells

```
ldo_core_cmos5l                   top level — issue #20
└── ldo_erramp_cmos5l             two-stage Miller-compensated OTA — issue #20
```

Cell names are suffixed `_cmos5l` rather than reusing `ldo_core` /
`ldo_erramp_placeholder`. That is deliberate and load-bearing, not
cosmetic: `design/xschemrc` puts **both** `design/` and
`design/sg13cmos5l/` on `XSCHEM_LIBRARY_PATH`, and xschem takes a
`.subckt`'s port list from the *symbol* it resolves by bare name. Shadowed
names would let a bare `ldo_core.sym` reference resolve to the other
branch's symbol depending on search order — silently miswiring or dropping
ports instead of erroring.

### What ratifies this topology

[`spec/decision-records/DR-0002-sg13cmos5l-device-topology.md`](../spec/decision-records/DR-0002-sg13cmos5l-device-topology.md)
(PR #23, closing #19). Both schematics cite it by path in their own header
comments. DR-0002 ratifies device flavours and structure only; it
explicitly leaves sizing, the bias scheme, and the nulling resistor to this
phase, and those choices are flagged as provisional everywhere they appear
below.

### `ldo_core_cmos5l` pinout (in netlist port order)

| Pin     | Dir   | Meaning |
| ------- | ----- | ------- |
| `VIN`   | inout | Supply — the **3.3 V analog rail** |
| `VOUT`  | inout | Regulated output |
| `VSS`   | inout | Ground |
| `VREF`  | in    | External reference input — no on-chip bandgap (DR-0002) |
| `IBIAS` | inout | External bias-current input — **new on this branch**, see below |

`ldo_erramp_cmos5l` pinout: `INP INN OUT VDD VSS IBIAS`. `VDD` and `IBIAS`
are the two pins the SG13G2 branch's ideal-VCVS placeholder did not need
and which ["Error amplifier"](#error-amplifier) above predicted a real
amplifier would; DR-0002's Consequences section anticipated the same.

`python3 design/netlist.py --design sg13cmos5l --check` asserts both port
lists (and that each cell's `.sym` pin order matches its `.sch` port order),
so a schematic edit that drifts from this interface fails loudly.

### Rails and the Challenge #6 slot budget

The Challenge #6 brief pairs a **1.2 V digital** rail with a **3.3 V
analog** rail. Per DR-0002, this block sits entirely on the analog rail:
`VIN` is that rail, the amplifier's `VDD` is tied to `VIN`, and every
transistor in the hierarchy is an HV (3.3 V-class) flavour —
`sg13_hv_pmos` / `sg13_hv_nmos`, never an LV device. **There is no 1.2 V
node anywhere in this hierarchy.** LV devices are disqualified on ratings,
not on preference: DR-0002's table quotes `BVDSSP013` = −2.2 V worst case
against a 3.3–3.63 V rail and a 1.65 V `VGS` limit.

Against the brief's slot budget, this block claims **no digital control
inputs and no digital test outputs**. It presents `VIN`/`VOUT`/`VSS` plus
two analog lines (`VREF`, `IBIAS`) — so adding the real amplifier cost one
additional analog line versus the SG13G2 placeholder, and nothing else.

### Clean-room provenance

`ldo_core_cmos5l.sch` and `ldo_erramp_cmos5l.sch` were authored from
DR-0002 and this PDK's own device menu — not by copying or mechanically
translating this repo's `design/ldo_core.sch` /
`design/ldo_erramp_placeholder.sch`, and not from either sibling repo's
sources. This is the same discipline ["Clean-room provenance"](#clean-room-provenance)
above records for the SG13G2 schematic, applied here relative to the SG13G2
files in *this* repo.

What is deliberately carried across is **interface convention, not circuit
content**: the `VIN`/`VOUT`/`VSS`/`VREF` port names and order, the
`FB`/`EAOUT` node names, the two-resistor feedback-divider approach, and the
`INP=FB` / `INN=VREF` polarity convention. The polarity itself is re-derived
in each new schematic's header from that schematic's own devices. There is
also nothing to have copied from the placeholder amplifier: it is a single
ideal VCVS with no gain stage, bias network, or compensation.

### Pass device

`Mpass` is `sg13_hv_pmos`, common-source, source at `VIN`, drain at `VOUT`,
body at `VIN` (the source) — DR-0002 Decision (a), the same flavour and
topology `DR-0001` ratified for SG13G2.

**Sizing was resized by #25 from the phase-2 DC-sanity first cut.**
`w=2800u l=0.5u ng=1 m=1` replaces the original `w=300u`, which #21's
closed-loop PVT sweep found missed the 300mV dropout target by 4–7× and
never reached regulation at all at 4/15 corners. `w=2800u` is derived from
`sim/pass-device-screening`'s bare-device implied-width data (worst corner
~2169–2350µm for 300mV/50mA) plus ~20–30% headroom for this closed-loop
bench's discretized dropout-scan step and for interaction with the
re-derived compensation network below; the re-run sweep confirms dropout
0.20–0.24V (worst `ss/125°C`) against the 300mV target. `l=0.5u` is
unchanged and still not arbitrary: the process spec rates HV
`VGS ≤ 3.3 V` only at `LG ≥ 0.5 µm`. Full derivation:
[`spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md`](../spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md).

`DR-0001`'s carried-forward `|Vsg| ≤ 3.3 V` constraint is inherited by this
branch and binds whatever current-limit loop it eventually grows — there is
no current limit in this increment.

### Error amplifier

`Xamp` (`ldo_erramp_cmos5l.sch`/`.sym`) is a real two-stage,
Miller-compensated, single-ended-output OTA built entirely from HV devices,
replacing the SG13G2 branch's ideal-VCVS placeholder. Structure, per
DR-0002 Decision (b):

- **Tail** `Mtail` — `sg13_hv_pmos` current source from the rail.
- **Input pair** `Minp`/`Minn` — `sg13_hv_pmos`, `INP=FB` (non-inverting),
  `INN=VREF` (inverting). PMOS because at `VICM ≈ 0.9 V` an HV-NMOS pair is
  at or below its lower ICMR limit *nominally* (DR-0002's hand calculation).
  Issue #21's closed-loop DC sweep converges around this bias point at
  every one of the 15 PVT corners without an input-pair headroom failure,
  but does not include a dedicated ICMR-margin sweep — that remains open.
- **First-stage load** `Mn1`/`Mn2` — `sg13_hv_nmos` mirror, diode-connected
  on the `VREF`-side leg (`Mn1`), first-stage output `G1` taken at the
  `FB`-side leg (`Mn2`).
- **Second stage** `Mn3` — single `sg13_hv_nmos` common-source device,
  source at `VSS`, drain at `OUT`, loaded by the `Mload2` `sg13_hv_pmos`
  current source from the rail.
- **Compensation** — `Cc` (MoM) in series with `Rz` from `OUT` back to `G1`.
- **`VREF` stays an external port.** No on-chip bandgap.

Polarity check, re-derived in the schematic header: `FB` rises → `Minp`
conducts less → the `VREF` leg takes more tail current → `N1` rises → `Mn2`
sinks harder → `G1` falls → `Mn3` conducts less → `Mload2` pulls `OUT` up →
`Mpass`'s `|Vsg|` shrinks → `VOUT` falls. Negative feedback.

#### Judgement calls this phase made that DR-0002 did not

The bias-mirror ratios and the `Cc`/`Rz` compensation network were
re-derived by #25 against #21's closed-loop PVT evidence; see
[`DR-0003`](../spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md)
for the full pole/zero reasoning. These remain first-cut engineering
choices — what the current PVT record supports, not a claim of
optimality:

1. **Bias scheme: an external `IBIAS` current input, mirrored on-block.**
   `Mb0` is a diode-connected `sg13_hv_pmos` from `VDD` whose gate/drain
   node *is* the `IBIAS` pin; `Mtail` (`m=3`, raised from #20's `m=2` by
   #25) and `Mload2` (`m=6`, raised from `m=4`) mirror from it, so an
   external sink of `Iref` sets tail = `3·Iref` and second stage =
   `6·Iref`. Chosen over a `VBIAS` *voltage* port (would not track the
   mirror's `Vsg` over PVT) and over an on-block resistor self-bias
   (current becomes a direct function of the supply — bad PSRR in a
   regulator). An external current input is also the consistent interface
   for a block DR-0002 keeps bandgap-free: the reference is off-block, so
   the bias should be too, and a testbench can sweep it. The higher
   mirror ratios speed up the first/second stage's own `gm` (see item 2)
   while keeping Iq inside budget — confirmed at 21.9–23.1µA (no load and
   full load) against the 30µA target.
2. **Nulling resistor `Rz`: included, and substantially enlarged by #25**
   (`l`: `5.3µm`→`1200µm`, `w` unchanged at the PDK's `rhigh` minimum,
   `1µm`) from the phase-2 textbook `Rz≈1/gm2` first cut. **Issue #21
   found that first cut alone left phase margin essentially zero
   (≈0.2–0.35°, vs. a 45° target) regardless of `Rz`'s corner**
   (`res_bcs`/`res_typ`/`res_wcs`) or `Cc`'s value (`0.5×`–`2×` nominal).
   #25's re-derivation instead uses the enlarged `Rz` (in series with the
   enlarged `Cc` below) to place a deliberate left-half-plane phase-lead
   zero near the loop's unity-gain crossover (empirically ~50–140kHz
   across the PVT grid at this sizing) — a standard technique for
   reclaiming margin when a bare RHP-zero-cancellation estimate is
   insufficient, at the cost of a much larger resistor (implied ~1.2–1.7
   MΩ at `rhigh`'s corner spread, a schematic-level-only 1200:1 aspect
   ratio deferred to phase 4's meandered layout). Re-run: phase margin
   54.4–72.7° worst-case, gain margin 17.1–25.9dB worst-case, both across
   the full 15-corner grid and the Cc-value/Rz-corner sensitivity sweeps
   (`sim/ldo-cmos5l-pvt-sweep/README.md` "Results", tracked as #25).
3. **`Rz` is a PDK `rhigh`, while the feedback divider is still behavioral
   `res.sym`.** `cornerRES.lib` gives `rhigh` a real corner spread (unlike
   `cornerCAP.lib`'s `Cc`, which has none at this PDK's pin — see the MoM-cap
   caveat row below); issue #21's main 15-point PVT grid holds `Rz` at
   `res_typ` throughout (no established MOS-corner/R-corner correlation
   convention exists yet in this repo) and checks `Rz`'s own corner spread
   separately, at nominal `tt/27°C` only (`sim/ldo-cmos5l-pvt-sweep/README.md`
   "PDK pin, corner naming, and the resistor/cap corner axes") — not, as an
   earlier draft of this note anticipated, folded into the main corner
   sweep itself. The divider's *ratio*, not its absolute PVT spread, is what
   matters there, and keeping it behavioral preserves the SG13G2 branch's
   documented deferral so the two dividers stay comparable. See "Known
   gaps" below — this is a real gap for #22.
4. **`Rz`'s body terminal is tied to `VSS`, not the PDK's global `sub!`.**
   These cells are `.subckt`s with an explicit `VSS` pin and no `.global`
   declaration, so `sub!` would netlist as an undeclared, floating local
   node. This is the same "`VSS` is an explicit pin, never an implicit
   global-ground alias" rule the SG13G2 branch already follows.
5. **Sizing generally** is a DC-sanity first cut for every device #25 did
   not touch — `Mb0`/`Minp`/`Minn`/`Mn1`/`Mn2`/`Mn3` keep #20's original
   widths; only `Mtail`/`Mload2`'s mirror ratios and the `Cc`/`Rz`
   compensation values changed in #25 (see items 1–2 above and `Mpass`
   above). `L ≥ 1 µm` on every amplifier device (the HV `VGS ≤ 3.3 V`
   rating needs `LG ≥ 0.5 µm`, and longer channels buy the matching and
   output resistance a micro-power amplifier needs). `ng=1` throughout —
   fingering is a phase-4 layout concern.

| Device | Flavour | Size | Role |
| ------ | ------- | ---- | ---- |
| `Mpass` | `sg13_hv_pmos` | `w=2800u l=0.5u m=1` | pass device |
| `Mb0` | `sg13_hv_pmos` | `w=5u l=2u m=1` | bias mirror reference (gate/drain = `IBIAS`) |
| `Mtail` | `sg13_hv_pmos` | `w=5u l=2u m=3` | tail current source |
| `Minp` / `Minn` | `sg13_hv_pmos` | `w=20u l=1u m=1` | input pair (`FB` / `VREF`) |
| `Mn1` / `Mn2` | `sg13_hv_nmos` | `w=5u l=1u m=1` | first-stage mirror (diode / output leg) |
| `Mn3` | `sg13_hv_nmos` | `w=20u l=1u m=1` | second-stage common source |
| `Mload2` | `sg13_hv_pmos` | `w=5u l=2u m=6` | second-stage current-source load |
| `Cc` | `cap_cmomi` | `w=100u l=30u`, M1–M4 | Miller cap, **≈3.2 pF** |
| `Rz` | `rhigh` | `w=1u l=1200u b=0` | nulling/phase-lead resistor, **≈1.70 MΩ** |
| `Rtop` / `Rbot` | `res.sym` | `300k` each | feedback divider, `FB = VOUT/2` |

The operating point implied by the sizes above, at `Iref = 2 µA`: 2 µA
mirror reference + 6 µA tail + 12 µA second stage = 20 µA in the
amplifier, plus 2 µA in the divider = **22 µA** nominal, confirmed by
#25's closed-loop sweep at 21.9–23.0µA (no load) and 23.05–23.08µA (full
load, 50mA) across the full PVT grid — comfortably inside
`spec/porting-plan.md`'s 16–26 µA allocation and the ratified <30µA Iq
target at both load points.

`Cc`'s ≈3.2 pF and `Rz`'s ≈1.70 MΩ are computed the same way the
phase-2 values were: `Cc` by the PDK's own display helper
(`libs.tech/xschem/sg13cmos5l_pr/cap_cmomi.tcl`, which reproduces
`cap_cmomi.va`'s low-frequency capacitance, ≈1.09 fF/µm² over an M1–M4
stack, scaled from the original 30µm-square ≈0.95pF figure by area); `Rz`
by that symbol's own `value` expression evaluated at `w=1 µm`,
`l=1200 µm`, `b=0` (`rhigh.sym`'s `value=expr_eng(...)`, using
`res_typ`'s ≈1360 Ω/sq — the corner sweep in
`sim/ldo-cmos5l-pvt-sweep/records/` shows the real `res_bcs`/`res_wcs`
spread, roughly ≈1.2–1.7 MΩ).

### PDK caveats honoured (evidence rules carried in)

| Caveat | How this branch honours it |
| ------ | -------------------------- |
| **No MIM caps** — `cmim`/`rfcmim` need a layer this PDK forbids | The only capacitor in the hierarchy is `cap_cmomi`, a MoM cap. No MIM symbol is instantiated anywhere. |
| **MoM caps are not validated on CMOS5L silicon** — `cornerCAP.lib` maps every corner/mismatch/stat section to the same nominal model | **Every result that depends on `Cc`'s value is `insufficient-evidence`** — confirmed by issue #21's own reading of `cornerCAP.lib` at this PDK's pin (every section maps to the identical nominal `cap_cmomi` model). That includes every phase- and gain-margin claim about this loop. Selecting a cap corner is a no-op on this PDK, so #21 ran a *value* sensitivity sweep instead (`Cc` width `0.5×`/`1×`/`2×` nominal, at `tt/27°C`): with the phase-2 sizing, phase margin moved between `0.19°` and `0.35°` across that whole range — the near-zero-margin verdict itself did not depend on the uncharacterized `Cc` value. #25 re-ran the same sensitivity sweep at the resized `Cc`/`Rz` and found the PASS verdict holds the same way: phase margin `56.9°`–`76.4°` and gain margin `18.6dB`–`23.5dB` across both the `0.5×`–`2×` nominal `Cc` value sweep and the `res_bcs`/`res_typ`/`res_wcs` `Rz` corner sweep — the qualitative verdict (now PASS) still does not depend on the uncharacterized `Cc` value, even though the exact numbers remain `insufficient-evidence` pending real silicon characterization (`sim/ldo-cmos5l-pvt-sweep/README.md` "MoM-cap (Cc) sensitivity sweep"). |
| **No isolated NMOS** in this PDK's design kit | Honoured by construction: the only NMOS flavour used is `sg13_hv_nmos`. |
| **M1–M4 + TM1 metal stack only** | `Cc` is declared `mmin=1 mmax=4` — an M1–M4 MoM stack. Nothing in this branch's sources or documentation references a second thick top metal. |
| **Bipolar input stage is structurally ruled out** (no HBT; `pnpMPA`'s collector is the substrate and β ≈ 1.1) | No bipolar device is instantiated. DR-0002 §"The installed PDK tree, read directly" is the evidence. |

### Known gaps on this branch

- ~~**The feedback divider is behavioral `res.sym`, not a PDK resistor
  flavour.**~~ **Closed in phase 4a (#28).** `Rtop`/`Rbot` are now real
  `sg13cmos5l_pr/rhigh` instances (`w=1u l=25.43u b=7`, 300.44 kΩ per leg by
  the PDK symbol's own value expression — +0.15 % on the 300 kΩ they replace,
  with the divider ratio exactly 1/2 by construction since both legs are the
  same drawn device). The divider is LVS-visible; see
  `layout/README.md`. **One consequence to carry forward:** the divider now
  carries `rhigh`'s real corner spread, which #21/#25's PVT evidence — taken
  against the behavioural 300 kΩ — predates.
- ~~**`Mpass` (`w=2800u`) and `Rz` (`l=1200u`) have no floorplanned
  layout.**~~ **Closed in phase 4a (#28).** `Rz` is now declared
  `l=28.81u b=39` (forty stripes; a geometry change, not a resize — `leff`
  moves 1200.000 µm → 1199.896 µm, 0.009 % low, and the simulated device is
  unchanged at 1.700 MΩ), and `Mpass` is drawn as 4 rows × 28 fingers × 25 µm
  = 2800 µm. `ng`/`m` stay `1` in the *schematic* on purpose: the
  row/finger split is a layout decision recorded in
  `layout/sg13cmos5l-ldo_core_cmos5l/generate.py`, and the schematic
  continues to state only the electrical total. DR-0003 records the original
  deferral.
- **No enable, current limit, soft start, output capacitor, load, or
  start-up circuit.** Same scope boundary as the SG13G2 branch. Note that a
  self-biased mirror needs no start-up circuit only because `IBIAS` is
  externally driven — if the bias is ever moved on-block, start-up becomes a
  real requirement.
- **No CI job** runs `--design sg13cmos5l --check`.
  `.github/workflows/ci.yml` provisions `ihp-sg13g2` via klayout-tools'
  `scripts/fetch-ihp-sg13g2.sh`, and no equivalent pinned fetch script
  exists for `ihp-sg13cmos5l` — it is a separate upstream repository
  (`IHP-GmbH/ihp-sg13cmos5l`), not a variant directory inside the
  `IHP-Open-PDK` tarball that script downloads. Filed upstream as
  `2AMLogic/klayout-tools#1929`. Until that lands, this branch's check is a
  local/manual step.
- **Install shape is a dispatch hazard.** `ihp-sg13cmos5l`'s device symbols
  and HV model cards are *relative* symlinks into a sibling `ihp-sg13g2`
  checkout (`../../../../ihp-sg13g2/...`). Install **both** variants under
  the same `PDK_ROOT` or every device symbol dangles, and the failure looks
  like a missing device rather than a missing sibling PDK. DR-0002 carries
  this forward for phases 2–4; `2AMLogic/klayout-tools#1406` is the upstream
  report.

### Exporting and checking this branch

```bash
python3 design/netlist.py --design sg13cmos5l            # regenerate
python3 design/netlist.py --design sg13cmos5l --check -v # verify + ERC
python3 design/netlist.py --design sg13cmos5l --cell ldo_erramp_cmos5l -v
```

Requirements are the same as the SG13G2 branch (**`xschem` >= 3.4.7**), plus
an `ihp-sg13cmos5l` install *next to* an `ihp-sg13g2` install under the same
`PDK_ROOT`. `--design` selects the source directory, the top cell, the
expected port list, and the PDK variant together (see `DESIGNS` in
`design/netlist.py`), so neither branch can be netlisted against the other's
PDK by accident.

In the GUI:

```bash
PDK=ihp-sg13cmos5l xschem --rcfile design/xschemrc \
  design/sg13cmos5l/ldo_core_cmos5l.sch
```

PDK devices on this branch are referenced as `sg13cmos5l_pr/<device>.sym`
(never `sg13g2_pr/`), resolved against `$PDK_ROOT/$PDK/libs.tech/xschem`.
Everything else in ["Working in the GUI"](#working-in-the-gui) below applies
unchanged.

## Exporting the netlist

> SG13G2 branch. For `design/sg13cmos5l/`, see
> ["Exporting and checking this branch"](#exporting-and-checking-this-branch)
> above.

```bash
python3 design/netlist.py            # regenerate design/netlist/*.spice
python3 design/netlist.py --check    # verify committed netlists are current
python3 design/netlist.py --cell ldo_erramp_placeholder -v
```

Requirements: **`xschem` >= 3.4.7** on `PATH`, plus the `ihp-sg13g2` PDK
installed. `design/netlist.py` resolves the PDK itself (`PDK_ROOT`/`PDK` env
vars, falling back to the usual open_pdks-shaped search roots:
`/usr/share/pdk`, `/usr/local/share/pdk`, `~/share/pdk`, `~/.ciel`,
`~/.volare`) — this repo has no `sim/` harness yet, so there is no second
PDK-discovery implementation to keep in sync; see `design/netlist.py`'s own
module docstring for the full resolution order and its relationship to this
fleet's `sg13g2-bandgap`/`sg13g2-pll` `sim/env.sh` convention.

> **Why the version floor:** Ubuntu 24.04's apt package (xschem 3.4.4-1) has
> a `top_is_subckt` regression — it fails to wrap the top-of-invocation cell
> as an active `.subckt`, instead emitting a double-comment-prefixed
> `**.subckt`/`**.ends` pair, even though this file's `xschemrc` sets
> `top_is_subckt 1`. `netlist.py` netlists every cell individually (each
> cell is the "top of invocation" for its own xschem run), so every cell
> hits this — not just `ldo_core` — which is why `--check` fails on an
> otherwise-unmodified worktree with `.subckt <cell> not found in its own
> netlist`. This is the identical regression `2AMLogic/gf180-temp-por` hit
> and fixed (its own issue #89 / PR #95). xschem 3.4.7 does not have this
> defect and reproduces `design/netlist/*.spice` byte-for-byte; there is no
> known-good newer apt/PPA package as of this writing, so CI
> (`.github/workflows/ci.yml`) builds 3.4.7 from source rather than relying
> on the distro package. If your local `xschem --version` is older than
> 3.4.7, do the same: download a
> [3.4.7+ release tarball](https://github.com/StefanSchippers/xschem/releases),
> then `./configure && make && sudo make install`.

Under the hood, per cell, with xschem's electrical rule check enabled:

```bash
xschem -x -q -r --rcfile design/xschemrc -o <outdir> design/<cell>.sch \
  --command "xschem netlist -erc"
```

`-x` batch (no X11), `-q` quit when done, `-r` no tclreadline.
`design/xschemrc` sets the library path (xschem generic devices → PDK
symbols → `design/`) and, critically, `top_is_subckt 1`: **every** cell —
including the top — netlists as a `.subckt`, never as a flat simulation
deck. Cells here are blocks a future testbench instantiates; the deck
belongs to the testbench.

`netlist.py` then rewrites the absolute paths xschem records in its
`sch_path`/`sym_path` comments to repo-relative form, and treats any of
xschem's undriven-node / open-net / shorted-node / shorted-pin /
missing-symbol messages as a hard failure (xschem does not reliably signal
these through its exit code alone, so a naive exit-code check would miss
them). That is what makes the export **deterministic and ERC-checked**: the
same sources produce byte-identical netlists on any machine, and a broken
wire never silently ships.

### What `--check` verifies

1. **Committed netlists are current** — regenerating into a temp directory
   reproduces `design/netlist/*.spice` byte-for-byte. This is simultaneously
   the staleness check and the reproducibility check.
2. **ERC is clean** — see above.
3. **The top-level pinout matches the interface table above** — exact port
   list and order.
4. **Symbol pins match schematic ports**, per cell, in order. xschem takes
   the `.subckt` port list from the *symbol* when one exists, so a symbol
   that has drifted from its schematic silently drops or miswires a port on
   every instantiation.
5. **Every sub-circuit is instantiated in the top level** with the right
   number of nets.

`--check` exits non-zero on any failure and prints the offending diff.

## Using the netlist from a future testbench

`design/netlist/` holds one file per cell:

- `ldo_core.spice` — the whole hierarchy: `ldo_core` plus every sub-circuit
  it instantiates (currently just `ldo_erramp_placeholder`). Include this to
  simulate the block.
- `ldo_erramp_placeholder.spice` — that sub-circuit alone.

```spice
.include design/netlist/ldo_core.spice
Xdut VIN VOUT VSS VREF ldo_core
```

> **Include exactly one of these files per deck.** `ldo_core.spice` already
> contains the sub-circuit definition; including it *and*
> `ldo_erramp_placeholder.spice` redefines the same `.subckt` twice.

Port order is positional in SPICE — take it from the `.subckt` line of the
file you include, or from the symbol pin list, which the check above keeps
in sync.

The SG13CMOS5L branch has its own `design/sg13cmos5l/netlist/` with the same
one-file-per-cell shape — `ldo_core_cmos5l.spice` (whole hierarchy) and
`ldo_erramp_cmos5l.spice` (the amplifier alone). Its top-level port list is
five wide, not four:

```spice
.include design/sg13cmos5l/netlist/ldo_core_cmos5l.spice
Xdut VIN VOUT VSS VREF IBIAS ldo_core_cmos5l
```

A testbench for that branch must also sink a bias current out of `IBIAS`
(see ["Error amplifier"](#error-amplifier-1) under "SG13CMOS5L branch") —
leaving it open starves the amplifier.

## Working in the GUI

```bash
export PDK_ROOT=/path/to/pdk-root PDK=ihp-sg13g2   # or rely on the search roots below
xschem --rcfile design/xschemrc design/ldo_core.sch
```

Conventions:

- **PDK devices are referenced as `sg13g2_pr/<device>.sym`** (e.g.
  `sg13g2_pr/sg13_hv_pmos.sym`), resolved against
  `$PDK_ROOT/$PDK/libs.tech/xschem`. Never write an absolute PDK path into a
  schematic.
- **Generic xschem devices are referenced by bare name** (e.g. `res.sym`,
  `vcvs.sym`, `ipin.sym`, `opin.sym`, `iopin.sym`, `lab_pin.sym`) —
  `design/xschemrc` puts the xschem-install `devices/` directory itself on
  the library path, not just its parent, so the unqualified form resolves.
- **Project cells are referenced by bare name** (`ldo_erramp_placeholder.sym`),
  resolved against `design/`.
- **Connectivity is expressed with net labels** (`lab_pin.sym` placed near a
  device pin, or the `lab=` attribute on an `ipin`/`opin`/`iopin` instance),
  not by relying on wires happening to touch across the schematic.
- **Do not hand-edit `design/netlist/*.spice`.** Edit the schematic and
  re-run the export; `--check` will catch it if you forget.
- **Keep symbol pins and schematic ports in the same order.** When you add a
  port, add it to both the `.sch` and the `.sym`.
- Re-run `python3 design/netlist.py` and commit the regenerated netlists
  with the schematic change, so the netlist in the tree always matches the
  sources.
