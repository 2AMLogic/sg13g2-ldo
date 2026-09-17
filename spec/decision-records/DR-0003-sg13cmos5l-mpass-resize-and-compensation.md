# DR-0003: SG13CMOS5L port — `Mpass` resize and error-amp re-compensation

> **AMENDED by [`DR-0005`](DR-0005-sg13cmos5l-cc-recompensation.md) (issue
> #35), 2026-09-17, in exactly one value: `Cc` is `w=170µm, l=30µm`
> (≈5.5 pF), not the `w=100µm` this record sized.** Everything else in
> Decision (b) stands — the `Mtail`/`Mload2` mirror ratios (`m=3`/`m=6`),
> `Rz` (`w=1µm`, `leff` 1200 µm), and above all the *approach* (use the
> nulling resistor's zero as a deliberate phase-lead element near
> crossover, not only as an RHP-zero canceller). Decision (a), the `Mpass`
> resize to `w=2800µm`, is untouched.
>
> **Why**: this record's evidence held the resistor corner at `res_typ`
> across its main grid and swept it only at `tt`/27 °C, so its "PASS at
> every corner" stability verdict was never tested at `res_bcs`/125 °C.
> [`DR-0004`](DR-0004-sg13cmos5l-resistor-corner-stability.md) found
> `PM ≥ 45°` failing there at all five MOS corners once #31 crossed the
> axes in full; `DR-0005` closes that gap on `Cc` alone and re-verifies at
> all 45 points. **Cite `DR-0005`, not this record, for any claim about
> this branch's stability across the resistor corner.** The tables below
> are left as written — they are what was measured at the time, on the
> grid that was run at the time — and are not retro-edited.

- **Status**: Proposed (this PR is the ratification act — see "Status" below).
- **Date**: 2026-09-16
- **Scope**: The **SG13CMOS5L branch only** (issue #25, phase 3.5/4 of the
  SG13CMOS5L port tracked by #12, Epic `2AMLogic/2am#542` Phase 5A). This
  record amends the *sizing* `DR-0002` explicitly left open — it does not
  revisit `DR-0002`'s device-flavour or topology decisions, and it does not
  touch the SG13G2 branch (`design/ldo_core.sch`) at all.
- **Related**: [`DR-0002`](DR-0002-sg13cmos5l-device-topology.md) (device
  flavours + topology this record's sizing implements),
  [`DR-0001`](DR-0001-pass-device-flavor.md) (the carried-forward `|Vsg| ≤
  3.3 V` constraint this resize still respects), `spec/porting-plan.md`
  §1.3 (gf180-ldo's own compensation work took ten decision records of
  negative results before its loop was stable across PVT — the precedent
  this record's single-pass positive result is checked against), issue #21
  (closed-loop PVT verification that produced the failing evidence this
  record responds to), `sim/ldo-cmos5l-pvt-sweep/README.md` (the harness
  and the before/after evidence cited throughout).

## Status

**Proposed.** Per the fleet's standing ratification policy
(`2AMLogic/2am#357`: "a builder drafts the ratification/DR as a PR on the
evidence, and the operator's PR approval is the ratification act"), this
record is drafted as a PR on the evidence gathered below. **Operator
approval of that PR is what moves this record to Accepted** — there is no
separate ratification step.

## Context

### What #21 found, and why it forced this record

Issue #21 ran the first closed-loop PVT verification of
`design/sg13cmos5l/ldo_core_cmos5l.sch` against the full
`{tt,ss,ff,sf,fs} × {-40,27,125}°C` grid. Both `Mpass`
(`design/sg13cmos5l/ldo_core_cmos5l.sch`) and the error amplifier's
`Cc`/`Rz` compensation network (`design/sg13cmos5l/ldo_erramp_cmos5l.sch`)
were, at that point, explicitly flagged DC-sanity first cuts — "not sized
against any dropout ... target" and "none of them is backed by a testbench
yet" per each schematic's own header. The sweep found:

- **Dropout @ 50mA**: 1.29V–1.83V at the 11/15 corners that reached
  regulation at all; 4 corners (`tt/125°C`, `ss/27°C`, `ss/125°C`,
  `fs/125°C`) never reached regulation within the swept `Vin` range
  (2.00V–3.63V) — 4–7× over the 300mV target even at the best corner.
- **Load regulation**: failed (25%–248% deviation, target <1%) at exactly
  the same 4 severe corners.
- **Loop stability**: phase margin ≈0.19°–0.35° at *every* corner
  (target 45°) — essentially zero margin, confirmed across a `Cc`-value
  sensitivity sweep (0.5×–2× nominal) and an `Rz`-corner sensitivity sweep
  (`res_bcs`/`res_typ`/`res_wcs`). Gain margin was similarly short
  (4.0dB–5.4dB vs. a 10dB target).
- Output accuracy, quiescent current (no load), and PSRR all already
  passed with margin — this was specifically an `Mpass`-sizing and
  `Cc`/`Rz`-compensation problem, not a wholesale topology failure.

Full data: `sim/ldo-cmos5l-pvt-sweep/README.md`
(`records/20260916-083154-7aa1d3f.csv` / `.sensitivity.csv` / `.md`).

### What this record had to settle

1. Resize `Mpass` against the dropout/current-limit targets.
2. Re-derive the error amplifier's `Cc`/`Rz` compensation network (and, if
   needed, its bias currents/`gm`) to close the phase-margin gap.
3. Re-verify against the full 15-corner grid plus the existing
   sensitivity sweeps, using the existing testbenches unmodified — no new
   harness.
4. Record whatever the evidence actually shows, including any spec row
   that still cannot be met, per this repo's ratified-spec rule (CLAUDE.md:
   "no claim without a testbench" — never relax a target to pass).

## Decision

### (a) `Mpass`: `w=300u` → `w=2800u` (l=0.5u unchanged)

`sim/pass-device-screening`'s bare-device implied-width data
(`records/20260909-220347-ed18110.csv`, `w1u_l0.5u` and `w300u_l0.5u`
rows, `Ron·W`-normalized `sg13_hv_pmos` characterization) already gave a
worst-corner (`ss/125°C`) implied width of **2169µm** (normalized) /
**2351µm** (direct, non-normalized, drawn-at-300µm cross-check) for
300mV/50mA. This record starts from that data, as the issue's own scope
note directed, and adds **~20–30% headroom** on top of it — landing on
`w=2800u` — for two reasons the bare-device screen cannot capture:

- The screen's dropout bias point is a *fixed* `Vin=2.10V`/`Vout=1.80V`/
  gate-at-0V DC operating point; the closed-loop bench's dropout metric is
  a discretized 10mV `Vin` scan (`sim/ldo-cmos5l-pvt-sweep/README.md`
  "Benches"), so the reported worst-corner dropout is granular to that
  step size, not a continuous value.
- The re-derived compensation network (below) changes the amplifier's own
  bias currents and the pass gate's loading, which interacts with (but
  does not fundamentally alter) `Mpass`'s effective `Ron` at the dropout
  operating point.

`l=0.5u` is unchanged from `DR-0002`: the process spec rates HV
`VGS ≤ 3.3 V` only at `LG ≥ 0.5 µm` (`SG13CMOS5L_os_process_spec.pdf`
Rev. 0.2 Sec 2.1.5, per `DR-0002`'s ratings table), and this record does
not touch that constraint.

**Result**: dropout @ 50mA is now 0.20V–0.24V at every corner (worst
`ss/125°C`) — inside the 300mV target with margin, and every corner now
reaches regulation (the 4 corners that previously never regulated at all
are resolved as a direct consequence of the wider pass device, not a
separate fix).

### (b) Error amplifier: bias-mirror ratios and `Cc`/`Rz` re-derived

#### Why the phase-2 first cut had (essentially) zero margin

The phase-2 network sized `Rz` to the textbook `Rz ≈ 1/gm2` RHP-zero
cancellation estimate. Simulation shows the resulting loop has a very
high DC gain (≈122–124dB across corners) — driven by three cascaded gain
stages (the amplifier's first stage at `G1`, its second stage at `OUT`
feeding `Mpass`'s gate directly, and `Mpass` itself as a third common-
source gain stage into `VOUT`, loaded by the bench's 1µF `Cout`) — with
several internal poles clustered within about two decades of each other
at relatively low frequency (a direct consequence of the amplifier's
micro-power, single-digit-µA-class bias currents). A bare-Miller-cap
compensation scheme that only splits the first two stages' poles cannot,
on its own, push those poles far enough apart relative to a ≈50–140kHz
unity-gain crossover set by that much DC gain — confirmed empirically:
sweeping `Cc` alone over a 16× range (`30e-6`→`500e-6` `w`, `l` fixed, `Rz`
held at #20's original value) moved phase margin only from about −3.1° to
−0.8° at the resized `Mpass`, nowhere near the 45° target.

#### What actually closes the gap: a deliberate phase-lead zero from a much larger `Rz`

Sweeping `Rz` alone (holding `Cc` at a modest multiple of nominal) shows a
sharp, monotonic phase-margin recovery once `Rz`'s length passes roughly
8× its phase-2 value — consistent with `Rz` (in series with `Cc`, from
`OUT` back to `G1`) placing a left-half-plane phase-lead zero that moves
into the vicinity of the loop's unity-gain crossover, rather than merely
cancelling the Miller stage's own RHP zero. This is a standard, if
non-textbook-minimal, LDO compensation technique: use the nulling
resistor's zero as a deliberate phase-boost element near crossover, not
only as an RHP-zero canceller. The final sizing:

| Device | Phase 2 (#20) | This record (#25) | Change |
|---|---|---|---|
| `Mtail` | `m=2` | `m=3` | tail current 4µA→6µA (at `Iref=2µA`) |
| `Mload2` | `m=4` | `m=6` | second-stage current 8µA→12µA |
| `Cc` (`cap_cmomi`) | `w=l=30µm` (≈0.95pF) | `w=100µm, l=30µm` (≈3.2pF) | ≈3.3× wider |
| `Rz` (`rhigh`) | `w=1µm, l=5.3µm` (≈7.7kΩ) | `w=1µm, l=1200µm` (≈1.70MΩ) | ≈226× longer |

The bias-mirror increase (item 1 of the table) is a secondary lever: it
was tuned alongside `Cc`/`Rz` to keep PSRR @ 1kHz comfortably above the
50dB target (see "PSRR trade-off" below) while giving the compensation
search more headroom, not because a specific gm target was derived
analytically. All four values were converged on by directly sweeping the
existing `sim/ldo-cmos5l-pvt-sweep/testbench/tb_loopgain_cmos5l.spice.tmpl`
bench (reused unmodified, per the issue's own scope note) against
successive candidate values, not by a closed-form pole-zero solve — this
is exactly the "iterative negative-then-positive result trail"
`spec/porting-plan.md` §1.3 anticipated from gf180-ldo's own compensation
work, compressed into one PR because the fast local sweep (≈5s for the
full 51-point grid) made many iterations affordable within one session.

#### PSRR trade-off — a real regression found and re-balanced along the way, not just phase margin

One candidate explored along the way (`Mpass=2500u`, `Cc` at 10× nominal,
`Rz` retuned to reach the phase-margin target, bias mirrors left at #20's
original `m=2`/`m=4`) reached the phase-margin and gain-margin targets but
dropped PSRR @ 1kHz to 46.2dB–50.1dB, worst at the `125°C` corners —
**below** the 50dB target at those corners, a genuine regression against a
previously-passing row. Isolating the cause (holding `Mpass` and the bias
mirrors fixed, varying only `Cc`/`Rz`) confirmed the large `Rz`/`Cc` pair
itself, not the wider `Mpass`, was responsible: PSRR tracks loop gain at
1kHz, and the phase-lead zero's placement pulls gain down in that band as
a side effect of its intended action near crossover. A separate candidate
that raised the bias-mirror ratios first (`Mtail`/`Mload2` to `m=4`/`m=8`,
i.e. 2× #20's original) alongside a smaller `Cc` (3.3× nominal) and a
correspondingly larger `Rz` reached the stability targets with PSRR @ 1kHz
already comfortably above target (59.9dB worst-corner) — confirming more
bias current directly buys back the 1kHz loop gain the large `Rz`/`Cc`
pair costs. The final sizing settles on an intermediate bias increase
(`m=3`/`m=6`, 1.5× #20's original — smaller than the `m=4`/`m=8` point
that first restored PSRR) paired with a further-enlarged `Rz`
(`l=1200µm`) to reach the same stability margins at that lower bias
current, trading some `Rz` length for Iq headroom (worst-case Iq
22.98µA vs. the `m=4`/`m=8` point's ≈29µA, both under the 30µA target but
the chosen point leaves substantially more margin) while keeping
worst-corner PSRR @ 1kHz at 58.2dB. This is recorded explicitly because a
design pass that fixes phase margin while silently breaking a
previously-passing row is exactly
the failure mode CLAUDE.md's "PVT corners on every recorded result" rule
exists to catch — the acceptance criterion is *every* spec row still
passing, not just the two rows #21 flagged as failing.

## Evidence: before/after PVT re-verification

Re-run of `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh`, unmodified benches
(`tb_dcsweep_cmos5l.spice.tmpl`, `tb_loopgain_cmos5l.spice.tmpl`,
`tb_psrr_cmos5l.spice.tmpl`), against the resized schematic. 51/51
simulation points passed (ngspice exit 0, no convergence/model-load
errors); completeness matrix OK. Full record:
`sim/ldo-cmos5l-pvt-sweep/records/<record-id>.csv` /
`.sensitivity.csv` / `.md` (see `sim/ldo-cmos5l-pvt-sweep/README.md`
"Results" for the record ID this PR cites).

| Parameter | Target | Before (#21, phase-2 sizing) | After (#25, this record) | Verdict |
|---|---|---|---|---|
| Output accuracy | 1.8V ±2% | 1.80022V–1.80040V | 1.80023V–1.80064V | **PASS** (unchanged) |
| Dropout @ 50mA | <300mV worst corner | 1.29V–1.83V, 4/15 corners never regulate | 0.20V–0.24V, all corners regulate | **PASS** (was FAIL) |
| Line regulation | <5mV/V | 0.151–0.200 mV/V | 0.162–0.245 mV/V | **PASS** (unchanged, no-load-only caveat carries forward) |
| Load regulation | <1% over full load | 0.021%–248% (4/15 corners fail) | 0.0076%–0.025% | **PASS** (was FAIL) |
| Iq, no load | <30µA | 16.94µA–16.99µA | 21.87µA–22.98µA | **PASS** (unchanged, higher due to raised bias currents) |
| Iq, full load | <30µA | not separable (dropout failure) | 23.05µA–23.08µA | **PASS** (newly measurable and passing) |
| PSRR @ 1kHz | >50dB | 65.9dB–69.3dB | 58.21dB–61.85dB | **PASS** (unchanged verdict, reduced margin — see trade-off above) |
| PSRR @ 100kHz | >20dB | 35.8dB–40.6dB | 33.82dB–35.28dB | **PASS** (unchanged verdict) |
| Stability: phase margin | ≥45° worst corner | 0.19°–0.35° | 54.40°–72.72° | **PASS** (was FAIL) |
| Stability: gain margin | ≥10dB worst corner | 4.0dB–5.4dB | 17.07dB–25.87dB | **PASS** (was FAIL) |

Every row this issue was scoped to fix now passes at every corner, and
every row that already passed under #21 still passes (PSRR @ 1kHz retains
≈8dB of margin over target at its worst corner, not zero). No spec row
required relaxation to reach this result.

Cc-value (`0.5×`–`2×` nominal) and `Rz`-corner (`res_bcs`/`res_typ`/
`res_wcs`) sensitivity re-run at the new nominal, `tt/27°C`: phase margin
56.9°–76.4°, gain margin 18.6dB–23.5dB across both sweeps — the PASS
verdict holds across the full sensitivity range tested, not just at the
nominal point, mirroring the same "verdict does not depend on the
uncharacterized `Cc` caveat" reasoning #21 established for the pre-#25
FAIL verdict (`cornerCAP.lib` still maps every corner/mismatch/stat
section to the same nominal `cap_cmomi` model at this PDK's pin — see
`design/README.md` "PDK caveats honoured" — so the *exact* numbers above
remain `insufficient-evidence` pending real CMOS5L MoM-cap silicon
characterization, even though the qualitative PASS verdict does not
depend on that caveat).

## Consequences

- `design/sg13cmos5l/ldo_core_cmos5l.sch` and
  `design/sg13cmos5l/ldo_erramp_cmos5l.sch` (and their regenerated
  netlists) carry the sizing this record ratifies; both schematics' own
  headers were updated to describe the resize and cite this record.
- `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh` and
  `testbench/tb_loopgain_cmos5l.spice.tmpl` both hardcode a verbatim copy
  of `Mpass`'s top-level instantiation line (for the loop-break sync
  check) and a Cc-sensitivity base-width pattern; both were updated to
  match the new sizing as a mechanical consequence of this resize, not a
  scope expansion — `run_sweep.sh`'s own `assert_loopgain_topology_sync()`
  would otherwise FATAL on every future run.
- `design/README.md`'s SG13CMOS5L section (status callout, "Pass device",
  "Error amplifier" judgement calls, the device table, and the PDK-caveats
  table) was updated to describe the new sizing and the new PASS spec
  table, rather than leaving stale phase-2 numbers alongside a passing
  record.
- **New known gap for phase 4 (#22)**: `Mpass` (`w=2800u`, still `ng=1
  m=1`) and `Rz` (`l=1200µm` at the PDK's `rhigh` minimum width, a
  1200:1 aspect ratio) are both large, schematic-level-only draws sized
  purely against electrical targets. Neither has a floorplanned layout —
  `Mpass` needs multi-finger/multi-row layout, and `Rz` needs the PDK's
  own `rhigh` PCell meandering (`b` bends parameter, currently `0`) to fit
  a practical die footprint. This is recorded explicitly rather than left
  implicit, matching this record's own "PSRR trade-off" section's standard
  of surfacing costs rather than hiding them.
- This record does **not** resolve the MoM-cap (`Cc`) insufficient-
  evidence caveat `DR-0002` already flagged — that requires real CMOS5L
  silicon characterization, which is out of scope for any schematic-level
  phase. The qualitative stability verdict (now PASS, previously FAIL)
  does not depend on that caveat either way, exactly as `DR-0002` and #21
  already established for the opposite verdict.
- This record does **not** touch the SG13G2 branch. That branch's own
  `Mpass`/error-amp sizing (`design/ldo_core.sch`,
  `design/ldo_erramp_placeholder.sch`) remains whatever its own phase
  left it at; DR-0002's own "Does this motivate an equivalent SG13G2
  record?" reasoning applies unchanged here.

### What would overturn parts of this

- Real CMOS5L MoM-cap silicon characterization that shows `cap_cmomi`'s
  actual PVT spread differs materially from the nominal model used here
  would require re-running the phase-margin/gain-margin verification (not
  necessarily re-deriving the sizing) against real corner data.
- A phase-4 (#22) layout pass that finds `Rz`'s implied 1200:1 aspect
  ratio, or `Mpass`'s 2800µm width, cannot be floorplanned inside a
  reasonable die budget would motivate revisiting this record's specific
  values (not its general approach) — e.g., trading some `Rz` length for
  more `Cc` area (both directions were explored during this record's own
  derivation and are roughly interchangeable for a fixed target zero
  frequency, within the ranges tested), or replacing the fixed-resistor
  `Rz` with the gm-tracking triode-MOS refinement `DR-0002`/the phase-2
  header already flagged as a fallback.
- A future decision to relax the 30µA Iq budget (currently used at
  21.9–23.1µA, about 7µA of headroom) would open room for a more
  analytically "textbook" compensation (smaller `Rz`, more bias current)
  if a future phase finds the phase-lead-zero technique used here
  undesirable for some other reason (e.g., a layout-area argument against
  the large `Rz`).

## References

- Issue #25 (this record's tracking issue) and its cited dependency,
  issue #21 (the PVT verification that produced the failing evidence).
- `sim/ldo-cmos5l-pvt-sweep/README.md` — full methodology, the loop-gain
  measurement derivation, and both the before-#25 (FAIL) and after-#25
  (PASS) results tables.
- `sim/pass-device-screening/README.md` and
  `records/20260909-220347-ed18110.csv` — the bare-device implied-width
  data this record's `Mpass` resize starts from.
- `DR-0001`, `DR-0002` — the device-flavour and topology decisions this
  record's sizing implements without amending.
- `spec/porting-plan.md` §1.3 — the gf180-ldo compensation-history
  precedent this record's single-PR convergence is checked against.
