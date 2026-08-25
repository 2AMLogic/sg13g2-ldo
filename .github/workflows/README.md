# CI workflows

## `ci.yml`

Runs on every push to `main`, every pull request, and on manual
`workflow_dispatch`. It runs the one self-check that exists in this repo
today — nothing more.

### What it checks

- **`python3 design/netlist.py --check`** — re-runs the `xschem` netlist
  export for every cell in `design/*.sch` into a scratch directory and:
  1. diffs the result against the committed `design/netlist/*.spice`
     byte-for-byte (catches a schematic edit whose export was never
     re-run, and confirms the export is machine-independent/reproducible);
  2. fails if `xschem`'s own electrical rule check (`xschem netlist -erc`)
     reports an undriven node, an open net, a shorted node/pin, or a
     missing symbol (`design/netlist.py`'s own module docstring documents
     why this is scraped from stdout/stderr rather than trusted to the
     exit code alone);
  3. fails if the `ldo_core` top-level pinout, or any cell's symbol-pin-vs-
     schematic-port order, has drifted from the interface `design/README.md`
     documents.

To do any of that, the job needs `xschem >= 3.4.7` on `PATH` and a real
`ihp-sg13g2` PDK install — `design/netlist.py --check` isn't a syntax check,
it's a reproducibility + ERC check against the actual PDK. The workflow:

1. Checks out this repo, plus a **pinned** ref (`v0.3.0`) of
   `2AMLogic/klayout-tools`, solely to reuse that repo's
   `scripts/fetch-ihp-sg13g2.sh` — a checksum-verified fetch of a pinned
   IHP-Open-PDK release (`v0.3.0`; Apache-2.0). This repo does not carry its
   own copy of that fetch/pin logic, so it can never drift out of sync with
   `klayout-tools`' own.
2. **Builds xschem 3.4.7 from source** rather than `apt-get install xschem`.
   Ubuntu 24.04's apt package (3.4.4-1) has a `top_is_subckt` regression —
   it emits a double-comment-prefixed `**.subckt`/`**.ends` wrapper for the
   top-of-invocation cell instead of an active one, even though
   `design/xschemrc` sets `top_is_subckt 1`. `netlist.py` netlists every
   cell individually (each is the "top of invocation" for its own xschem
   run), so this breaks `--check` on every cell, not just `ldo_core` — see
   `design/README.md`'s Requirements note for the full root cause (the
   identical regression `2AMLogic/gf180-temp-por` hit and fixed, its own
   issue #89 / PR #95). The workflow asserts the built `xschem --version`
   string so a future xschem release accidentally changing this fails
   loudly instead of silently drifting.
3. Caches the fetched PDK (`actions/cache`, keyed on the pinned version) so
   the ~350 MB download only happens once per cache generation, not on
   every run.
4. Runs `python3 design/netlist.py --check -v` with `PDK_ROOT`/`PDK`
   pointed at the fetched install.

Runnable locally the same way, once you have `xschem` and an `ihp-sg13g2`
PDK installed (see `design/README.md` → "Exporting the netlist" for local
setup, including the same `PDK_ROOT`/`PDK` search-root convention this
workflow's own env vars use):

```bash
python3 design/netlist.py --check
```

### Why the PDK-backed check runs on every push/PR, unlike `gf180-ldo`'s CI

`2AMLogic/gf180-ldo`'s own `ci.yml` splits a PDK-free `harness-selftest` job
(every push/PR) from a PDK-backed `pvt-smoke` job (gated to
schedule/`workflow_dispatch`/an opt-in PR label), specifically so a normal
PR never pays for a PDK fetch it doesn't need. This repo has no such
PDK-free tier to split off `design/netlist.py --check` from: the check
*is* the PDK-backed xschem export, there is no cheaper subset of it that
runs without a PDK, and no `sim/` harness exists yet to fill that role (see
`ci.yml`'s own header comment). Gating the only check this repo has would
mean an ordinary PR runs no CI at all — the opposite of this workflow's
purpose (issue #8: catch a schematic edit that forgot to re-run the export,
or that broke ERC, before it lands on `main`). So it runs unconditionally,
with `actions/cache` absorbing the repeat-fetch cost instead.

### What it does NOT check (known gaps)

- **No `sim/` harness self-test.** `sim/` has no testbench yet (issue #8's
  own Non-goals, and `sim/README.md` as of this workflow's introduction).
  Add an equivalent CI step once one lands.
- **No linter/formatter.** `package.json`'s `lint` and `check:ci` scripts
  are honest "not configured" placeholders. Add a CI job for either if/when
  one is adopted.
- **No layout/DRC/LVS checks.** `layout/` has no artifacts yet; this
  workflow only covers `design/`.
