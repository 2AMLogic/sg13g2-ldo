# Row-5 graded `klt sim` corner-matrix envelope `20261123-213537-06bd6576-probe`

DR-0007 row 5, **Line / load regulation < 5 mV/V; < 1 % over full load** -- an Open row of the target spec. The verdict below is `klt sim`'s own: all six graded measurements carry `limits` in `request.json`.

Line: 1000 * |Vout(3.63 V) - Vout(2.97 V)| / 0.66 at Iload 0, 25 and 50 mA, graded as a klt sim derived expr over analysis_steps.

Load: 100 * |Vout(0 mA) - Vout(50 mA)| / Vout(0 mA) at Vin 2.97, 3.30 and 3.63 V, graded as a klt sim derived expr over analysis_steps.

> **PROBE RECORD.** Never cited as row evidence.

- Corners: 2/2 reported, every coordinate exactly once: True; all eight steps ok at every reported corner: True.
- Envelope `status`: **pass** (passed 2, failed 0, errored 0, inconclusive 0).
- Corner status counts: {'pass': 2}; error-severity diagnostics: 0.
- Graded measurements (`coverage.measurements_with_limits` = 6), all tagged `dr0007-row5-line-load-regulation`; all pass: True; all strictly below target: True.
- Worst line: 0.205658 mV/V (`line_i0_mvpv`, `ss` / 125 C / `res_typ`) against 5 mV/V.
- Worst load: 0.0134963 % (`load_v3v63_pct`, `ss` / 125 C / `res_typ`) against 1 %.
- Definitive matrix claim permitted: **False**.

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
| `mos_ss__res_typ__cap_typ/novdd/125C` | pass | 0.205658 | 0.166666 | 0.169948 | 0.0121882 | 0.0124862 | 0.0134963 |
| `mos_tt__res_typ__cap_typ/novdd/27C` | pass | 0.179223 | 0.159437 | 0.161395 | 0.00883344 | 0.00893235 | 0.00948642 |

## Provenance

- batch_job_ids: `["klt-sim-8bd7db39c8ae"]`
- git_sha: 06bd6576
- invocation: python3 sim/ldo-cmos5l-pvt-sweep/row5_envelope.py submit --probe
- klt_sim_argv: klt sim request.json --backend batch --wait-for-capacity 600 -o /tmp/row5-envelope-artifacts.trsyzw9_ --format json
- klt_sim_exit: 0
- measurement_definition: line and load regulation graded as klt sim derived expr measurements over analysis_steps, never computed by repo Python
- pdk: ihp-sg13cmos5l
- pdk_pin: sim/pdk-cmos5l.json
- pdk_pin_projection_sha256: 751c9b6a3b1911c662127288528be290e63bb2b85c38e1e43007033bb27d2f37
- pdk_root: /home/ubuntu/share/pdk
- probe: True
- record_id: 20261123-213537-06bd6576-probe
- solver_options: `{"abstol": 1e-15, "reltol": 1e-09}`
- spec_row: DR-0007 row 5 (line / load regulation) -- Open; this envelope does not ratify it
- substitutions: `{"design_netlist_include": "../../../../design/sg13cmos5l/netlist/ldo_core_cmos5l.spice", "osdi_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/osdi", "pdk_models_dir": "/home/ubuntu/share/pdk/ihp-sg13cmos5l/libs.tech/ngspice/models"}`

Input sha256:

- `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`: `08a7b857e1fad43dd7af1f575de97853a058e85541601ecc47567fbc28dbae57`
- `design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice`: `75ee39ce0c48b54cab6c8a31acd1f199c37c1ccd1ac074a3515dee81cc656fb4`
- `sim/ldo-cmos5l-pvt-sweep/testbench/tb_row5_envelope_cmos5l.spice.tmpl`: `2e0cb9b4daf6f854d67bb467394dbda2214779b92d0bca2003f32c5429c97742`
- `sim/tools/render_deck.py`: `1342231eb9d396774dfb3f838ec31f58a704b3f86e047d6f0188b61c8406a833`

Machine summary: `row5-envelope.json`; graded envelope: `report.json`; request: `request.json`, `tb.spice`, `corners.lib`.
