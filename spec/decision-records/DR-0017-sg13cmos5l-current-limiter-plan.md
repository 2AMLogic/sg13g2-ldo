# DR-0017: SG13CMOS5L current limiter — proposed topology, sizing, error budget and validation plan for row 8

> **Numbering note.** DR-0017 is the next free number. DR-0010, DR-0011 and
> DR-0013 stay skipped for the reason given in
> [`DR-0012`](DR-0012-row4-dropout-measurement.md): `spec/porting-plan.md`
> cites those numbers. No open pull request or remote branch carries a
> DR-0017 (checked against `origin` at `ed55de7c` on 2026-10-15).

- **Status**: **Accepted for bounded development only** (reconciled in the
  #165 implementation PR; the plan itself was proposed in #163). The
  acceptance act is the operator ruling on issue #165 of 2026-10-19
  (<https://github.com/2AMLogic/sg13g2-ldo/issues/165#issuecomment-6283868941>),
  which accepts this record as the development plan for #165 and nominal
  smoke checks only. It is dated 2026-10-19 and is not a retroactive approval
  of PR #163. It is not numerical ratification or validation of the limiter:
  the sizes and the 72.32 mA value below are still candidates and
  calculations, and nothing in this record is ratified or measured except the
  [M]-tagged anchors. Row 8 (current limit, `65–80 mA
  brickwall over PVT; short-survivable`) stays **Open** in
  [`DR-0007`](DR-0007-target-spec-row-ratification.md) and in the root
  `README.md`. Row 1's carried `|Vsg|` gate stays open as well. The target is
  unchanged and no gate, threshold, record or verdict is loosened. The record
  changes no schematic, netlist, testbench, layout or measurement record.
  This record originally named operator approval of the pull request that
  carries it as the acceptance act for the *plan* (fleet policy
  `2AMLogic/2am#357`, as quoted in `DR-0002`). #163 was merged by the fleet
  bot without that approval, so the 2026-10-19 ruling above is the acceptance
  act instead. The two review keys still release row 8 itself, later and on
  evidence.
- **Date**: 2026-10-15
- **Scope**: the SG13CMOS5L branch only (`design/sg13cmos5l/`). Issue #63.
  The record covers the limiter topology and how it maps to SG13CMOS5L
  devices, the threshold equation, candidate dimensions, the error budget,
  the integration plan at `EAOUT`, the consumer inventory, and the
  executable-testbench specification that the later implementation and
  evidence work must satisfy. **Zero simulations were run for this record.**
  Every number below is tagged by where it comes from (see "Evidence tags").
- **Related**: [`DR-0001`](DR-0001-pass-device-flavor.md) (the carried
  `|Vsg| <= 3.3 V` constraint, SG13G2-scoped),
  [`DR-0002`](DR-0002-sg13cmos5l-device-topology.md) (CMOS5L device menu and
  ratings; extends the `DR-0001` constraint to this branch "unchanged"),
  [`DR-0003`](DR-0003-sg13cmos5l-mpass-resize-and-compensation.md) (the
  `2800 u / 0.5 u` `Mpass`), [`DR-0004`](DR-0004-sg13cmos5l-resistor-corner-stability.md)
  and [`DR-0006`](DR-0006-rhigh-family-width-offset-double-count.md) (`rhigh`
  corners and width offset), [`DR-0007`](DR-0007-target-spec-row-ratification.md)
  (row 8 Open / statistical), [`DR-0008`](DR-0008-sg13cmos5l-enable-interface.md)
  (enable interface, #67), `spec/porting-plan.md` §1.2, §2.3 and §4 item 6,
  issues #55 (deterministic coverage) and #56 (statistical evidence).

## Evidence tags

Each quantity carries one tag:

- **[M]** measured: a committed record or a PDK file, cited by path. The
  measurement is quoted, not re-run.
- **[C]** calculated in this record from [M] values and/or [A] values. The
  arithmetic is shown so it can be checked.
- **[A]** assumption. It must be replaced by a measurement in the
  implementation work before any claim depends on it.
- **[U]** unmeasured or unknown, with no defensible value yet. It is listed
  under "Missing characterization".

## Sibling reference (pinned)

Sibling: `2AMLogic/gf180-ldo` at commit
**`d83daea06432b21b91a1cef32ddedc386f5a1e32`** (that repository's `main`
on 2026-10-15, read through `gh api .../contents?ref=<sha>`). Files read, with
the sha256 of the bytes fetched:

| File | sha256 |
|---|---|
| `design/ldo_ilimit.sch` | `b1b6b4bc62b120ca31563016593f6a79ad85039be4bd340f0a21a6e3674aef26` |
| `design/netlist/ldo_ilimit.spice` | `e212a0cf3fc3c85d2c0e92eb5032bc82f4ada3cfa58b84b4d457007dfe927857` |
| `spec/decision-records/DR-0005-current-limit-window.md` | `edfe0b3f5c8c603b248bc1fa0d82cb682d86f2d3adeabc65c4a370e77ecfc8e6` |

What the sibling circuit is, at that commit:

- `XMsense` (`pfet_03v3`, `W = 70 u`, `L = 0.28 u`) shares `Mpass`'s gate and
  source. It is one more unit of the same `40 x 70 u` array, so `N = 40`.
  Its drain current returns to `VOUT` through `XRsns` (`ppolyf_u`, 10 units
  in parallel), so the sense current reaches the load.
- A threshold current `Iref` comes from a VREF-across-`Rbias` V-to-I
  (`XMp1/XMp2/XMl1/XMl2/XMs2` amplifier driving `XMconv` into `XRbias`),
  mirrored by `XMpd/XMrefp` into `XRref`, which also returns to `VOUT`. So
  `V(VTH) = VOUT + Iref·Rref`.
- A PMOS comparator (`XMca` on `ISNS`, `XMcb` on `VTH`, resistor tail
  `XRtail`, NMOS mirror `XMna/XMnb`, dominant-pole cap `XCc` on `CO`) drives
  `XMg2`, which pulls `CLG` down against `XRl2`. `XMclamp`
  (`pfet_03v3 50 u / 0.5 u`, `PASS_GATE CLG VIN VIN`) then pulls the pass
  gate toward `VIN`. `XMclamp_bg` does the same on a follower gate (`BG`)
  that exists only in the sibling's amplifier.
- Enable gating comes from a local inverter, `XMben`, `XMen_t`, `XMen_co`
  and `XMcoff`.
- Trip equation (`DR-0005`): `I_lim = 41 · VREF · (Rref/Rbias) / Rsns`.
  `Rref/Rbias` cancels, which leaves **one uncancelled absolute resistance**
  (`Rsns`). The sibling measured `±20.4 %` from the resistor sheet corner
  alone, against `< ±1.2 %` from everything else, and had to widen its
  window to 62–95 mA (DR-0005, ratified 2026-09-15).

**What transfers:** the architecture of a sense replica returned to
`VOUT`, a threshold riding on `VOUT`, a PMOS comparator, a gain stage and a
gate pull-up clamp. The reasoning that the sense current is delivered to
the load (so it is not Iq), the resistor-tail argument for comparator
headroom, the `Men_co` lesson (park `CO` while disabled or the gain stage
crowbars the clamp-off device), and the lesson that clamp authority depends
on what the amplifier sinks also transfer. **What does not transfer:**
every numeric size, the achieved window, the `VREF/Rbias` reference and
`XMclamp_bg`. The next sections give the reasons.

## Context

### What this branch has today [M]

`design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` at `origin/main` `ed55de7c`:

```
.subckt ldo_core_cmos5l VIN VOUT VSS VREF IBIAS EN
XMpass VOUT EAOUT VIN VIN sg13_hv_pmos w=2800u l=0.5u ng=1 m=1
XRtop VOUT FB VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7
XRbot FB VSS VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7
Xamp FB VREF EAOUT VIN VSS IBIAS EN ldo_erramp_cmos5l
XMen EAOUT EN VIN VIN sg13_hv_pmos w=40u l=0.5u ng=1 m=1
XMbdis IBIAS EN VIN VIN sg13_hv_pmos w=5u l=0.5u ng=1 m=1
```

There is no limiter. `EAOUT` is the integration node. It is `Mpass`'s gate,
the drain of the amplifier's second stage (`XMn3` sink, `XMload2` 6 x
`IBIAS` source), and `XMen`'s drain. `IBIAS` is the gate/drain of the
amplifier's bias diode `XMb0` (`sg13_hv_pmos 5 u / 2 u`), sunk externally
at 2 µA by every bench. The `EN` interface from #67 has landed (`DR-0008`,
Proposed; issue #67 closed). The layout draws `Mpass` as
`4 rows x 28 fingers x 25 u` (`layout/sg13cmos5l-ldo_core_cmos5l/generate.py`).

### Measured anchors this plan argues from

| Quantity | Value | Source |
|---|---|---|
| `rhigh` sheet, `res_bcs / res_typ / res_wcs` | 1020 / 1360 / 1700 Ω/□ | [M] `cornerRES.lib`, quoted in `DR-0004` |
| `rhigh` divider leg (w = 1 µm), all 45 PVT points | 186.9 kΩ (ff/125 °C/`res_bcs`) … 455.9 kΩ (ss/−40 °C/`res_wcs`), i.e. 0.596x–1.454x of 313.5 kΩ at `res_typ`/27 °C; **2.44 : 1** | [M] `sim/ldo-cmos5l-pvt-sweep/records/20261011-070111-5391c68.csv` (`r_divider_leg_ohm`) |
| `rhigh` temperature slope at `res_typ` | 364.8 kΩ (−40 °C) → 249.2 kΩ (125 °C), about −0.19 %/K average | [M] same CSV; slope [C] |
| Divider standing current (no load) | 1.974 µA (ss/−40 °C/`res_wcs`) … 4.817 µA | [M] same CSV (`i_divider_a`) |
| No-load Iq, 45 points | 21.72 … 24.72 µA | [M] same CSV (`iq_a`) |
| `sg13_hv_pmos` `|Vth|`, `L = 0.5 u`, 15 corner/T points | 0.449 V (ff/125 °C) … 0.776 V (ss/−40 °C) | [M] `sim/pass-device-screening/records/20260909-220347-ed18110.csv` (`w300u_l0.5u`, `w1u_l0.5u`; SG13G2 pin, model cards byte-identical per `DR-0002`) |
| Fully-on current density, `Vsg = Vsd = 3.63 V` | 150.5 … 283.4 µA/µm | [M] same CSV (`id_stress_a_per_um`, `w300u_l0.5u`) |
| Gate capacitance, 300 µm device | 0.679 … 0.740 pF | [M] same CSV (`cgate_f`) |
| `XMb0` gm/I at 2 µA | 6.17 … 9.17 V⁻¹ (4 operating points) | [M] `sim/ldo-cmos5l-pvt-sweep/records/20261012-115531-cfa681f9.e1op.csv` |
| Unlimited startup into 1 µF / 1 mA, 135 points | peak supply current 0.283 … 0.775 A; peak `Vsg(Mpass)` 2.961 … **3.628 V** | [M] `sim/ldo-cmos5l-pvt-sweep/records/20261011-070146-0c95530-startup-grid.md` |
| MOS mismatch (PDK) | `delvto` σ = 4.5 mV·µm/√(WL) (HV PMOS), 7 mV·µm/√(WL) (HV NMOS); `factuo` 0.4 / 0.5 %·µm; per instance | [M] PDK `sg13g2_moshv_mismatch.lib`, quoted in `sim/ldo-cmos5l-monte-carlo/README.md` |
| `rhigh` mismatch (PDK) | `smm_rsh` = 5 %·µm per instance; drawn with mean 1 (every instance +1σ) | [M] PDK `resistors_mod_mismatch.lib`, same README |
| HV ratings | `VGS <= 3.3 V @ 27 °C, LG >= 0.5 µm`; `BVDSSPHV04` −5.3 … −6.3 V; `BVDSSNHV013` >= 5.3 V | [M] `SG13CMOS5L_os_process_spec.pdf` §2.1.4/§2.1.5, quoted in `DR-0002` |

The measured rows were made under PDK pins that are older than the current
`sim/pdk-cmos5l.json` pin (`f7bca326…`). The screening deck ran on SG13G2
v0.3.0 and the PVT and startup records on `607e18d4…`. They are cited as
design anchors, not as evidence for the limiter.

Derived anchors [C]:

- Unlimited short current: 2800 µm x 150.5…283.4 µA/µm = **0.421 … 0.793 A**,
  i.e. 1.53 … 2.88 W at 3.63 V. The startup peaks above agree.
- `Mpass` gate capacitance: (2800/300) x 0.679…0.740 pF = **6.3 … 6.9 pF**.

### Why the sibling's reference cannot be reused here [C]

With the gf180 reference, `I_lim ∝ 1/Rsns`. On this PDK `rhigh` moves 2.44 : 1
over the PVT grid (global corner and temperature together; the divider leg
above), so `I_lim` would span `1/1.454 … 1/0.596` = 0.688x … 1.678x of
nominal. The 65–80 mA row needs at most 80/65 = **1.23 : 1**. No centering
fits. Keeping the sibling's reference would make the row infeasible before
mismatch is even counted, and would force exactly the widening DR this
issue tells us not to slip in. Other flavours (`rsil`, `rppd`) have not
been characterized on this branch [U]. The topology below removes the
absolute resistance from the threshold instead of hoping a flavour is
tighter.

## Decision (proposed)

### 1. Topology: sense replica, ratioed resistors, threshold set by the external `IBIAS`

A new internal cell **`ldo_ilimit_cmos5l`** (`design/sg13cmos5l/ldo_ilimit_cmos5l.{sch,sym}`):

```
.subckt ldo_ilimit_cmos5l VIN VOUT EAOUT IBIAS EN VSS
```

1. **Sense.** `XMsense` is one more `25 u / 0.5 u` finger of the `Mpass`
   array (`D = ISNS`, `G = EAOUT`, `S = B = VIN`), so `N = 2800/25 = 112`.
   Its current returns to `VOUT` through `Rsns`.
2. **Threshold current from `IBIAS`, not from `VREF/R`.** `Iref` mirrors
   the existing `XMb0` diode (gate on the core's `IBIAS` node) into `Rref`,
   which returns to `VOUT`: `V(VTH) = VOUT + Iref·Rref`. **`Rsns` and
   `Rref` are built from identical `rhigh` unit resistors**: `Rref` is
   `s` units in series and `Rsns` is `p` units in parallel. Their ratio is
   then the integer `s·p` at every global corner and temperature, and the
   remaining absolute quantity is the external bias current. This is the
   departure from gf180. It follows the repo's existing convention that
   the external references (`VREF`, `IBIAS`) are ideal at block level, the
   same exclusion row 2 makes for `VREF` (`sim/ldo-cmos5l-monte-carlo/README.md`).
3. **Comparator, gain stage, clamp.** The sibling structure, rebuilt in HV
   devices: a PMOS pair (`XMca` on `ISNS`, `XMcb` on `VTH`) with a resistor
   tail, an NMOS mirror load, a `cap_cmomi` dominant-pole cap on `CO`, an
   NMOS gain stage `XMg2` pulling `CLG`, a PMOS load on `CLG` mirrored from
   `IBIAS`, and **`XMclamp`** (`D = EAOUT`, `G = CLG`, `S = B = VIN`).
4. **Enable.** A local inverter (`ENB`, as `DR-0008`'s amplifier addendum
   does), `XMen_t` (opens the tail), `XMen_co` (parks `CO` at `VSS`) and
   `XMcoff` (holds `CLG` at `VIN`). `Iref` and the `CLG` load go off by
   themselves, because `XMbdis` already pulls `IBIAS` to `VIN` when
   `EN` is low.
5. **Dropped from the sibling:** the VREF-across-`Rbias` V-to-I and its
   MIM cap (replaced by the `IBIAS` mirror) and `XMclamp_bg` (this
   amplifier has no follower gate). `VREF` is **not** a limiter pin.

**Core pins do not change**: `VIN VOUT VSS VREF IBIAS EN` (the
`design/netlist.py` six-port invariant holds). The core gains one instance:

```
Xilim VIN VOUT EAOUT IBIAS EN VSS ldo_ilimit_cmos5l
```

### 2. Threshold equation and candidate values

At trip, `Isns·Rsns = Iref·Rref + Vos`. The core's output current is
`I_out = Ipass + Isns + Iref − I_div`. `Iref` and `I_div` are µA against
tens of mA (about 0.004 %), so

```
I_lim = (N + 1) · Iref · (Rref / Rsns) · (1 + ε)
      = (N + 1) · (k · IBIAS) · (s · p) · (1 + ε)
```

where `ε` collects every error term in the budget below. The `N + 1` is the
sibling's 41-not-40 point: the sense current also reaches the load.

| Symbol | Candidate | Basis |
|---|---|---|
| `N` | 112 (`2800 u / 25 u`, equal finger width and `L`) | [C] from DR-0003's `Mpass` and the layout finger |
| `k` | 1/2 → `Iref = 1.000 µA` | [C] see "Why `Iref = IBIAS/2`" |
| `s · p` | 640 (`s = 32` series in `Rref`, `p = 20` parallel in `Rsns`) | [C] |
| `I_lim,nom` | 113 x 1.000 µA x 640 = **72.32 mA** (window centre 72.5 mA; −10.1 % to 65 mA, +10.6 % to 80 mA) | [C] |
| `Isns` at trip | 72.32 mA / 113 = 0.640 mA, i.e. 25.6 µA/µm, the same density as `Mpass` | [C] |
| `R_u` (unit) | 5.0 kΩ at `res_typ`/27 °C, `rhigh`, `w = 2 u`, `l ≈ 7.4 u`, `b = 0`. The final `l` comes from the simulated value, not the symbol expression (DR-0006 double count) | [C]/[A] |
| `Rsns` / `Rref` | 250 Ω / 160 kΩ (typ) | [C] |
| `V_th = Iref·Rref` | 160 mV typ. With `R_u` tracking the measured 0.596x–1.454x leg spread: **95 … 233 mV** | [C] (tracking assumes the 2 µm unit spreads like the 1 µm leg [A]) |

**Why `Iref = IBIAS/2`.** `Iref` flows into `VOUT`. This PMOS-pass
regulator cannot sink, so at no load the divider has to absorb it. The
measured minimum divider current is **1.974 µA** (ss/−40 °C/`res_wcs`) [M].
A 1:1 mirror (2 µA) would exceed it, and `VOUT` would rise out of
regulation at no load at that corner. That option is rejected. At 1 µA
(+3σ mismatch ≈ 1.05 µA [C], below), at least ~0.92 µA of the divider
current is still delivered through `Mpass`, so regulation is kept. `k = 1/2`
is realized as **two gate-shared, series-stacked copies of `XMb0`'s exact
geometry** (`5 u / 2 u` each). That gives the W/2L equivalent in the same
geometry family, plus self-cascode output resistance for plateau flatness.
The stack's exact ratio is [U].

`Iref` replaces pass current, so it adds no net no-load Iq. The comparator
tail does add Iq (see below).

### 3. Candidate dimensions (implementation must confirm by simulation)

| Instance | Model | Candidate size | D G S B | Role |
|---|---|---|---|---|
| `XMsense` | `sg13_hv_pmos` | 25 u / 0.5 u, 1 finger | `ISNS EAOUT VIN VIN` | 1/112 replica, interior finger of the `Mpass` array |
| `XRsns` | `rhigh` | 20 x unit in parallel | `ISNS–VOUT` | sense resistor, 250 Ω typ |
| `XMref1/2` | `sg13_hv_pmos` | 2 x (5 u / 2 u) series stack | `VTH IBIAS VIN VIN` | `Iref = IBIAS/2` |
| `XRref` | `rhigh` | 32 x unit in series | `VTH–VOUT` | threshold resistor, 160 kΩ typ |
| `XMca`, `XMcb` | `sg13_hv_pmos` | 40 u / 2 u | `CN ISNS TAIL VIN`, `CO VTH TAIL VIN` | comparator pair |
| `XMna`, `XMnb` | `sg13_hv_nmos` | 10 u / 8 u | `CN CN VSS VSS`, `CO CN VSS VSS` | mirror load |
| `XRtail` | `rhigh` | ≈ 580 kΩ typ (`w = 1 u`) | `TAIL–TAILP` | resistor tail (sibling reasoning: headroom) |
| `XMen_t` | `sg13_hv_pmos` | 5 u / 0.5 u | `TAILP ENB VIN VIN` | opens tail when disabled |
| `XCcl` | `cap_cmomi` | ≈ 0.5 pF (to be sized on the limiter loop gain) | `CO VSS` | limiter-loop dominant pole |
| `XMen_co` | `sg13_hv_nmos` | 1 u / 1 u | `CO ENB VSS VSS` | parks `CO` when disabled |
| `XMg2` | `sg13_hv_nmos` | 10 u / 1 u | `CLG CO VSS VSS` | gain stage |
| `XMlg` | `sg13_hv_pmos` | 5 u / 2 u | `CLG IBIAS VIN VIN` | 2 µA `CLG` load (zero current while idle) |
| `XMcoff` | `sg13_hv_pmos` | 2 u / 0.5 u | `CLG EN VIN VIN` | holds clamp off when disabled |
| `XMclamp` | `sg13_hv_pmos` | 40 u / 0.5 u (`XMen`'s geometry) | `EAOUT CLG VIN VIN` | gate pull-up, the override device |
| `XMinvp/n` | `sg13_hv_pmos` / `_nmos` | 1 u / 1 u | `ENB EN VIN/VSS` | local inverter |

The device count is 15 MOS, 52 `rhigh` units plus `XRtail`, and 1
`cap_cmomi`. All devices are HV flavour (DR-0002: LV is disqualified on the
3.3 V rail).

### 4. Error budget

Deterministic (corner) terms are what the 135-point grid can see.
Statistical terms are what #56 must measure. They are budgeted separately.
**Global resistor spread is budgeted on its own row and is zero by
construction, not by measurement.**

**(a) Global resistor spread (sheet corner and temperature)** [C]: `Rref/Rsns
= s·p` exactly, provided the units are identical (same `w`, `l`, `b`,
orientation and current direction) and isothermal. Residual: thermal
gradient between `Rsns` and `Rref` units during a short. At −0.19 %/K [M/C],
1 K of gradient gives 0.19 % and 5 K gives ≈ 1 %. **The gradient is [U]**:
there is no thermal model of the die. It becomes a layout requirement
(common-centroid, interdigitated, equidistant from `Mpass`).

**(b) Deterministic circuit terms** (all [U], placeholder budgets [A]):

| Term | Mechanism | Budget [A] |
|---|---|---|
| Sense `Vds` offset | `Vds(sense) = Vds(pass) − V_th`, with `V_th` 95–233 mV; error ≈ λ·V_th. λ at `L = 0.5 u` is unmeasured; assumed 0.05–0.15 V⁻¹ | +0.5 … +3.5 % (limit reads high) |
| `Iref` stack ratio | stacked-pair equivalence vs exact 1/2 | ±1 % |
| `Iref` vs `VOUT` | `VTH` moves ≈ 1.9 V across a 1.8 V → 0 V sweep; output conductance of the self-cascoded stack | ±2 % (plateau tilt) |
| Comparator systematic offset | pair in triode at low common mode (short), mirror `Vds` asymmetry | ±1 mV → 0.4–1.1 % |

Planning total: about ±3–4 % around a possibly shifted centre. The 135-point
grid measures this directly. If the measured shift is systematic, it is
re-centred through `s·p` or `k`, in a later record, by measurement.

**(c) Statistical terms** (σ, [C] from the PDK mismatch coefficients, using
the stated gm/I):

| Term | σ of the device parameter | gm/I | σ of `I_lim` |
|---|---|---|---|
| Sense vs pass `ΔVt` | 4.5/√(25·0.5) = 1.27 mV (`Mpass` 0.12 mV) | 3–6 V⁻¹ [A] at 25.6 µA/µm | 0.38–0.76 % |
| Sense `β` (`factuo`) | 0.4 %·µm/√12.5 | — | 0.11 % |
| `Iref` mirror `ΔVt` | `XMb0` 1.42 mV, stack ≈ 1.01 mV, RSS 1.74 mV | 6.2–9.2 V⁻¹ [M] (4 points) | 1.08–1.60 % |
| Comparator `Vos` | pair √2·4.5/√80 = 0.71 mV, load √2·7/√80 = 1.11 mV (gm_n/gm_p = 1 [A]); RSS 1.32 mV | ÷ `V_th` 95–233 mV | 0.57–1.39 % |
| `Rref/Rsns` | unit 5/√14.8 = 1.30 %; `Rsns` 0.29 %, `Rref` 0.23 % | — | 0.37 % |
| **RSS** | | | **1.34 … 2.28 % (3σ: 4.0 … 6.9 %)** |

The PDK's mean-1 `rhigh` mismatch draw (+1σ on every instance) cancels in
the ratio because both sides are built from identical units [C].

**(d) Excluded by convention**: external `IBIAS` error. It passes 1:1 into
`I_lim`. The row-8 claim is therefore a *block* claim with an ideal 2 µA
bias, like row 2's ideal `VREF`. A product-level window needs the
integrator's `IBIAS` tolerance added. The ratification packet must say so.

**Feasibility reading.** Deterministic ±3–4 % plus statistical 3σ of
4.0–6.9 % gives 7–11 %, against −10.1 % / +10.6 %. On paper the target is
**plausible but unproven**. The dominant statistical term is the existing
`XMb0` (5 u x 2 u), which this record does not resize: that would be an
amplifier change with its own record. **No widening is proposed.** If the
135-point grid or #56 shows the window cannot be met, the answer is a
separately reviewed DR (re-centring, trim, a larger bias diode, or a window
change), never a silent edit. The σ figures are calculations and **no
statistical yield is claimed**.

### 5. Integration at `EAOUT`: override without unsafe contention

- **Mechanism.** Below threshold, `CO` is low, `XMg2` is off, `CLG` is at
  `VIN` and `XMclamp` is off, so it adds only junction and overlap
  capacitance to `EAOUT`. Above threshold, `XMclamp` sources current into
  `EAOUT` and raises it until `I_out = I_lim`. The limit is a second
  negative-feedback loop around `Mpass` that regulates current. It does not
  latch.
- **Contention.** In an overload `FB < VREF`, so the amplifier drives
  `EAOUT` low through `XMn3`, whose gate `G1` can rise only as far as
  `TAIL ≈ FB + Vsg(XMinp)`. The sink that `XMclamp` must out-source is
  therefore [U] and is largest at mild overload (forced `VOUT` near 1.7 V).
  A rough estimate is 0.1–1.2 mA [A]. As an anecdote, not evidence,
  `DR-0008` reports ~1.1 mA in a discarded run where `XMen` fought the
  active amplifier at `VOUT = 0`. This current flows `VIN → XMclamp →
  XMn3 → VSS`. It does not reach `VOUT`, so it does not move `I_lim`, but
  it adds to fault input power and supply current. Requirement: measure it
  at every DC plateau point and every transient fault, and report
  `I(VIN) − I_out`. **Revisit trigger**: if it exceeds 2 mA, or if recovery
  fails because of amplifier windup, evaluate a limiter-driven `G1`
  pull-down (the `DR-0008` addendum pattern) as a design change in a
  follow-up record. It is not adopted now because it adds a second
  injection point into the main loop.
- **No conflict with `XMen`.** Both are PMOS pull-ups on `EAOUT`. When
  disabled, `XMen` holds the pass device off and `XMcoff` holds the clamp
  off.
- **Bias and startup.** `Iref` and `XMlg` depend on the external `IBIAS`.
  With `IBIAS` absent, `Iref = 0`, so any pass current exceeds the threshold
  and the clamp holds `Mpass` off. That is the fail-safe direction, and it
  must be documented in `design/README.md` at implementation. At `EN`
  rise the threshold ramps with the bias. The initially-shorted startup
  case below exercises this. In normal startup the limiter caps inrush:
  today's 0.283–0.775 A [M] would become ≈ `I_lim`. The 1 µF charge at
  roughly `I_lim − I_load` then takes tens of µs [C] instead of today's
  2–5 µs rise [M], which changes row-9 behaviour. The startup campaign must
  be re-run (consumer list). Brickwall rather than foldback is kept for the
  reason `porting-plan.md` §1.2 gives: `I_lim,min = 65 > 50 mA`, so startup
  into rated load cannot latch.
- **Compensation.**
  - *Main loop* (limiter idle): the change at `EAOUT` is `XMclamp`'s drain
    capacitance (same geometry as `XMen`) plus `XMsense`'s gate, about
    25/2800 = 0.9 % of `Mpass`'s 6.3–6.9 pF [C]. The precedent is that
    `DR-0008` measured ≤ 0.015° PM movement for `XMen` + `XMbdis`. That is
    a precedent, not evidence: rows 6 and 10 must be re-run.
  - *Limiter loop*: the loop is current sense (`Rsns/N`) → comparator gm →
    `CO` (dominant, `XCcl`) → `XMg2` → `CLG` → `XMclamp` → `EAOUT`
    (6.3–6.9 pF against the amplifier's output resistance) → `Mpass` gm.
    It needs its own loop-gain bench (break at `CLG`) in limiting, at forced
    `VOUT` = 0, 0.9 and 1.7 V, over the grid. Proposed design criterion,
    which is not a spec row: PM ≥ 45° and no sustained oscillation in the
    transient (last-1 ms ripple ≤ 2 % of mean `I_out`).
- **Clamp delay** (estimate only): `CO` slews on the tail current (resistor
  tail, ≈ 0.2–1.5 µA in regulation [C/A]) into ≈ 0.5 pF over ≈ 0.7 V, which
  gives 0.2–1.8 µs [C/A]. The amplifier can collapse `EAOUT` faster than
  that (6.3–6.9 pF against an mA-class `XMn3` sink [A]). For that interval
  the pass device is close to fully on: about 0.42–0.79 A, with `|Vsg|` near
  `VIN`. Thermally this is negligible (≈ 6 µJ [C] against ≈ 2.6 mJ over the
  10 ms hold [C]), but it is a gate-rating question (see "Terminal stress").
- **Iq.** The tail is ≈ 1 µA typical and up to ≈ 3–4 µA at `VIN` = 3.63 V
  and `res_bcs`/125 °C [C/A]. Added to the 24.72 µA worst point [M] (a
  conservative sum; the two worst corners need not coincide), that is
  ≈ 28–29 µA [C], under the proposed 30 µA (row 7, Open) with a thin margin. Iq must
  be re-measured. `XMlg` and `XMclamp` draw nothing while idle.
- **Dropout (row 4, ratified).** `Rsns` is not in the pass path. In dropout
  both `Mpass` and `XMsense` are in triode and `XMsense` sees the smaller
  `Vds`, so the sense under-reads and no false trip results [C]. The row-4
  campaign must still be re-run on the new netlist, and it must still pass.

### 6. Enable coordination (#67 / `DR-0008`)

The interface from #67 has landed on `origin/main` (`EN` port, `XMen`,
`XMbdis`, and the `G1` pull-down from #89). `DR-0008` is still Proposed. The
limiter **adds no new enable semantics**. It takes the core's `EN` net
internally, with the same `VIN`-domain rail-to-rail level requirement and
the same untreated transition region. When `EN` is low it must add only
leakage. `XMcoff`'s `Vsg = VIN − EN` reaches 3.63 V at `EN = 0` and
`VIN = 3.63 V`. That is the over-rating condition `DR-0008` already records
for `XMen`, and it is recorded here too, not hidden. If `DR-0008` changes
(for example a level shifter or polarity), the limiter's gating follows it
in the same change. The off-state benches in `sim/ldo-cmos5l-enable/` and
the startup bench's off-state samples (2.000–2.264 µA [M]) are the
regression reference.

## Validation specification (requirements for the later work, not results)

### Grid (135 combinations)

| Axis | Values | Exact name in the current runner and PDK |
|---|---|---|
| MOS | tt, ss, ff, sf, fs | `.lib ".../ihp-sg13cmos5l/libs.tech/ngspice/models/cornerMOShv.lib" mos_tt` (likewise `mos_ss`, `mos_ff`, `mos_sf`, `mos_fs`) |
| Resistor | typ, bcs, wcs | `.lib ".../cornerRES.lib" res_typ` (likewise `res_bcs`, `res_wcs`) |
| Capacitor | fixed | `.lib ".../cornerCAP.lib" cap_typ` (no characterized MoM spread) |
| Temperature | −40, 27, 125 °C | `.options temp=<T> tnom=27` (junction temperature; no self-heating) |
| Supply | 2.97, 3.30, 3.63 V | `Vin VIN 0 dc <V>` |

5 x 3 x 3 x 3 = **135** points. Point ids follow
`startup_campaign.py`: `mos_<m>__res_<r>__cap_typ` plus supply and
temperature. Models are `sg13_hv_pmos` / `sg13_hv_nmos` (PSP103, OSDI
`psp103.osdi`), `rhigh` (`r3_cmc.osdi`) and `cap_cmomi` (`cap_cmomi.osdi`),
under the PDK pin in `sim/pdk-cmos5l.json`. The `*_mismatch` sections are
**not** used: the grid is deterministic. Mismatch, Monte Carlo and yield
belong to #56 once the circuit exists. Execution goes through `klt sim` on
the batch fleet (`run_sweep.sh --batch` pattern), not as local grids.

Common conditions: `VREF = 0.90 V` (ideal) and `IBIAS` an ideal 2 µA sink
(the existing convention). `EN` is tied to `VIN` except in the startup case.

**Current-sign convention.** A 0 V ammeter `Vmeas VOUTPIN OUT dc 0` sits
between the core's `VOUT` pin and the external node `OUT`. `I_out = i(Vmeas)`
is positive when the core sources. KCL at `OUT`:
`I_out = I_C + I_L + I_shunt`, each positive leaving `OUT`. Capacitor
discharge current is `−I_C`. Where the OSDI device currents are readable
(`@n.xtop.xilim.xmsense.nsg13_hv_pmos[ids]`, as the E1 record reads
`@n.xmpass...`), `Id(Mpass)` and `Id(Msense)` are also reported. `I_out` is
the normative pass current (it includes the sense branch, which reaches the
load).

### DC bench

1. **Forced-`VOUT` sweep**: a source on `OUT` sweeps 1.80 → 0.00 V in 10 mV
   steps, then 0.00 → 1.80 V to detect hysteresis or latch. No other load.
   Record `I_out`, `I(VIN)`, `V(EAOUT)`, `V(xilim.ISNS) − V(xilim.VTH)` and
   `V(xilim.CLG)`. Limiter **engaged** means `V(ISNS) >= V(VTH)` and
   `V(CLG) < V(VIN) − 0.3 V`.
2. **Hard-short point**: a separate `.op` with a zero-volt source
   `Vshort OUT 0 dc 0`, solved from scratch, to confirm the short operating
   point is unique and not inherited from the sweep.
3. **Plateau metrics**: `I_onset = I_out(1.764 V)` (2 % droop, where the
   amplifier is saturated), `I_short = I_out(0 V)`. The **window** check is
   65 mA <= `I_out` <= 80 mA at **every** plateau point from 0 V to 1.764 V.
   `I_out(1.80 V)` sits on the setpoint and is excluded.
4. **Brickwall vs foldback**, proposed classification:
   - brickwall: `max/min` of `I_out` over the plateau <= 1.05, **and**
     0.95 <= `I_short/I_onset` <= 1.05;
   - foldback: `I_short/I_onset < 0.95`, with `I_out` falling as `VOUT`
     falls;
   - anything else is *non-flat* (inverse fold, kinks or hysteresis) and
     counts as a fail.
   Only brickwall satisfies row 8.
5. **Normal regulation** at 0, 1 and 50 mA (`Iload` current sink, as in the
   existing DC bench): `VOUT` against the pre-limiter record
   `20261011-070111-5391c68` at the same corner. Flag `|ΔVOUT| > 1 mV`.
   **No engagement**: at 50 mA, `V(ISNS) − VOUT <= 0.8·(V(VTH) − VOUT)`
   and `V(CLG) >= V(VIN) − 50 mV`.

### Transient: fault on a running regulator

- Start from the closed-loop DC operating point: `Cout = 1 µF`, ESR 0,
  rated load **`R_L = 36 Ω`** (50 mA at 1.8 V). A resistor is used because
  an ideal 50 mA sink is non-physical at `VOUT ≈ 0` and during recovery.
- **Pre-fault settle gate**: at 1 ms, `VOUT` in [1.764, 1.836] V and
  `|VOUT(1.0 ms) − VOUT(0.9 ms)| <= 1 mV`. If not, the point is reported
  as *pre-fault not settled* (a fail, not a skip), and 1 ms is declared
  insufficient for that point.
- **Shunt**: 10 mΩ from `OUT` to ground, applied at 1 ms with a 100 ns edge,
  held through 11 ms, released with a 100 ns edge, and simulated to 16 ms.
  Recommended form: a B-source `I = V(OUT)·G(t)` with `log10 G` ramped by
  PWL between −9 (1 nS) and +2 (100 S). The record must state the exact form
  it used. Time resolution: at least 5 points per edge and the achieved step
  near each edge reported.
- **Capacitor discharge vs pass current**: Cout discharges about 1.8 µC
  through the shunt in roughly the edge time, with amperes of peak current
  [C]. None of it flows through `Vmeas`. Report `I_out(t)` and `−I_C(t)`
  separately, plus `∫−I_C dt` over the edge. Never attribute shunt current
  to the pass device.

### Transient: initially-shorted startup

The shunt is on from t = 0. `EN` follows the startup bench's profile
(`EN = VIN·CTL`, 0 → `VIN` at 1 ms with a 1 µs edge). The shunt is released
at 11 ms and the run ends at 16 ms. The same metrics apply, with the peak
window starting at the `EN` edge.

### Metrics per point (both transient cases, and DC where applicable)

| Metric | Definition |
|---|---|
| `I_out,steady` | mean `I_out` over [10, 11] ms; must lie within 65–80 mA |
| `I_out,peak` | max `I_out` over the fault window (from the `EN` edge in the startup case) |
| `|Vsg|`, `|Vgd|`, `|Vds|` of `Mpass`, steady and peak | `V(VIN)−V(EAOUT)`, `|V(EAOUT)−V(VOUTPIN)|`, `V(VIN)−V(VOUTPIN)`; steady = mean over [10, 11] ms, peak = max over the run |
| Time above 3.3 V | total duration with `|Vsg| > 3.3 V` |
| Clamp delay | `t_engage`: first `V(ISNS) >= V(VTH)` after the edge. `t_clamp`: time from the edge until `I_out` enters ±5 % of `I_out,steady` and stays there |
| Fault supply overhead | `I(VIN) − I_out` (contention plus bias) |
| Pass power | `p(t) = (V(VIN) − V(VOUTPIN))·I_out`; peak and steady |
| Fault energy | `E = ∫ p dt` from the fault edge to the end of the release edge |
| Recovery | `t_rec`: time after the release edge ends from which `VOUT` stays in [1.764, 1.836] V through 16 ms; peak overshoot reported |
| Limiter-loop ripple | peak-to-peak `I_out` over [10, 11] ms, as a fraction of the mean |

**Recovery deadline (proposed): `t_rec <= 3 ms`**, under the 36 Ω rated
load, with `VOUT` inside ±2 % from 14 ms to 16 ms. A restart from a
discharged output is a startup, so the deadline mirrors row 9's "inside
±2 % within 3 ms". The measured startup settling, at most 0.441 ms [M]
(1 mA load), shows the deadline is not vacuous. A saturated amplifier
(windup) is expected to overshoot on release, and the startup grid already
fails overshoot without a limiter [M]. That counts against recovery. It is
not excused.

### Terminal stress: rating sources and per-metric classification

Each metric is classified **individually, per device and per point**:
**PASS** (within a cited rating), **FAIL** (over a cited rating, including
transiently), **UNRESOLVED** (no published rating, package or model), or
**INSUFFICIENT** (missing or non-converged data). Classes are never
aggregated into a single verdict.

| Stress | Rating source | Note |
|---|---|---|
| `|Vgs|` HV PMOS/NMOS | `VGS <= 3.3 V @ 27 °C, LG >= 0.5 µm`, process spec §2.1.5 (PMOS). The NMOS `VGS` line is to be read from §2.1.4 [U] | **Steady-state `|Vsg(Mpass)| <= 3.3 V` at all 135 points is DR-0001's carried gate** (via DR-0002). A transient exceedance is a FAIL against the published maximum, reported with its duration. Accepting it needs a transient/TDDB rating the cited spec does not give [U], or a separate DR. Ratings above 27 °C are not published [U] |
| `|Vds|` | `BVDSSPHV04` −5.3 V worst; `BVDSSNHV013` >= 5.3 V | 3.63 V max on the rail [C] |
| `|Vgd|`, `|Vgb|` | none published separately [U] | The 3.3 V oxide limit is applied as a proxy [A] and reported |
| `XMclamp` / `XMcoff` / inverter `|Vsg|` | as `|Vgs|` | `CLG` can be driven to `VSS` transiently (and `EN = 0`): up to 3.63 V. The `DR-0008`-type over-rating is reported, not hidden |
| `rhigh` current density, voltage | not cited on this branch [U] | `Rsns` carries 32 µA per unit at trip and up to ≈ 0.35 mA per unit at the unlimited peak [C] |
| Metal electromigration (80 mA continuous, ≈ 0.8 A µs peaks) | PDK EM rules [U] | layout follow-up |

If a steady-state FAIL or a transient FAIL is found, the mitigations to
evaluate in a follow-up are: a faster limiter path, an `EAOUT` floor clamp
that bounds `EAOUT >= VIN − 3.3 V` (it must not touch the ratified dropout
row), or a separate rating DR.

### Short-survivability: thermal acceptance rule

A finite electrical transient **cannot** show continuous thermal survival.
Rule:

```
T_A,max + θ_JA · P_short,max <= T_J,max = 125 °C
P_short,max = max over the 135 points of [ V(VIN)·I_out(0 V) + V(VIN)·(I(VIN) − I_out) ]
```

using DC hard-short values. 125 °C is the hottest characterized model
temperature. The grid's temperature axis is junction temperature.

| `I_short` at 3.63 V | `P` | θ_JA limit at `T_A` = 25 / 70 / 85 °C |
|---|---|---|
| 65 mA | 0.236 W | 424 / 233 / 170 °C/W |
| 72.32 mA | 0.263 W | 381 / 209 / 152 °C/W |
| 80 mA | 0.290 W | 344 / 189 / 138 °C/W |

The figures are [C] and exclude the few-mW overhead term. **No package,
θ_JA or `T_A,max` is declared anywhere in this repository [U].**
"Short-survivable" therefore cannot be ratified until one of these lands:
a ratified package/integration assumption (gf180's delegate-to-integration
posture, its DR-0005 / note 5), or an on-chip thermal-shutdown decision
(sky130's posture). That is `spec/porting-plan.md` §4 item 8, made with a
record that uses the measured `P_short,max`. Survival also requires every
steady-state terminal stress to be PASS and recovery to pass at all 135
points.

## Row 8 cannot be reported satisfied without all of

1. The limiter implemented, and `python3 design/netlist.py --design sg13cmos5l --check` clean.
2. 135-point DC and both transient records, with every point inside 65–80 mA
   (plateau and steady), brickwall-classified, with no pre-fault-settle
   failures and recovery within the deadline.
3. #56's statistical evidence for the window. The σ figures here are not
   that evidence.
4. Every steady-state terminal stress PASS. Every transient FAIL mitigated
   or ruled on by a separate DR. Every UNRESOLVED rating either resolved or
   carried explicitly into the ratification packet.
5. The thermal rule closed by a ratified package/θ_JA/`T_A` or a
   thermal-shutdown record.
6. Regression on the new netlist for rows 2, 4 (ratified), 5, 6, 7, 9 and
   10, plus the off-state benches.
7. Physical evidence regenerated (below), and post-layout verification of
   the sense path once extraction exists (T1 item 7).
8. Both review keys.

## Follow-up boundaries

- **Implementation** (new issue, after this review): the new cell, the
  core instance, regenerated netlists (outputs, not sources), the
  `design/README.md` limiter section, and the new benches under a new
  `sim/ldo-cmos5l-current-limit/` (DC, two transients, limiter loop gain),
  with reducer unit tests and negative controls (for example, a disabled
  clamp must fail the window; a ratio-broken netlist must fail flatness).
- **#55** owns the subsequent *deterministic* row coverage: its coverage
  inventory and any `klt sim` envelopes for row 8 once the limiter exists.
  #55's existing benches **do not** cover row 8. Its current inventory
  correctly lists row 8 as not implemented, and nothing here changes that.
- **#56** owns the subsequent *statistical* evidence: mismatch Monte Carlo
  on the implemented limiter at its named corners (`mos_*_mismatch` with
  `res_*_mismatch`), and the yield statement. Its existing row-2 campaign
  **does not** cover row 8. Item 6 stays uncited for the reasons
  `signoff/README.md` gives.
- **Cout/ESR extremes, 0 mA pre-fault load and supply transients during a
  fault** are follow-up coverage, not part of this plan's first deliverable.

## Consumer inventory

Command, run against `origin/main` `ed55de7c`:
`git grep -l 'ldo_core_cmos5l' origin/main -- design sim layout` gives
**6301 paths**. Grouped:

**Sources and generated outputs that the implementation changes or regenerates:**

- `design/sg13cmos5l/ldo_core_cmos5l.sch`: the new `Xilim` instance. `.sym`
  is unchanged (same ports). `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`
  is regenerated, and a new `ldo_ilimit_cmos5l.spice` is generated
  (`design/netlist.py` exports every cell in the directory).
  `design/sg13cmos5l/ldo_erramp_cmos5l.sch` is unchanged (it matches only
  through a comment).
- `design/netlist.py` (the port invariant holds; check run),
  `design/README.md`, `design/xschemrc`.

**Benches with a flattened copy of the core body** (must be updated by
hand, and `run_sweep.sh`'s topology guard will reject them until they are):

- `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh` (`LOOPGAIN_EXPECTED_BODY` and its
  negative controls), `testbench/tb_loopgain_cmos5l.spice.tmpl`,
  `tb_loopgain2v_cmos5l.spice.tmpl`, `tb_loopgain2i_cmos5l.spice.tmpl`,
  `tb_e1op_cmos5l.spice.tmpl`.

**Benches that include the netlist** (they pick up the limiter, then need
re-running and re-recording):

- `testbench/tb_dcsweep_cmos5l.spice.tmpl`, `tb_dropout_cmos5l.spice.tmpl`,
  `tb_psrr_cmos5l.spice.tmpl`, `tb_startup_cmos5l.spice.tmpl`,
  `run_e1op.sh`, `run_loopgain2.sh`, `startup_campaign.py`,
  `dropout_campaign.py`, `item5_evidence.py`, `test_ac_sweep.py`,
  `test_batch_backend.py`.
- `sim/ldo-cmos5l-monte-carlo/` (`tb_row2_accuracy.spice`,
  `tb_row2_accuracy_en.spice`, `test_deck_versioning.py`, `README.md`).
- `sim/ldo-cmos5l-enable/` (12 benches, including the pre-#67 baseline and
  `README.md`).
- `sim/characterization/` (`selection.json`, the generated report). Its
  netlist sha256 pins go stale, so item 8 needs re-selection after
  re-runs, per `signoff/README.md#regenerating`.
- `sim/README.md`, `sim/ldo-cmos5l-pvt-sweep/README.md`,
  `sim/migration-inventory-155.md`.

**Layout** (all regenerated in the layout follow-up):
`layout/sg13cmos5l-ldo_core_cmos5l/generate.py`, `layout/lvs_reference.py`,
`layout/run_flow.sh`, `layout/README.md`, and the GDS, extracted netlist,
LVS reference, DRC/LVS/ERC/extract reports, `lvs_request.json` and
`erc-supply-spec.md` in that directory.

**Append-only evidence that is NOT edited** (each item stays tied to the
netlist it was made from): `sim/ldo-cmos5l-pvt-sweep/{records,corners,netlist-snapshots,evidence,startup,backend-validation}/`,
`sim/ldo-cmos5l-enable/records/`, `sim/ldo-cmos5l-monte-carlo/{records,evidence}/`
(about 6000 paths in total).

## Layout / LVS follow-up

- `XMsense`: one additional `25 u / 0.5 u` finger, interior to the `Mpass`
  array, with the same orientation. `Mpass` keeps its 112 fingers and
  2800 µm. Taking a finger out would resize `Mpass` and reopen `DR-0003`.
  The drain is routed separately to `Rsns`, and the `Rsns`/`Rref` return
  joins `VOUT` at a Kelvin point near the pass drains. A few-Ω metal
  difference between the sense and pass drain paths is a ratio error [U]
  until extraction exists.
- The 52 `rhigh` units are interdigitated and common-centroid with dummies,
  isothermal with respect to `Mpass` (term (a) above). LVS compares `rhigh`
  at device level today (`lvs_reference.py` `rhigh_reference_ohms`).
  Whether `klt lvs` combines 32 series and 20 parallel units, or the
  reference must list them unit by unit, has to be checked. If the deck
  cannot express it, file a generic `2AMLogic/klayout-tools` issue.
- `XCcl` (`cap_cmomi`) inherits today's name-equality-only LVS compare.
- VOUT/VIN/sense metal must be sized for 80 mA continuous at `T_J` 125 °C
  against PDK EM rules. DRC does not check this [U].
- The ERC tie spec and tap boxes need updating for the new NWell/substrate
  regions.
- **Existing physical evidence stays tied to its original netlist.** The
  committed GDS and DRC/LVS/ERC reports and their item 2/3/4/11 pins
  describe the current limiter-less core. They are superseded only by a
  regenerated set, never edited to match.

## Missing characterization (explicit list)

1. λ (output conductance) of `sg13_hv_pmos` at `L = 0.5 u` and of the
   series-stacked `5 u / 2 u` pair; the exact stack ratio.
2. gm/I of `Mpass`/`XMsense` at 25.6 µA/µm (only 1 mA points exist).
3. `XMn3`'s saturated sink current with `FB` low (the contention current),
   across the grid.
4. Comparator behaviour at a common mode of 0.1–0.25 V (triode pair) and
   at `VIN − CM ≈ 0.93 V` (`VIN = 2.97 V`, ss/−40 °C).
5. Whether a 2 µm `rhigh` unit tracks the 1 µm leg's corner and
   temperature spread; `rhigh` current density and voltage ratings.
6. Die thermal gradient during a short (no thermal model).
7. HV NMOS `VGS` rating line; any rating above 27 °C; any `|Vgd|`/`|Vgb|`
   or transient oxide rating.
8. Package θ_JA and `T_A,max` (none declared).
9. Metal EM limits for the output path.
10. Limiter-loop stability margins and clamp delay (they need the circuit).

## Alternatives considered

- **Copy the gf180 reference (`VREF/Rbias`, one uncancelled `Rsns`).**
  Rejected: 2.44 : 1 measured `rhigh` spread against a 1.23 : 1 window [C].
- **Widen the window now (as gf180 DR-0005 did).** Rejected for this
  record: the target is retained, and any widening needs its own reviewed
  DR on measured evidence.
- **`Iref = IBIAS` (1:1 mirror).** Rejected: 2 µA exceeds the 1.974 µA
  minimum divider current [M], which would lose no-load regulation.
- **Current-mode comparison, sense current to `VSS`.** Rejected: the sense
  current (≈ 0.45 mA at 50 mA with `N = 112`) would land in Iq at full load,
  against the < 30 µA row.
- **PMOS current-source tail.** Not adopted: about 0.93 V of headroom at
  `VIN = 2.97 V` and ss/−40 °C (`|Vth|` up to 0.776 V [M]) leaves too little
  for a saturated tail. This is the sibling's resistor-tail reasoning.
- **Gate-voltage clamp (diode stack `VIN`–`EAOUT`).** Not adopted:
  stack turn-on spreads by corner and would bite into the ratified dropout
  operating point. It is held in reserve as the `EAOUT` floor-clamp
  mitigation above.
- **Bipolar sensing.** Not available: `pnpMPA` is the only bipolar device,
  with a substrate collector and β ≈ 1 (`DR-0002`).

## Consequences

- No file other than this record and a pointer in `spec/porting-plan.md`
  §4 item 6 changes. Row 8 and row 1 stay Open. `README.md`, `DR-0007` and
  `spec/README.md` are untouched. Hash-pinned inputs are unaffected, so no
  signoff regeneration is needed.
- `reuse.lock.json` is not changed. The sibling is a topology reference,
  not a reused block.
- After review, implementation proceeds as its own issue, then evidence
  (#55, #56), then layout, then ratification, in that order.

## References

- gf180-ldo @ `d83daea06432b21b91a1cef32ddedc386f5a1e32`: `design/ldo_ilimit.sch`,
  `design/netlist/ldo_ilimit.spice`, `spec/decision-records/DR-0005-current-limit-window.md`.
- `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`, `ldo_erramp_cmos5l.spice`.
- `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh`, `startup_campaign.py`,
  `testbench/tb_dcsweep_cmos5l.spice.tmpl`, `tb_startup_cmos5l.spice.tmpl`.
- Records cited: `20261011-070111-5391c68.csv`, `20261011-070146-0c95530-startup-grid.md`,
  `20261012-115531-cfa681f9.e1op.csv` (all under `sim/ldo-cmos5l-pvt-sweep/records/`),
  `sim/pass-device-screening/records/20260909-220347-ed18110.csv`.
- `sim/ldo-cmos5l-monte-carlo/README.md` (PDK mismatch coefficients).
- `spec/porting-plan.md` §1.2, §1.3 (thermal postures), §2.3, §4 items 6 and 8.
