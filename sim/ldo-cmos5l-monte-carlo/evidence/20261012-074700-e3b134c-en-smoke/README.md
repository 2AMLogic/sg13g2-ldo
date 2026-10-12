# 20261012-074700-e3b134c-en-smoke -- EN-enabled row-2 bench, one-corner batch smoke on the re-stamped PDK (issue #155)

**Non-gating evidence, not a campaign record.** Same request as
`20261010-193208-028a3f8-en-smoke/` (`request-row2-smoke-en.json`: tt_nom, 27 C,
VREF 0.90 V, MC off, one unit), re-run with the model closure staged from the
re-stamped PDK install. It makes **no row-2 claim**. No Monte Carlo campaign was
re-run for #155: the only row-2 campaign record is the pre-EN five-port
`records/20261009-003009-3ee8306`, whose deck no longer elaborates against the
current six-port core (historical only, see this directory's README). A row-2
statement about the EN design still needs a new campaign record
(`run_campaign.sh submit`), which #155 did not mint.

| Field | Value |
|---|---|
| Command | `PDK_ROOT=<scratch>/ihp-open-pdk PDK=ihp-sg13cmos5l klt sim sim/ldo-cmos5l-monte-carlo/request-row2-smoke-en.json --backend batch -o <dir>/artifacts --format json > <dir>/raw/row2-smoke-en.sim.json` (exit 0) |
| Fleet job | `klt-sim-1b9c76686f85`, aws-batch-fleet, Spot `c7i.8xlarge`, runner klt 0.5.0, client klt `0.7.0+gff97d692a147` |
| PDK | `ihp-sg13cmos5l` @ `f7bca32694fe3d58be0cc7d9df4b9f5db7161a14` (read from the scratch install's `.fetched-version`), `sim/pdk-cmos5l.json` |
| Result | `status: pass`, 1/1 unit, `vout_v = 1.800306041 V` |

Compared with `20261010-193208-028a3f8-en-smoke`: `vout_v` is identical to all
ten printed digits (1.800306041 V). That run reported one `singular_matrix`
warning (recovered by dynamic gmin stepping); this run reports none
(`diagnostic_counts` is empty). The design netlists differ between the two runs
(that run used the pre-#89 netlist), so no PDK-attributable cause is claimed.
The staged model-card closure is byte-identical between the two PDK installs
(see `sim/migration-inventory-155.md`).
