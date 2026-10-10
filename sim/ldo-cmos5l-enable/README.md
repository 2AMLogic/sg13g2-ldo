# ldo-cmos5l-enable — enable-interface smoke checks (issue #67)

Schematic-level smoke evidence for the `EN` port added to
`design/sg13cmos5l/ldo_core_cmos5l.sch` (design record:
[`DR-0008`](../../spec/decision-records/DR-0008-sg13cmos5l-enable-interface.md)).
**One corner only** (tt MOS, typical resistor, 27 C). Not a PVT sweep. No
layout, DRC or LVS exists for the EN-bearing design (that is #68), so nothing
here is a post-layout or signoff claim. No target is ratified, relaxed or
invented by this experiment: the requests declare **no limits**.

## Entry point

```bash
PDK=ihp-sg13cmos5l source sim/env.sh            # exports PDK_ROOT
sim/ldo-cmos5l-enable/run_smoke.sh <record-dir> [request-name ...]
python3 sim/ldo-cmos5l-enable/summarize.py <record-dir>/raw/*.sim.json
python3 sim/ldo-cmos5l-enable/derive.py <record-dir>/raw
sim/ldo-cmos5l-enable/check.sh <record-dir>      # offline: regenerate derived.txt + summary.csv, fail on drift
```

`run_smoke.sh` submits each `request-<name>.json` with `klt sim --backend
batch` (one request at a time). It does **not** launch ngspice locally: this
host's ngspice 42 cannot load the PDK's OSDI v0.4 models, and the dispatch
host policy sends SPICE to the batch fleet. If a submit fails, the failure is
reported, not retried locally.

## Requests

| Request | Deck | What it measures (Vin 2.97 / 3.30 / 3.63 V unless stated) |
|---|---|---|
| `enable-reg` | `tb_enable_reg.spice` | EN tied to VIN; VOUT / EAOUT / FB / supply current / Vsg(Mpass) at 0 and 50 mA |
| `baseline-reg` | `tb_baseline_reg.spice` | same, **pre-#67 netlist** (`baseline/ldo_core_cmos5l.pre-67.spice`, sha256 `c6e630e9...f11041`) |
| `disabled-reg` | `tb_disabled_reg.spice` | EN = 0, VOUT floating: same quantities |
| `enable-rload` / `disabled-rload` | `tb_enable_rload.spice` / `tb_disabled_rload.spice` | 1.8 k load, EN tied to VIN / EN = 0, plus Vsg of the enable devices |
| `enable-leak` | `tb_disabled_leak.spice` | EN = 0 with VOUT clamped to 0 V (worst-case Vds): current into the clamp = pass leakage |
| `enable-ensweep` | `tb_enable_ensweep.spice` | EN swept 0..3.3 V at Vin = 3.30 V (1.8 k load) |
| `enable-psrr` / `baseline-psrr` | `tb_psrr_en.spice` / `tb_psrr_baseline.spice` | `vdb(vout)` at 10 Hz / 1 kHz / 100 kHz with Vin AC = 1 V (PSRR = -value) |
| `enable-loopgain` / `baseline-loopgain` | `tb_loopgain_en.spice` / `tb_loopgain_baseline.spice` | Flattened core with the single FB-to-FBAMP break; DC gain, unity-gain frequency, phase |

`enable-leak` is named for the experiment; it runs the EN-**low** deck.

## Caveats the numbers depend on

- **Cc stand-in (AC decks only).** The fleet runner image has no `cap_cmomi`
  OSDI. The AC decks substitute a linear 5.47 pF capacitor in **both** the EN
  and the baseline design, so the EN-vs-baseline delta is like-for-like but the
  absolute phase margin / unity-gain frequency are not comparable to
  `sim/ldo-cmos5l-pvt-sweep` records. DC decks use a 1 pF stand-in (an open
  circuit at DC). Gain margin was not extracted.
- **Loop gain from `.meas` of `fb` only.** With `Vbreak` AC 1, `v(fbamp) =
  v(fb) - 1`, so `L = -v(fb)/v(fbamp) = fb/(1-fb)` and `|L| = 1` exactly when
  `Re(fb) = 0.5`; `derive.py` reconstructs gain and phase from `vr(fb)`/`vi(fb)`.
- **Sweep, not point solves.** DC points are read out of a continuous
  `dc Vin 2.00 3.64 0.01` sweep started at the supply floor, the same
  continuation the pvt-sweep bench relies on; cold-start point solves of this
  circuit did not converge on the fleet's ngspice 46 (both designs).
- **Runner mismatch.** The fleet runner's klt (0.5.0) differs from the
  submitting client's; reports record `runner_compatibility: mismatch`, as the
  Monte Carlo record does. OSDI: the runner's baked `/opt/pdk/ihp-sg13g2`
  binaries (`runner-preamble.cir`, shared with `sim/ldo-cmos5l-monte-carlo/`).
- The EN-sweep transition region is DC-solver-dependent (see DR-0008) and is
  not a characterized threshold.

## Records

`records/<id>/` holds the raw `klt sim` JSON reports (`raw/`), per-corner
ngspice logs (`artifacts/`), `summary.csv` (every measurement) and
`derived.txt` (deltas against the baseline). Append-only: a new run gets a new
id; existing records are never edited. CI (`enable-record`) runs `check.sh` on every
`records/*/`; the `artifacts/` ngspice logs are raw run output, not derived, so
they have nothing to regenerate.

Record `20261010-023648-4d45f5d`: design under test
`design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` sha256
`7953b25be4cb00053f8df5f283bee0500f60a826b7a2d6519b88a8578d222cc1`
(`ldo_erramp_cmos5l.spice` unchanged, `7982d728...c8e38c`); schematic
`ldo_core_cmos5l.sch` `e5c02aff5fad9f0c...`; symbol `18e1af5b40ae113b...`.
Every raw report pins its deck, `runner-preamble.cir` and the core netlist by
sha256 in `environment.netlist_closure`.
