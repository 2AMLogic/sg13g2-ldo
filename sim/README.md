# sim/ — ngspice testbenches and append-only evidence records

Per `CLAUDE.md`: **verification is the product, no claim without a
testbench**, PVT corners on every recorded result, and results here are
**append-only evidence** — a re-run mints a new, timestamped record; nothing
under an experiment's `records/`, `netlist-snapshots/` or `corners/` is ever
edited or deleted after it lands. This follows the same per-experiment shape
(`README.md` / `testbench/` / `corners/` / `netlist-snapshots/` / `records/`)
`sg13g2-bandgap/sim/<experiment>/` and `sg13g2-opamp/sim/gm-id-characterization/`
already established on this same PDK (`spec/porting-plan.md` §1.2: "the
testbench structure... transfers as the evidence schema for this repo's
`sim/`... a convention shared across the fleet, not a PDK-specific
artifact").

## PDK pin

Every record in this tree is generated against the PDK revision pinned in
[`pdk.json`](pdk.json) (`IHP-Open-PDK` tag `v0.3.0`, fetchable via
`klayout-tools`' `scripts/fetch-ihp-sg13g2.sh`). `source env.sh` resolves
`PDK_ROOT`/`PDK` the same way both sibling repos' `sim/env.sh` do (env vars
first, then the usual `open_pdks` install prefixes) — every experiment's
`run_*.sh` sources it, and an interactive `ngspice` session can too.

## Directory / naming convention

```
sim/
  README.md            this file — the authoritative convention
  pdk.json              pinned PDK revision (see "PDK pin" above)
  env.sh                 PDK_ROOT/PDK resolution, sourced by every testbench
  tools/
    build-osdi.sh          builds the OSDI device models (see below)
  <experiment-slug>/     one directory per distinct claim under test
    README.md            testbench rationale, cold-start invocation, PDK pin,
                          and any device/model substitutions + why (required)
    testbench/
      tb_<name>.spice.tmpl   the testbench netlist generation template
    run_*.sh              the cold-start entry point for this experiment
    netlist-snapshots/
      <record-id>/
        <corner-id>.spice    the exact generated netlist for that PVT point
    corners/
      <record-id>/
        <corner-id>.log      raw ngspice batch output for that PVT point
    records/
      <record-id>.md         append-only human-readable summary
      <record-id>.csv         append-only parsed/machine-readable data
```

- **`<experiment-slug>`** — short, kebab-case, one directory per distinct
  claim being tested (e.g. `pass-device-screening`), not per run.
- **`<record-id>`** — `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (UTC), e.g.
  `20260909-220347-ed18110`. A re-run mints a new `<record-id>`; nothing
  under an existing one is ever edited.
- **`<corner-id>`** — testbench-specific (see each experiment's own
  `README.md`); `sim/pass-device-screening/`'s own convention is
  `<bench>_<device-label>_<process>_<temp>c` (no supply-voltage component —
  see that experiment's README "Corner grid and axes swept" for why).

## Append-only rule

`records/*.md`, `records/*.csv`, `netlist-snapshots/**` and `corners/**`
files are **never** edited or deleted after creation. A correction or a
re-run always mints a new `<record-id>`. Not yet mechanically enforced in
this repo (no `check_evidence_formats.py`-equivalent exists here as of this
writing — `sg13g2-bandgap`'s own copy is the fleet's reference
implementation if/when this repo grows enough experiments to warrant
porting it); enforced by PR review for now.

## OSDI device models: required setup

SG13G2's HV/LV MOS (PSP103.6) compact model is Verilog-A; ngspice can only
instantiate it through an OSDI-compiled shared library, and the pinned
IHP-Open-PDK v0.3.0 release ships the Verilog-A *sources* only (no prebuilt
`.osdi`). `sim/tools/build-osdi.sh` compiles the PDK's own sources with a
checksum-pinned OpenVAF-Reloaded release (see that script's header for full
provenance — copied structurally from `sg13g2-bandgap`'s and
`sg13g2-opamp`'s own `sim/tools/build-osdi.sh`, which document the full
approach-and-alternatives-rejected rationale this repo does not repeat);
`--check` verifies the models are present and loadable without rebuilding.
Every experiment's `run_*.sh` preflights this before simulating.

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # fetch pinned compiler, build models
sim/tools/build-osdi.sh --check         # verify only (models present + loadable)
```

## CI: syntax/`--check-env` only, never a `records/` entry

**CI checks that a deck still parses; it never produces evidence.** Every
record under `sim/*/records/` is minted deliberately by a human or agent on
a machine with the PDK, the OSDI models and ngspice — never by a CI robot.
`.github/workflows/ci.yml`'s `pass-device-screening-check` job runs
`sim/pass-device-screening/run_sweep.sh --check-env` (one netlist per bench,
`mos_tt`/27°C, syntax-checked via `ngspice -b`) on every push/PR — see that
job and `run_sweep.sh`'s own header comment. This mirrors the posture
`sg13g2-bandgap`'s own `sim/README.md` states for its (separate, stdlib-only)
evidence-format checker: CI verifies shape/syntax, a human or agent mints
the actual evidence.

## Experiments landed so far

- [`pass-device-screening/`](pass-device-screening/README.md) — screens
  `sg13_hv_pmos` (Mpass's flavor, `design/README.md` "Pass device") against
  the dropout test point (`Vth`, `Ron·W`, `Cgate`) and the continuous-short
  current-limit condition (terminal voltage/current stress vs. the PDK's
  stated ratings), across the full `{tt,ss,ff,sf,fs} × {-40,27,125}°C`
  process/temperature grid (issue #13) — the input to
  `spec/porting-plan.md` §4 item 1, the porting plan's own "single most
  consequential record". See that experiment's README for the full
  methodology, corner-grid rationale, and the `sg13_hv_pmos` hypothesis
  verdict.
