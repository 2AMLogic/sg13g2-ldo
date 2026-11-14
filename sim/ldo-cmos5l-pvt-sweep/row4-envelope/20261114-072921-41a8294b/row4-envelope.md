# Row-4 graded `klt sim` corner-matrix envelope `20261114-072921-41a8294b`

DR-0007 row 4, **Dropout @ 50 mA < 300 mV worst corner** -- the one ratified
row of the target spec. The verdict below is `klt sim`'s own: both graded
measurements carry `limits` in `request.json`, so each corner's pass/fail and
the matrix verdict (`status`) are computed by the tool, not by this repo.

Measurement definition: the LEGACY row-4 quantity DR-0007 ratified --
the lowest Vin whose VOUT is still within 1 % of the fixed
1.800 V target, minus that target. DR-0012's own-regulated-output
reference is PROPOSED and is not expressible as a `klt sim` request (a `.meas`
`WHEN` threshold must be a literal); see `signoff/README.md`.

- Corners: 45/45 reported, every coordinate exactly once: True.
- Envelope `status`: **pass** (passed 45, failed 0, errored 0, inconclusive 0).
- Corner status counts: {'pass': 45}; error-severity diagnostics: 0.
- Graded measurements (`coverage.measurements_with_limits` = 2): vout_at_dropout_limit_v, vin_1pct_loss_v; all pass: True.
- Definitive worst-corner claim permitted: **True** (requires the whole 45-coordinate matrix reported, resolved, graded and clean).

- Worst corner: `ss` / 125 C / `res_bcs` (`mos_ss__res_bcs__cap_typ/novdd/125C`): dropout 237.06 mV (`vin_1pct_loss_v` 2.03706 V - 1.800 V), VOUT at the 2.100 V limit 1.79982 V.
- Margin to the 300 mV target: 62.94 mV = 62.94 mV / 50 mA = 1.259 ohm series resistance, before any parasitic extraction.
- Conservative read: the Vin axis is 5 mV, so the worst dropout's grid upper bound is 242.06 mV, still under 300 mV.

## Per-corner

| corner | status | dropout (mV) | `vin_1pct_loss_v` (V) | `vout_at_dropout_limit_v` (V) | `vout_nominal_v` (V) |
|---|---|---|---|---|---|
| `mos_ff__res_bcs__cap_typ/novdd/-40C` | pass | 123.97 | 1.92397 | 1.79991 | 1.80014 |
| `mos_ff__res_bcs__cap_typ/novdd/125C` | pass | 178.40 | 1.9784 | 1.79993 | 1.80023 |
| `mos_ff__res_bcs__cap_typ/novdd/27C` | pass | 145.32 | 1.94532 | 1.79992 | 1.80017 |
| `mos_ff__res_typ__cap_typ/novdd/-40C` | pass | 123.97 | 1.92397 | 1.79991 | 1.80014 |
| `mos_ff__res_typ__cap_typ/novdd/125C` | pass | 178.40 | 1.9784 | 1.79993 | 1.80023 |
| `mos_ff__res_typ__cap_typ/novdd/27C` | pass | 145.32 | 1.94532 | 1.79992 | 1.80017 |
| `mos_ff__res_wcs__cap_typ/novdd/-40C` | pass | 123.96 | 1.92396 | 1.79991 | 1.80014 |
| `mos_ff__res_wcs__cap_typ/novdd/125C` | pass | 178.40 | 1.9784 | 1.79993 | 1.80023 |
| `mos_ff__res_wcs__cap_typ/novdd/27C` | pass | 145.32 | 1.94532 | 1.79992 | 1.80017 |
| `mos_fs__res_bcs__cap_typ/novdd/-40C` | pass | 157.01 | 1.95701 | 1.79987 | 1.80012 |
| `mos_fs__res_bcs__cap_typ/novdd/125C` | pass | 219.51 | 2.01951 | 1.79987 | 1.8002 |
| `mos_fs__res_bcs__cap_typ/novdd/27C` | pass | 181.70 | 1.9817 | 1.79987 | 1.80015 |
| `mos_fs__res_typ__cap_typ/novdd/-40C` | pass | 157.01 | 1.95701 | 1.79987 | 1.80012 |
| `mos_fs__res_typ__cap_typ/novdd/125C` | pass | 219.50 | 2.0195 | 1.79987 | 1.8002 |
| `mos_fs__res_typ__cap_typ/novdd/27C` | pass | 181.70 | 1.9817 | 1.79987 | 1.80015 |
| `mos_fs__res_wcs__cap_typ/novdd/-40C` | pass | 157.01 | 1.95701 | 1.79987 | 1.80012 |
| `mos_fs__res_wcs__cap_typ/novdd/125C` | pass | 219.50 | 2.0195 | 1.79987 | 1.8002 |
| `mos_fs__res_wcs__cap_typ/novdd/27C` | pass | 181.69 | 1.98169 | 1.79987 | 1.80015 |
| `mos_sf__res_bcs__cap_typ/novdd/-40C` | pass | 133.78 | 1.93378 | 1.79989 | 1.80012 |
| `mos_sf__res_bcs__cap_typ/novdd/125C` | pass | 190.66 | 1.99066 | 1.79991 | 1.8002 |
| `mos_sf__res_bcs__cap_typ/novdd/27C` | pass | 156.15 | 1.95615 | 1.7999 | 1.80014 |
| `mos_sf__res_typ__cap_typ/novdd/-40C` | pass | 133.78 | 1.93378 | 1.79989 | 1.80012 |
| `mos_sf__res_typ__cap_typ/novdd/125C` | pass | 190.66 | 1.99066 | 1.79991 | 1.8002 |
| `mos_sf__res_typ__cap_typ/novdd/27C` | pass | 156.15 | 1.95615 | 1.7999 | 1.80014 |
| `mos_sf__res_wcs__cap_typ/novdd/-40C` | pass | 133.78 | 1.93378 | 1.79989 | 1.80012 |
| `mos_sf__res_wcs__cap_typ/novdd/125C` | pass | 190.65 | 1.99065 | 1.79991 | 1.8002 |
| `mos_sf__res_wcs__cap_typ/novdd/27C` | pass | 156.15 | 1.95615 | 1.7999 | 1.80014 |
| `mos_ss__res_bcs__cap_typ/novdd/-40C` | pass | 170.84 | 1.97084 | 1.79984 | 1.80009 |
| `mos_ss__res_bcs__cap_typ/novdd/125C` | pass | 237.06 | 2.03706 | 1.79982 | 1.80017 |
| `mos_ss__res_bcs__cap_typ/novdd/27C` | pass | 197.00 | 1.997 | 1.79985 | 1.80012 |
| `mos_ss__res_typ__cap_typ/novdd/-40C` | pass | 170.84 | 1.97084 | 1.79984 | 1.80009 |
| `mos_ss__res_typ__cap_typ/novdd/125C` | pass | 237.06 | 2.03706 | 1.79982 | 1.80017 |
| `mos_ss__res_typ__cap_typ/novdd/27C` | pass | 197.00 | 1.997 | 1.79985 | 1.80012 |
| `mos_ss__res_wcs__cap_typ/novdd/-40C` | pass | 170.83 | 1.97083 | 1.79984 | 1.80009 |
| `mos_ss__res_wcs__cap_typ/novdd/125C` | pass | 237.05 | 2.03705 | 1.79982 | 1.80017 |
| `mos_ss__res_wcs__cap_typ/novdd/27C` | pass | 197.00 | 1.997 | 1.79985 | 1.80012 |
| `mos_tt__res_bcs__cap_typ/novdd/-40C` | pass | 145.00 | 1.945 | 1.79988 | 1.80012 |
| `mos_tt__res_bcs__cap_typ/novdd/125C` | pass | 204.56 | 2.00456 | 1.79989 | 1.8002 |
| `mos_tt__res_bcs__cap_typ/novdd/27C` | pass | 168.48 | 1.96848 | 1.79989 | 1.80014 |
| `mos_tt__res_typ__cap_typ/novdd/-40C` | pass | 144.99 | 1.94499 | 1.79988 | 1.80012 |
| `mos_tt__res_typ__cap_typ/novdd/125C` | pass | 204.56 | 2.00456 | 1.79989 | 1.8002 |
| `mos_tt__res_typ__cap_typ/novdd/27C` | pass | 168.48 | 1.96848 | 1.79989 | 1.80014 |
| `mos_tt__res_wcs__cap_typ/novdd/-40C` | pass | 144.99 | 1.94499 | 1.79988 | 1.80012 |
| `mos_tt__res_wcs__cap_typ/novdd/125C` | pass | 204.56 | 2.00456 | 1.79989 | 1.8002 |
| `mos_tt__res_wcs__cap_typ/novdd/27C` | pass | 168.48 | 1.96848 | 1.79989 | 1.80014 |

## Provenance

- batch_job_ids: `["klt-sim-4d08baab81eb"]`
- git_sha: 41a8294b
- invocation: python3 sim/ldo-cmos5l-pvt-sweep/row4_envelope.py submit
- klt_sim_argv: klt sim request.json --backend batch --wait-for-capacity 600 -o /tmp/row4-envelope-artifacts.mq2489yk --format json
- klt_sim_exit: 0
- measurement_definition: legacy dropout_v_50ma (1 % loss vs the fixed 1.800 V target); DR-0012's own-V_reg reference is PROPOSED and not expressible as a klt sim request
- pdk: ihp-sg13cmos5l
- pdk_pin: sim/pdk-cmos5l.json
- pdk_root: /home/ubuntu/share/pdk
- probe: False
- ratified_row: DR-0007 row 4 (Dropout @ 50 mA < 300 mV worst corner)
- record_id: 20261114-072921-41a8294b
- substitutions: `{"design_netlist_include": "../../../../design/sg13cmos5l/netlist/ldo_core_cmos5l.spice", "osdi_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/osdi", "pdk_models_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/models"}`

Input sha256:

- `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`: `08a7b857e1fad43dd7af1f575de97853a058e85541601ecc47567fbc28dbae57`
- `design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice`: `75ee39ce0c48b54cab6c8a31acd1f199c37c1ccd1ac074a3515dee81cc656fb4`
- `sim/ldo-cmos5l-pvt-sweep/testbench/tb_row4_envelope_cmos5l.spice.tmpl`: `e354514b13c448553d85f813637a5f27ca1136f5a5c27846723ab3dac0740cad`
- `sim/pdk-cmos5l.json`: `1d72f2f677078a136b209561f446f5c809277db3cd62dbc990f1f5d277cb3db4`

Machine summary: `row4-envelope.json`; the graded envelope itself: `report.json`; the request that produced it: `request.json`, `tb.spice`, `corners.lib`.
