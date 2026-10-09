# ldo-cmos5l-monte-carlo

Per `CLAUDE.md`: **verification is the product, no claim without a
testbench**, PVT corners on every recorded result, and results here are
**append-only evidence**. A re-run mints a new record id. Nothing under
`records/`, `corners/` or `netlist-snapshots/` is ever edited after it lands
(`sim/README.md`).

## What this is, and what it is not

The bounded **row-2 (output accuracy) Monte Carlo campaign** for the
SG13CMOS5L branch (issue #56, part of the T1 gap tracker #5). It measures how
device mismatch spreads the regulated output of the committed
`design/sg13cmos5l/` regulator (`ldo_core_cmos5l` + `ldo_erramp_cmos5l`,
instantiated whole and **unchanged**) and grades the spread with `klt yield`
against the **proposed** row-2 window, 1.8 V ±2 % = **1.764–1.836 V**.

- **Row 2 is Open, not ratified.** DR-0007 classifies it as statistical and
  assigns this campaign to #56 *before* ratification. The results here are
  evidence **against an Open target**. They do not ratify it. Ratifying,
  clarifying or revising row 2 (including its scope wording below) goes
  through the installed two-key review (`ratification/`) and a decision
  record, never through this directory.
- **Row 8 (current-limit window) stays deferred.** It is statistical by
  construction, but no limiter exists yet (#63), so there is nothing to
  sample. It is **not** "no statistical row".
- **This campaign does not discharge T1 item 6.** Item 6 covers every
  statistical row. Row 8 is unevidenced and row 2's target is unratified.
  `signoff/README.md` explains why item 6 is left uncited.
- **Complementary, not overlapping:** #55 owns the deterministic corner
  evidence (T1 item 5). #62 owns startup.

## Measurement definition (row 2, as measured here)

Row 2 reads "Output 1.8 V ±2 % (fixed)". DR-0007 notes the table does not
say what the ±2 % includes. This campaign measures one stated quantity and
does **not** decide the row's wording:

| Condition | Value | Why |
|---|---|---|
| Quantity | `VOUT` at the DC operating point | DC accuracy. No dynamic quantity is measured. |
| `Vin` | 3.30 V | Nominal of the Input row (3.3 V ±10 %). The DC sweep 3.29–3.31 V exists only so `.meas FIND ... AT=3.30` can interpolate. |
| Load | none (0 A) | The committed corner record's `vout_no_load_v` condition (`sim/ldo-cmos5l-pvt-sweep/run_sweep.sh`). The 0–50 mA load span belongs to row 5 (load regulation, 0.0076–0.025 % in that record, i.e. under 0.5 mV). |
| `IBIAS` | 2 µA, sunk externally | The design's documented bias point. |
| `VREF` | **ideal 0.900 V source** | **Reference error is excluded.** This is *regulator-only* accuracy: error-amplifier offset, bias/mirror mismatch and divider-ratio mismatch. A real reference's own spread must be added (root-sum-square for independent sources) before this number can be read against a system-level ±2 % budget. |
| `Cout`, `Cc` | not in the DC solution | `Cc` (`cap_cmomi`) is replaced by a DC-only 1 pF stand-in (`tb_row2_accuracy.spice`): its OSDI model is not in the fleet image and it has no mismatch model. A capacitor is open at DC, so this cannot move `VOUT`. |
| Limits | 1.764 ≤ `VOUT` ≤ 1.836 V, both inclusive | `klt yield`'s default `>=`/`<=` semantics, pinned by `test_build_yield_inputs.py`. |

## Variation coverage

**Model and switches.** Every campaign corner selects the PDK's own
`*_mismatch` sections (`row2-corners.lib`). The PDK files are selected, not
edited:

| Family | Instances | PDK mechanism (pinned bytes: the record's `environment.staged_model_inputs`) | Distribution |
|---|---|---|---|
| HV MOS (`sg13_hv_pmos`/`_nmos`, PSP103) | error-amp input pair `XMinp`/`XMinn`, NMOS mirror `XMn1`/`XMn2`, second stage `XMn3`, bias mirror `XMb0`/`XMtail`/`XMload2`, pass device `XMpass` | `sg13g2_moshv_mismatch.lib` + `sg13g2_moshv_mod_mismatch.lib`: `delvto = agauss(0, A/sqrt(m·W·L))` (A = 7 mV·µm nmos, 4.5 mV·µm pmos), `factuo = agauss(1, A_u/sqrt(m·W·L))` (0.5 % / 0.4 %·µm), `w`, `l = agauss(nominal, 3 nm)` | Gaussian, 1σ = the stated value, **independent per instance** (a `m>1` instance is one draw scaled by `1/sqrt(m)`) |
| `rhigh` (r3_cmc) | divider `XRtop`/`XRbot`, nulling resistor `XRz` | `resistors_mod_mismatch.lib` → r3_cmc `sw_mman=1`: `nsmm_rsh`, `nsmm_w`, `nsmm_l = gauss(1, 1, 1)` standard deviations of `smm_rsh = 5 %·µm`, `smm_w = smm_l = 0.01 µm^1.5` | Gaussian, independent per instance. Note the PDK draws these with **mean 1, not 0**: every instance sits +1σ on average. Equal-geometry divider legs cancel that common shift in the ratio. It is a PDK observation, not something this bench corrects. |
| `cap_cmomi` (`XCc`) | Miller cap | none at this PDK pin (`cornerCAP.lib` maps every section to the nominal model) | **not sampled**; open at DC, so it has no effect on this measurement |

**Correlations.** Within a draw, every instance's parameters are independent
draws (the PDK's local-mismatch model has no correlation terms). Global
process variation is **not** sampled statistically. The PDK's `*_stat`
sections cannot be combined with `*_mismatch` in one section. Process spread
is instead covered by **running the mismatch Monte Carlo at five named
corners**:

| Population | MOS section | Resistor section | Temp | Why this point |
|---|---|---|---|---|
| `tt` | `mos_tt_mismatch` | `res_typ_mismatch` | 27 °C | nominal |
| `ss_rbcs` | `mos_ss_mismatch` | `res_bcs_mismatch` | −40 °C | lowest `vout_no_load_v` of the 45-point corner record (1.80023 V) |
| `ff_rwcs` | `mos_ff_mismatch` | `res_wcs_mismatch` | 125 °C | highest `vout_no_load_v` (1.80066 V) |
| `sf_rwcs` | `mos_sf_mismatch` | `res_wcs_mismatch` | 125 °C | n/p skew, the skew's hottest/highest point (1.80051 V) |
| `fs_rbcs` | `mos_fs_mismatch` | `res_bcs_mismatch` | −40 °C | opposite skew, coldest point (1.80026 V) |

Corner selection uses the committed corner record
`sim/ldo-cmos5l-pvt-sweep/records/20260917-023832-7061e8f.csv`. Its whole
45-point corner spread of the mean is 0.43 mV, about 1/80 of the window
half-width. Each population is graded on its own; draws are **never pooled
across corners**, and corner counts are never multiplied into a sample count.
`klt yield` would pool a multi-corner report into one population, so
`build_yield_inputs.py` splits it first (mechanically: no value is edited,
dropped or reordered).

**Attribution (sampler control).** `request-row2-attribution.json` runs
tt/27 °C three ways: no mismatch at all (`tt_nom`), MOS mismatch only
(`tt_mosmm`) and `rhigh` mismatch only (`tt_resmm`). The no-mismatch
population must show **zero spread** and reproduce the committed corner value
(1.80030601 V). That is the sampler's own negative control: the per-draw seed
changes, and nothing else may. The two partial sigmas are compared with the
full-mismatch sigma. This tests DR-0007's hypothesis that `Mpass` is
accuracy-irrelevant **by including it**, not by omitting it: `Mpass`'s own
mismatch is sampled in every MOS population.

**Not covered, disclosed:** global/process statistical sampling (corners
stand in, see above); supply (`Vin`) and load variation (rows 1/5, #55);
reference error (excluded by definition above); `cap_cmomi` (no model);
layout-dependent effects and post-layout parasitics (T1 item 7). The
`klt sim` `family_mismatch` report reads `active: null` for every family,
because the request names no `models.pdk` (it stages its own model library).
Mismatch activity is therefore established by the attribution populations'
measured spread, not by that field.

## Seeds, sample size, convergence

- **Seeds.** `klt sim`'s seed contract: `monte_carlo.seed` (56001 for the
  main, negative-control and reproduction requests; 56002 for attribution)
  derives a per-draw `.options seed=<n>` from a SHA-256 of (base seed, corner
  index, sample index). Every draw's seeds are in the raw report and in the
  record CSV. The negative control and the reproduction request put `tt` at
  corner index 0, so draw *i* there has **the same seed** as `tt` draw *i*
  in the main request.
- **Sample size: N = 400 per population** (2000 for the five corners). The
  planning yield is `target_yield = 0.99`. It is a sample-size design input,
  **not a ratified spec value**, because the spec states no yield target and
  choosing one is part of ratifying row 2. With zero failures, the
  Clopper-Pearson lower bound is `(0.025)^(1/N)`: N ≥ 368 is needed to show
  ≥ 99 % at 95 % confidence, and N ≥ 183 to resolve the yield to ±1 point.
  N = 400 clears both with margin and keeps the fleet cost bounded. It cannot
  resolve a ppm-level tail; Cpk / sigma-to-spec (a normal-fit extrapolation,
  with its Anderson-Darling verdict) is the statistic that speaks to the tail.
- **Failures and convergence.** A draw with no finite value is kept as `null`
  and counted as `errored` by `klt yield` (excluded from the conditional
  yield, with the whole-draw figure stated in a warning). The split refuses
  to write if any draw is unaccounted for. `--null-policy
  failed_unmeasurable` counts such draws as design failures instead. A draw
  `klt sim` grades `inconclusive` is counted as such. The runner's klt 0.5.0
  does not grade a solve that needed gmin stepping (`options.fail_on_diagnostic`
  is newer), so recovered solves are disclosed from the retained logs in the
  record rather than graded.

## Negative control (deterministic)

`request-row2-negctl.json` re-runs the `tt` population with **one change**:
`VREF` 0.90 → 0.93 V through `klt sim`'s `supply_v` axis (`alter vref=0.93`),
which servos `VOUT` up by about 60 mV, beyond the 36 mV half-window. It is
attached to the `tt` population as `klt yield`'s `negative_control` (its
verdict must be `detected`). It is also graded on its own, and that verdict
must be `fail`. Because the seeds are shared, the per-draw shift
(negative control minus nominal at the same seed) is reported too. Its
spread must be far below the population spread: the same draws were
reproduced, only shifted. `klt sim` cannot carry a negative control on its
own report (klayout-tools#2563), which is the second reason for the split
helper.

## Reproduction

`request-row2-repro.json` is an independent fleet job of the `tt` population
(same seed, N = 50). `crosscheck.py` requires identical seeds and values
within 1 µV for every one of the 50 draws. The probe request
(`request-row2-probe.json`, MC off, VREF 0.90/0.93 V) checks the bench, the
staging and the VREF axis against the committed corner value before anything
is sampled.

```bash
export PDK_ROOT=/path/to/pdk-parent     # holds ihp-sg13cmos5l/ (pinned, sim/pdk-cmos5l.json) and ihp-sg13g2/
sim/ldo-cmos5l-monte-carlo/run_campaign.sh submit  sim/ldo-cmos5l-monte-carlo/records/<record-id>
KLT_YIELD=/path/to/klt-with-native \
sim/ldo-cmos5l-monte-carlo/run_campaign.sh analyse sim/ldo-cmos5l-monte-carlo/records/<record-id>
python3 -m unittest sim/ldo-cmos5l-monte-carlo/test_build_yield_inputs.py \
                    sim/ldo-cmos5l-monte-carlo/test_crosscheck.py
```

`analyse` alone re-derives every committed yield report, `crosscheck.json`
and the record CSV from the committed raw reports. It is offline, with no PDK
and no simulator.

## Toolchain (and its friction)

- **Simulation** runs only on the 2AM batch fleet (`klt sim --backend batch`;
  the dispatch host never runs the grid). The fleet image pins **klt 0.5.0**,
  ngspice 46 and ihp-sg13g2 0.3.0 at `/opt/pdk` (2am `batch-image-pins.env`).
  The submitting client was klt `0.7.0+g4cbdfa769875`, so the requests set
  `batch.runner_version_check: "warn"`, and every report records
  `runner_compatibility: mismatch`. Only request fields that klt 0.5.0
  implements are used (`corners`, `exclude`, `supply_v`, `monte_carlo`,
  `.meas`). Model staging is done client-side. This version skew is tracked
  upstream (klayout-tools#2901, #2877, #2894, #2851; 2am#2193).
- **OSDI.** klt 0.5.0 has no `options.osdi_preload`, so `runner-preamble.cir`
  loads the image's own PSP103/r3_cmc binaries with `pre_osdi` and prints
  their sha256 into every retained log. They are compiled from the same
  ihp-sg13g2 Verilog-A sources the SG13CMOS5L tree symlinks to.
  `cornerMOShv.lib`/`cornerRES.lib` are likewise byte-identical across the
  two PDK trees (`sim/pdk-cmos5l.json`).
- **`klt yield`** needs the `klt_yield_native` extension, and
  `klayout-tools[yield]` does not resolve from PyPI (klayout-tools#2900). The
  committed yield reports were produced by klt `0.7.0+g4cbdfa769875` with the
  extension built from that same source tree into a scratch virtualenv
  (`maturin develop --release` in `native/yield/`). No host-wide tool was
  installed or changed.
- **Upstream issues filed from this campaign:** klayout-tools#2908 (item 6
  has no notion of the statistical-row set or of partial/unratified coverage)
  and klayout-tools#2909 (a bit-identical sample set is reported as
  non-degenerate). The second is visible in this campaign's `tt_nom`
  attribution report.

## Records

- [`records/20261009-003009-3ee8306.md`](records/20261009-003009-3ee8306.md):
  the first campaign (issue #56).
