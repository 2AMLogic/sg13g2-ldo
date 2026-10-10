# 20261010-193208-028a3f8-en-smoke — EN-enabled row-2 bench, one-corner batch smoke (issue #88)

**Non-gating evidence, not a campaign record.** This run shows that the
successor bench `tb_row2_accuracy_en.spice` elaborates against the current
six-port core and completes on the batch fleet. It is a single corner with
Monte Carlo off. It makes **no row-2 claim**. The row-2 campaign record is
still `records/20261009-003009-3ee8306` (five-port, pre-EN design). Any
row-2 statement about the EN design needs a new campaign record, minted by
`run_campaign.sh submit`.

| Field | Value |
|---|---|
| Request | `request-row2-smoke-en.json` (tt_nom, 27 °C, VREF 0.90 V, MC off, one unit) |
| Command | `PDK=ihp-sg13cmos5l source sim/env.sh && klt sim sim/ldo-cmos5l-monte-carlo/request-row2-smoke-en.json --backend batch -o <dir>/artifacts --format json > <dir>/raw/row2-smoke-en.sim.json` (exit 0) |
| Fleet job | `klt-sim-ec04a78c8228`, aws-batch-fleet, Spot `m6i.4xlarge`, state `done`, runner klt 0.5.0, client klt `0.7.0+g39f6da54ae4c` (`runner_compatibility: mismatch`, as in the campaign) |
| Bench | `sim/ldo-cmos5l-monte-carlo/tb_row2_accuracy_en.spice` sha256 `6cc1467a…26800` |
| Preamble | `runner-preamble.cir` sha256 `24a2581f…3e4bf` (unchanged from the campaign) |
| Core | `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` sha256 `7953b25b…222cc1` (six-port, EN; the DR-0008 addendum's design) |
| Models | `row2-corners.lib` sha256 `a0b07d8e…59383` (unchanged), closure staged and pinned in `environment.staged_model_inputs` |
| PDK | `ihp-sg13cmos5l` @ `607e18d4bd92…` (`sim/pdk-cmos5l.json`) |
| Result | `status: pass`, 1/1 unit, `vout_v = 1.800306041 V` |

Raw report: `raw/row2-smoke-en.sim.json`. The retained corner deck and
ngspice log are under `artifacts/tt_nom_novdd_27C/`.

## Observations

- **Value.** 1.800306041 V matches the historical five-port probe at the
  same point (`records/20261009-003009-3ee8306`, `tt_nom/0.900V/27C`,
  1.800306041 V) to all ten printed digits. This agrees with the DR-0008
  addendum, which found no-load VOUT moved by -0.46 µV on the full PVT grid.
  It is one corner with no mismatch, so it is not a statement about the
  spread.
- **Solver recovery (disclosed, not graded).** This solve needed ngspice's
  dynamic gmin stepping. `klt sim` reports one `singular_matrix` warning at
  `n.xtop.xamp.xrz.nr1#i1` (the r3_cmc internal node of the nulling resistor
  `Rz`), and the log shows OSDI `vmax` warnings on the same instance, then
  `Dynamic gmin stepping completed`. The historical probe log for the same
  corner (`corners/20261009-003009-3ee8306/probe_tt_nom_0p900V_27C.log`)
  shows no such recovery. The decks differ in the core's two EN devices and
  in the historical probe's `alter vref=0.9` (its `supply_v` axis). This run
  does not establish which difference causes the recovery. The runner's
  klt 0.5.0 cannot fail a recovered solve (`options.fail_on_diagnostic` is
  newer; campaign README, "Failures and convergence"). A new campaign on
  the EN design should therefore disclose recovered solves from its
  retained logs, as the first campaign did.
