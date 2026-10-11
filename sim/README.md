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

## PDK pin and model provenance

Three different things are easy to conflate here, so they are kept apart:

- **Design branch** -- which device family the experiment's circuit is built
  from (SG13G2 pass-device screening, or the SG13CMOS5L regulator).
- **Intended local PDK pin** -- the revision a local checkout is expected to
  be at, per [`pdk.json`](pdk.json) (`IHP-Open-PDK` tag `v0.3.0`, fetchable
  via `klayout-tools`' `scripts/fetch-ihp-sg13g2.sh`) or
  [`pdk-cmos5l.json`](pdk-cmos5l.json) (`IHP-GmbH/ihp-sg13cmos5l`, a separate
  upstream repository with no tagged releases, pinned by commit sha `607e18d`;
  see that file for why the fetch/pin shape differs).
- **Recorded fleet-model provenance** -- what a given record's own committed
  raw reports show the simulator actually loaded. Several records ran on the
  EDA batch fleet, whose runner image bakes its own PDK and OSDI binaries
  and whose klt is older than the submitting client. A local pin file does not
  by itself describe those runs.

The fleet facts below are read from the committed `klt sim` reports
(`environment.remote`, `environment.staged_model_inputs`) and the experiments'
`runner-preamble.cir`, not inferred. Every fleet report in this tree records
`runner_klt_version: 0.5.0`, `runner_compatibility: mismatch`, ngspice 46
(`/usr/bin/ngspice`) and AMI `ami-0e40e3245f1923ac8`. The reports do **not**
record a PDK commit or release for the runner's baked tree, or for the local
checkout that model cards were staged from; they record only sha256 values of
the staged files. Where a revision is not recorded it is stated as unknown.

| Experiment | Design branch | Intended local PDK pin | Recorded model provenance |
|---|---|---|---|
| [`pass-device-screening/`](pass-device-screening/README.md) | SG13G2 (`sg13_hv_pmos`) | [`pdk.json`](pdk.json): IHP-Open-PDK `v0.3.0` | Local ngspice-46 run against a local `ihp-sg13g2` install with locally built OSDI (record `20260909-220347-ed18110`). No fleet involvement. |
| [`ldo-cmos5l-pvt-sweep/`](ldo-cmos5l-pvt-sweep/README.md) | SG13CMOS5L | [`pdk-cmos5l.json`](pdk-cmos5l.json): `ihp-sg13cmos5l` commit `607e18d4` | Mixed. Records `20260916-083154-7aa1d3f`, `20260916-112842-c25ff53`, `20260916-210331-9d3ace1`, `20260917-023832-7061e8f` and the local probe `20261010-032206-4d45f5d` ran on local ngspice-46 against the pinned checkout. Records from `20261010-025634-60a3e81` onward (grid, dynamic DoE, dropout, startup, `20261011-051956-eda9285`, `20261011-070111-5391c68`) ran on the fleet via `run_sweep.sh --batch`: model cards staged from the local PDK install (sha256 in each `report.json`), all six OSDI binaries staged from the local build and loaded by `pre_osdi`. Runner klt `0.5.0`; client klt varies per record (`0.7.0+g5e5b55992a7f`, `+g8eec069c7576`, `+gca3089cd4b9f`, `+g0d0312b30708`). The local checkout's commit is not recorded in the fleet reports (unknown; intended `607e18d4`). |
| [`ldo-cmos5l-enable/`](ldo-cmos5l-enable/README.md) | SG13CMOS5L (EN-bearing core) | [`pdk-cmos5l.json`](pdk-cmos5l.json) (`PDK=ihp-sg13cmos5l source sim/env.sh`) | Fleet only (`run_smoke.sh`, `klt sim --backend batch`). Model cards staged from the local PDK install (sha256 recorded). OSDI is the **runner's baked** `/opt/pdk/ihp-sg13g2/libs.tech/ngspice/osdi/{psp103,psp103_nqs,mosvar,r3_cmc}.osdi` via [`runner-preamble.cir`](ldo-cmos5l-enable/runner-preamble.cir); the image has no `cap_cmomi`, so `Cc` is a linear stand-in. Runner klt `0.5.0`; client klt `0.7.0+g5e5b55992a7f` (record `20261010-023648-4d45f5d`) and `0.7.0+g0d0312b30708` (`20261011-031743-df3f802`). The baked tree's revision is unknown from the reports; the experiment README and `runner-preamble.cir` cite 2am `batch-image-pins.env` (`BAKED_PDK_ROOT=/opt/pdk`), which is a claim, not something the reports verify. |
| [`ldo-cmos5l-monte-carlo/`](ldo-cmos5l-monte-carlo/README.md) | SG13CMOS5L (five-port core, historical record) | [`pdk-cmos5l.json`](pdk-cmos5l.json) for staged model cards (the experiment names no `models.pdk`) | Fleet only (`klt sim --backend batch`, `remote.hosts: 5`). Model cards (`row2-corners.lib` closure) staged from the local PDK install; OSDI is the runner's baked `/opt/pdk/ihp-sg13g2` binaries via the shared `runner-preamble.cir`, no `cap_cmomi` (DC-only stand-in). Runner klt `0.5.0`, client klt `0.7.0+g4cbdfa769875`. The experiment README states the image pins ihp-sg13g2 0.3.0 and ngspice 46; the reports confirm ngspice 46 but record no PDK revision, so the baked tree's version is unverified here. |

Notes:

- **`characterization/`** is not a row. It is an offline aggregate over one
  hash-pinned record from the experiments above; it runs no simulator and has
  no PDK of its own, so it inherits the provenance of whichever record it
  selects (see its [README](characterization/README.md)).
- Fleet runs mix a staged-from-local model-card closure with either locally
  built OSDI (`ldo-cmos5l-pvt-sweep/`) or the runner's baked OSDI
  (`ldo-cmos5l-enable/`, `ldo-cmos5l-monte-carlo/`). Cross-experiment
  comparisons should keep that difference in view; the enable README's
  like-for-like EN-vs-baseline deltas are unaffected because both sides use the
  same stand-in and runner.
- Historical records are unchanged by this table. It describes them; it does
  not revise their pins or verdicts.

`source env.sh` resolves `PDK_ROOT`/`PDK` the same way both sibling repos'
`sim/env.sh` do (env vars first, then the usual `open_pdks` install prefixes)
-- every local experiment's `run_*.sh` sources it, and an interactive
`ngspice` session can too.

## Directory / naming convention

```
sim/
  README.md            this file — the authoritative convention
  pdk.json              pinned PDK revision (see "PDK pin" above)
  env.sh                 PDK_ROOT/PDK resolution, sourced by every testbench
  tools/
    build-osdi.sh          builds the OSDI device models (see below)
    check_append_only.py   PR-time append-only guard (see "Append-only rule")
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

- [`characterization/`](characterization/README.md) — not an experiment:
  the offline **aggregate** that reads one explicitly selected, hash-pinned
  record from the experiments above and emits the per-spec-row
  characterization report plus the generic envelope T1 item 8 cites
  (issue #58). It mints no `records/` entry and reruns no simulator.

## Append-only rule

Landed evidence is **never** edited, deleted or renamed. A correction or a
re-run always mints a new `<record-id>`; a changed generator or provenance
statement does too.

This is mechanically enforced on pull requests by
[`tools/check_append_only.py`](tools/check_append_only.py) (CI job
`sim-append-only`; tests in `tools/test_check_append_only.py`). It diffs the
PR head against its merge base and rejects any path that already existed at
the merge base and was modified, deleted, type-changed, renamed away, or
overwritten. New files and new record IDs always pass. The protected set is
exactly these six classes:

- `sim/*/records/**`
- `sim/*/corners/**`
- `sim/*/netlist-snapshots/**`
- `sim/*/evidence/**`
- `sim/*/backend-validation/**`
- `sim/*/startup/**`

`evidence/` is protected, not freely mutable derived output. The checker
fails closed (exit 2) when the base or head cannot be resolved or diffed, or
when the allowlist is invalid. The allowlist is read from the committed blob at
the evaluated `--head` commit, never from the working tree; the
`--allowlist FILE` override is for local debugging only and is refused under
`GITHUB_ACTIONS`. Run it locally with
`python3 sim/tools/check_append_only.py --base origin/main`.

### Exact-path exceptions

Only when minting a new record ID is genuinely impossible, add an entry to
`sim/tools/append_only_allowlist.json` (absent by default), reviewed in the
same PR:

```json
{"exceptions": [
  {"path": "sim/<experiment>/records/<record-id>.md",
   "rationale": "why a new record ID cannot be used"}
]}
```

Each entry names one exact protected file path and a non-empty rationale.
Wildcards, directories (including nested ones without a trailing slash: a path
that is a tree at the merge base or at head is rejected), blank rationales, unprotected paths, duplicates and
extra keys make the check fail. An entry permits only that path (for a
rename, both sides must be listed). There is no blanket exception for any
class; the historical `coverage-inventory.*` edits in `434c822` are not
grandfathered and are a negative test.

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

**ngspice version floor: >= 46 (OSDI ABI v0.4).** The pinned
OpenVAF-Reloaded (`v24.0.1mob`) emits OSDI **ABI v0.4**, and an ngspice
whose OSDI loader predates that ABI refuses every model outright:

```
NGSPICE only supports OSDI v0.3 but ".../psp103.osdi" targets v0.4!
```

This rules out the distro package on every current Ubuntu LTS — 24.04
(noble) ships ngspice 42 — so `.github/workflows/ci.yml` builds ngspice 46
from a checksum-verified upstream tarball rather than `apt install ngspice`.
46 is the same version `pdk.json`'s `ngspice_actually_used` records for this
tree's committed evidence, so CI and the records share one simulator build.
If you bump the compiler pin in `build-osdi.sh`, re-check the ABI it emits
against the ngspice both CI and your local install run.

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
- [`ldo-cmos5l-pvt-sweep/`](ldo-cmos5l-pvt-sweep/README.md) — the first
  circuit-level (closed-loop) PVT verification in this repo, on either PDK
  branch: verifies `design/sg13cmos5l/ldo_core_cmos5l.sch`'s closed loop
  (pass device + real two-stage OTA error amp, issue #20) against a spec
  table re-derived at SG13CMOS5L's 3.3V analog rail, across the full
  `{tt,ss,ff,sf,fs} × {-40,27,125}°C` process/temperature grid plus a
  Miller-cap (`Cc`) value sensitivity sweep and an `Rz` corner sensitivity
  sweep (issue #21, phase 3/4 of the SG13CMOS5L port tracked by #12). See
  that experiment's README for the loop-gain measurement method, the
  spec-table verdicts, and why several rows fail against the schematic's
  current (explicitly provisional, unratified) sizing.
- [`ldo-cmos5l-monte-carlo/`](ldo-cmos5l-monte-carlo/README.md) -- the
  bounded **row-2 (output accuracy) Monte Carlo campaign** on the same
  SG13CMOS5L regulator (issue #56): PDK per-instance MOS + `rhigh` mismatch
  sampled at five process/temperature corners (N = 400 each, fixed seeds),
  graded per population with `klt yield` against the *proposed* 1.764–1.836 V
  window. It includes a deterministic VREF negative control, a sampler
  control (mismatch off), MOS-vs-resistor attribution and an independent
  reproduction job. All simulation runs as `klt sim` requests on the batch
  fleet. Row 2 stays Open and row 8 is deferred (#63), so this does not
  discharge T1 item 6 (see that README and `signoff/README.md`).
