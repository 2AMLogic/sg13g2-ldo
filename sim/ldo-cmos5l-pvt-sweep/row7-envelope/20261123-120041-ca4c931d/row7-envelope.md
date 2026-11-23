# Row-7 graded `klt sim` corner-matrix envelope `20261123-120041-ca4c931d`

DR-0007 row 7, **Iq (excluding load) < 30 uA at no load and at full load** -- an Open row of the target spec. The verdict below is `klt sim`'s own: all six graded measurements carry `limits` in `request.json`, so each corner's pass/fail and the matrix verdict (`status`) are computed by the tool, not by this repo.

Measurement definition: |i(VIN)| - Iload per (Vin, Iload) operating point; the same quantity the legacy evidence base recorded as iq_a (includes the 2 uA mirror-reference leg and the divider standing current, excludes the load). Graded over the full Input-row supply window at both load states -- six `analysis_steps[]` operating points per corner (Vin 2.97 / 3.30 / 3.63 V x Iload 0 / 50 mA), the graded figures derived `expr` measurements over each step's raw supply current.

- Corners: 45/45 reported, every coordinate exactly once: True; all six steps ok at every reported corner: True.
- Envelope `status`: **error** (passed 2, failed 0, errored 43, inconclusive 0).
- Corner status counts: {'error': 43, 'pass': 2}; error-severity diagnostics: 353.
- Graded measurements (`coverage.measurements_with_limits` = 6): 6 Iq figures, all tagged `dr0007-row7-iq`; all pass: False.

- Worst no-load Iq: 24.4520 uA (`iq_i0_v3v30_a`, `fs` / 125 C / `res_bcs`); margin to the 30 uA target: 5.5480 uA.
- Worst full-load Iq: 24.6675 uA (`iq_i50m_v3v63_a`, `ff` / 125 C / `res_bcs`); margin to the 30 uA target: 5.3325 uA.
- Definitive matrix claim permitted: **False** (requires the whole 45-coordinate matrix reported, every step ok, resolved, graded and clean).

## Solver convergence setting (not an error bound)

NOT an error bound. The request pins .options reltol/abstol of the 'tight-1e-12' profile; ngspice's stopping test compares each iterate with the previous one and bounds nothing about the distance to the exact operating point. For the standard profile (reltol=1e-9 abstol=1e-15) the threshold at the largest current is ~5e-11 A (0.0002 % of the 30 uA limit). Full-load Iq is graded as a derived expr inside ngspice (klt sim analysis_steps, klayout-tools #2482), never as an offline subtraction. The observed change under tighter tolerances is a separate, measured quantity: see the paired record's row7-pair.json. The step supply currents are reported ungraded per corner in `report.json`, so every graded difference can be re-derived by hand.

## Exclusions this evidence must be read with

- ideal 0.90 V reference: no on-chip reference-generator current is included
- ideal 2 uA IBIAS sink: no on-chip bias-generator current is included (the sunk 2 uA itself flows through the core and IS included)
- evidence is for the core WITHOUT the #190 current limiter
- schematic level, corner grid only, no Monte Carlo (DR-0007 classifies the row deterministic)

The row stays Open under DR-0007; ratification is `spec/` + `ratification/` work (#318), never a `signoff/` edit. This envelope exists so a ratified row has a tagged, limited, tool-graded matrix to cite.

## Per-corner

| corner | status | iq_i0_v2v97_a (uA) | iq_i50m_v2v97_a (uA) | iq_i0_v3v30_a (uA) | iq_i50m_v3v30_a (uA) | iq_i0_v3v63_a (uA) | iq_i50m_v3v63_a (uA) |
|---|---|---|---|---|---|---|---|
| `mos_ff__res_bcs__cap_typ/novdd/-40C` | error |   | 23.1799 | 23.1169 | 23.1881 |   | 23.1953 |
| `mos_ff__res_bcs__cap_typ/novdd/125C` | error | 23.9202 | 24.6546 |   | 24.6614 |   | 24.6675 |
| `mos_ff__res_bcs__cap_typ/novdd/27C` | error | 23.6067 | 23.6993 |   | 23.7069 |   | 23.7135 |
| `mos_ff__res_typ__cap_typ/novdd/-40C` | error |   | 22.6159 |   | 22.6241 |   |   |
| `mos_ff__res_typ__cap_typ/novdd/125C` | error | 22.9161 | 23.8288 | 22.9010 | 23.8356 |   | 23.8416 |
| `mos_ff__res_typ__cap_typ/novdd/27C` | error |   | 23.0430 | 22.9559 |   |   |   |
| `mos_ff__res_wcs__cap_typ/novdd/-40C` | error |   | 22.1961 | 22.1313 | 22.2043 |   |   |
| `mos_ff__res_wcs__cap_typ/novdd/125C` | error | 22.1049 | 23.2143 |   | 23.2211 |   | 23.2271 |
| `mos_ff__res_wcs__cap_typ/novdd/27C` | error |   | 22.5546 |   | 22.5622 |   |   |
| `mos_fs__res_bcs__cap_typ/novdd/-40C` | error |   | 23.1743 |   | 23.1828 |   | 23.1901 |
| `mos_fs__res_bcs__cap_typ/novdd/125C` | error | 24.4471 | 24.6483 | 24.4520 | 24.6554 |   | 24.6616 |
| `mos_fs__res_bcs__cap_typ/novdd/27C` | error |   | 23.6934 |   | 23.7013 |   |   |
| `mos_fs__res_typ__cap_typ/novdd/-40C` | error |   | 22.6104 |   | 22.6187 |   | 22.6260 |
| `mos_fs__res_typ__cap_typ/novdd/125C` | pass | 23.5949 | 23.8225 | 23.5990 | 23.8296 | 23.6020 | 23.8357 |
| `mos_fs__res_typ__cap_typ/novdd/27C` | error |   | 23.0371 |   | 23.0450 |   | 23.0518 |
| `mos_fs__res_wcs__cap_typ/novdd/-40C` | error |   | 22.1905 | 22.1322 | 22.1990 |   | 22.2062 |
| `mos_fs__res_wcs__cap_typ/novdd/125C` | error | 22.9501 | 23.2080 |   | 23.2150 |   | 23.2212 |
| `mos_fs__res_wcs__cap_typ/novdd/27C` | error |   | 22.5487 |   | 22.5566 |   | 22.5634 |
| `mos_sf__res_bcs__cap_typ/novdd/-40C` | error | 23.1089 | 23.1780 |   | 23.1863 | 23.1244 | 23.1935 |
| `mos_sf__res_bcs__cap_typ/novdd/125C` | error |   | 24.6524 | 24.2153 | 24.6593 | 24.2121 | 24.6654 |
| `mos_sf__res_bcs__cap_typ/novdd/27C` | error | 23.6094 | 23.6972 |   | 23.7049 |   | 23.7116 |
| `mos_sf__res_typ__cap_typ/novdd/-40C` | error |   | 22.6140 |   | 22.6222 |   | 22.6294 |
| `mos_sf__res_typ__cap_typ/novdd/125C` | error | 23.2947 | 23.8266 | 23.2897 | 23.8335 |   | 23.8396 |
| `mos_sf__res_typ__cap_typ/novdd/27C` | error |   |   |   | 23.0487 |   |   |
| `mos_sf__res_wcs__cap_typ/novdd/-40C` | error |   | 22.1942 | 22.1318 | 22.2025 |   | 22.2096 |
| `mos_sf__res_wcs__cap_typ/novdd/125C` | error |   | 23.2121 |   | 23.2190 | 22.5521 | 23.2250 |
| `mos_sf__res_wcs__cap_typ/novdd/27C` | error |   | 22.5526 |   | 22.5602 |   |   |
| `mos_ss__res_bcs__cap_typ/novdd/-40C` | error |   | 23.1724 |   | 23.1810 |   |   |
| `mos_ss__res_bcs__cap_typ/novdd/125C` | error |   | 24.6462 |   | 24.6534 |   | 24.6596 |
| `mos_ss__res_bcs__cap_typ/novdd/27C` | error |   | 23.6915 |   | 23.6995 | 23.6283 |   |
| `mos_ss__res_typ__cap_typ/novdd/-40C` | error |   | 22.6084 |   | 22.6170 |   |   |
| `mos_ss__res_typ__cap_typ/novdd/125C` | error |   | 23.8205 | 23.6520 | 23.8276 | 23.6566 | 23.8338 |
| `mos_ss__res_typ__cap_typ/novdd/27C` | error |   | 23.0353 |   |   |   | 23.0501 |
| `mos_ss__res_wcs__cap_typ/novdd/-40C` | error |   | 22.1887 |   | 22.1972 |   | 22.2046 |
| `mos_ss__res_wcs__cap_typ/novdd/125C` | error |   | 23.2060 | 23.0205 | 23.2131 |   | 23.2192 |
| `mos_ss__res_wcs__cap_typ/novdd/27C` | error |   | 22.5469 |   | 22.5548 |   | 22.5617 |
| `mos_tt__res_bcs__cap_typ/novdd/-40C` | error |   | 23.1761 |   |   |   | 23.1918 |
| `mos_tt__res_bcs__cap_typ/novdd/125C` | error | 24.3709 | 24.6503 | 24.3734 | 24.6573 |   | 24.6635 |
| `mos_tt__res_bcs__cap_typ/novdd/27C` | error | 23.6113 | 23.6953 | 23.6191 | 23.7031 |   |   |
| `mos_tt__res_typ__cap_typ/novdd/-40C` | error |   | 22.6121 |   | 22.6205 |   |   |
| `mos_tt__res_typ__cap_typ/novdd/125C` | error | 23.4951 | 23.8246 |   | 23.8315 |   | 23.8376 |
| `mos_tt__res_typ__cap_typ/novdd/27C` | pass | 22.9534 | 23.0390 | 22.9612 | 23.0468 | 22.9679 | 23.0536 |
| `mos_tt__res_wcs__cap_typ/novdd/-40C` | error |   | 22.1923 | 22.1321 | 22.2007 |   | 22.2079 |
| `mos_tt__res_wcs__cap_typ/novdd/125C` | error | 22.8228 | 23.2100 |   | 23.2170 | 22.8202 | 23.2231 |
| `mos_tt__res_wcs__cap_typ/novdd/27C` | error |   | 22.5506 | 22.4714 | 22.5584 | 22.4780 | 22.5651 |

## Provenance

- batch_job_ids: `["klt-sim-909851cc56ab"]`
- git_sha: ca4c931d
- invocation: python3 sim/ldo-cmos5l-pvt-sweep/row7_envelope.py submit --profile tight-1e-12 --pair-of 20261121-001957-ed6b0587
- klt_sim_argv: klt sim request.json --backend batch --wait-for-capacity 600 -o /tmp/row7-envelope-artifacts.00z7nud7 --format json
- klt_sim_exit: 4
- measurement_definition: Iq = |i(VIN)| - Iload per (Vin, Iload) operating point; graded as klt sim derived expr measurements over analysis_steps (klayout-tools #2482), never computed by repo Python
- pair_of: 20261121-001957-ed6b0587
- pdk: ihp-sg13cmos5l
- pdk_pin: sim/pdk-cmos5l.json
- pdk_pin_projection_sha256: 751c9b6a3b1911c662127288528be290e63bb2b85c38e1e43007033bb27d2f37
- pdk_root: /home/ubuntu/share/pdk
- probe: False
- record_id: 20261123-120041-ca4c931d
- solver_convergence_setting_a: 5.003100000000001e-11
- solver_options: `{"abstol": 1e-17, "reltol": 1e-12}`
- solver_profile: tight-1e-12
- spec_row: DR-0007 row 7 (Iq excluding load < 30 uA at no load and at full load) -- Open; this envelope does not ratify it
- substitutions: `{"design_netlist_include": "../../../../design/sg13cmos5l/netlist/ldo_core_cmos5l.spice", "osdi_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/osdi", "pdk_models_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/models"}`

Input sha256:

- `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`: `08a7b857e1fad43dd7af1f575de97853a058e85541601ecc47567fbc28dbae57`
- `design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice`: `75ee39ce0c48b54cab6c8a31acd1f199c37c1ccd1ac074a3515dee81cc656fb4`
- `sim/ldo-cmos5l-pvt-sweep/testbench/tb_row7_envelope_cmos5l.spice.tmpl`: `97844d22fffc5fad6e7f2e577853eacd91481ddbd14b2af967cc63b05e4d8ba6`
- `sim/tools/render_deck.py`: `1342231eb9d396774dfb3f838ec31f58a704b3f86e047d6f0188b61c8406a833`

Machine summary: `row7-envelope.json`; the graded envelope itself: `report.json`; the request that produced it: `request.json`, `tb.spice`, `corners.lib`.
