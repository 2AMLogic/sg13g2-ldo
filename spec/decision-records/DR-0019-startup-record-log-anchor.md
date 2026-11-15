# DR-0019: Startup record rows do not carry a log anchor — the `raw_sha256`/log asymmetry is deliberate

- **Status**: **Decided: no log anchor.** Startup campaign record rows carry
  `raw_sha256` and will not carry a `log_sha256` (or any other klt/ngspice log
  hash). This record exists so a future dead-code or provenance scan that
  rediscovers the asymmetry — rawfile anchored, log not — reads this before
  refiling it as a gap, and so the never-read `lg` binding in
  `sim/ldo-cmos5l-pvt-sweep/startup_campaign.py` (deleted by #232) is not
  restored as "the obvious place a log anchor was meant to go". It authorizes
  no circuit change, no simulation, no layout work and no spec/window change;
  no threshold, CI gate, record or verdict is loosened.
- **Date**: 2026-11-15 (evidence snapshot: `origin/main` `630a6e77`,
  2026-11-15)
- **Scope**: the startup campaign's record schema only
  (`sim/ldo-cmos5l-pvt-sweep/startup_campaign.py` row assembly and the
  `<rid>-startup-<stage>.csv` rows it writes). Issue #238. Other campaigns are
  untouched: `sim/ldo-cmos5l-monte-carlo/` and
  `sim/ldo-cmos5l-pvt-sweep/corners/` commit their logs outright and have no
  asymmetry to fix. **Zero new simulations were run**; the evidence below is
  read out of already-committed files.

## Evidence

All line numbers are `sim/ldo-cmos5l-pvt-sweep/startup_campaign.py` @
`630a6e77`; #232 shifts them — re-locate by content (`grep -n 'raw_sha256'`),
not by line.

1. **The log's informative content is already committed — beside the ignored
   artifacts, not inside them.** `.gitignore` excludes only
   `sim/*/startup/**/artifacts/` (the ~2 MB rawfiles); the per-corner klt
   `report.json` next to it **is** committed (93 files tracked). The cited
   report
   (`sim/ldo-cmos5l-pvt-sweep/startup/20261010-075612-91e92aa/grid/g001_v2970mv_i1ma_c1000nf_e0mohm_t1000ns_T27/report.json`)
   carries, at top level and per corner:

   - `environment.engine` = `"ngspice"`, `environment.ngspice_binary`,
     `environment.models_lib_sha256`, `environment.netlist_sha256`
     (`environment.engine_version` is `null` in this report — engine identity
     survives via the other fields);
   - per-corner `diagnostics[]` (here `{"severity": "error", "code":
     "timeout", "message": "ngspice did not complete within 150s, killed"}`)
     and a top-level `diagnostic_counts`
     (`{"timeout": 15, "measurement": 15}`, `{"error": 30}`,
     `corners_with_diagnostics: 15}`).

   Engine identity and convergence diagnostics are therefore **not** log-only;
   the original "for" argument ("the log is the only place the rest of that
   context survives") is false.

2. **The slot the dropped `lg` binding occupies cannot anchor the logs that
   matter.** The binding (`lg = (c.get("artifacts") or {}).get("log")`, `:464`)
   sits inside `if raw and os.path.isfile(raw):` (`:460`), one line above
   `row["raw_sha256"] = sha256_file(raw)` (`:465`). In the cited report **all
   15 corners** are `status: "error"` with `artifacts.raw == null` and
   `artifacts.log` non-null — a `log_sha256` written in that slot would be
   empty on precisely the corners whose logs carry the convergence story, and
   populated only where the rawfile already parsed. Anchoring the failing
   corners would require moving the harvest out of the `if raw` branch — a
   source change this decision exists to not make.

3. **A hash of an unkept artifact buys no provenance.** The startup log is
   deleted with the artifacts; the committed `artifacts.log` value in the
   cited report is an absolute path into a since-removed
   `.loom/worktrees/issue-69/` tree, so it cannot be used to find one; startup
   logs are not byte-stable across runs; and there is no committed log to diff
   a hash against. A hash you cannot diff is not provenance.

4. **The cost side is real.** `startup_campaign.py` is hash-pinned
   (`signoff/evidence/item9-testbenches.inventory.json`), so the "yes" branch
   pays the `signoff/README.md#regenerating` cycle, and a new column forks the
   row schema against the 11 already-landed `*-startup-*.manifest.json`
   records (`sim/*/records/**` is append-only).

## Decision (ratified by issue #238)

1. **No `log_sha256` column.** Startup rows anchor the rawfile
   (`raw_sha256`) and the reduced trace (`trace_sha256`) only. The log is
   deliberately unanchored.
2. **The dead `lg` binding stays deleted** once #232 lands. It is an
   abandoned first draft from the file's introducing commit, not a
   half-finished anchor; do not restore it.
3. **The committed per-corner klt `report.json` is the log's proxy**: engine
   identity, model/netlist hashes, per-corner diagnostics and diagnostic
   counts live there. A scan looking for "log provenance" in the startup
   campaign should look there, not at the record rows.
4. **If byte-level log retention is ever needed**, the repo's established
   answer is committing the log itself, monte-carlo style
   (`!sim/*/corners/**/*.log`; 104 logs under
   `sim/ldo-cmos5l-monte-carlo/corners/`, 5,337 under
   `sim/ldo-cmos5l-pvt-sweep/corners/`) — strictly better than hashing, and a
   separate issue if the committed `report.json` ever proves insufficient.
   Not done here.

## Reopen conditions

Reopen (new DR) if any of the following holds:

- per-corner `report.json` stops being committed, or drops
  `environment.*`/`diagnostics[]`/`diagnostic_counts`, removing the log's
  committed proxy;
- a ratified need for byte-level log provenance (not just content) appears;
- the startup campaign adopts monte-carlo-style log retention, making an
  anchor diffable (then prefer the committed log over a hash column).

## Consequences

- `startup_campaign.py`, the startup README row-contract prose
  (`write_md`'s "## Points"), `_IDENT_COLS`, every inventory, envelope and
  T1 report are untouched: this decision is cycle-free by design (no
  completeness glob covers `spec/**`; no DR is pinned by path).
- This record is intentionally not indexed in `spec/README.md`: that file is
  hash-pinned (`item10-repo-hygiene.inventory.json`) and its index is
  selective, not exhaustive (DR-0008, DR-0015, DR-0016, DR-0017 are likewise
  absent).
- `python3 sim/tools/check_append_only.py --base origin/main` and
  `python3 signoff/evidence_inventory.py check` both stay green with no
  inventory edit.
