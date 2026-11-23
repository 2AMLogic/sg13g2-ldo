# Row-5 graded `klt sim` corner-matrix envelope `20261123-213711-06bd6576`

DR-0007 row 5, **Line / load regulation < 5 mV/V; < 1 % over full load** -- an Open row of the target spec. The verdict below is `klt sim`'s own: all six graded measurements carry `limits` in `request.json`.

Line: 1000 * |Vout(3.63 V) - Vout(2.97 V)| / 0.66 at Iload 0, 25 and 50 mA, graded as a klt sim derived expr over analysis_steps.

Load: 100 * |Vout(0 mA) - Vout(50 mA)| / Vout(0 mA) at Vin 2.97, 3.30 and 3.63 V, graded as a klt sim derived expr over analysis_steps.

- Corners: 45/45 reported, every coordinate exactly once: True; all eight steps ok at every reported corner: True.
- Envelope `status`: **pass** (passed 45, failed 0, errored 0, inconclusive 0).
- Corner status counts: {'pass': 45}; error-severity diagnostics: 0.
- Graded measurements (`coverage.measurements_with_limits` = 6), all tagged `dr0007-row5-line-load-regulation`; all pass: True; all strictly below target: True.
- Worst line: 0.243766 mV/V (`line_i0_mvpv`, `ff` / 125 C / `res_wcs`) against 5 mV/V.
- Worst load: 0.0241452 % (`load_v3v63_pct`, `ff` / 125 C / `res_wcs`) against 1 %.
- Definitive matrix claim permitted: **True**.

## Solver convergence setting (not an error bound)

NOT an error bound. The request pins .options reltol=1e-09 abstol=1e-15; ngspice's stopping test compares each iterate with the previous one and bounds nothing about the distance to the exact operating point. No paired tight-tolerance record exists for row 5: observed solver sensitivity is not claimed.

## Remaining qualifications

- ideal 0.90 V reference: reference error is excluded
- discrete sampling only: three line loads (0, 25, 50 mA) and three load-regulation supplies (2.97, 3.30, 3.63 V), not a continuous-window claim
- the row's 'inside the accuracy window' coupling to row 2 is NOT demonstrated by this envelope
- schematic level, corner grid only, no Monte Carlo; core WITHOUT the #190 limiter

The row stays Open under DR-0007; ratification is `spec/` + `ratification/` work (#318), never a `signoff/` edit.

## Per-corner

| corner | status | line_i0_mvpv | line_i25m_mvpv | line_i50m_mvpv | load_v2v97_pct | load_v3v30_pct | load_v3v63_pct |
|---|---|---|---|---|---|---|---|
| `mos_ff__res_bcs__cap_typ/novdd/-40C` | pass | 0.172725 | 0.159199 | 0.160413 | 0.00742446 | 0.00747376 | 0.00787533 |
| `mos_ff__res_bcs__cap_typ/novdd/125C` | pass | 0.236081 | 0.17632 | 0.176756 | 0.0177055 | 0.0184036 | 0.0198784 |
| `mos_ff__res_bcs__cap_typ/novdd/27C` | pass | 0.185942 | 0.162765 | 0.163746 | 0.00878036 | 0.00895083 | 0.0095934 |
| `mos_ff__res_typ__cap_typ/novdd/-40C` | pass | 0.173009 | 0.159199 | 0.160413 | 0.00747996 | 0.00753273 | 0.00794125 |
| `mos_ff__res_typ__cap_typ/novdd/125C` | pass | 0.239904 | 0.17632 | 0.176756 | 0.0195997 | 0.0203633 | 0.0219125 |
| `mos_ff__res_typ__cap_typ/novdd/27C` | pass | 0.186479 | 0.162766 | 0.163747 | 0.00886378 | 0.00904135 | 0.0096965 |
| `mos_ff__res_wcs__cap_typ/novdd/-40C` | pass | 0.173267 | 0.159199 | 0.160413 | 0.00752992 | 0.00758584 | 0.00800066 |
| `mos_ff__res_wcs__cap_typ/novdd/125C` | pass | 0.243766 | 0.17632 | 0.176756 | 0.021691 | 0.0225216 | 0.0241452 |
| `mos_ff__res_wcs__cap_typ/novdd/27C` | pass | 0.186969 | 0.162764 | 0.163747 | 0.00893958 | 0.00912361 | 0.00979026 |
| `mos_fs__res_bcs__cap_typ/novdd/-40C` | pass | 0.170074 | 0.160557 | 0.163034 | 0.00775016 | 0.00771122 | 0.00800776 |
| `mos_fs__res_bcs__cap_typ/novdd/125C` | pass | 0.218077 | 0.175274 | 0.177869 | 0.0128108 | 0.013177 | 0.0142837 |
| `mos_fs__res_bcs__cap_typ/novdd/27C` | pass | 0.18142 | 0.163545 | 0.166035 | 0.00906481 | 0.00912227 | 0.00962819 |
| `mos_fs__res_typ__cap_typ/novdd/-40C` | pass | 0.170315 | 0.160557 | 0.163034 | 0.00780525 | 0.00776903 | 0.00807168 |
| `mos_fs__res_typ__cap_typ/novdd/125C` | pass | 0.219629 | 0.175274 | 0.177869 | 0.0131735 | 0.0135629 | 0.0147032 |
| `mos_fs__res_typ__cap_typ/novdd/27C` | pass | 0.181887 | 0.163543 | 0.166035 | 0.00914339 | 0.00920669 | 0.00972388 |
| `mos_fs__res_wcs__cap_typ/novdd/-40C` | pass | 0.170534 | 0.160557 | 0.163034 | 0.0078548 | 0.00782107 | 0.00812926 |
| `mos_fs__res_wcs__cap_typ/novdd/125C` | pass | 0.221153 | 0.175274 | 0.177868 | 0.0135626 | 0.0139752 | 0.0151482 |
| `mos_fs__res_wcs__cap_typ/novdd/27C` | pass | 0.182313 | 0.163545 | 0.166035 | 0.00921435 | 0.009283 | 0.00981047 |
| `mos_sf__res_bcs__cap_typ/novdd/-40C` | pass | 0.16437 | 0.152493 | 0.154068 | 0.00719769 | 0.00721743 | 0.00757491 |
| `mos_sf__res_bcs__cap_typ/novdd/125C` | pass | 0.216554 | 0.166651 | 0.167825 | 0.0141486 | 0.0146732 | 0.0159337 |
| `mos_sf__res_bcs__cap_typ/novdd/27C` | pass | 0.1766 | 0.155837 | 0.157285 | 0.00848583 | 0.00861364 | 0.00919339 |
| `mos_sf__res_typ__cap_typ/novdd/-40C` | pass | 0.164633 | 0.152493 | 0.154068 | 0.00725062 | 0.0072735 | 0.00763748 |
| `mos_sf__res_typ__cap_typ/novdd/125C` | pass | 0.219169 | 0.166652 | 0.167825 | 0.0151689 | 0.0157368 | 0.0170497 |
| `mos_sf__res_typ__cap_typ/novdd/27C` | pass | 0.1771 | 0.155837 | 0.157285 | 0.00856365 | 0.00869791 | 0.0092895 |
| `mos_sf__res_wcs__cap_typ/novdd/-40C` | pass | 0.164871 | 0.152493 | 0.154068 | 0.00729826 | 0.00732398 | 0.00769386 |
| `mos_sf__res_wcs__cap_typ/novdd/125C` | pass | 0.221842 | 0.166652 | 0.167825 | 0.0163156 | 0.0169285 | 0.0182943 |
| `mos_sf__res_wcs__cap_typ/novdd/27C` | pass | 0.177554 | 0.155836 | 0.157284 | 0.00863417 | 0.00877433 | 0.0093767 |
| `mos_ss__res_bcs__cap_typ/novdd/-40C` | pass | 0.162347 | 0.154344 | 0.157181 | 0.00754603 | 0.00747948 | 0.00773495 |
| `mos_ss__res_bcs__cap_typ/novdd/125C` | pass | 0.204397 | 0.166666 | 0.169948 | 0.011948 | 0.0122279 | 0.0132099 |
| `mos_ss__res_bcs__cap_typ/novdd/27C` | pass | 0.17287 | 0.157189 | 0.160139 | 0.00881045 | 0.00882864 | 0.00927662 |
| `mos_ss__res_typ__cap_typ/novdd/-40C` | pass | 0.162568 | 0.154346 | 0.15718 | 0.00759882 | 0.00753473 | 0.00779589 |
| `mos_ss__res_typ__cap_typ/novdd/125C` | pass | 0.205658 | 0.166666 | 0.169948 | 0.0121882 | 0.0124862 | 0.0134963 |
| `mos_ss__res_typ__cap_typ/novdd/27C` | pass | 0.173304 | 0.157189 | 0.160138 | 0.00888521 | 0.00890871 | 0.00936729 |
| `mos_ss__res_wcs__cap_typ/novdd/-40C` | pass | 0.162769 | 0.154345 | 0.15718 | 0.00764632 | 0.00758442 | 0.00785077 |
| `mos_ss__res_wcs__cap_typ/novdd/125C` | pass | 0.206859 | 0.166666 | 0.169948 | 0.0124343 | 0.0127498 | 0.0137865 |
| `mos_ss__res_wcs__cap_typ/novdd/27C` | pass | 0.173699 | 0.157189 | 0.160138 | 0.00895266 | 0.00898103 | 0.00944923 |
| `mos_tt__res_bcs__cap_typ/novdd/-40C` | pass | 0.166975 | 0.156282 | 0.158296 | 0.00745786 | 0.00744861 | 0.00777556 |
| `mos_tt__res_bcs__cap_typ/novdd/125C` | pass | 0.216327 | 0.170598 | 0.172468 | 0.0130973 | 0.0135318 | 0.014704 |
| `mos_tt__res_bcs__cap_typ/novdd/27C` | pass | 0.178741 | 0.159437 | 0.161395 | 0.00875555 | 0.00884833 | 0.00939085 |
| `mos_tt__res_typ__cap_typ/novdd/-40C` | pass | 0.167226 | 0.156282 | 0.158296 | 0.00751177 | 0.00750544 | 0.0078387 |
| `mos_tt__res_typ__cap_typ/novdd/125C` | pass | 0.218268 | 0.170598 | 0.172468 | 0.0136782 | 0.0141433 | 0.015356 |
| `mos_tt__res_typ__cap_typ/novdd/27C` | pass | 0.179223 | 0.159437 | 0.161395 | 0.00883344 | 0.00893235 | 0.00948642 |
| `mos_tt__res_wcs__cap_typ/novdd/-40C` | pass | 0.167455 | 0.156282 | 0.158296 | 0.00756027 | 0.0075566 | 0.00789558 |
| `mos_tt__res_wcs__cap_typ/novdd/125C` | pass | 0.220234 | 0.170598 | 0.172468 | 0.0143248 | 0.0148214 | 0.0160745 |
| `mos_tt__res_wcs__cap_typ/novdd/27C` | pass | 0.179663 | 0.159437 | 0.161395 | 0.00890384 | 0.00900838 | 0.00957294 |

## Provenance

- batch_job_ids: `["klt-sim-2bf28ff85453"]`
- git_sha: 06bd6576
- invocation: python3 sim/ldo-cmos5l-pvt-sweep/row5_envelope.py submit
- klt_sim_argv: klt sim request.json --backend batch --wait-for-capacity 600 -o /tmp/row5-envelope-artifacts.3udxp4s8 --format json
- klt_sim_exit: 0
- measurement_definition: line and load regulation graded as klt sim derived expr measurements over analysis_steps, never computed by repo Python
- pdk: ihp-sg13cmos5l
- pdk_pin: sim/pdk-cmos5l.json
- pdk_pin_projection_sha256: 751c9b6a3b1911c662127288528be290e63bb2b85c38e1e43007033bb27d2f37
- pdk_root: /home/ubuntu/share/pdk
- probe: False
- record_id: 20261123-213711-06bd6576
- solver_options: `{"abstol": 1e-15, "reltol": 1e-09}`
- spec_row: DR-0007 row 5 (line / load regulation) -- Open; this envelope does not ratify it
- substitutions: `{"design_netlist_include": "../../../../design/sg13cmos5l/netlist/ldo_core_cmos5l.spice", "osdi_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/osdi", "pdk_models_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/models"}`

Input sha256:

- `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`: `08a7b857e1fad43dd7af1f575de97853a058e85541601ecc47567fbc28dbae57`
- `design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice`: `75ee39ce0c48b54cab6c8a31acd1f199c37c1ccd1ac074a3515dee81cc656fb4`
- `sim/ldo-cmos5l-pvt-sweep/testbench/tb_row5_envelope_cmos5l.spice.tmpl`: `2e0cb9b4daf6f854d67bb467394dbda2214779b92d0bca2003f32c5429c97742`
- `sim/tools/render_deck.py`: `1342231eb9d396774dfb3f838ec31f58a704b3f86e047d6f0188b61c8406a833`

Machine summary: `row5-envelope.json`; graded envelope: `report.json`; request: `request.json`, `tb.spice`, `corners.lib`.
