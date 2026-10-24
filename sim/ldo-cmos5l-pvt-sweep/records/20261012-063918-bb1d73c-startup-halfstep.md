# Startup campaign record `20261012-063918-bb1d73c` stage `halfstep` (issue #69)

SCHEMATIC-LEVEL evidence for the EN-bearing SG13CMOS5L core. Proposed methodology (README.md "Startup campaign (issue #69)"); DR-0007 row 9 stays **Open**. Verdicts come from `startup_eval.py`; a missing or non-converged trace is `insufficient`, never a pass.

## Coverage

- Requested points: **2**
- Points with a result row: 2
- Evaluated (data sufficient): **2**
- Insufficient / missing data: **0**
- Verdicts: pass 0, fail 2, insufficient 0
- Complete: **yes**
- Engine: ngspice-46; runner klt 0.5.0; client klt 0.7.0+gff97d692a147
- klt sim requests: 1; fleet jobs recorded: 1
- PDK pin (sim/pdk-cmos5l.json) f7bca32694fe; installed checkout f7bca32694fe (match)
- OSDI binaries (sha256): cap_cmomf.osdi 52ce5c95055a, cap_cmomi.osdi 61491e722c30, mosvar.osdi 25e64a374ab5, psp103.osdi 2e4299c46839, psp103_nqs.osdi 839b16448320, r3_cmc.osdi 4fead17bc2e9
- Source hashes: `sim/ldo-cmos5l-pvt-sweep/testbench/tb_startup_cmos5l.spice.tmpl` ad9e077575a7, `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` 08a7b857e1fa, `sim/ldo-cmos5l-pvt-sweep/startup_eval.py` da3543a6d412, `sim/ldo-cmos5l-pvt-sweep/startup_campaign.py` a445a7177f5c

## Extrema over the evaluated points

| metric | min | at | max | at |
|---|---|---|---|---|
| start overshoot above 1.8 V [V] | 0.225588 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 0.403735 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| start peak VOUT [V] | 2.02559 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 2.20374 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| start settle time [s] | 0.000181788 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 0.000332714 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| start 10-90 % rise time [s] | 1.93326e-06 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 2.63543e-06 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| start max downward excursion [V] | 0.189992 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 0.367802 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| re-enable overshoot [V] | 0.225291 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 0.502456 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| re-enable max downward excursion [V] | 0.189391 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 0.466755 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| off-state max VOUT [V] | 9.36442e-06 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 0.000472278 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| off-state supply current [A] | 2.00523e-06 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 2.26401e-06 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| start max Vsg(Mpass) [V] | 3.62277 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 3.62679 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| start max Vds(Mpass) [V] | 3.62953 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 3.62999 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |
| start peak supply current [A] | 0.567961 | `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | 0.774608 | `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm_t500ns` |

## Failure reasons (count of points)

- reen_downward excursion: 2
- reen_peak overshoot: 2
- start_downward excursion: 2
- start_peak overshoot: 2

## Timestep sensitivity (1 us cap vs 0.5 us cap)

| point | metric | 1 us | 0.5 us | delta |
|---|---|---|---|---|
| `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start overshoot above 1.8 V [V] | 0.538852 | 0.225588 | -0.313 |
| `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start peak VOUT [V] | 2.33885 | 2.02559 | -0.313 |
| `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start settle time [s] | 0.000440999 | 0.000181788 | -0.000259 |
| `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start 10-90 % rise time [s] | 2.63731e-06 | 2.63543e-06 | -1.89e-09 |
| `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start max downward excursion [V] | 0.50375 | 0.189992 | -0.314 |
| `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | re-enable overshoot [V] | 0.340631 | 0.225291 | -0.115 |
| `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | re-enable max downward excursion [V] | 0.305457 | 0.189391 | -0.116 |
| `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | off-state max VOUT [V] | 0.000472278 | 0.000472278 | -4.34e-19 |
| `st_ff_125c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | verdict | fail | fail | |
| `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start overshoot above 1.8 V [V] | 0.510983 | 0.403735 | -0.107 |
| `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start peak VOUT [V] | 2.31098 | 2.20374 | -0.107 |
| `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start settle time [s] | 0.000418079 | 0.000332714 | -8.54e-05 |
| `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start 10-90 % rise time [s] | 1.93118e-06 | 1.93326e-06 | +2.09e-09 |
| `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | start max downward excursion [V] | 0.475527 | 0.367802 | -0.108 |
| `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | re-enable overshoot [V] | 0.449052 | 0.502456 | +0.0534 |
| `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | re-enable max downward excursion [V] | 0.413312 | 0.466755 | +0.0534 |
| `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | off-state max VOUT [V] | 9.36442e-06 | 9.36442e-06 | +0 |
| `st_ff_-40c_rwcs_v3630mv_i1ma_c1000nf_e0mohm` | verdict | fail | fail | |

## Points

Per-point metrics, trace file names and trace sha256 are in `20261012-063918-bb1d73c-startup-halfstep.csv`; reduced traces in `20261012-063918-bb1d73c-startup-halfstep.traces/` (`t,vout,en,vin,eaout,ivin`, gzip). Rawfile sha256 per point is the `raw_sha256` column (rawfiles themselves, about 2 MB each, are not committed).
