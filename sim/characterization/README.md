# sim/characterization/ — per-spec-row characterization aggregate (T1 item 8)

One command turns the committed `sim/` records into one aggregated,
per-target-row report and the `kind: generic` envelope that
[`signoff/sg13g2-ldo.json`](../../signoff/sg13g2-ldo.json) cites for T1 item 8
(issue #58, part of #5). It is an **aggregation**, not an experiment: it
mints no `records/` entry, reruns no simulator, needs no PDK, and never edits
a historical record.

## Cold start

Any clean checkout, `python3` >= 3.9, nothing else installed:

```bash
python3 sim/characterization/generate.py          # regenerate the three outputs
python3 sim/characterization/generate.py --check  # verify they reproduce byte-for-byte (CI)
python3 -m unittest discover -s sim/characterization -p 'test_*.py'   # fixtures + negative controls
```

After regenerating, update the item-8 `content_hash` in
`signoff/sg13g2-ldo.json` to the envelope's `provenance.input.content_hash`
and regenerate `signoff/sg13g2-ldo.t1-report.json` with the pinned grading
build ([`signoff/README.md`](../../signoff/README.md)).

| File | What |
|---|---|
| `selection.json` | **Input.** The explicit record selection, bench conditions, design-freshness pins, and the selection policy. |
| `generate.py` | The generator and `--check` gate. |
| `characterization-report.json` | Canonical aggregate: per row — target, stretch, ratification, verdict, coverage gaps, per-metric worst case with its (process, temperature, resistor corner), bench conditions, counts, source record/column. Also every source path + sha256. |
| `characterization-report.md` | The same content rendered for reading. |
| `characterization-envelope.json` | The klt generic envelope (`schema_version: 1`, `kind: generic`, `status`, `source`, `t1_item: 8`, `provenance`). |
| `test_generate.py` | Row mapping, unit conversion, worst-case retention, censored dropout, ambiguous crossings, draft/stale classification, and the negative controls. |

## Selection policy (reproducible, never filesystem order)

`selection.json` names one circuit record by id and pins each file by sha256.
The generator never lists a directory to choose a record. A missing record or
bytes that differ from the pin is a hard error. Moving to a newer record
(e.g. when #55/#56/#57 land) is a deliberate edit to `selection.json` in the
same change that regenerates the artifact. Older records are not read, except
one quoted sentence from `sim/ldo-cmos5l-pvt-sweep/README.md` that is shown as
*superseded* context for Iq at full load, never as a current measurement. The
bare pass-device screen is used only as labelled device context on the Input
row, never as a closed-loop measurement.

## What the envelope verdict means (and does not)

`status: pass` means the **artifact is complete and fresh**:

- all ten target rows appear exactly once with an explicit verdict, taken from
  `README.md`'s target table (target text is checked against the thresholds
  coded in `generate.py`; a target edit is a spec change and is refused until
  reviewed) and cross-checked against DR-0007's disposition table;
- every selected record matches its pin; the 45-point process × temperature ×
  resistor-corner grid is whole and numeric;
- the selected record is current against the design netlists (hash pins taken
  from DR-0007's evidence base). If either netlist changes, evidence becomes
  `stale_against_design` and the envelope turns `fail` until a new record is
  selected.

It does **not** mean the circuit meets its spec. Row verdicts are reported
separately and today include `not_measured` (Input), `pass_partial_coverage`
(Output, Load, Line/load, PSRR, Iq), `pass_full_coverage` (Dropout, the one
ratified row), `ambiguous` (Stability) and `not_implemented` (Current limit,
Startup). A `pass_*` verdict is a measurement against the target at the
stated conditions only; nine of ten targets are still unratified (DR-0007).
`klt signoff` trusts the envelope's status and does not read the report;
the `--check` gate here and in CI is what verifies content and freshness.

Principles the report enforces:

- **Measured failure vs missing vs draft vs old design** are distinct states
  (`fail`, `not_measured`/`not_implemented`, `ratification.state`,
  `evidence_state`).
- **Censored dropout**: points sitting on the sweep floor are upper bounds,
  counted and flagged; a stretch target is not credited from them.
- **Ambiguous AC crossings**: points with more than one 0 dB crossing are not
  scored for phase margin; the first-crossing scalar and the record's
  unresolved `phase_margin_worst_deg` are shown beside the count.
- **Single AC condition** (1 mA, 1 µF, ESR 0, Vin 3.30 V, nominal `Cc`) is
  stated on every AC metric and is never extrapolated to the Cout/ESR/load
  window.
- **Post-layout**: no performance metric exists post-layout; `layout/` reports
  are DRC/LVS/ERC and are not inferred from.

## Failure behaviour

On any generator error (missing/changed record, non-numeric field, malformed
table, README/DR-0007 disagreement) the generator prints the reason, rewrites
`characterization-envelope.json` as `status: fail` with no provenance, and
exits 1 — a previously committed passing envelope is never left standing. In
`--check` mode it changes nothing and exits 1 on any drift, missing file,
tampered report, envelope/report hash mismatch, or incomplete artifact.
