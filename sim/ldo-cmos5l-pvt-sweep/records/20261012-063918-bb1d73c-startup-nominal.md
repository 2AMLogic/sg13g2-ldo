# Startup campaign record `20261012-063918-bb1d73c` stage `nominal` (issue #69)

SCHEMATIC-LEVEL evidence for the EN-bearing SG13CMOS5L core. Proposed methodology (README.md "Startup campaign (issue #69)"); DR-0007 row 9 stays **Open**. Verdicts come from `startup_eval.py`; a missing or non-converged trace is `insufficient`, never a pass.

## Coverage

- Requested points: **1**
- Points with a result row: 1
- Evaluated (data sufficient): **1**
- Insufficient / missing data: **0**
- Verdicts: pass 0, fail 1, insufficient 0
- Complete: **yes**
- Engine: ngspice-46; runner klt 0.5.0; client klt 0.7.0+gff97d692a147
- klt sim requests: 1; fleet jobs recorded: 1
- PDK pin (sim/pdk-cmos5l.json) f7bca32694fe; installed checkout f7bca32694fe (match)
- OSDI binaries (sha256): cap_cmomf.osdi 52ce5c95055a, cap_cmomi.osdi 61491e722c30, mosvar.osdi 25e64a374ab5, psp103.osdi 2e4299c46839, psp103_nqs.osdi 839b16448320, r3_cmc.osdi 4fead17bc2e9
- Source hashes: `sim/ldo-cmos5l-pvt-sweep/testbench/tb_startup_cmos5l.spice.tmpl` ad9e077575a7, `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` 08a7b857e1fa, `sim/ldo-cmos5l-pvt-sweep/startup_eval.py` da3543a6d412, `sim/ldo-cmos5l-pvt-sweep/startup_campaign.py` a445a7177f5c

## Extrema over the evaluated points

| metric | min | at | max | at |
|---|---|---|---|---|
| start overshoot above 1.8 V [V] | 0.293096 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 0.293096 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| start peak VOUT [V] | 2.0931 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 2.0931 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| start settle time [s] | 0.000241386 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 0.000241386 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| start 10-90 % rise time [s] | 3.11816e-06 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 3.11816e-06 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| start max downward excursion [V] | 0.257266 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 0.257266 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| re-enable overshoot [V] | 0.222613 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 0.222613 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| re-enable max downward excursion [V] | 0.187404 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 0.187404 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| off-state max VOUT [V] | 1.08795e-06 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 1.08795e-06 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| off-state supply current [A] | 2.00061e-06 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 2.00061e-06 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| start max Vsg(Mpass) [V] | 3.29516 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 3.29516 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| start max Vds(Mpass) [V] | 3.3 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 3.3 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |
| start peak supply current [A] | 0.485602 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | 0.485602 | `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` |

## Failure reasons (count of points)

- reen_downward excursion: 1
- reen_peak overshoot: 1
- start_downward excursion: 1
- start_peak overshoot: 1

## Points

Per-point metrics, trace file names and trace sha256 are in `20261012-063918-bb1d73c-startup-nominal.csv`; reduced traces in `20261012-063918-bb1d73c-startup-nominal.traces/` (`t,vout,en,vin,eaout,ivin`, gzip). Rawfile sha256 per point is the `raw_sha256` column (rawfiles themselves, about 2 MB each, are not committed).
