# design/ — xschem sources and netlist export

Schematic entry for the LDO core, in xschem, against the `ihp-sg13g2` PDK.
This directory is the source of truth for the block's electrical interface —
a future `sim/` harness and `layout/` LVS flow will both consume the
netlists exported from here.

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
any dropout, current-limit, or area target. The confirming screening deck
`spec/porting-plan.md` §4 item 1 calls for (`Ron·W` and `Vth` measured
directly against SG13G2's own `sg13_hv_pmos` model, at the `Vin = Vout +
dropout ≈ 2.10 V` test point and at the continuous-short condition) has not
been run — that is out of scope for this issue and is the single most
consequential follow-on decision record this port owes
(`spec/porting-plan.md` §4 item 1). Do not read this width as a dropout- or
area-sized value; it mirrors how `gf180-ldo`'s own first design-source
issue (#8) flagged its pass-device width as "2 mm, #8's DC-sanity
simplification of the ratified ~4 mm sizing" rather than presenting it as
final.

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

## Exporting the netlist

```bash
python3 design/netlist.py            # regenerate design/netlist/*.spice
python3 design/netlist.py --check    # verify committed netlists are current
python3 design/netlist.py --cell ldo_erramp_placeholder -v
```

Requirements: `xschem` on `PATH` and the `ihp-sg13g2` PDK installed.
`design/netlist.py` resolves the PDK itself (`PDK_ROOT`/`PDK` env vars,
falling back to the usual open_pdks-shaped search roots: `/usr/share/pdk`,
`/usr/local/share/pdk`, `~/share/pdk`, `~/.ciel`, `~/.volare`) — this repo
has no `sim/` harness yet, so there is no second PDK-discovery
implementation to keep in sync; see `design/netlist.py`'s own module
docstring for the full resolution order and its relationship to this
fleet's `sg13g2-bandgap`/`sg13g2-pll` `sim/env.sh` convention.

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
