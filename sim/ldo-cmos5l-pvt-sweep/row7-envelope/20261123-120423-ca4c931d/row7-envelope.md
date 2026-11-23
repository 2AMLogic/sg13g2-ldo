# Row-7 graded `klt sim` corner-matrix envelope `20261123-120423-ca4c931d`

DR-0007 row 7, **Iq (excluding load) < 30 uA at no load and at full load** -- an Open row of the target spec. The verdict below is `klt sim`'s own: all six graded measurements carry `limits` in `request.json`, so each corner's pass/fail and the matrix verdict (`status`) are computed by the tool, not by this repo.

Measurement definition: |i(VIN)| - Iload per (Vin, Iload) operating point; the same quantity the legacy evidence base recorded as iq_a (includes the 2 uA mirror-reference leg and the divider standing current, excludes the load). Graded over the full Input-row supply window at both load states -- six `analysis_steps[]` operating points per corner (Vin 2.97 / 3.30 / 3.63 V x Iload 0 / 50 mA), the graded figures derived `expr` measurements over each step's raw supply current.

- Corners: 45/45 reported, every coordinate exactly once: True; all six steps ok at every reported corner: True.
- Envelope `status`: **pass** (passed 45, failed 0, errored 0, inconclusive 0).
- Corner status counts: {'pass': 45}; error-severity diagnostics: 0.
- Graded measurements (`coverage.measurements_with_limits` = 6): 6 Iq figures, all tagged `dr0007-row7-iq`; all pass: True.

- Worst no-load Iq: 24.4980 uA (`iq_i0_v3v63_a`, `ss` / 125 C / `res_bcs`); margin to the 30 uA target: 5.5020 uA.
- Worst full-load Iq: 24.6675 uA (`iq_i50m_v3v63_a`, `ff` / 125 C / `res_bcs`); margin to the 30 uA target: 5.3325 uA.
- Definitive matrix claim permitted: **True** (requires the whole 45-coordinate matrix reported, every step ok, resolved, graded and clean).

## Solver convergence setting (not an error bound)

NOT an error bound. The request pins .options reltol/abstol of the 'tight-1e-10' profile; ngspice's stopping test compares each iterate with the previous one and bounds nothing about the distance to the exact operating point. For the standard profile (reltol=1e-9 abstol=1e-15) the threshold at the largest current is ~5e-11 A (0.0002 % of the 30 uA limit). Full-load Iq is graded as a derived expr inside ngspice (klt sim analysis_steps, klayout-tools #2482), never as an offline subtraction. The observed change under tighter tolerances is a separate, measured quantity: see the paired record's row7-pair.json. The step supply currents are reported ungraded per corner in `report.json`, so every graded difference can be re-derived by hand.

## Exclusions this evidence must be read with

- ideal 0.90 V reference: no on-chip reference-generator current is included
- ideal 2 uA IBIAS sink: no on-chip bias-generator current is included (the sunk 2 uA itself flows through the core and IS included)
- evidence is for the core WITHOUT the #190 current limiter
- schematic level, corner grid only, no Monte Carlo (DR-0007 classifies the row deterministic)

The row stays Open under DR-0007; ratification is `spec/` + `ratification/` work (#318), never a `signoff/` edit. This envelope exists so a ratified row has a tagged, limited, tool-graded matrix to cite.

## Per-corner

| corner | status | iq_i0_v2v97_a (uA) | iq_i50m_v2v97_a (uA) | iq_i0_v3v30_a (uA) | iq_i50m_v3v30_a (uA) | iq_i0_v3v63_a (uA) | iq_i50m_v3v63_a (uA) |
|---|---|---|---|---|---|---|---|
| `mos_ff__res_bcs__cap_typ/novdd/-40C` | pass | 23.1087 | 23.1799 | 23.1169 | 23.1881 | 23.1240 | 23.1953 |
| `mos_ff__res_bcs__cap_typ/novdd/125C` | pass | 23.9202 | 24.6546 | 23.9097 | 24.6614 | 23.8981 | 24.6675 |
| `mos_ff__res_bcs__cap_typ/novdd/27C` | pass | 23.6067 | 23.6993 | 23.6143 | 23.7069 | 23.6209 | 23.7135 |
| `mos_ff__res_typ__cap_typ/novdd/-40C` | pass | 22.5437 | 22.6159 | 22.5519 | 22.6241 | 22.5590 | 22.6312 |
| `mos_ff__res_typ__cap_typ/novdd/125C` | pass | 22.9161 | 23.8288 | 22.9010 | 23.8356 | 22.8849 | 23.8416 |
| `mos_ff__res_typ__cap_typ/novdd/27C` | pass | 22.9483 | 23.0430 | 22.9559 | 23.0506 | 22.9624 | 23.0572 |
| `mos_ff__res_wcs__cap_typ/novdd/-40C` | pass | 22.1231 | 22.1961 | 22.1313 | 22.2043 | 22.1384 | 22.2114 |
| `mos_ff__res_wcs__cap_typ/novdd/125C` | pass | 22.1049 | 23.2143 | 22.0852 | 23.2211 | 22.0644 | 23.2271 |
| `mos_ff__res_wcs__cap_typ/novdd/27C` | pass | 22.4579 | 22.5546 | 22.4654 | 22.5622 | 22.4719 | 22.5688 |
| `mos_fs__res_bcs__cap_typ/novdd/-40C` | pass | 23.1089 | 23.1743 | 23.1175 | 23.1828 | 23.1248 | 23.1901 |
| `mos_fs__res_bcs__cap_typ/novdd/125C` | pass | 24.4471 | 24.6483 | 24.4520 | 24.6554 | 24.4558 | 24.6616 |
| `mos_fs__res_bcs__cap_typ/novdd/27C` | pass | 23.6125 | 23.6934 | 23.6205 | 23.7013 | 23.6273 | 23.7081 |
| `mos_fs__res_typ__cap_typ/novdd/-40C` | pass | 22.5441 | 22.6102 | 22.5527 | 22.6187 | 22.5600 | 22.6260 |
| `mos_fs__res_typ__cap_typ/novdd/125C` | pass | 23.5949 | 23.8225 | 23.5990 | 23.8296 | 23.6020 | 23.8357 |
| `mos_fs__res_typ__cap_typ/novdd/27C` | pass | 22.9549 | 23.0371 | 22.9628 | 23.0450 | 22.9696 | 23.0518 |
| `mos_fs__res_wcs__cap_typ/novdd/-40C` | pass | 22.1237 | 22.1905 | 22.1322 | 22.1990 | 22.1395 | 22.2062 |
| `mos_fs__res_wcs__cap_typ/novdd/125C` | pass | 22.9501 | 23.2080 | 22.9533 | 23.2150 | 22.9555 | 23.2212 |
| `mos_fs__res_wcs__cap_typ/novdd/27C` | pass | 22.4652 | 22.5487 | 22.4731 | 22.5566 | 22.4798 | 22.5634 |
| `mos_sf__res_bcs__cap_typ/novdd/-40C` | pass | 23.1089 | 23.1780 | 23.1173 | 23.1863 | 23.1244 | 23.1935 |
| `mos_sf__res_bcs__cap_typ/novdd/125C` | pass | 24.2175 | 24.6524 | 24.2153 | 24.6593 | 24.2121 | 24.6654 |
| `mos_sf__res_bcs__cap_typ/novdd/27C` | pass | 23.6094 | 23.6972 | 23.6171 | 23.7049 | 23.6237 | 23.7116 |
| `mos_sf__res_typ__cap_typ/novdd/-40C` | pass | 22.5440 | 22.6140 | 22.5523 | 22.6222 | 22.5595 | 22.6294 |
| `mos_sf__res_typ__cap_typ/novdd/125C` | pass | 23.2947 | 23.8266 | 23.2897 | 23.8335 | 23.2836 | 23.8396 |
| `mos_sf__res_typ__cap_typ/novdd/27C` | pass | 22.9513 | 23.0410 | 22.9590 | 23.0487 | 22.9656 | 23.0553 |
| `mos_sf__res_wcs__cap_typ/novdd/-40C` | pass | 22.1235 | 22.1942 | 22.1318 | 22.2025 | 22.1389 | 22.2096 |
| `mos_sf__res_wcs__cap_typ/novdd/125C` | pass | 22.5694 | 23.2121 | 22.5613 | 23.2190 | 22.5521 | 23.2250 |
| `mos_sf__res_wcs__cap_typ/novdd/27C` | pass | 22.4612 | 22.5526 | 22.4689 | 22.5602 | 22.4755 | 22.5669 |
| `mos_ss__res_bcs__cap_typ/novdd/-40C` | pass | 23.1087 | 23.1724 | 23.1173 | 23.1810 | 23.1247 | 23.1884 |
| `mos_ss__res_bcs__cap_typ/novdd/125C` | pass | 24.4869 | 24.6462 | 24.4930 | 24.6534 | 24.4980 | 24.6596 |
| `mos_ss__res_bcs__cap_typ/novdd/27C` | pass | 23.6134 | 23.6915 | 23.6214 | 23.6995 | 23.6283 | 23.7064 |
| `mos_ss__res_typ__cap_typ/novdd/-40C` | pass | 22.5439 | 22.6084 | 22.5526 | 22.6170 | 22.5599 | 22.6243 |
| `mos_ss__res_typ__cap_typ/novdd/125C` | pass | 23.6463 | 23.8205 | 23.6520 | 23.8276 | 23.6566 | 23.8338 |
| `mos_ss__res_typ__cap_typ/novdd/27C` | pass | 22.9558 | 23.0353 | 22.9638 | 23.0432 | 22.9707 | 23.0501 |
| `mos_ss__res_wcs__cap_typ/novdd/-40C` | pass | 22.1235 | 22.1887 | 22.1321 | 22.1972 | 22.1395 | 22.2046 |
| `mos_ss__res_wcs__cap_typ/novdd/125C` | pass | 23.0153 | 23.2060 | 23.0205 | 23.2131 | 23.0247 | 23.2192 |
| `mos_ss__res_wcs__cap_typ/novdd/27C` | pass | 22.4662 | 22.5469 | 22.4742 | 22.5548 | 22.4811 | 22.5617 |
| `mos_tt__res_bcs__cap_typ/novdd/-40C` | pass | 23.1090 | 23.1761 | 23.1175 | 23.1845 | 23.1247 | 23.1918 |
| `mos_tt__res_bcs__cap_typ/novdd/125C` | pass | 24.3709 | 24.6503 | 24.3734 | 24.6573 | 24.3749 | 24.6635 |
| `mos_tt__res_bcs__cap_typ/novdd/27C` | pass | 23.6113 | 23.6953 | 23.6191 | 23.7031 | 23.6258 | 23.7099 |
| `mos_tt__res_typ__cap_typ/novdd/-40C` | pass | 22.5442 | 22.6121 | 22.5526 | 22.6205 | 22.5598 | 22.6277 |
| `mos_tt__res_typ__cap_typ/novdd/125C` | pass | 23.4951 | 23.8246 | 23.4961 | 23.8315 | 23.4961 | 23.8376 |
| `mos_tt__res_typ__cap_typ/novdd/27C` | pass | 22.9534 | 23.0390 | 22.9612 | 23.0468 | 22.9679 | 23.0536 |
| `mos_tt__res_wcs__cap_typ/novdd/-40C` | pass | 22.1237 | 22.1923 | 22.1321 | 22.2007 | 22.1393 | 22.2079 |
| `mos_tt__res_wcs__cap_typ/novdd/125C` | pass | 22.8228 | 23.2100 | 22.8220 | 23.2170 | 22.8202 | 23.2231 |
| `mos_tt__res_wcs__cap_typ/novdd/27C` | pass | 22.4636 | 22.5506 | 22.4714 | 22.5584 | 22.4780 | 22.5651 |

## Provenance

- batch_job_ids: `["klt-sim-68494cc776ad"]`
- git_sha: ca4c931d
- invocation: python3 sim/ldo-cmos5l-pvt-sweep/row7_envelope.py submit --profile tight-1e-10 --pair-of 20261121-001957-ed6b0587
- klt_sim_argv: klt sim request.json --backend batch --wait-for-capacity 600 -o /tmp/row7-envelope-artifacts.nt8n07by --format json
- klt_sim_exit: 0
- measurement_definition: Iq = |i(VIN)| - Iload per (Vin, Iload) operating point; graded as klt sim derived expr measurements over analysis_steps (klayout-tools #2482), never computed by repo Python
- pair_of: 20261121-001957-ed6b0587
- pdk: ihp-sg13cmos5l
- pdk_pin: sim/pdk-cmos5l.json
- pdk_pin_projection_sha256: 751c9b6a3b1911c662127288528be290e63bb2b85c38e1e43007033bb27d2f37
- pdk_root: /home/ubuntu/share/pdk
- probe: False
- record_id: 20261123-120423-ca4c931d
- solver_convergence_setting_a: 5.003100000000001e-11
- solver_options: `{"abstol": 1e-15, "reltol": 1e-10}`
- solver_profile: tight-1e-10
- spec_row: DR-0007 row 7 (Iq excluding load < 30 uA at no load and at full load) -- Open; this envelope does not ratify it
- substitutions: `{"design_netlist_include": "../../../../design/sg13cmos5l/netlist/ldo_core_cmos5l.spice", "osdi_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/osdi", "pdk_models_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/models"}`

Input sha256:

- `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`: `08a7b857e1fad43dd7af1f575de97853a058e85541601ecc47567fbc28dbae57`
- `design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice`: `75ee39ce0c48b54cab6c8a31acd1f199c37c1ccd1ac074a3515dee81cc656fb4`
- `sim/ldo-cmos5l-pvt-sweep/testbench/tb_row7_envelope_cmos5l.spice.tmpl`: `97844d22fffc5fad6e7f2e577853eacd91481ddbd14b2af967cc63b05e4d8ba6`
- `sim/tools/render_deck.py`: `1342231eb9d396774dfb3f838ec31f58a704b3f86e047d6f0188b61c8406a833`

Machine summary: `row7-envelope.json`; the graded envelope itself: `report.json`; the request that produced it: `request.json`, `tb.spice`, `corners.lib`.
