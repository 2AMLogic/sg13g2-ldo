# pass-device-screening-hbt

Screens SG13G2's heterojunction bipolar devices (`npn13G2`, `npn13G2l`,
`npn13G2v`, `pnpMPA`) as a candidate **pass element**, beside the MOS screen in
[`../pass-device-screening/`](../pass-device-screening/README.md). Issue #139.

`spec/decision-records/DR-0001-pass-device-flavor.md` ("Bipolar pass device —
considered, not adopted") ruled the HBTs out *without a measurement* and said
revisiting that "requires its own screening deck and decision record". This
directory is that deck. It adds evidence only: it changes neither the ratified
spec nor the MOS design. The decision lives in
[`DR-0001a`](../../spec/decision-records/DR-0001a-hbt-pass-device-screening.md).

## Cold start

```bash
export PDK_ROOT=/path/to/ihp-open-pdk    # parent dir containing ihp-sg13g2/
export PDK=ihp-sg13g2
sim/pass-device-screening-hbt/run_sweep.sh --check-env             # CI mode: 1 corner per request, local, no record
sim/pass-device-screening-hbt/run_sweep.sh submit  <record-dir>    # full matrix on the batch fleet -> <record-dir>/raw/
sim/pass-device-screening-hbt/run_sweep.sh analyse <record-dir>    # derive <record-dir>.csv / .md from the raw reports
sim/pass-device-screening-hbt/run_sweep.sh check   <record-dir>    # offline byte-for-byte reproduction (CI)
python3 sim/pass-device-screening-hbt/gen_decks.py --check          # generated decks match the generator
```

The entry point is `run_sweep.sh`, like the MOS deck. Differences that follow
from the devices: the bipolar models are **native ngspice** (VBIC level 9 for
the `npn13G2*` family, Gummel-Poon level 1 for `pnpMPA`), so there is **no OSDI
build** (`sim/tools/build-osdi.sh` is not needed); and the grid is a set of
`klt sim` requests (`decks/request-*.json`) rather than a shell loop over
`ngspice`, so the 72-unit matrix runs as `klt sim --backend batch` jobs on the
Spot fleet and never on the submitting host. A failed batch submit is reported,
not retried locally.

## What is screened

Load points are the ratified dropout row's: **50 mA** (DR-0007 row 4) and the
**100 mA** stretch load. Fixed absolute collector-emitter voltages, as in the
MOS deck (`Vin` is not an independent axis; `spec/porting-plan.md` §1.4):

| `Vce` | meaning |
|---|---|
| 0.30 V | the dropout differential, `Vin` 2.10 V − `Vout` 1.80 V |
| 1.00 V | an active-region reference point (used for the Early extrapolation) |
| 1.50 V | nominal headroom, `Vin` 3.30 V − `Vout` 1.80 V |
| 1.83 V | `Vin_max` headroom, 3.63 V − 1.80 V |

Two benches per device (`gen_decks.py` writes both):

- **`servo`** — one DC point per group. A high-gain servo sets the base current
  `Ib = clamp(20·(T − Ic), 0, Ibmax)` so that the collector current equals a
  target `T` at the fixed ideal `Vce`; `.meas` reads `Ib`, the achieved `Ic` and
  the base-emitter voltage. Groups: both load points × the four `Vce`, plus a
  single-cell ladder (`T` = 100 µA, 1 mA, 10 mA, 25 mA at `Vce` = 1.0 V). From
  these: beta vs `Ic`, quasi-saturation (beta at 0.30 V vs the active region),
  Early voltage (the beta ratio at 1.5 V vs 1.0 V, same `Ic`), `Vbe`, and the
  base current as a multiple of the Iq budget. A group whose clamp cannot
  deliver `T` is **unreached**: the achieved fraction `Ic/T` is the result.
- **`vcesweep`** — a `Vce` sweep (0.02–1.8 V) at a fixed `Ib = Ic/beta_f` for
  `beta_f` ∈ {1, 10, 20, 50}; `.meas WHEN` reports the smallest `Vce` at which
  `Ic` reaches the target: the `Vce(sat)` / dropout the device needs at that
  forced beta.

Corner grid: the PDK's own HBT corners `hbt_bcs` / `hbt_typ` / `hbt_wcs`
(`cornerHBT.lib`; the PDK ships three, not the MOS deck's five) × {−40, 27,
125} °C = 9 corners; 4 devices × 2 benches × 9 corners = 72 `klt sim` units.
`decks/hbt-corners.lib` is the single `models.lib` klt takes, selecting one
PDK section per corner; the PDK file is not edited.

## Topology reading (why these `Vce` and what "dropout" means for a bipolar)

- **NPN (`npn13G2*`)** — a high-side NPN pass device is an emitter follower
  (collector on `Vin`, emitter on `Vout`). With the base drive limited to
  `Vin`, regulation needs `Vin − Vout ≥ Vbe`; reaching the 0.30 V dropout
  differential needs a base drive `Vbe − 0.30 V` above `Vin` (a boosted supply
  or charge pump). The record tabulates this from the measured `Vbe`.
- **PNP (`pnpMPA`)** — the common-emitter high-side PNP is the topology the MOS
  design copies. The model's collector is the substrate (`isc`/`ikr`/`ccb` scale
  with the substrate area `sub_a`), and the PDK describes the device as the
  bandgap PNP (`libs.tech/xschem/README.md`). The deck simulates the model as
  written, collector on the load node, as a *what-if*: a layout in which the
  load current returns through the substrate is not a regulator output. The
  model also has `bf ≈ 1.1`, so the numbers are a screen of the model, not a
  proposal for a layout.
- **Device sizing is a screening choice, not a layout proposal.** `npn13G2*`:
  `Nx = 10` (the model's largest valid emitter count), `m` = 2 cells at 50 mA
  and 4 at 100 mA, so each cell carries ≤ 25 mA, inside the model's stated
  validity (`ic < 0.003·Nx` A per the lib header = 30 mA per `Nx = 10` cell).
  `pnpMPA`: 10 µm × 10 µm cell (`a = 100p`, `p = 40u`), same `m`.

## Model-validity and rating notes (read before quoting a number)

- **`vce_max`.** The `.model` cards in `sg13g2_hbt_mod.lib` state
  `vce_max = 1.6` V for `npn13G2` / `npn13G2l` and `2.2` V for `npn13G2v`
  (`vbc_max` 5.1 / 7.0 V); `pnpMPA_mod` states none. Regulating at `Vin_max`
  puts 1.83 V across the pass device and a continuous short puts 3.63 V, so the
  record tabulates the overshoot against those cards. The simulator does not
  enforce them: a number at 1.83 V is an extrapolation past the model's
  stated range, flagged as such.
- **Model validity.** The lib header gives the VBIC model's valid range as
  `ic < 0.003·Nx` A, `Vbe` 0.65–0.96 V, `Vce` 0.4–2.0 V, −40..125 °C. The
  0.30 V group is **outside** the stated `Vce` range; it is reported because it
  is the ratified dropout point, with that caveat.
- **Self-heating.** The PDK subckt defaults to `selft=1`. With an ideal
  current-driven base the DC solve thermally runs away (NaN in the
  temperature-limiting function) before reaching the collector targets, so the
  decks set `selft=0`: **isothermal**, ambient = the corner temperature. At
  50–100 mA × 1.5 V the real junction would be hotter than modelled; this is
  not shown here and is the first thing a follow-up on the NPN would need.
- **Not run:** mismatch / Monte Carlo (`_stat`, `_mismatch` sections are not
  used), AC, transient, noise, any closed-loop circuit around a bipolar pass
  device, layout, DRC/LVS. This is a device screen like the MOS deck, not a
  circuit.

## Why a servo and not a base-current sweep

A log-spaced base-current sweep at a fixed `Vce` was tried first and
abandoned. With an ideal fixed-`Vce` collector, `Ic` runs to amperes as the
sweep overshoots the target and the solve fails (singular VBIC emitter node,
gmin/source stepping exhausted) at the cold/slow corner, losing every
measurement of that unit. A collector load resistor that caps `Ic` fixed the
current but not the deep-saturation failures. The DC servo keeps every group
at exactly the intended `Vce` and `Ic`, needs one solve, and converged in
every corner probed.

## Records

`records/<UTC>-<sha>/raw/<device>-<bench>.sim.json` are the `klt sim --backend
batch` reports, committed verbatim (they pin the netlist closure and the staged
PDK model files by sha256 and carry the fleet job id). `records/<id>.csv` and
`records/<id>.md` are derived from them by `record.py`; `record.py check`
(CI's `characterization-report`-style offline job, no PDK, no simulator)
regenerates both and fails on any byte of drift or any failed sanity line.
Records are **append-only** (`sim/tools/check_append_only.py`): a correction
mints a new record ID. The record asserts no spec threshold; the
interpretation is the DR-0001 addendum.

## Toolchain note

The fleet runner image pins klt 0.5.0 while the submitting client is newer, so
every raw report records `runner_compatibility: mismatch`
(`runner_version_check: warn`), as the other batch records in this repo do.
Nothing in these requests uses a feature newer than 0.5.0 knows about beyond
`options.stage_model_inputs`, which the existing records already rely on.
