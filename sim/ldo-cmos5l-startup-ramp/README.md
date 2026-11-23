# ldo-cmos5l-startup-ramp — DR-0020 bounded experiment (issue #314)

The confirm/reject gate of [`DR-0020`](../../spec/decision-records/DR-0020-sg13cmos5l-startup-remedy-plan.md)
for the row-9 reference-ramp soft start. Authorised **as an experiment only** by
the operator ruling of 2026-11-23 on #314 (`authorize_experiment`). DR-0020
stays Proposed, `DR-0007` row 9 stays Open, `design/sg13cmos5l/` is untouched,
no threshold, verdict rule or existing record is edited.

## What is here

| File | Role |
|---|---|
| `gen_core_with_ramp.py` | Derives the testbench-local netlist from the committed core (read-only), fails closed if the core changed shape. |
| `core_with_ramp.spice` | Its output, committed. Same core subckt name and six ports (so the unchanged startup bench instantiates it), `Xamp` reference moved `VREF` -> internal `VREFR`, ramp cell added. |
| `ramp_campaign.py` | Thin driver over `../ldo-cmos5l-pvt-sweep/startup_campaign.py` (bench template, `startup_eval.py`, request builder and record writer used **unchanged**): `plan`, `submit`, `collect`, `clauses`. |
| `../ldo-cmos5l-pvt-sweep/test_startup_ramp_wrapper.py` | Unit test, incl. a negative control (a plan without the wrapper redirect does not reach the deck). |

## Ramp cell (candidate values, unvalidated)

`I_ramp` = `IBIAS` mirrored through a `w=1u l=20u` PMOS (2 uA x 0.05/2.5 = 40 nA),
`Css` = 96 x 96 um `cap_cmomi` (~10 pF at ~1.09 fF/um^2, `design/README.md`),
nominal `T_ramp = Css*VREF/I_ramp` ~ 225 us. Reset: NMOS on a local `EN`
inverter. Clamp (`VREFR <= VREF`): a second instance of the committed
`ldo_erramp_cmos5l` used as a comparator that drives an NMOS pull-down on
`VREFR`. **That clamp realisation costs far more than DR-0020's sub-uA branch
budget (a full amplifier's static current); this experiment makes no row-7
claim and the integration follow-up would need a cheaper clamp.**
The parked `IBIAS` (`XMbdis`, `EN` low) switches the mirror off, so `Css` is
not trickle-charged while disabled.

## Points (7, counted from DR-0020; no eighth invented)

tt/27 C/3.30 V/1 mA/1000 nF/0 mohm; ff/27 C/rtyp/3.63 V and ss/-40 C/rtyp/3.63 V
(same load/network; these two are the binding points, run at the 0.5 us step cap,
all others at 1 us); tt/27 C/3.63 V at {330 nF/0 mohm, 4700 nF/500 mohm} x {0, 50 mA}.
The bench differs by load/Cout/ESR between points, so the 7 points are 7
single-corner requests submitted together in **one** `klt sim --batch-set`
invocation (`--backend batch --wait-for-capacity 600`). No local run.

## Clauses, pre-registered before the run

(a) verdict `pass` and `reen_pass` at every point; (b) `start_peak_supply_current_a`
<= `(Cout*2*VREF/T_ramp + I_load) * 1.25 + 1 mA` with the measured `T_ramp`;
(c) `start_max_vsg_pass_v` and `reen_max_vsg_pass_v` <= 3.3 V; (d) measured
`T_ramp` (10-90 % of `VREF` on `v(xtop.vrefr)`, divided by 0.8) inside
**180-450 us** in both windows. Any failed clause = **reject**.

Caveat: The committed reduced traces carry no `vrefr` column: `startup_campaign.py` hard-codes the reduced column set (`reduce_trace`/`write_trace`) and was kept unchanged by scope, so DR-0020's "Metrics per point" expectation that the column list gains `vrefr` was **not met** (a deviation). `T_ramp`, the clause-(b) bound (computed from `T_ramp`) and `VREFR max V` were read from the uncommitted rawfiles (sha256 in the `raw_sha256` column) and cannot be re-derived from the committed traces.

## Reproduce

```bash
PDK=ihp-sg13cmos5l source sim/env.sh
python3 sim/ldo-cmos5l-startup-ramp/gen_core_with_ramp.py | diff - sim/ldo-cmos5l-startup-ramp/core_with_ramp.spice
python3 sim/ldo-cmos5l-startup-ramp/ramp_campaign.py plan    --rid <RID>
python3 sim/ldo-cmos5l-startup-ramp/ramp_campaign.py submit  --rid <RID>
python3 sim/ldo-cmos5l-startup-ramp/ramp_campaign.py collect --rid <RID>
python3 sim/ldo-cmos5l-startup-ramp/ramp_campaign.py clauses --rid <RID>
```

## Result (record `20261123-212501-9e332bb0`): REJECT

7 of 7 points evaluated on the batch fleet (runner klt 0.9.0, ngspice 47). `Vsg(Mpass)` max 0.80-1.51 V
(clause c holds), start peaks 1.834-1.839 V, but clauses (a), (b) and (d) fail; see
`records/20261123-212501-9e332bb0-startup-ramp.clauses.md` and the DR-0020 addendum. First attempt
`20261123-212200-433395a5` failed all 7 jobs (`status: error`, `exit_code: 4`); it is kept under
`startup/20261123-212200-433395a5/ramp/{plan,envelope}.json` plus `klt-sim.stderr`. The committed attempt-1
artifacts do not contain the string `osdi_load_failed` (per-job `report.json` was not committed), so the
diagnosis is an **inference, not re-derivable from them**: the deck-side OSDI preamble conflicts with the
runner's `osdi_preload` (per `batch_backend.py`, #313; closed klayout-tools#5766). Its direct support is that
dropping the preamble made the identical 7-request set pass. The driver now writes an empty preamble (and
therefore also drops `set num_threads=1`, harmless here as every request is a single corner). The same
preamble remains in `startup_campaign.py` and will affect the next batch startup campaign: tracked in #330.
