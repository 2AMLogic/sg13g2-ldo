# DR-0002: SG13CMOS5L port — pass device `sg13_hv_pmos`, CMOS-input error amplifier

- **Status**: Proposed (this PR is the ratification act — see "Status" below).
- **Date**: 2026-09-15
- **Scope**: The **SG13CMOS5L branch only** (issue #19, phase 1/4 of the
  SG13CMOS5L port tracked by #12, Epic `2AMLogic/2am#542` Phase 5A). This
  record does **not** ratify, amend, or pre-decide anything on the SG13G2
  branch — see "Does this motivate an equivalent SG13G2 record?" below,
  which answers that scope question explicitly rather than leaving it
  implicit.
- **Related**: [`DR-0001`](DR-0001-pass-device-flavor.md) (SG13G2 pass
  device — read first; this record extends it to a second PDK and inherits
  its carried-forward `|Vsg|` constraint), `spec/porting-plan.md` §2.1,
  §2.2, §4 items 1 and 5, `design/README.md` "Pass device" / "Error
  amplifier", `2AMLogic/2am` `docs/pdk/sg13cmos5l.md` (PDK verdict, install
  path, analog caveats), `2AMLogic/sg13g2-bandgap`
  `spec/decision-records/0004-cmos5l-bipolar-device-selection.md` (the
  fleet's precedent for a CMOS5L device-selection phase-1 record; a
  *bandgap* core, a different block with a genuinely bipolar requirement),
  #20 (phase 2, schematic capture — consumes this record), `2AMLogic/2am#357`
  (the ratification policy this record follows).

## Status

**Proposed.** Per the fleet's standing ratification policy
(`2AMLogic/2am#357`: "a builder drafts the ratification/DR as a PR on the
evidence, and the operator's PR approval is the ratification act"), this
record is drafted as a PR on the evidence gathered below. **Operator
approval of that PR is what moves this record to Accepted** — there is no
separate ratification step.

This record recommends **one** pass-device flavor and **one** error-amplifier
topology. It does not present a menu.

## Context

### What this phase had to settle, and what it must not assume

#12's decomposition scopes this phase to two questions for the SG13CMOS5L
branch:

1. **Pass device** — `DR-0001` ratified `Mpass` as `sg13_hv_pmos`,
   common-source, for SG13G2. Does that transfer to SG13CMOS5L, or does the
   device menu force something else?
2. **Error amplifier** — `Xamp` (`design/ldo_erramp_placeholder.sch`) is
   still an ideal VCVS. `design/README.md` "Error amplifier" states the full
   topology decision ("bipolar vs. CMOS input stage, on-chip bandgap vs.
   external `VREF`") is out of scope for the issue that created it, and
   `spec/porting-plan.md` §4 item 5 still lists it as an open record **for
   SG13G2**. So this is not a port of an existing bipolar amplifier: no
   amplifier topology has ever been ratified for *either* PDK in this repo.

**A claim this record explicitly does not carry forward.** An earlier
Champion review of #12 (2026-08-29, repeated 2026-08-30 and 2026-09-16)
asserted that this repo's design "depends on the same device class [SiGe
HBT] ... chosen specifically because SG13G2 offers a real HBT over a
parasitic PNP," citing "decision record 0001." That is **incorrect for this
repo**: `DR-0001` here ratifies a *MOSFET* pass device and its own "Bipolar
pass device — considered, not adopted" section rejects bipolar on Iq
grounds. Re-verified on this branch:

```
$ grep -rlniE 'npn|hbt' design/*.sch design/*.sym
(no matches)
$ grep -rniE 'pnp|bipolar' design/*.sch design/*.sym design/README.md
design/ldo_core.sch:43:* (bipolar vs. CMOS input stage, on-chip bandgap vs. external VREF) is
design/README.md:116:A full amplifier topology decision — bipolar vs. CMOS input stage, on-chip
design/ldo_erramp_placeholder.sch:11:* pattern by name). A full bipolar-vs-CMOS input-stage decision for a
```

All three matches are prose recording that the amplifier decision is
*undecided*.
No bipolar device is instantiated anywhere in `design/`. The claim appears to
conflate this repo's `DR-0001` with `sg13g2-bandgap`'s differently-scoped
`0001-bipolar-device-selection.md` (a bandgap core, which genuinely does need
bipolar devices for PTAT/CTAT generation). **Every device-availability claim
below was therefore re-derived by reading the installed PDK tree directly**,
not inherited from that review or from any summary document.

### The installed PDK tree, read directly

Host `robb-studio`, `~/share/pdk/ihp-sg13cmos5l`, `git log -1` =
`607e18d4bd9214a52575c194b4181ef449f9252f` — the exact commit
`2AMLogic/2am` `docs/pdk/sg13cmos5l.md` ("Install path / commit per host")
records for all four fleet hosts. Cross-checked against the PDK's own
`libs.doc/doc/SG13CMOS5L_os_process_spec.pdf` (Rev. 0.2, 2025-12-15).
Paths below are relative to that PDK root.

**1. The MOS front end is literally the same files as SG13G2, not merely
"aligned with" it.**

`libs.tech/xschem/sg13cmos5l_pr/` contains 33 entries. Every MOS symbol this
design could use is a **symlink into the sibling `ihp-sg13g2` checkout**:

```
sg13_hv_pmos.sym -> ../../../../ihp-sg13g2/libs.tech/xschem/sg13g2_pr/sg13_hv_pmos.sym
sg13_hv_nmos.sym -> ../../../../ihp-sg13g2/libs.tech/xschem/sg13g2_pr/sg13_hv_nmos.sym
sg13_lv_pmos.sym -> ../../../../ihp-sg13g2/libs.tech/xschem/sg13g2_pr/sg13_lv_pmos.sym
pnpMPA.sym       -> ../../../../ihp-sg13g2/libs.tech/xschem/sg13g2_pr/pnpMPA.sym
```

(plus `sg13_lv_nmos`, the four `sg13_*_rf_*` variants, `sg13_svaricap`,
`moscap_n`/`moscap_p`, `ntap1`/`ptap1`/`sub`, `rsil`/`rppd`/`rhigh`, the
`cap_cmom*` MoM caps, and the ESD/antenna cells.)

The same holds on the simulation side. In `libs.tech/ngspice/models/`:

```
cornerMOShv.lib          -> ../../../../ihp-sg13g2/libs.tech/ngspice/models/cornerMOShv.lib
cornerMOSlv.lib          -> ../../../../ihp-sg13g2/libs.tech/ngspice/models/cornerMOSlv.lib
sg13g2_moshv_mod.lib     -> ...  (and _parm/_stat/_mismatch/_mod_mismatch)
```

and in `libs.tech/ngspice/osdi/`, the compiled PSP103 binary itself:

```
psp103.osdi -> ../../../../ihp-sg13g2/libs.tech/ngspice/osdi/psp103.osdi
```

Reading through those symlinks, `cornerMOShv.lib`'s corner sections are still
named `mos_tt` / `mos_ss` / `mos_ff` / `mos_sf` / `mos_fs` (plus `_mismatch`
and `_stat` variants), and its parameters are still spelled
`sg13g2_hv_pmos_*` / `sg13g2_hv_nmos_*`. **On this install, an HV-MOS ngspice
simulation run under `PDK=ihp-sg13cmos5l` and one run under `PDK=ihp-sg13g2`
resolve to byte-identical model cards and the same compiled PSP103 binary.**
The two processes differ in the back end of line (M1–M4 + a single 2 µm TM1,
per `docs/sg13cmos5l.md`'s metal-stack bullet), not in the MOS device models.

*Install-shape caveat*: because these are relative symlinks into a
`../../../../ihp-sg13g2` sibling, they are dangling in an
`ihp-sg13cmos5l`-only install. They resolve on this host because
`~/share/pdk/ihp-sg13g2` is also present. `docs/pdk/sg13cmos5l.md` records
`ihp-sg13g2` as persistent on `loom-worker-1` only, `/tmp`-rooted on
`robb-pro`/`loom-worker-2`, and absent on `robb-studio` (tracked at
`2AMLogic/2am#544`) — so this is a real dispatch hazard for phases 2–4, not a
device-availability question. It is carried forward in "Consequences", not
resolved here.

**2. There is no SiGe HBT — confirmed by absence in three independent
places, not by a doc summary.**

| Check | `ihp-sg13g2` | `ihp-sg13cmos5l` |
| --- | --- | --- |
| xschem symbols matching `npn`/`hbt` | `npn13G2{,l,v}{,_5t}.sym` (6 files) | **none** |
| ngspice model files matching `npn`/`hbt` | `cornerHBT.lib`, `sg13g2_hbt_{mod,mod_mismatch,stat}.lib` | **none** |
| Process-spec device sections | HBT sections present | **§2.1 is NMOS / PMOS / iNMOS / HV-NMOS / HV-PMOS / HV-iNMOS; §2.2 is Rsil / Rppd / Rhigh / S-Varicap. No bipolar device section exists.** |

The process spec's §1.4 processing sequence does still list "Bipolar Window
opening / Collector Window opening / Emitter opening / Emitter Poly
definition / Base Poly definition" — the module steps are retained — but no
bipolar device is *characterized* anywhere in the spec, and none is offered
in the design kit. `SG13CMOS5L_os_process_spec.pdf` §5 "Known Issues" is
empty in Rev. 0.2.

**3. The only bipolar device is `pnpMPA`, and it is structurally unusable for
either of this record's two roles.** This is the finding that decides the
error-amplifier question, so it is stated with its evidence:

- **Its collector is the substrate.** The PDK's own LVS unit testcase,
  `libs.tech/klayout/tech/lvs/testing/testcases/unit/bjt_devices/netlist/pnpMPA.cdl`,
  is headed `* CMOS5L pnpMPA test structure - lateral PNP without nBuLay
  isolation` and instantiates the device as:

  ```
  QQ1 sub! PAD VDD pnpMPA a=2e-12 p=6e-06 m=1
  ```

  i.e. collector = `sub!`, the global substrate node. The model card agrees:
  `sg13cmos5l_pnpMPA_mod.lib` derives `isc` and `ikr` from a substrate area
  (`sub_a`/`sub_p` defaults `ac=13.33p`, `pc=14.64u`) and sets `cjs = 0` —
  there is no collector–substrate junction to model because the collector
  *is* the substrate. **A device whose collector is hard-tied to `VSS`
  cannot be a differential-pair input transistor** (a differential pair needs
  two independent collector nodes to develop a differential output current)
  and **cannot be a series pass element** (the pass element's output terminal
  must be `VOUT`, not the substrate).
- **Its current gain is ≈ 1.** `sg13cmos5l_pnpMPA_mod.lib` sets
  `bf = '1.10*sgp_mpa_bf'`, with `sgp_mpa_bf` scaled 0.76 (`wcs`) … 1.24
  (`bcs`) in `cornerPNP.lib`. At β ≈ 1.1, α = β/(1+β) ≈ 0.52 — roughly half
  the emitter current is base current. Against `spec/porting-plan.md`'s
  ≈16–26 µA total-block Iq allocation (and the tighter 10 µA stretch), an
  input stage built from this device would spend its entire budget on base
  current. The same model card also carries `rb = 'rb0*sgp_mpa_rb'` with
  `rb0 = 700` Ω, a base resistance that would dominate the amplifier's
  input-referred noise.
- It *is* extracted by the SG13CMOS5L LVS deck
  (`libs.tech/klayout/tech/lvs/rule_decks/bjt_extraction.lvs`:
  `extract_devices(CustomBJTExtractor.new('pnpMPA', true), ...)`;
  `globals.lvs`: `'pnpMPA' => 'Q'`), so the constraint is a device-physics
  constraint, not a deck gap. The device is perfectly usable in the role it
  is characterized for — the model card's own header reads
  `DUT: diode_pp=pnpMPA`, i.e. diode-connected — which is exactly the role
  `sg13g2-bandgap`'s `0004` adopts it for. It is not usable as an amplifier
  input device or a pass element.

*(Noted in passing: `ihp-sg13g2`'s `libs.tech/ngspice/models/` contains no
`pnpMPA` model file at all, even though `sg13g2_pr/pnpMPA.sym` exists — so
`pnpMPA` is simulatable on SG13CMOS5L and not on SG13G2. Not load-bearing
for this record; recorded because it inverts the intuition that SG13G2's
device menu is a superset of SG13CMOS5L's.)*

**4. HV vs. LV ratings, from the process spec.** The Challenge #6 brief pairs
a 1.2 V digital rail with a **3.3 V analog rail** (`docs/pdk/sg13cmos5l.md`,
"Rails"; #12). Every device in this block sits on the analog rail.

| | LV (`§2.1.2 PMOS`) | HV (`§2.1.5 HV-PMOS`) |
| --- | --- | --- |
| Max `VGS` | **≤ 1.65 V @ 125 °C** | ≤ 3.3 V @ 27 °C, `LG ≥ 0.5 µm` |
| `BVDSS` (max/min) | −2.2 / −2.9 V (`BVDSSP013`) | −5.3 / −6.3 V (`BVDSSPHV04`) |
| `Vth` (min/target/max) | −0.41 / −0.47 / −0.53 V (`VTP10x013`) | −0.59 / −0.65 / −0.71 V (`VTPHV10x04`) |
| `Idsat` | −215 µA/µm (`IDSP013`) | −240 µA/µm (`IDSPHV04`) |

and for the n-side, `§2.1.4 HV-NMOS`: `VTNHV10x045` = 0.63 / **0.70** /
0.77 V, `IDSNHV045` = 560 µA/µm, `BVDSSNHV013` ≥ 5.3 V.

**LV devices are disqualified for anything referenced to the 3.3 V analog
rail** — a −2.2 V worst-case `BVDSS` cannot survive a 3.3 V (3.63 V at the
`+10 %` Input-row corner) rail across the device, and the 1.65 V `VGS` limit
is exceeded by more than 2× at the continuous-short bias `DR-0001` already
characterizes. This is a rating fact from the PDK's own spec, not a margin
judgement.

*(Refinement to a carried-in evidence rule: `docs/pdk/sg13cmos5l.md`'s
analog-caveat bullet "**No isolated NMOS**" is correct **as a design-kit
fact** — no `inmos`/`iNMOS` symbol or ngspice model exists in
`libs.tech/xschem/sg13cmos5l_pr/` or `libs.tech/ngspice/models/`. The process
spec does characterize iNMOS (§2.1.3) and HV-iNMOS (§2.1.6) at the
process-control level, so the device exists in silicon but is not offered in
the kit. The rule stands unchanged and is honoured below; the nuance is
recorded so a future reader does not mistake the spec sections for a
contradiction.)*

### Input common-mode range: the number that picks the input-pair flavour

`design/ldo_core.sch` divides `VOUT` with `Rtop = Rbot = 300 k` against an
assumed `VREF = 0.9 V` for `VOUT = 1.8 V` (both provisional, per
`design/README.md`). So the amplifier's input common-mode level is
**≈ 0.9 V** on a 3.3 V rail — and if #20 retargets the output downward
toward the brief's 1.2 V digital rail, `FB` moves *lower*, not higher.

Against the HV thresholds above:

- **HV-NMOS input pair**: needs `VICM ≥ Vth(max) + Vov + Vdsat(tail)` ≈
  `0.77 + 0.1 + 0.15` ≈ **1.0 V** at 27 °C typical-max, before any `ss`-corner
  or cold-temperature `Vth` increase. At `VICM ≈ 0.9 V` the pair is at or
  below its lower ICMR limit **in the nominal case**, and further out of
  range at every corner that raises `Vth` or at any lower `VOUT` target.
- **HV-PMOS input pair**: upper ICMR limit ≈ `VDD − |Vth(max)| − Vov −
  Vdsat(tail)` ≈ `3.3 − 0.71 − 0.1 − 0.15` ≈ **2.3 V**; lower limit is set by
  the NMOS mirror load's `Vdsat` plus the input device's own `Vds,sat`,
  ≈ **0.3 V**. `VICM ≈ 0.9 V` sits comfortably inside that window with ≈ 0.6 V
  of headroom below and ≈ 1.4 V above, and stays inside it for a 1.2 V output
  retarget (`FB` ≈ 0.6 V).

This is a first-order hand calculation from process-spec threshold data, not
a simulated ICMR sweep. It is decisive enough to *choose* the flavour — the
NMOS pair fails nominally, not marginally — and phase 3 (#21) still owes the
simulated ICMR sweep that confirms it, per this repo's "no claim without a
testbench" rule.

## Decision

### (a) Pass device — `sg13_hv_pmos`, common-source, unchanged from `DR-0001`

**Adopt `sg13_hv_pmos` (the HV/3.3 V-class thick-oxide PMOS) as `Mpass` for
the SG13CMOS5L port, common-source: source tied to the 3.3 V analog input
rail, drain to `VOUT`, body to source.** This is the same flavour and the
same topology `DR-0001` ratified for SG13G2.

Why, specifically for this PDK:

1. **The device exists under the same name, in the same role.**
   `libs.tech/xschem/sg13cmos5l_pr/sg13_hv_pmos.sym` is present (symlinked to
   the SG13G2 symbol), with `model=sg13_hv_pmos`, `spiceprefix=X`, and the
   `w`/`l`/`ng`/`m` parametrization `design/ldo_core.sch`'s `Mpass` already
   uses. The SG13CMOS5L LVS deck extracts it by that exact name
   (`mos_extraction.lvs`: `extract_devices(mos4('sg13_hv_pmos'), ...)`;
   `globals.lvs`: `'sg13_hv_pmos' => 'M'`) and ships a unit testcase for it
   (`testcases/unit/mos_devices/netlist/sg13_hv_pmos.cdl`). So the choice is
   verifiable end-to-end in this PDK's own flow, not only simulatable.
2. **The ratings clear on this PDK's own process spec.** `§2.1.5 HV-PMOS`
   gives `VGS ≤ 3.3 V`, `BVDSSPHV04` = −5.3 … −6.3 V, `VTPHV10x04` = −0.65 V
   target, `IDSPHV04` = −240 µA/µm — numerically the same device class
   `DR-0001` argued from, and the same `BVDSS` margin against the 3.63 V
   continuous-short `|Vds|` that `DR-0001`'s point 4 relied on.
3. **The alternatives are disqualified, not merely less attractive.**
   - `sg13_lv_pmos`: `BVDSSP013` −2.2 V worst case against a 3.3–3.63 V rail,
     `VGS ≤ 1.65 V`. Disqualified on ratings.
   - `pnpMPA`: collector is the substrate (cannot be the `VOUT`-side series
     terminal) and β ≈ 1.1 (base current alone would exceed the Iq budget).
     Disqualified structurally — a *stronger* disqualification than the
     Iq-budget argument `DR-0001` used to set SG13G2's bipolar alternative
     aside, because there is no configuration of this device that could serve
     as a pass element at all.
4. **`DR-0001`'s measured screening evidence transfers, with a stated
   basis and a stated limit.** `sim/pass-device-screening/` was run against
   `cornerMOShv.lib` → `sg13g2_moshv_{mod,parm,stat,mismatch}.lib` +
   `psp103.osdi`. On this install, SG13CMOS5L resolves *those same files*
   through symlinks (listed above). So the `Ron·W`, `Vth`, and `Cgate`
   numbers in `sim/pass-device-screening/records/20260909-220347-ed18110.csv`
   would be reproduced bit-for-bit under `PDK=ihp-sg13cmos5l`. **This record
   does not treat that as discharging the evidence obligation**: phase 3
   (#21) must re-run the corner grid under `PDK=ihp-sg13cmos5l` and record
   its own `sim/` evidence, because (i) the symlink structure is an
   install-shape property of these hosts, not a guarantee from the PDK, and
   (ii) this repo's rule is that a claim carries a testbench in the
   configuration it is claimed for. The transfer argument is stated so that
   a phase-3 result *differing* from `DR-0001`'s is read as a red flag about
   the environment, not as new physics.

**`DR-0001`'s carried-forward `|Vsg| ≤ 3.3 V` constraint applies unchanged to
the SG13CMOS5L branch.** Same device, same model card, same rating: the
current-limit loop, whenever it is built on this branch, must keep
clamped/steady-state `|Vsg|` at or below 3.3 V under a continuous-short
fault across the full PVT grid, demonstrated by its own testbench.

**Sizing is explicitly not decided here.** `w=300u l=0.5u` in
`design/ldo_core.sch` is provisional on the SG13G2 branch and is not
ratified for this branch either; #20/#21 own it, against whatever output
target #20 fixes.

### (b) Error amplifier — CMOS input stage: a two-stage Miller-compensated OTA with an `sg13_hv_pmos` input pair

**Adopt a CMOS (MOS) input stage. Specifically: a two-stage,
Miller-compensated, single-ended-output OTA built entirely from HV
(3.3 V-class) devices —**

- **Tail**: `sg13_hv_pmos` current source from the 3.3 V analog rail.
- **Input pair**: `sg13_hv_pmos` differential pair; `FB` on the
  non-inverting-path device, `VREF` on the other, preserving
  `design/ldo_core.sch`'s established polarity (`INP = FB`, `INN = VREF`).
- **First-stage load**: `sg13_hv_nmos` current-mirror, **diode-connected on
  the `VREF`-side leg**, with the first-stage output node taken at the
  `FB`-side leg.
- **Second stage**: a single `sg13_hv_nmos` common-source gain device
  (source at `VSS`, drain at `EAOUT`) loaded by an `sg13_hv_pmos` current
  source from the rail.
- **Compensation**: a Miller capacitor (with a series nulling resistor if the
  RHP zero requires one) from `EAOUT` back to the first-stage output node,
  realized as a MoM cap (`cap_cmomi`/`cap_cmomf`) — see the flagged caveat
  below.
- **No on-chip bandgap**: `VREF` stays an external port, exactly as
  `spec/porting-plan.md` §1.2/§2.2 sets as the default and as
  `design/ldo_core.sch` already wires it.

Why this and not a bipolar input stage:

1. **The bipolar branch does not exist in this process.** There is no HBT,
   and the one bipolar device that does exist cannot form a differential pair
   at all (collector = substrate). This is not a trade-off between two viable
   options — it is a single viable option. `spec/porting-plan.md` §2.2's
   three open questions (bipolar `gm/IC` vs. MOS `gm` bought with area;
   bipolar offset/noise mechanisms; a bipolar bandgap) are questions about
   SG13G2's HBTs. **None of them is answerable on SG13CMOS5L, because none of
   the devices they are about is present.**
2. **Both siblings' amplifiers are CMOS OTAs.** `spec/porting-plan.md` §2.2
   records that gf180-ldo uses a two-stage Miller-compensated OTA and
   sky130-ldo a current-mirror/"symmetric" OTA. §2.2's own reason for not
   defaulting to a straight CMOS port was *"SG13G2's HBTs reopen two
   questions neither sibling had to answer."* On SG13CMOS5L those questions
   are not reopened, so §2.2's stated default — the sibling CMOS topology —
   applies without a departure. This mirrors `sg13g2-bandgap`'s `0004`
   exactly, which reverted to the sibling repos' precedent for the same
   reason (its own `0001` had departed from the siblings *because* SG13G2
   offered a device SG13CMOS5L does not).
3. **Two stages, not one.** The pass device's gate is a large capacitive load
   driven from a low-Iq amplifier; a single-stage OTA would have to supply
   both the DC loop gain and the gate drive from one node. Two stages
   separate the gain node from the drive node and give Miller compensation a
   well-defined dominant pole — the same structure gf180-ldo uses for the
   same pass-device class.
4. **PMOS input pair, from the ICMR number.** See "Input common-mode range"
   above: at `VICM ≈ 0.9 V` an HV-NMOS pair is at/below its lower ICMR limit
   *nominally* (`Vth(max)` = 0.77 V), while an HV-PMOS pair has ≈ 0.6 V of
   headroom to spare and stays valid if #20 retargets `VOUT` downward. The
   PMOS pair is also the flavour whose `Vth` the same corner file already
   characterizes for `Mpass`, so the amp and the pass device track each other
   across corners rather than opposing each other.
5. **NMOS second stage, from the drive asymmetry that matters.** With the
   mirror diode on the `VREF` leg, a rising `FB` lowers the first-stage
   output node, and an inverting n-type common-source second stage raises
   `EAOUT` — satisfying `design/ldo_core.sch`'s required loop polarity
   (`FB` above `VREF` ⇒ `EAOUT` rises ⇒ `|Vsg|` shrinks ⇒ `VOUT` falls). The
   asymmetry this buys is an *actively driven* pull-down of `EAOUT` and a
   current-source-limited pull-up. That is the right way round for a PMOS
   pass device: the spec-critical transient is the load-step-**up**
   undershoot, where `EAOUT` must fall fast to turn `Mpass` on, and at a
   16–26 µA Iq budget a current-source pull-down would be far too slow. The
   cost is a slew-limited pull-up on load release. **This is the
   lowest-confidence element of this decision** — see "What would overturn
   this" below.
6. **HV flavour throughout, from the ratings table.** Every node in the amp
   is referenced to the 3.3 V analog rail; LV devices are disqualified on
   `BVDSS` and `VGS` as shown above. No LV or isolated-NMOS device is used,
   so `docs/pdk/sg13cmos5l.md`'s "No isolated NMOS" evidence rule is honoured
   by construction.

#### Flagged, not resolved: the compensation capacitor

This topology needs exactly one capacitor, and it lands squarely on the
carried-in analog caveats. This PDK has **no MIM cap** — `cornerCAP.lib`'s own header corroborates
`docs/pdk/sg13cmos5l.md` directly: *"the MIM caps cmim/rfcmim need the
forbidden MIM layer and are excluded"* — and its **MoM caps are "not
validated on CMOS5L silicon" with no corner or mismatch models** (`docs/pdk/sg13cmos5l.md`). Confirmed in the tree: `cap_cmomf.lib` /
`cap_cmomi.lib` and `cap_cmom{f,i}.osdi` are the only real, non-symlinked cap
artifacts in this PDK, and `cornerCAP.lib` — which *does* define
`cap_typ`/`cap_typ_mismatch`/`cap_typ_stat`/`cap_bcs`/`cap_wcs` sections —
says so in its own header: *"no characterised process-corner or mismatch
spread yet … every corner/mismatch/stat section below maps to the SAME
nominal models."* Selecting a corner for these caps is therefore a no-op, and
a PVT sweep over them measures nothing.

**Disposition: use a MoM cap (`cap_cmomi` or `cap_cmomf`), and mark every
spec row that depends on its value `insufficient-evidence` until a
sensitivity sweep bounds it** — the exact handling the operator's ruling
prescribes and `sg13g2-bandgap`#63 already applies. A MOS cap
(`moscap_n`/`moscap_p`) is a fallback if the sweep shows the MoM tolerance
cannot be bounded, but it is *not* co-recommended here: its capacitance is
strongly bias-dependent, which is poor behaviour for a compensation element
whose pole position sets the loop's phase margin, and its models on this PDK
are themselves symlinks to SG13G2's. The sweep (phase 3, #21) decides whether
the fallback is needed; this record names MoM as the choice.

## Does this motivate an equivalent SG13G2 record? — the open scope question, answered

`spec/porting-plan.md` §4 item 5 ("Error-amplifier input-stage and
reference-interface choice") is still open **for SG13G2**. This record could
be read as settling it by implication. **It does not, and should not be.**

**The two tracks stay formally independent. This record binds the
SG13CMOS5L branch only.** Reasoning:

1. **The decisive evidence here is a device-availability fact that is false
   on SG13G2.** Every load-bearing step in decision (b) — no HBT, only a
   substrate-collector β≈1 PNP — is a statement about SG13CMOS5L's tree.
   `npn13G2{,l,v}` and `cornerHBT.lib`/`sg13g2_hbt_mod.lib` genuinely exist in
   `ihp-sg13g2`. Porting a conclusion across that asymmetry would be exactly
   the inference error the Champion review made, run in the opposite
   direction: it assumed this repo's SG13G2 design depended on a device it
   never instantiated; ratifying SG13G2's amplifier from SG13CMOS5L's
   device menu would rule out a device SG13G2 actually has, on the grounds
   that a *different* process lacks it.
2. **§2.2's SG13G2 questions are measurement questions, not availability
   questions.** Whether an `npn13G2l` input pair beats an HV-PMOS pair on
   `gm` per µA, on offset, and on input-referred noise under a 16–26 µA
   budget is decidable — but only by an HBT screening deck that has never
   been run in this repo (the same way `DR-0001` waited for #13's screening
   deck rather than asserting the pass device from the device menu). Closing
   item 5 now, on this record's evidence, would relax the very standard
   `DR-0001` set.
3. **There is nonetheless a real coupling, and ignoring it would be the
   wrong kind of independence.** If item 5 later picks a bipolar input stage
   for SG13G2, the fleet carries two structurally different amplifiers for
   one block, and the SG13CMOS5L branch stops being a *port* and becomes a
   second design — doubling the verification surface and cutting against this
   repo's own framing that "the PDK is the variable, not the design"
   (`CLAUDE.md`). If item 5 picks CMOS, the branches converge and — given
   that the HV-MOS model cards are literally the same files — the two
   amplifiers differ only in sizing and back-end constraints.

**Concretely, this record's input to §4 item 5 is a tiebreak, not a
decision**: *if* item 5's HBT screening does not show a decisive advantage
for a bipolar input stage on SG13G2's own measured data, prefer the CMOS
topology decided here, on fleet-convergence grounds. If the screening *does*
show a decisive bipolar advantage, item 5 should take it and accept the
divergence — with this record's existence as the reason the divergence is a
deliberate, documented one rather than an accident.

This record therefore leaves §4 item 5's status **unchanged (open)** and does
not edit `spec/porting-plan.md`.

## Consequences

- **The SG13CMOS5L branch has a ratified pass-device flavour and error-amp
  topology.** #20 (phase 2, schematic capture) can proceed: `sg13_hv_pmos`
  common-source `Mpass`, and an HV all-CMOS two-stage Miller OTA replacing
  `Xamp`'s ideal VCVS on the CMOS5L branch. #20 must cite this record by path
  in the new schematic's own header, per its own acceptance criteria.
- **The SG13G2 branch is untouched.** `design/ldo_core.sch`,
  `design/ldo_erramp_placeholder.sch`, `design/netlist.py`, and
  `spec/porting-plan.md` are unmodified by this record — #19's scope is the
  decision record only.
- **The real amplifier will change `Xamp`'s pin list on the CMOS5L branch.**
  `design/README.md` already anticipates this ("a real amplifier will very
  likely need a `VDD` pin (and possibly `EN`)"); a two-stage OTA on the
  3.3 V rail needs at minimum `VDD` and a bias input or an on-block bias
  device. #20 owns that interface change and its documentation.
- **`DR-0001`'s `|Vsg| ≤ 3.3 V` constraint is inherited**, binding on
  whatever current-limit loop the CMOS5L branch eventually grows.
- **Every MoM-cap-dependent row is `insufficient-evidence` until swept.**
  #21 owes a compensation-cap sensitivity sweep; until it lands, no phase/gain
  margin claim on this branch may be reported as corner-verified.
- **`sim/env.sh`-equivalent PDK plumbing for `PDK=ihp-sg13cmos5l` does not
  exist yet in this repo** (`docs/pdk/sg13cmos5l.md` records that no canary's
  `env.sh` has been extended for CMOS5L). #20/#21 will hit this before any
  simulation runs.
- **Dispatch hazard carried forward**: the CMOS5L device symbols and HV model
  cards are relative symlinks into a sibling `ihp-sg13g2` checkout, which is
  *not* persistent on three of the four fleet hosts (`2AMLogic/2am#544`).
  Phases 2–4 must either run on a host with both PDKs present or resolve the
  install shape; a dangling-symlink failure there will look like a missing
  device, not a missing sibling PDK.
- **The bipolar input stage remains ruled out for the SG13CMOS5L branch
  structurally**, not provisionally — revisiting it would require the process
  to grow a device it does not have, not new measurement.

### What would overturn parts of this

- **Decision (a) — pass device**: a phase-3 corner run under
  `PDK=ihp-sg13cmos5l` that does *not* reproduce `DR-0001`'s `Ron·W`/`Vth`
  figures would mean the symlink-equivalence argument above is wrong for that
  host, and both this record's transfer claim and the environment need
  re-examination before `Mpass` sizing proceeds.
- **Decision (b), second-stage polarity**: this is the element resting on a
  qualitative slew-asymmetry argument rather than on PDK data. If #21's
  load-release testbench shows the current-source-limited pull-up of `EAOUT`
  produces an out-of-spec overshoot at light load, the fix is a push-pull /
  class-AB output stage (or the p-type dual with the mirror diode moved to the
  `FB` leg) — a revision *within* the two-stage CMOS Miller topology, not a
  reversal of the CMOS-vs-bipolar decision, which no transient result can
  overturn.
- **Decision (b), input-pair flavour**: a simulated ICMR sweep in #21 that
  contradicts the hand-calculated PMOS-pair window. The HV-NMOS alternative
  would still be out of range at `VICM ≈ 0.9 V`, so the realistic outcome is a
  bias-point change, not a flavour change.

## References

Read directly for this record (host `robb-studio`,
`~/share/pdk/ihp-sg13cmos5l` @ `607e18d4bd9214a52575c194b4181ef449f9252f`):

- `libs.tech/xschem/sg13cmos5l_pr/` — full symbol listing; `sg13_hv_pmos.sym`,
  `sg13_hv_nmos.sym`, `pnpMPA.sym` symlink targets.
- `libs.tech/ngspice/models/` — `cornerMOShv.lib`, `cornerMOSlv.lib`,
  `cornerPNP.lib`, `sg13cmos5l_pnpMPA_mod.lib`, `sg13cmos5l_pnpMPA_stat.lib`,
  `cornerCAP.lib`, `cap_cmomf.lib`, `cap_cmomi.lib`, and the symlink set.
- `libs.tech/ngspice/osdi/` — `psp103.osdi` symlink target.
- `libs.tech/klayout/tech/lvs/rule_decks/{globals,mos_extraction,bjt_extraction}.lvs`.
- `libs.tech/klayout/tech/lvs/testing/testcases/unit/{mos_devices,bjt_devices}/netlist/`.
- `libs.doc/doc/SG13CMOS5L_os_process_spec.pdf` Rev. 0.2 (2025-12-15) —
  §1.4, §2.1.2 PMOS, §2.1.4 HV-NMOS, §2.1.5 HV-PMOS, §2.2, §5.
- `~/share/pdk/ihp-sg13g2/libs.tech/{xschem/sg13g2_pr,ngspice/models}/` — for
  the HBT presence/absence comparison.

Repo and fleet documents cited:

- `spec/decision-records/DR-0001-pass-device-flavor.md`.
- `spec/porting-plan.md` §1.2, §1.4, §2.1, §2.2, §4 items 1 and 5.
- `design/README.md` "Pass device", "Error amplifier", "Reference voltage";
  `design/ldo_core.sch` header.
- `sim/pass-device-screening/records/20260909-220347-ed18110.{md,csv}`
  (cited by path, not re-run).
- `2AMLogic/2am` `docs/pdk/sg13cmos5l.md`; `2AMLogic/2am#357`, `#542`, `#544`.
- `2AMLogic/sg13g2-bandgap` `spec/decision-records/0004-cmos5l-bipolar-device-selection.md`.
- This repo's #12 (phase tracker), #19 (this phase), #20 (phase 2), #21
  (phase 3), #22 (phase 4).
