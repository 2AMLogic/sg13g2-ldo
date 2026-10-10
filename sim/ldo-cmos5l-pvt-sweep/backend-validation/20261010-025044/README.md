# Batch-backend validation 20261010-025044

This run checks that `batch_backend.py` (`run_sweep.sh --batch`) produces the
same raw data a local `ngspice -b` run produces. The batch fleet runs the
decks, and the backend rebuilds the `wrdata` CSVs from the runner's rawfiles.
The run was made before the first `--batch` record (`20261010-025634-60a3e81`)
for PR #87.

## Method

- Inputs are the pre-#67 state from `main`: the three
  `testbench/tb_*_cmos5l.spice.tmpl` templates and
  `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` (sha256 `c6e630e9...f11041`).
  These are the exact inputs of record `20260917-023832-7061e8f`, which was
  produced by the local loop on ngspice-46.
- Decks were generated with `run_sweep.sh`'s own `gen_netlist` substitutions
  at two points, each run on all three benches (6 points in total):
  `tt`/27C/`res_typ` (nominal) and `ss`/125C/`res_bcs` (the phase-margin
  binding corner). `queue.tsv` lists them. The decks themselves were scratch
  files and are not kept. `_batch/<group>/tb.spice` is the body each one
  reduced to.
- They ran through `batch_backend.py run` on the EDA batch fleet: 6 `klt sim`
  requests, runner klt 0.5.0, ngspice-46. All six OSDI binaries were staged,
  including `cap_cmomi`, which the runner image lacks.
  `_batch/backend.json` holds the job ids. Each `_batch/<group>/report.json`
  is the klt report, and each `*.corner.cir` is the deck that ran.
- The backend version used was commit `57823ad`'s `batch_backend.py`. The
  later change in `60a3e81`, which adds duplicate-point layering and
  `--plan-only`, does not affect these points.

## Result

All 6 produced CSVs are **byte-identical** to the committed
`corners/20260917-023832-7061e8f/` files (`produced-csv.sha256`):

```bash
cd sim/ldo-cmos5l-pvt-sweep/corners/20260917-023832-7061e8f
sha256sum -c ../../backend-validation/20261010-025044/produced-csv.sha256
```

This covers the nested DC grid (820 rows, 8 columns) and the loop-gain and
PSRR reductions, which `batch_backend.py` recomputes from complex rawfile
vectors with the templates' `let` expressions. Their output matches ngspice's
own `wrdata` to the last printed digit. The fleet's ngspice-46 run therefore
produced the same solution as the ngspice-46 build behind the 7061e8f record,
at these points and with these model files.

## Limits

- Six points, not the grid. The other 208 points use the same three benches
  and the same reduction code, varying only in corner section, temperature or
  substituted netlist.
- The comparison is with ngspice-46 on both sides. It shows nothing about
  other simulator versions.
