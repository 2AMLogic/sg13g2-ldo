# Porting plan: gf180-ldo and sky130-ldo → sg13g2-ldo

**Status: informational — not a decision record and not a spec.** This
document does not ratify anything and sets no numeric target. It exists so
the port that follows is deliberate: what the two sibling repos already
settled and why, what SG13G2's device set forces to be re-argued rather than
copied, and what the starter-grade klayout-tools deck is likely to be unable
to check yet. Every claim below cites the sibling file, decision record, or
upstream source it comes from; nothing here is invented to fill a gap. Where
a source could not be read, that is stated explicitly rather than guessed at
(see "Sources and their limits" at the end).

**Read for this plan**: `2AMLogic/gf180-ldo` and `2AMLogic/sky130-ldo`, both
cloned in full (not just browsed) — `spec/`, `design/`, `sim/README.md`,
`layout/README.md` in each, plus every decision record in
`spec/decision-records/` in both repos. Also read: the `2AMLogic/klayout-tools`
issues that shipped the SG13G2 curated deck (#905, #911, #524, #522) and the
IHP-Open-PDK v0.3.0 device-symbol and ngspice-model trees directly, to ground
§2 and §3 in the actual SG13G2 device menu rather than in memory of other
BiCMOS processes.

---

## 1. What carries over: the port-parity baseline

### 1.1 The block, unchanged

Both siblings port the same block, and this repo's own README already states
the same mission: a **3.3 V ±10 % in, 1.8 V ±2 % out, 0–50 mA** LDO. That
framing is not re-argued here — it is the reason the repo exists
(`README.md`: "Port parity: the targets below mirror the ratified gf180-ldo
spec — same block, third PDK"). What *does* need re-arguing, and is the
subject of §2, is whether SG13G2's device set can deliver that framing the
way gf180mcu did (yes, cheaply — see §2.1) or the way sky130 was forced to
(a real, costed departure — see §2.1 and DR-001's whole argument).

### 1.2 Spec rows that transfer as the starting draft, verbatim or near-verbatim

gf180-ldo's ratified table (`README.md`, ratified by
[`DR-0004`](https://github.com/2AMLogic/gf180-ldo/blob/main/spec/decision-records/DR-0004-spec-ratification.md),
2026-07-31) is the primary source, exactly as sky130-ldo's own
`spec/target-spec.md` already treats it ("gf180-ldo (ratified). The primary
source... same block, two PDKs — so the DRAFT starts by mirroring gf180-ldo's
ratified table, then flags every place [the target PDK] forces a departure").
This repo should draft its own `spec/target-spec.md` the same way sky130-ldo
did — one row at a time, citing gf180's ratified value as "G" and any
already-run sky130 numbers as a second data point where they exist — rather
than re-deriving each row from first principles. Rows that transfer
essentially unchanged, because they are properties of the *block*, not of the
PDK:

- **Output**: 1.8 V ±2 %, fixed, unit-resistor-string divider
  ([gf180 `DR-0003`](https://github.com/2AMLogic/gf180-ldo/blob/main/spec/decision-records/DR-0003-output-programmability.md)).
  No new argument is needed for "why fixed, not programmable" — DR-0003's
  reasoning (a late reversal invalidates the amplifier's offset budget, the
  stability matrix, and the testbench count simultaneously) is PDK-agnostic.
- **Load**: 0–50 mA, 0 mA meaning no external load, divider standing current
  the only inherent preload
  ([gf180 `DR-0001`](https://github.com/2AMLogic/gf180-ldo/blob/main/spec/decision-records/DR-0001-output-cap-strategy.md)).
- **Output capacitor philosophy**: external-cap, output-pole-dominant,
  ceramic-stable (no minimum ESR) as the primary architecture; capless is a
  forked variant, not a mode of the primary design (gf180
  `spec/architecture-survey.md` §4, ratified into DR-0001). The *numeric*
  C_eff/ESR window is **not** portable (§1.4) — sky130-ldo already had to
  re-derive it rather than copy gf180's 0.33–4.7 µF / 0–500 mΩ window, for
  reasons specific to its own pass-device sizing
  ([sky130 `DR-002`](https://github.com/2AMLogic/sky130-ldo/blob/main/spec/decision-records/DR-002-output-capacitor-esr-window.md)).
- **Current-limit shape**: constant-current (brickwall), not foldback, on the
  grounds that a folded-back limit can prevent startup into a loaded output
  (gf180 `DR-0004` "the two judgment calls", item 2). This reasoning is
  circuit-topology-independent and applies unchanged. The *numeric* window
  does not transfer — gf180 itself found ex post that an untrimmed on-chip
  resistor's process spread makes ±10 % unreachable and had to widen the
  window (`DR-0005`, proposed 2026-08-01: the sense-path error is under
  ±1.2 % but the absolute on-chip resistance the threshold is built from
  moves ±20 % ff-to-ss). SG13G2's own resistor flavors (`rsil`, `rhigh`,
  `rppd`) will have their own spread and must be characterized fresh, not
  assumed to match gf180's `ppolyf_u`/`npolyf_u` numbers.
- **Reference is external / black-box**: neither sibling designs or assumes
  an on-chip bandgap. gf180-ldo's `design/README.md` states plainly that
  `Vref1` is "an ideal source — no bandgap block exists", and the ratified
  spec's accuracy row is explicitly **regulator-only, excluding the
  reference's own error** (gf180 `DR-0004` note 2, "the two judgment calls"
  item 1). sky130-ldo's `design/README.md` likewise treats `VREF` as an
  external port with an explicitly undefined tempco, and its `DR-005`
  (thermal shutdown) states outright that it cannot pin a trip point to
  `VREF` because "this block has no on-chip bandgap" and the sibling
  `2AMLogic/sky130-bandgap` canary is deliberately *not* consulted for actual
  reference values, only for harness patterns, per the clean-room mandate.
  **This is the port-parity default for SG13G2 too**: design against an
  external `VREF` port, not an on-chip reference, unless a decision record
  argues otherwise. §2.2 below is where SG13G2's bipolar devices reopen that
  question specifically (a BJT-based bandgap is a natural fit for a BiCMOS
  process) — but reopening it is a choice this port must make explicitly,
  not one it inherits by default.
- **Verification-corner axis**: process `{tt, ff, ss, fs, sf}` × temperature
  `{−40, 27, 125} °C` × `Vin {2.97, 3.3, 3.63} V`, plus the (PDK-specific)
  output-capacitor window. Confirmed directly against the SG13G2 model
  library rather than assumed: `cornerMOShv.lib` in the pinned IHP-Open-PDK
  v0.3.0 tree states "Corner naming scheme: typical mean=tt, worst case=ss,
  best case=ff, combinations sf, fs" — the identical five-corner convention
  both siblings already use, and `sky130-ldo DR-004` had to do exactly this
  binding exercise for sky130's corner-section names. The equivalent binding
  record for SG13G2 is cheap because the naming scheme matches, but it is
  still a record this port owes (§4), not an assumption.
- **Testbench structure**: the `sim/<experiment-slug>/{testbench,
  netlist-snapshots, corners, records}/` directory convention and the
  append-only `<record-id>.md` evidence format
  (`gf180-ldo/sim/README.md`, adopted unmodified by sky130-ldo) transfers as
  the evidence schema for this repo's `sim/` — it is a convention shared
  across the fleet (gf180-bandgap, sky130-bandgap, sky130-pll), not a
  PDK-specific artifact, and there is no reason for this repo to invent a
  fourth format. The specific testbenches gf180-ldo built out
  (`dropout-vs-load`, `psrr-dc`, `psrr-vs-freq`, `load-regulation`,
  `line-regulation`, `load-transient`, `loop-stability`, `amp-openloop`,
  `amp-selfosc`, `current-limit`, `soft-start`/`startup`,
  `enable-shutdown`, `quiescent-current`, `mc-output-accuracy`,
  `op-point-sanity`) are the working list of testbenches this repo will
  eventually need one-for-one; sky130-ldo's leaner `sim/` (currently
  `dropout-vs-load`, `load-transient`, `loop-gain`, `mc-output-accuracy`,
  `psrr-dc`, `pex-post-layout`) reflects an earlier point in that same build-out,
  not a different set.
- **DRC/LVS flow shape**: a scripted, one-command DRC (curated `klt drc`
  subset + the PDK's own full deck, run side by side and reported as two
  distinct numbers, never conflated — gf180 `layout/README.md` "Coverage,
  honestly") plus LVS with mandatory negative controls (a topology mutation
  and a parameter mutation, both required to mismatch). sky130-ldo's
  `layout/README.md` follows the identical shape (trivial-cell proof before
  LDO layout, negative controls, append-only `records/<record-id>/`). This
  structure — prove the flow on a trivial cell first, DRC-clean claims cite
  the PDK deck's rule-category count not just the curated subset, LVS
  "match" is only evidence once a known-bad netlist is shown to mismatch —
  transfers directly to SG13G2 regardless of what the curated deck can check
  (§3).

### 1.3 Where the two siblings already diverged, and why — inherit the reasoning, not just the artifact

- **Pass-device family is not a foregone conclusion — it is the single
  question each port has had to re-argue from its own PDK's device menu.**
  gf180mcu has a native 3.3 V PMOS (`pfet_03v3`), so gf180's `DR-0002`
  answer ("3.3 V-flavor devices throughout, 5 V deferred") was cheap: no
  rating mismatch, just a headroom argument. sky130 has **no** 3.3 V-class
  device at all — only a 1.8 V core family and a 5.0 V-gate/10.5 V-drain
  family — so sky130's `DR-001` had to argue from device *ratings*, not
  performance: the 1.8 V core PMOS is disqualified categorically (a 3.3 V
  rail is ~2× its gate-oxide rating, a sustained-lifetime stress, not a
  transient one), leaving the 5 V-flavor device as the only rated option,
  at a real, quantified area/R_on cost (§3 of that record: ~2.7× more pass-
  device width than gf180mcu's native 3.3 V device, for the same target).
  **The lesson this port inherits is the method, not either answer**: read
  the actual device ratings against the actual worst-case terminal stress
  (normal regulation *and* the continuous-short current-limit condition,
  which sky130 DR-001 shows binds the **drain** rating, not just gate
  overdrive) before choosing a flavor. §2.1 below runs that method against
  SG13G2's own menu.
- **Compensation topology stayed a single line of inheritance in gf180 but
  needed a long negative-result trail.** gf180-ldo's architecture survey
  picked output-pole-dominant compensation with a folded-cascode or
  two-stage Miller error amp (survey §4–§5), and that held — but making the
  loop actually stable across the full 0–50 mA × PVT × C_eff/ESR envelope
  took ten more decision records after the ratified spec landed (`DR-0007`
  through `DR-0016`): a right-half-plane-pole precondition on the phase/gain
  margin test itself (`DR-0008`, ratified), a light-load gain-shelf
  mechanism that needed re-deriving twice (`DR-0009`, `DR-0012`), two
  negative-result records for buffer/sense-device variants that did not
  work (`DR-0010`, `DR-0011`, `DR-0013`), and a final Pareto-front record
  trading spec rows against compensation levers rather than finding a single
  clean answer (`DR-0016`). **The inherited lesson is that "stable at full
  load" and "stable at light load with the same compensation network" are
  different, harder claims**, and the gf180 negative results (what
  *doesn't* work: a direct super-source-follower sense device, an isolated-
  bias-reference variant, adaptive bias from the pass-device gate as the
  sole lever) are worth reading before this port's own compensation work
  starts, so the same dead ends are not re-discovered from scratch.
  sky130-ldo's own `design/README.md` independently arrived at a related
  topology (a current-mirror/"symmetric" OTA with Miller-plus-nulling-
  resistor compensation) sized against its own `sim/loop-gain` results, and
  states explicitly that it is clean-room work, not derived from gf180's
  schematic — this port should do the same: read gf180's compensation
  decision records for the *arguments*, not copy `error_amp.sch` verbatim.
- **Thermal shutdown was decomposed out of scope on both siblings, then
  became its own decision record on sky130 once the current-limit's actual
  short-circuit dissipation was measured** (sky130 `DR-005`: 673 mW at
  Vin_max into a dead short implies θJA ≤ 149 °C/W at Tj ≤ 125 °C, a real
  constraint the brickwall current limit alone does not protect against).
  gf180's ratified spec instead delegates sustained-short survivability to
  the package/integration spec (`DR-0004` note 5) and does not (yet) carry
  a thermal-shutdown row. This is a live disagreement between the two
  siblings, not a settled one — this port should expect to re-derive its
  own short-circuit dissipation once a pass-device size exists (§2.1) and
  decide, with a record, whether to follow gf180's delegate-to-integration
  posture or sky130's thermal-shutdown posture, rather than defaulting to
  either silently.
- **`README.md`'s draft table already anticipates the framing question**:
  "Input | 3.3 V ±10% ... confirm against SG13G2 device flavors" and
  "Output | 1.8 V ±2% (fixed) ... Ratification must confirm each row
  against SG13G2's device flavors (supply rails, pass-device options)."
  §2.1 does that confirmation now, ahead of the DR-0002/DR-001-style record
  this port will still need to file.

### 1.4 What does *not* transfer as a number, only as a method

Every *numeric* spec row that depends on a specific device's measured
electrical parameters — dropout headroom, current-limit window, Iq budget,
output-capacitor/ESR window, load-transient excursion — is PDK-specific and
must be re-derived from SG13G2's own characterization, the same way sky130's
`DR-002`/`DR-003` re-derived them from sky130's own screening data rather
than inheriting gf180's numbers. The *test point convention* transfers
(dropout is measured at `Vin = Vout + dropout ≈ 2.10 V`, not at `Vin_min` —
both gf180 `DR-0004` note 4 and sky130 `DR-001`/`DR-003` independently found
this is "the single easiest sizing trap" and the binding corner is
slow-and-hot, not simply worst-case-supply), but no number does.

---

## 2. What SG13G2's device set changes

### 2.1 Pass-device choice

**What the PDK actually offers.** Read directly from the IHP-Open-PDK
v0.3.0 device-symbol library
(`ihp-sg13g2/libs.tech/xschem/sg13g2_pr/`) and its ngspice model tree
(`ihp-sg13g2/libs.tech/ngspice/models/`), not assumed by analogy to gf180mcu
or sky130:

| Device family | Symbols | Voltage class | Model corner file |
|---|---|---|---|
| Thin-oxide ("LV") CMOS | `sg13_lv_nmos`, `sg13_lv_pmos` (+ `_rf` variants) | ~1.2 V core | `cornerMOSlv.lib` |
| Thick-oxide ("HV") CMOS | `sg13_hv_nmos`, `sg13_hv_pmos` (+ `_rf` variants) | 3.3 V | `cornerMOShv.lib` |
| HBTs (npn) | `npn13G2` (high-speed), `npn13G2l` (low-noise), `npn13G2v` (high-breakdown) — each with a `_5t` five-terminal variant | process-specific breakdown voltages per flavor | `cornerHBT.lib` |
| Lateral PNP | `pnpMPA` | — | `cornerHBT.lib` |
| Resistors | `rsil`, `rhigh`, `rppd` | — | `cornerRES.lib` |
| MIM / RF caps | `cap_cmim`, `cap_rfcmim`, `cap_cpara` | — | `cornerCAP.lib` |
| Varactor | `sg13_svaricap` | — | — |
| ESD structures | `diodevdd_2kv`/`_4kv`, `diodevss_2kv`/`_4kv`, `schottky_nbl1` | — | — |

**Unlike sky130, SG13G2 has a native 3.3 V-class device family (`sg13_hv_pmos`
/ `sg13_hv_nmos`) sitting directly alongside a 1.2 V core family.** That
structurally matches gf180mcu's situation (a dedicated 3.3 V flavor plus a
core flavor), not sky130's (core-or-5V-with-no-3.3V-option). The blunt
consequence: **the framing crisis that forced sky130-ldo's `DR-001` — "there
is no rated device for the input rail the spec asks for" — does not appear
to apply to SG13G2 on device-rating grounds.** `sg13_hv_pmos`, common-source,
source at Vin, is the direct SG13G2 analogue of gf180's `pfet_03v3` and the
starting hypothesis for this port's own pass-device record, following gf180
`DR-0002`'s headroom argument (§3.1 of gf180's architecture survey) rather
than sky130 `DR-001`'s rating-disqualification argument. That said, this
plan does **not** treat that hypothesis as settled — it is exactly the kind
of framing claim both siblings had to argue in a decision record from
measured screening data (gf180 `DR-0002`, sky130 `DR-001`/`DR-003`), and this
port owes the same: a screening deck against `sg13_hv_pmos`'s actual `Vth`,
`tox`-derived `Cox`, and `Ron·W` at the dropout test point
(`Vin = Vout + dropout ≈ 2.10 V`, per §1.4), across at least the `tt`/27 °C
and `ss`/125 °C corners the way both siblings' first-pass screening decks
did, before any width or Iq number is asserted. **This document does not run
that screening** (issue #1's explicit scope is the plan, not device
characterization) — it is the first item in §4's decision-record list.

**Supply/output rails the device set supports.** With `sg13_hv_pmos` rated
for the input rail, the README's draft framing (3.3 V ±10 % in / 1.8 V ±2 %
out) looks achievable on native devices without the sky130-style area/
rating penalty — but "looks achievable" is a hypothesis this port's
characterization record must confirm, specifically at the continuous-short
current-limit condition (`Vout = 0` at `Vin_max`), which is exactly where
sky130 `DR-001` found the *drain* rating (not the gate-headroom argument) to
be the binding constraint for the 5 V device family. `sg13_hv_pmos`'s drain
rating relative to 3.63 V must be checked the same way, not assumed safe by
analogy to either sibling's device.

**Bipolar as a pass-device alternative — deliberately not the primary
hypothesis.** SG13G2's HBTs (`npn13G2` family, `pnpMPA`) are named here for
completeness, not recommended as the pass device: a bipolar pass element
(e.g. a PNP or a Darlington) trades a base current draw against the Iq
budget in a way neither sibling's MOS pass device does, and a lateral PNP's
current gain and Early voltage are unlikely to compete with a MOS
common-source device's near-zero gate current for a low-Iq design. Ruling
this out formally (with SG13G2's actual HBT `beta`/`Early` numbers, not
assumed ones) belongs in the same pass-device decision record as the
`sg13_hv_pmos` hypothesis, so the record shows the alternative was
considered rather than never named — following the pattern sky130 `DR-001`
itself used (naming and explicitly ruling out stacked core devices and
extended-drain devices, not just picking a winner silently).

### 2.2 Error amplifier

Neither sibling's error amp is bipolar — both are CMOS OTAs (gf180: a
two-stage Miller-compensated OTA per `design/error_amp.md`; sky130: a
current-mirror/"symmetric" OTA per `design/README.md`). SG13G2's HBTs reopen
two questions neither sibling had to answer, and this port should treat both
as open rather than defaulting to a straight CMOS port of the sibling
topology:

1. **Input-stage device choice.** A bipolar differential pair (`npn13G2l`,
   the low-noise flavor, is the natural candidate) trades MOS's near-zero
   gate leakage and higher input impedance for higher transconductance per
   unit bias current and a fundamentally different offset mechanism (bipolar
   `V_BE` mismatch and base-current-driven source-resistance asymmetry,
   rather than MOS `V_th` mismatch). That changes **both** the offset
   budget gf180's `DR-0003`/`DR-0004` built (36 mV, regulator-only, 3σ) and
   the noise floor — a BJT input stage's input-referred noise is dominated
   by base shot noise and `r_b` thermal noise rather than MOS 1/f and
   thermal-channel noise, and neither sibling's design has a noise
   testbench to compare against (gf180's spec explicitly waives the noise
   row, `DR-0004` note 7, precisely because no reference/amplifier design
   existed to substantiate a number against — a BiCMOS error amp changes
   what that number would even mean once one exists).
2. **Iq cost.** A bipolar input stage's bias current sets its `g_m`
   directly (`g_m = I_C/V_T`), unlike a MOS stage where `g_m` also depends
   on `W/L` and can be bought with area instead of current. Under gf180's
   ≈16–26 µA total-block Iq allocation (survey §5) or the tighter 10 µA
   stretch, a bipolar input stage may reach a given `g_m`/bandwidth target
   at lower or higher standing current than an equivalent CMOS stage
   **depending on the specific bias point** — this is not free either way,
   and the comparison must be made numerically (both siblings' Iq
   allocations exist for exactly this kind of comparison) once SG13G2 HBT
   parameters are characterized, not asserted qualitatively here.
3. **Reference-interface choice.** §1.2 established that both siblings
   treat `VREF` as an external, black-box port with no on-chip bandgap. A
   BiCMOS process is the natural home for an on-chip bandgap (the classic
   `V_BE`-based bandgap topology needs a bipolar junction), and SG13G2's
   HBTs make that a real, available option in a way neither sibling's PDK
   offered as cheaply — but the fleet's own `2AMLogic/sg13g2-bandgap`
   sibling canary (referenced in `klayout-tools` issue #524's context) is
   presumably the natural owner of that block, not this repo. Per the
   clean-room mandate both siblings already follow for their own
   sibling-bandgap canaries (sky130 `DR-005`: "the sibling
   `2AMLogic/sky130-bandgap` canary is explicitly not consulted for its
   actual reference behaviour... harness patterns only, not reference
   values"), **this port's default position is the same as both
   siblings': keep `VREF` external for the primary design**, and treat
   "should this LDO grow its own bipolar bandgap reference" as an explicit,
   separately-scoped decision-record question rather than something decided
   implicitly by whoever designs the error amp — mirroring exactly how
   gf180 `DR-0002` refused to let the 5 V input-flavor headroom question be
   "decided implicitly by whoever designs the amplifier" (survey §3.3).

### 2.3 Spec rows the device set may make inappropriate, not merely harder

Following gf180 `DR-0004`'s own discipline (a spec row whose target the
device set makes wrong, not just difficult, gets a decision record, not a
silent edit) and its "provisional values and revisit triggers" pattern, the
rows most likely to need a departure once SG13G2 characterization exists:

- **Current-limit window.** Already shown to be a live risk on gf180mcu
  itself, on structural grounds (an untrimmed on-chip resistor's absolute
  value moves ±20 % process-corner-to-corner, `DR-0005`) that have nothing
  to do with gf180mcu specifically — the same argument applies to whichever
  SG13G2 resistor flavor (`rsil`/`rhigh`/`rppd`) sizes the sense threshold,
  with SG13G2's own spread, not gf180's `ppolyf_u`/`npolyf_u` numbers. This
  port should expect to need its own current-limit-window record from the
  start, not discover the need for one after building the circuit the way
  gf180 did.
- **Startup/settling window.** gf180's own `DR-0006` shows the ratified
  spec's ≤ 1 V/ms ramp bound and 3 ms settling bound are numerically
  incompatible for an untrimmed on-chip ramp (a 1.70:1 band that every
  part in every corner must land inside, and gf180's own measured circuit
  didn't). That is an arithmetic fact about the two bounds together, not
  about gf180mcu's devices — it applies to this port's startup design
  verbatim, and the two bounds should be checked for mutual consistency
  *before* committing to them in this port's own draft spec, not after
  building a soft-start circuit that fails one of them.
- **Iq budget.** Both siblings' ≈16–26 µA allocation (gf180 survey §5) is a
  function of the reference, divider, error-amp bias, and pass-gate-bias
  branches' current — all PDK-device-dependent. §2.2's bipolar-input-stage
  question directly feeds this row; until that record lands, the 30 µA
  target (10 µA stretch) is inherited as a *starting* draft number, per
  §1.2, not a settled one.
- **Dropout target.** §2.1's `sg13_hv_pmos` hypothesis needs its own
  `Ron·W` sizing before < 300 mV @ 50 mA can be confirmed reachable at the
  correct test point (`Vin = Vout + dropout`, §1.4) — inherited as a
  starting draft target per gf180's/sky130's own numbers, not confirmed.
- **Area.** sky130's pass device came in at ~1.3 % of the < 0.1 mm² budget
  before layout overhead (`DR-001` §"Width and area") despite the ~2.7×
  width penalty relative to gf180mcu — i.e. even a materially larger pass
  device did not, by itself, break the area row on sky130. SG13G2's
  `sg13_hv_pmos` device geometry (channel length, oxide thickness) has not
  been read against gf180's/sky130's numbers here — that comparison belongs
  in the pass-device characterization record (§4), not asserted now.

---

## 3. What the starter-grade klayout-tools deck likely can't check yet

CLAUDE.md already states the deck is new and starter-grade and that gaps are
expected friction to file, not route around. Reading the actual PR that
shipped the deck (`klayout-tools` #911, closing epic #905) makes the
specific shape of that gap concrete rather than generic, so layout-stage
gaps are recognized immediately as deck gaps rather than mistaken for design
bugs:

- **DRC coverage is 19 rules across seven layers only** (Activ, GatPoly,
  Cont, Metal1, Via1, Metal2, Via2 — width/space/enclosing/separation
  checks), explicitly "not a full transcription of SG13G2's rule set" (PR
  #911's own scope note) and, per the still-open tracking issue #524,
  smaller in scope than a from-scratch full transcription would be (#524 was
  twice rejected as oversized and remains open/unmerged — #911 shipped the
  narrower starter subset instead, with no cross-check against #524 possible
  since #524 never landed a competing deck to diff against). **Any DRC rule
  outside those seven layers or outside width/space/enclosing/separation
  categories — density, antenna, latch-up spacing, well-proximity, matching-
  structure rules, ESD-specific rules — is not checked by `klt drc --deck
  sg13g2` at all**, the same "deck reports zero categories, which is
  indistinguishable from clean, without a hard-error guard" risk gf180's own
  `layout/README.md` calls out generically. This block's guard rings
  (mentioned explicitly in CLAUDE.md as an analog-relevant DRC concern),
  matching structures for the feedback divider and any differential input
  pair, and the wide-metal / multi-finger pass-device layout a 50 mA path
  needs are exactly the categories most likely to fall outside that 19-rule
  subset.
- **Device extraction is MOS-only, and only the thin-oxide ("LV") flavor is
  explicitly named** ("`ExtractionDeck` recognizing thin-oxide ('-LV')
  NMOS/PMOS" — PR #911's summary). §2.1's pass-device hypothesis is the
  thick-oxide ("HV") flavor, `sg13_hv_pmos`. Whether the shipped extraction
  deck's MOS recognizer also covers the HV flavor is not established by
  this plan and should be checked directly (`klt extract --help` / the
  deck's own device-class listing) before assuming it — if it does not,
  that is this port's first concrete deck gap to file, and it blocks LVS
  of the pass device specifically, not just bipolar devices.
- **Bipolar, resistor, capacitor, diode, and varactor device recognition are
  explicitly out of scope for this increment** — PR #911's own scope
  section: "Resistor/capacitor/bipolar/diode device recognition and RC
  parasitics are explicitly out of scope for this increment... follow-on
  work." This maps directly onto the device classes this LDO needs beyond
  the pass FET: the feedback divider (resistors), the current-limit sense
  resistor (§2.3), the compensation cap, and — per §2.2 — any bipolar error-
  amp input stage this port chooses to pursue. **LVS via the `"klayout"`
  engine cannot presently produce a full-device netlist for this block's
  actual BOM**, only its MOS devices. Two mitigations exist and are worth
  checking, not assuming, before filing a gap: (a) `klt lvs`'s `"netgen"`
  engine compares two already-built SPICE netlists rather than doing its
  own extraction, and per `klayout-tools`' `docs/cli/pdk.md`, already
  resolves and runs against a real SG13G2 install's own
  `libs.tech/netgen/ihp-sg13g2_setup.tcl` — so a netgen-based LVS path may
  sidestep the extraction-deck gap for devices netgen's own layout
  extraction (if invoked directly, outside `klt`) can recognize; (b) the
  general-purpose bipolar/resistor/diode extraction machinery
  `klayout-tools` already built for the sky130/gf180mcu decks (issues #219,
  #222, #223, #336, #339, #432, #490, #541, #542, closed) is a generic
  capability this port can ask to be pointed at SG13G2's own layer set,
  rather than commissioning a from-scratch SG13G2 bipolar recognizer as a
  novel piece of work. Either way, **this is exactly the kind of gap
  CLAUDE.md's friction protocol asks to be filed generically** ("an LVS
  device it does not extract") once this port actually needs bipolar/
  resistor/capacitor LVS and finds the gap in practice, rather than
  pre-emptively — the specific rule/device text of the filing should
  describe the tool gap, not this repo's schematic.
- **No RC parasitics deck for SG13G2.** PR #911: "`ParasiticsDeck()`
  registers empty so `--parasitics` reports an honest 'uncalibrated' gap
  instead of an 'unknown deck' error." Post-layout re-verification (this
  repo's own maturity ladder, README.md) will not get calibrated parasitic
  extraction from `klt` for SG13G2 at all yet — worth knowing before that
  stage is reached, not discovering it there. gf180's own friction history
  (`klayout-tools` #592, closed: "extracted parasitic resistance has no
  in-path/distributed model") suggests even a landed parasitics deck may
  still be a coarse model relative to what a 50 mA pass-device path's IR
  drop needs; SG13G2 starting from zero here is a bigger gap than either
  sibling faced at the same maturity stage.
- **Precedent for how much friction a first analog LDO/bandgap-class block
  surfaces on a new deck.** The `klayout-tools` friction history against
  sky130/gf180mcu's own bipolar/resistor extraction work (18+ closed issues
  spanning device-class recognition, dummy-marker handling on bipolar and
  resistor devices, base-terminal connectivity, substrate/bulk synthesis,
  and node-count mismatches specifically on bipolar netlists) is a realistic
  size-of-effort signal for what SG13G2's from-scratch bipolar/resistor/cap
  support will likely need, and a reason to expect **several** filed gaps
  during this port's layout stage, not one. This is not a reason to avoid
  bipolar devices in the design (§2.1/§2.2 name them as real options) — it
  is a reason to expect the deck gaps and file them as they are hit, per
  CLAUDE.md, rather than reading a first deck failure as a design mistake.

---

## 4. Ordered list of decision records this port expects to need

Numbered in the dependency order the siblings' own records suggest (framing
before sizing before compensation before protection circuits, mirroring
gf180's issue sequence #7→#9→#10→#11 and sky130's #4→#10→#22/#25/#28), not
in a committed filename order:

1. **Pass-device flavor and headroom** (§2.1) — confirm or reject the
   `sg13_hv_pmos` common-source hypothesis against a real screening deck
   (dropout test point, both gate-oxide and drain-rating stress at the
   continuous-short condition), the SG13G2 analogue of gf180 `DR-0002` and
   sky130 `DR-001`/`DR-003` combined. This is the single most consequential
   record — nearly every other row and record below depends on it.
2. **Output capacitor / ESR window** — re-derived from the pass device's
   actual gate capacitance and the loop's large-signal response, sequenced
   *after* #1 per sky130 `DR-002`'s own explicit sequencing argument (the
   C_eff floor and the internal gate-node pole both depend on pass-device
   sizing). The SG13G2 analogue of gf180 `DR-0001` / sky130 `DR-002`.
3. **Output programmability** — very likely a straight adoption of gf180
   `DR-0003`'s reasoning (fixed 1.8 V, unit-resistor-string mask-option
   hedge only), since nothing in §2 changes that argument, but stated as
   its own record per §1.2/§1.4's "reasoning transfers, still needs its own
   record" rule rather than silently assumed.
4. **Verification-corner binding** — bind the abstract `{tt, ff, ss, fs,
   sf} × {−40, 27, 125} °C × {2.97, 3.3, 3.63} V` axis to SG13G2's actual
   `.lib` section names and any binding-corner assignments, the SG13G2
   analogue of sky130 `DR-004`. Likely cheap (§1.2 already confirms the
   naming scheme matches), but still a record, not an assumption.
5. **Error-amplifier input-stage and reference-interface choice** (§2.2) —
   CMOS OTA (straight port of either sibling's topology argument) vs. a
   bipolar input stage, and whether this design keeps `VREF` external
   (default, per §1.2/§2.2) or reopens an on-chip bipolar bandgap. Sequenced
   after #1 (needs the pass-device's Cgate for compensation) but should be
   argued before schematic entry, per both siblings' own sequencing (gf180
   #9 after #7/#8; sky130 #25 as a dedicated issue).
6. **Current-limit window** (§2.3) — sized against SG13G2's own resistor-
   flavor process spread (`rsil`/`rhigh`/`rppd`, whichever the sense path
   uses) from the start, informed by gf180's `DR-0005` negative-result
   pattern rather than repeating gf180's own path of ratifying an
   unreachable window first and re-deriving it after measurement.
7. **Startup/soft-start settling window** (§2.3) — checked for the same
   ramp-rate-vs-settling-time mutual consistency gf180's `DR-0006` found
   broken, before the two bounds are drafted into this repo's own spec
   table, not after a circuit is built against them.
8. **Thermal-shutdown posture** (§1.3) — an explicit choice between gf180's
   delegate-to-integration posture and sky130's on-chip-thermal-shutdown
   posture, made once #1's pass-device sizing gives a real short-circuit
   dissipation number to argue from (mirroring sky130 `DR-005`'s own
   trigger: a measured dissipation number implying a real θJA constraint).
9. **Compensation topology and stability envelope** — informed by gf180's
   full `DR-0007`–`DR-0016` trail (§1.3) so this port's own light-load /
   full-load / PVT / C_eff-ESR stability work starts from the documented
   dead ends (buffer/sense-device variants, adaptive-bias-only levers) and
   the documented working mechanism (a right-half-plane-pole precondition
   on the phase/gain-margin test itself, `DR-0008`) rather than
   re-discovering them. Likely the largest single record cluster in this
   port, as it was for gf180.
10. **SG13G2-flavor DRC/LVS deck-gap filings** (§3) — not a single record,
    but the running set of `2AMLogic/klayout-tools` issues this port will
    file as layout work hits the seven-layer/MOS-only/no-bipolar-resistor-
    capacitor-extraction/no-parasitics boundaries named in §3. Tracked here
    so a future reader of this plan can check which of §3's anticipated
    gaps were actually hit (and filed) versus turned out not to matter.

---

## Sources and their limits

Both `2AMLogic/gf180-ldo` and `2AMLogic/sky130-ldo` were reachable and were
cloned in full (`git clone`, not just browsed via the GitHub API) to write
this plan; every citation above is to a file or decision record actually
read in that clone, not reconstructed from a listing or a title. The
`2AMLogic/klayout-tools` issues cited (#905, #911, #524, #522, plus the
closed bipolar/resistor/extraction friction issues named in §3) were read
via `gh issue view`/`gh api`, not assumed from their titles alone, with the
exception of the long list of closed friction-issue titles in §3's last
bullet, which is cited as a *count and category* signal from a `gh issue
list --search` result, not individually read — if a future decision record
needs the specific content of any one of those, it should be read directly
rather than cited through this plan. The IHP-Open-PDK v0.3.0 device-symbol
and ngspice-model file listings in §2.1 were read directly from the pinned
tag's tree via the GitHub API (`IHP-GmbH/IHP-Open-PDK`, tag `v0.3.0`, the
same pin `2AMLogic/klayout-tools`' `scripts/fetch-ihp-sg13g2.sh` uses) — file
and symbol *names* and the corner-naming-scheme comment in `cornerMOShv.lib`
are quoted directly; no `Vth`, `Ron·W`, or other numeric device parameter is
asserted anywhere in this document, because none was measured — that
measurement is item 1 of §4, not a finding of this plan.
