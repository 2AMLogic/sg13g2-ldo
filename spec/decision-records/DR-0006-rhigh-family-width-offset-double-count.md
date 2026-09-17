# DR-0006: `rhigh`-family width-offset double-count — verdict and upstream disposition

- **Status**: Proposed (this PR is the ratification act — see "Status"
  below).
- **Date**: 2026-09-17
- **Scope**: **Documentation and upstream disposition only.** This record
  settles the question `DR-0004`'s "Separate observation" section left
  open (issue #36) — whether the PDK's `rhigh` symbol-expression/simulated
  4.35 % gap is a PDK bug or an intentional convention — and records where
  it was filed. It changes **no drawn value, no device size, no simulated
  result, and no spec row**. `DR-0004`'s own text is unmodified; this
  record supplements it rather than amending a ratified record, per
  `CLAUDE.md`'s instruction that spec changes go through their own record.
- **Related**:
  [`DR-0004`](DR-0004-sg13cmos5l-resistor-corner-stability.md) (the record
  whose "Separate observation" section first measured and named this gap,
  and explicitly deferred the verdict: *"Whether the double-count is a PDK
  bug or an intentional convention is not something this repo can settle
  from the installed tree alone; it is filed as its own follow-up..."*),
  issue #31 (the PVT run that produced the measurement), issue #36 (this
  record's own tracking issue).

## Status

**Proposed.** Per the fleet's standing ratification policy
(`2AMLogic/2am#357`: "a builder drafts the ratification/DR as a PR on the
evidence, and the operator's PR approval is the ratification act"), this
record is drafted as a PR on the evidence gathered below. **Operator
approval of that PR is what moves this record to Accepted** — there is no
separate ratification step.

## Context

`DR-0004`'s "Separate observation" section found that `rhigh.sym`'s
schematic-capture `value=` expression and the `r3_cmc` model every
simulation actually loads disagree by 4.35 % — 300.44 kΩ vs 313.5 kΩ for
the feedback-divider legs, 1.700 MΩ vs ≈1.774 MΩ for `Rz` — and traced the
mechanism to a width offset applied twice: `resistors_mod.lib`'s `.subckt
rhigh` narrows `w` by `0.04 µm` before handing `W=weff` to its `r3_cmc`
`.model` card, and that same model card's own `xw=-0.04` narrows it again.
That record explicitly declined to say whether this was a bug or a
deliberate convention, and filed the question forward rather than guessing.
This record is that follow-up.

## Investigation

Performed directly against the installed PDK tree (`$PDK_ROOT/ihp-sg13g2`,
`IHP-Open-PDK` v0.3.0 per `.fetched-version`), not inferred from `DR-0004`'s
summary.

### 1. Is the double application really there, and is it the same file both branches use?

`ihp-sg13cmos5l/libs.tech/ngspice/models/resistors_mod.lib` is a relative
symlink to `../../../../ihp-sg13g2/libs.tech/ngspice/models/resistors_mod.lib`
(confirmed directly, `ls -la`) — the same file `design/README.md`'s
"Install shape is a dispatch hazard" already documents this symlink
relationship for. There is one `resistors_mod.lib`, not two, so this is
not a question of divergence between the SG13G2 and SG13CMOS5L PDK trees —
whatever is true of one is true of both by construction.

`resistors_mod.lib`'s `.subckt rhigh`:

```
.subckt rhigh 1 2 bn
.param w=0.5e-6 l=0.96e-6 mm_ok=1 b=0 trise=0 m=1 sw_et=0
...
+weff=w-0.04e-6
+leff=(b+1)*l+(2/kappa*weff+ps)*b
...
NR1 1 bn 2 dt rmod_rhigh L=leff W=weff m=m
...
.model rmod_rhigh r3_cmc
...
+xw=-0.04
```

`libs.tech/verilog-a/r3_cmc/r3_cmc.va` (the compact-model source these
`.model` cards parameterize, compiled to the `r3_cmc.osdi` this repo's
`sim/tools/build-osdi.sh` builds and every testbench loads):

```
`MPRnb( xw        ,   0.0     ,"um"                      , "width  offset (total)")
...
weff_um  = (w_um+xw+(nwxw/w_um)+fdxwinf*(1.0-exp(-w_um/fdrw)))/(1.0-wexw*wd_um/a_um2);
```
(`r3_cmc.va` lines 153, 377). `w_um` is the model's own `W=` instance
parameter — i.e. the *already-narrowed* `weff` the subckt passed in — and
`xw` is added to it directly. The parameter's own doc string calls it the
width offset "(total)", not a residual on top of an already-applied one.
This is the exact double-count `DR-0004` described, confirmed at the
Verilog-A source rather than inferred from behavior.

### 2. Do the sibling `rhigh`-family devices show the same pattern?

Yes, identically, for both other `r3_cmc`-based resistor flavours in the
same file:

| Device | subckt `weff` offset | `.model` card `xw` | Foundry `DW*` target (`SG13G2_os_process_spec.pdf` Rev 1.2) |
| --- | --- | --- | --- |
| `rhigh` | `w - 0.04e-6` | `-0.04` | `DWRHIGH` (Sec 2.9): `-40 nm` |
| `rsil` | `w + 0.01e-6` | `0.01` | `DWRSIL` (Sec 2.7): `+10 nm` |
| `rppd` | `w + 0.006e-6` | `0.006` | `DWRPPD` (Sec 2.8): `+6 nm` |

Every `r3_cmc`-based resistor subckt in the file applies the construction;
the only resistor devices in this file that do *not* (`ptap1`, `ntap1`,
`Rparasitic`) use a plain SPICE `R` primitive with no `weff`/`xw` machinery
at all, so they are not evidence either way. The pattern is uniform across
the whole `r3_cmc` resistor family, in both the `ngspice` and `xyce` copies
of `resistors_mod.lib` under `libs.tech/`.

This repo's own design only instantiates `rhigh` (`Rtop`/`Rbot`/`Rz` —
`design/sg13cmos5l/ldo_core_cmos5l.sch`, `ldo_erramp_cmos5l.sch`); `rsil`
and `rppd` are not used anywhere in this hierarchy (see
`ldo_core_cmos5l.sch`'s header, "rhigh, not rsil/rppd"), so the `rsil`/
`rppd` rows above are upstream-scope findings, not something with a
committed simulated value in this repo to correct.

### 3. Which side disagrees with the foundry's own documented figures?

`SG13G2_os_process_spec.pdf` Rev 1.2's per-device tables (Sec 2.7–2.9) each
give exactly **one** "Line Width Delta" (`DW*`) target — not two, and not a
doubled one. That single target matches the subckt-level `weff` offset
exactly, and separately matches the model card's `xw` exactly (see table
above) — which is precisely what would be expected if one of the two
applications is a leftover of the model's calibration/wrapper history and
the other is the "real" one, not evidence that the two are meant to
compound. Nothing in the foundry document, the subckt, the `.model` card,
or `r3_cmc.va`'s own comments states or implies a doubled total. This is
the basis for the verdict below, not an assumption.

## Decision

1. **Confirmed: PDK bug, not an intentional convention.** The width offset
   is applied twice where the foundry's own process spec, the subckt
   construction, and the compact model's own parameter documentation all
   point to it being applied once. No sibling `r3_cmc` resistor flavour in
   the installed tree shows evidence of a deliberate doubled-offset
   convention — the pattern is uniform, but uniformity here reads as a
   copy-pasted subckt-wrapper bug propagated across three devices, not as
   a documented design intent for any of them.

2. **Scope**: all three `r3_cmc`-based resistor flavours in
   `resistors_mod.lib` — `rhigh`, `rsil`, `rppd` — in both the `ngspice`
   and `xyce` copies of the file, under both the `ihp-sg13g2` and
   `ihp-sg13cmos5l` PDK trees (one shared file via the symlink documented
   in `design/README.md`). This repo's own design is affected via `rhigh`
   only (`Rtop`, `Rbot`, `Rz`) — `rsil`/`rppd` are not instantiated
   anywhere in this hierarchy.

3. **Filed upstream**: `IHP-Open-PDK` owns `resistors_mod.lib`
   (`sim/pdk.json`'s `source`), so the finding was filed there rather than
   at `2AMLogic/klayout-tools` — per `CLAUDE.md`'s friction protocol, this
   is a PDK modelling discrepancy, not a `klayout-tools` tool gap.
   [`IHP-GmbH/IHP-Open-PDK#1235`](https://github.com/IHP-GmbH/IHP-Open-PDK/issues/1235)
   carries the full arithmetic, the three-device table above, and a
   suggested fix (drop the subckt-level pre-narrowing, or zero the
   `.model` card's `xw` — whichever matches the model's original
   calibration, which this repo cannot determine from the installed tree
   alone).

4. **No value in this repo changes.** Every committed `sim/` record
   already simulated the double-narrowed model (`DR-0004`'s point,
   restated: this was equally true of the `#21`/`#25` records, so no prior
   result moves). This record's only effect is documentary: every place
   quoting a `rhigh` symbol-expression value now states the simulated
   value alongside it and this record's verdict, rather than leaving a
   reader with two numbers and no answer. `DR-0004`'s own file is left
   unmodified — its "Separate observation" section is a historical record
   of what was known at #31/#35 time, and remains accurate as that; this
   record is the linked follow-up that section itself called for.

## Options considered and rejected

- **Normalise the double-count in this repo's own models or netlists**
  (e.g. patch a local copy of `resistors_mod.lib`, or hand-correct `Rz`'s
  drawn size to compensate). Rejected. `CLAUDE.md`: "the PDK is the
  variable, not the design" — this repo consumes the installed PDK tree
  as-is and routes friction upstream rather than forking around it. A
  local patch would also silently desynchronize this repo's simulated
  results from what a from-scratch install of the pinned PDK version
  actually produces, which is worse than the documented discrepancy it
  would "fix".
- **Leave the verdict unresolved pending upstream's response.** Rejected.
  The acceptance criteria for issue #36 require the confirm/refute step
  and the file/line evidence now, not contingent on an external
  maintainer's timeline; the upstream issue is the mechanism for getting a
  fix, not a precondition for stating what this repo's own investigation
  already found.
- **File the finding at `2AMLogic/klayout-tools` instead**, matching this
  repo's usual friction-protocol target. Rejected — explicitly out of
  scope per `CLAUDE.md`'s friction protocol and this issue's own framing:
  this is a PDK modelling discrepancy in a foundry-owned model file, not a
  `klayout-tools` capability gap.

## Consequences

- Every schematic header and `design/README.md` passage that quotes a
  `rhigh` symbol-expression value now carries the simulated value and this
  record's verdict alongside it, closing the last open item `DR-0004`'s
  "Separate observation" section left (*"Whether the double-count is a PDK
  bug or an intentional convention is not something this repo can settle
  from the installed tree alone"* — it now has been).
- `ldo_erramp_cmos5l.sch`'s header previously mislabeled its `Rz`
  before/after-meander comparison (`1.70001 MOhm` vs `1.70016 MOhm`) as
  "the simulated device" when those were in fact the symbol-expression
  (single-narrowed) values; that header is corrected alongside this record
  to also state the true simulated (double-narrowed) pair, ≈1.774 MΩ
  either side of the meander.
- If and when `IHP-GmbH/IHP-Open-PDK#1235` lands a fix upstream, every
  `rhigh`-instancing simulated result in this repo's `sim/` tree will shift
  toward the symbol-expression numbers (`Rz`: 1.774 MΩ → 1.700 MΩ, roughly
  a 4.2 % *decrease* in nulling-resistor value — `DR-0004`/`DR-0005`'s
  margin story was built on the larger, double-narrowed `Rz`, so a smaller
  post-fix `Rz` is worth a re-run at that time to confirm phase margin at
  `res_bcs`/125 °C still holds, not assumed benign). That re-verification
  is future work tied to the upstream fix landing, not owned by this
  record.
