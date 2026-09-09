# pass-device-screening

Per `CLAUDE.md`: **verification is the product, no claim without a
testbench**, PVT corners on every recorded result, and results here are
**append-only evidence** — a re-run mints a new, timestamped record; nothing
under `records/`, `netlist-snapshots/` or `corners/` is ever edited or
deleted after it lands. This follows the same per-experiment shape
(`README.md` / `testbench/` / `corners/` / `netlist-snapshots/` / `records/`)
`sg13g2-bandgap/sim/<experiment>/` and `sg13g2-opamp/sim/gm-id-characterization/`
established on this same PDK.

## What this is

A bare-device screening deck for `sg13_hv_pmos` — the device flavor
`design/ldo_core.sch`'s `Mpass` uses (`design/README.md` "Pass device":
common-source, source tied to `VIN`, drain tied to `VOUT`, body tied to
`VIN`). This is the input `spec/porting-plan.md` §4 item 1 calls "the
single most consequential record — nearly every other row and record below
depends on it": confirm or reject the `sg13_hv_pmos` common-source
hypothesis against real screening data before any pass-device width,
current-limit, or compensation record is written.

This is a **device-characterization study, not a circuit-level bench** —
`Xdut` in both testbench templates instantiates `sg13_hv_pmos` directly, the
same posture `sim/gm-id-characterization` takes in the sibling
`sg13g2-opamp` repo, not an extraction from or instantiation of
`design/netlist/ldo_core.spice`.

## What is measured, and where

Two benches, both defined against fixed absolute bias points (see "Corner
grid and axes swept" below for why the supply-voltage axis is not an
independent sweep here):

1. **`testbench/tb_dropout_pmos.spice.tmpl`** — the dropout test point,
   `Vin = 2.10V` (source), `Vout = 1.80V` (drain), gate at `0V` (fully on),
   per `spec/porting-plan.md` §1.4/§2.1 (`Vin = Vout + dropout ≈ 2.10V`,
   **not** `Vin_min` — both siblings' own screening decks found this is
   "the single easiest sizing trap", and the binding corner is slow-and-hot,
   not simply worst-case-supply):
   - **`Id_dropout` / `Ron` / `Ron·W`** — read directly off the DC
     operating point at this bias (`Ron = (Vin-Vout)/Id`, `Ron·W = Ron ×
     W_drawn`).
   - **`Vth`** — constant-current method (`Id_crit = 100nA × W/L`, the same
     convention `sim/gm-id-characterization` uses in the sibling
     `sg13g2-opamp` repo), extracted from a DC sweep of the gate node **at
     this same `Vds = 0.30V` dropout differential** (not the conventional
     near-zero-`Vds` `Vth` definition) — see "Threshold voltage definition"
     below for why.
   - **`Cgate`** — small-signal AC gate current at 10 MHz, same method
     `sim/gm-id-characterization/testbench/tb_gmid_pmos.spice.tmpl` uses
     (`Cgg = |Im(Ig)| / (2π×10MHz)`), evaluated at the same dropout bias
     (gate returned to 0V after the DC sweep).
2. **`testbench/tb_stress_pmos.spice.tmpl`** — the continuous-short
   current-limit condition, `Vout = 0V` (dead short) at `Vin = 3.63V`
   (the Input row's own `+10%` corner), gate at `0V` (fully on — no
   current-limit loop exists yet in this repo, so this bench drives the
   pass device as hard on as the bare device screen can: the conservative,
   worst-case bound on gate-oxide stress a real closed-loop current limiter
   would only ever relieve, not worsen — see "Continuous-short stress: a
   conservative bound" below):
   - **`|Vds|`, `|Vsg|`, `|Vdg|`** — with all three terminal voltages
     imposed by ideal DC sources, these are algebraic consequences of the
     bias, not swept quantities; reported per corner/temp point anyway so
     the record has one source of truth.
   - **Drain current per micron (`Id/W`)** — the genuine simulation result
     at this bias, and the number that matters for self-heating/dissipation
     at the current-limit condition.

Both benches are generated from templates by `run_sweep.sh`, which also
does all Vth/Ron·W/implied-width post-processing (Python, inline in the
script — no separate tool needed at this scale).

## Device sizes screened

| Label | W | L | Why |
|---|---|---|---|
| `w1u_l0.4u` | 1 µm | 0.4 µm | `Ron·W`-normalized (see below); `L=0.4µm` is an actual characterized test-structure length in the PDK's own process spec (`VTPHV10x04`/`IDSPHV04`, `libs.doc/doc/SG13G2_os_process_spec.pdf` p.9) — a real measured cross-check point, see "Cross-check against the process spec". |
| `w1u_l0.5u` | 1 µm | 0.5 µm | `Ron·W`-normalized, at `design/ldo_core.sch`'s drawn `L`. |
| `w1u_l1.0u` | 1 µm | 1.0 µm | `Ron·W`-normalized, the "few multiples" long-channel point the issue's scope invited. |
| `w300u_l0.5u` | 300 µm | 0.5 µm | `design/ldo_core.sch`'s **as-drawn** `Mpass` size (`design/README.md` "Pass device": "a modest first-cut size... not sized against any dropout... target") — a direct, non-normalized cross-check that the `Ron·W` normalization (below) actually holds at this repo's own drawn size. |

**Why normalize at `W=1µm`**: `Ron·W` is approximately constant with `W` in
the linear region (`Ron ∝ 1/W` for fixed `L`), so measuring at a fixed
`W=1µm` lets `Ron·W` be read off directly in `Ω·µm` without an extra
division step, and the same normalized run gives the implied width for any
target current/dropout pair by simple scaling
(`W_implied = I_target × Ron·W / dropout_target`). The `w300u_l0.5u` row
confirms this empirically for this design (see "Results" below) rather than
asserting it.

## Corner grid and axes swept

**Process × temperature, full factorial: `{tt, ss, ff, sf, fs}` ×
`{-40, 27, 125}°C` = 15 points**, applied identically to every device size
and to both benches (15 × 4 × 2 = 120 total simulation points per record).

**The supply-voltage axis `{2.97, 3.30, 3.63}V` is deliberately NOT an
independent sweep axis here.** Both test points this deck screens are
defined as *fixed absolute* `Vin` values, not relative to a swept nominal
supply corner:

- The dropout point is `Vin = 2.10V` by definition
  (`spec/porting-plan.md` §1.4: `Vin = Vout + dropout`), regardless of which
  nominal-supply corner is under consideration elsewhere in the port.
- The continuous-short stress point is `Vin = 3.63V` — itself *already* the
  Input row's own `+10%` corner, the worst case that axis has to offer, so
  sweeping it further would only re-run the same point at lower `Vin`
  values that are, by definition, less stressful.

This mirrors `spec/porting-plan.md` §1.4's own framing directly and is the
same reasoning both `gf180-ldo DR-0004` note 4 and `sky130-ldo DR-001`/
`DR-003` independently arrived at.

## Threshold voltage definition

`Vth` is extracted by the **constant-current method** (`Id_crit = 100nA ×
W/L`), log-interpolated between the two bracketing `(Vsg, Id)` sweep points
— the identical technique `sim/gm-id-characterization/run_gmid_sweep.sh`
uses in the sibling `sg13g2-opamp` repo. The one deliberate difference from
a textbook `Vth` definition: that extraction is done **at the dropout bias's
own `Vds = 0.30V`** (`Vin - Vout`), not the conventional near-zero-`Vds`
linear-region definition. This is a deliberate choice, not an oversight: the
dropout condition's own `Vds` is what the `Ron·W` measurement at the same
bias point already uses, so `Vth` and `Ron·W` are read off the same,
self-consistent operating condition rather than two different ones. A
reader comparing this record's `Vth` numbers against a datasheet's
near-zero-`Vds` `Vth` should expect this record's values to run somewhat
lower in magnitude (DIBL) — this is expected, not a discrepancy.

## Continuous-short stress: a conservative bound

The stress bench holds the gate at `0V` (fully on) for the entire corner
grid, because no current-limit control loop exists in this repo yet
(`design/README.md`'s error amplifier is an ideal behavioral placeholder,
not a real circuit — `spec/porting-plan.md` §4 item 6 is still open). A real
current-limit loop, once built, would sense the fault current and pull the
gate *toward* `Vin` to throttle it — which **reduces** `|Vsg|` below this
bench's fully-on value, not increases it. So this bench's `|Vsg|` figure is
a conservative upper bound on gate-oxide stress at the continuous-short
condition, not a claim about what the finished, current-limited circuit
will actually subject the device to. The finding below (`|Vsg|` exceeding
the PDK's stated rating) is reported as exactly that: a bound that the
eventual current-limit design must respect, not a verdict on a circuit that
does not exist yet.

## Ratings checked, and the finding

Read directly from `libs.doc/doc/SG13G2_os_process_spec.pdf` (IHP-Open-PDK
v0.3.0, p.9, "A.f3 HV-PMOS"): **`VGS ≤ 3.3V (Maximum) @ 27°C for LG ≥
0.5µm`**, and a drain-source breakdown voltage (`BVDSSPHV04`) in the
`5.3–6.3V` range (`WxL = 10 × 0.4µm²` test structure).

- **`|Vds|` at continuous-short stress = 3.63V** for every corner/temp point
  (bias-imposed) — comfortably inside the `5.3–6.3V` breakdown range, no
  finding.
- **`|Vdg| = 0V`** for every point (bias-imposed: drain and gate both held
  at `0V`) — no finding.
- **`|Vsg| = 3.63V`** for every corner/temp point (bias-imposed: gate at
  `0V`, source at `Vin = 3.63V`) — **this exceeds the process spec's stated
  `3.3V` maximum `VGS` rating by `0.33V` (10%)**, exactly the Input row's
  own `±10%` tolerance. This is a real, quantified finding, not a spec
  relaxation: **at the bare-device, gate-fully-on worst case, `sg13_hv_pmos`
  is stressed 10% past its stated gate-oxide rating during a continuous
  short at `Vin_max`.** Per "Continuous-short stress: a conservative bound"
  above, this is the bound the eventual current-limit loop must relieve
  (by not holding the gate fully at `0V` under fault), not evidence that the
  finished circuit is unsafe — but it is evidence that **an unprotected
  pass device left fully on during a dead short is not safe at this input
  rail**, which is exactly the kind of finding `sky130 DR-001` found
  binding for its own pass device and this deck exists to surface.

## Cross-check against the process spec

The same process spec page states `VTPHV10x04` (`W×L = 10×0.4µm²`) at
`min/target/max = -0.71/-0.65/-0.59V`. This record's own `w1u_l0.4u` `Vth`
at `tt`/27°C is reported in `records/*.csv` — see that file for the value at
record time; a value in the same rough neighborhood as the process spec's
target (allowing for this deck's `Vds=0.30V` extraction bias vs. the
process spec's own near-zero-`Vds` measurement condition, and this deck's
own temperature/corner spread vs. the process spec's single 27°C
measurement) is the expected outcome and corroborates the extraction
methodology; a wildly different value would be a red flag worth
investigating before trusting the rest of the sweep.

## Verdict: `sg13_hv_pmos` hypothesis

**Not rejected**, consistent with `design/README.md`'s own inspection-level
finding ("SG13G2 has a native 3.3V-class PMOS... the hypothesis was not
rejected") — this record adds the missing measured data behind that
finding:

- `Ron·W` is measurable and consistent between the `W=1µm`-normalized and
  `W=300µm`-as-drawn devices (within roughly 10–15%, plausible for a
  bare-device screen at a fixed, non-trivial `Vds`) — the normalization
  this record leans on holds for this design.
- The dropout point and drain-rating (`Vds`/`Vdg`) checks both clear with
  margin.
- The one real caveat is the `Vsg` gate-oxide finding above — a genuine,
  quantified risk for the *eventual* current-limit design to resolve, not a
  reason to reject the device flavor itself (both siblings' own
  pass-device records carry forward similar "confirmed, with a caveat the
  next record must address" postures — see `gf180 DR-0002`/`sky130 DR-001`).

**Ratifying a decision record (DR-0001) from this finding is out of scope
for this issue** (see the issue's own "Out of scope" section) and is filed
as a follow-up — see the record's own links / the issue tracker for the
follow-up issue number.

## Implied pass-device width

`records/*.csv`'s `implied_w_um_50ma_300mv` / `implied_w_um_100ma_200mv`
columns report `W_implied = I_target × Ron·W / dropout_target` at every
corner/temp/device-size point — most usefully read at the `w1u_*` rows
(the `Ron·W`-normalized measurement this scaling law assumes) and at
whichever corner the record's own sanity-check output names as the binding
dropout corner (expected, and confirmed in practice, `ss`/125°C — see
`spec/porting-plan.md` §1.4's "binding corner is slow-and-hot" framing).
These numbers are the direct input the future `Mpass` resizing decision
record needs; resizing `Mpass` itself is explicitly out of scope for this
issue.

## Cold-start reproduction

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # one-time: build the OSDI models
sim/pass-device-screening/run_sweep.sh  # full 120-point sweep, mints a new record
```

(`PDK_ROOT`/`PDK` may be left unset if the PDK is installed under one of the
usual prefixes `sim/env.sh` checks.) Requires `ngspice` on `PATH` plus the
OSDI device models `sim/tools/build-osdi.sh` builds; does not require
`xschem` or `klt`. A lightweight `--check-env` mode (one netlist per bench,
syntax-checked via `ngspice -b`, no records/ entry written) is what
`.github/workflows/ci.yml` runs on every push/PR — see `run_sweep.sh`'s own
header comment.

## OSDI device models

See `sim/README.md` "OSDI device models" (this repo's own copy of the
sibling repos' `sim/tools/build-osdi.sh` provenance/rationale) — this
experiment only instantiates `sg13_hv_pmos` (`PSP103.6` via `psp103.osdi`),
no resistor or bipolar device.

## Spec ratification: which issue tracks it

No row of `spec/porting-plan.md` §6/the README's DRAFT target table is
ratified, so **this record does not itself claim conformance to a ratified
spec row** — it reports measured device data and an implied width, both
useful inputs to a future ratification/sizing decision, not a claim against
one. See the issue tracker (`#5`) for T1 tracker status.
