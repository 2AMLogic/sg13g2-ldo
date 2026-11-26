#!/usr/bin/env python3
"""Aggregate per-spec-row characterization report + klt generic envelope (T1 item 8).

Offline, stdlib-only, deterministic. Reads ONLY committed files (no PDK, no
simulator, no network, no git): the explicitly selected sim records named in
``selection.json``, the README target table, and DR-0007. Writes three files
next to this script:

  characterization-report.json   canonical aggregate (machine-readable)
  characterization-report.md     the same content rendered for humans
  characterization-envelope.json klt ``kind: generic`` envelope for item 8

Cold start (any clean checkout, python3 >= 3.9, nothing else installed):

  python3 sim/characterization/generate.py          # (re)generate
  python3 sim/characterization/generate.py --check  # CI: regenerate in memory,
                                                    # fail on any drift/error

What the envelope verdict means
-------------------------------
``status: pass`` means ONE thing: the characterization ARTIFACT is complete and
fresh -- every target-spec row appears exactly once with an explicit state,
every selected source file exists and matches its pinned hash, the grid is
whole, and the selected record is current against the design netlists. It does
NOT mean the circuit meets its spec: rows that honestly measure as failing,
ambiguous, unmeasured or unimplemented are listed as such inside a "pass"
artifact. ``status: fail`` means the artifact itself is incomplete or stale.
klt's generic grader trusts this verdict and never reads the report, so this
generator (and the ``--check`` CI gate) is where the content is verified.

Error discipline: any generator error (missing record, hash mismatch, bad
numeric field, malformed table) prints the reason, rewrites the envelope as
``status: fail`` with no provenance, and exits non-zero -- a previously
committed passing envelope is never left standing next to a failed run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import traceback
from pathlib import Path

# Resolve imports from this checkout when invoked by path or imported as generate.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Some helpers are re-exported for callers that import generate directly.
from sim.characterization.common import (
    CORNERS,
    DEFAULT_ROOT,
    ENVELOPE_JSON,
    EXPECTED_ROWS,
    GENERATOR_VERSION,
    PVT_NUMERIC,
    REPORT_JSON,
    REPORT_MD,
    RES,
    ROW7_TARGET_A,  # noqa: F401
    ROW_VERDICTS,
    TEMPS,
    GenError,
    cc_window,
    load_selection,
    metric,  # noqa: F401
    num,
    pinned,
    point_id,
    read_csv,
    sha256_file,
    unpinned,
)
from sim.characterization.loaders import (
    STARTUP_BAND_HI_V,  # noqa: F401
    _fmt_hz,  # noqa: F401
    _pdk_pin_projection_sha256,  # noqa: F401
    _trace_ceiling_hz,  # noqa: F401
    load_dc_informational,
    load_row5_envelope,
    load_row7_envelope,
    load_row10,
    load_startup,
    startup_row_verdict,  # noqa: F401
)
from sim.characterization.rows import (
    RowContext,
    row_1_input,
    row_2_output,
    row_3_load,
    row_4_dropout,
    row_5_regulation,
    row_6_psrr,
    row_7_iq,
    row_8_current_limit,
    row_9_startup,
    row_10_stability,
)

# --------------------------------------------------------------------------- #
# spec tables
# --------------------------------------------------------------------------- #

_SPLIT = re.compile(r"(?<!\\)\|")


def _table_rows(text: str, header_prefix: str) -> list[list[str]]:
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith(header_prefix):
            out = []
            for body in lines[i + 2:]:
                if not body.startswith("|"):
                    break
                cells = [c.strip() for c in _SPLIT.split(body.strip())[1:-1]]
                out.append(cells)
            return out
    raise GenError(f"table with header {header_prefix!r} not found")


def parse_readme(text: str) -> list[dict]:
    rows = _table_rows(text, "| Parameter | Target | Stretch |")
    if len(rows) != len(EXPECTED_ROWS):
        raise GenError(f"README target table has {len(rows)} rows, expected {len(EXPECTED_ROWS)}")
    out = []
    for n, (cells, (name, target)) in enumerate(zip(rows, EXPECTED_ROWS), 1):
        if len(cells) != 4:
            raise GenError(f"README row {n} has {len(cells)} cells, expected 4")
        if cells[0] != name:
            raise GenError(f"README row {n} parameter {cells[0]!r} != expected {name!r}")
        if cells[1] != target:
            raise GenError(
                f"README row {n} ({name}) target text changed: {cells[1]!r} != "
                f"{target!r}. A target edit is a spec change; review the "
                f"grading thresholds before updating EXPECTED_ROWS.")
        status = cells[3]
        if status.startswith("RATIFIED"):
            state = "ratified"
        elif status.startswith("OPEN"):
            state = "open_unratified"
        else:
            raise GenError(f"README row {n} status not RATIFIED/OPEN: {status!r}")
        out.append({"id": n, "parameter": name, "target": target,
                    "stretch": cells[2], "readme_status": status,
                    "ratification": state})
    return out


def parse_dr7(text: str) -> dict[int, dict]:
    rows = _table_rows(text, "| # | Row | Current target |")
    out = {}
    for cells in rows:
        if len(cells) < 6 or not cells[0].isdigit():
            raise GenError(f"DR-0007 disposition row malformed: {cells[:2]}")
        n = int(cells[0])
        disp = cells[3].replace("*", "").strip()
        if disp.startswith("Ratified"):
            state = "ratified"
        elif disp.startswith("Open"):
            state = "open_unratified"
        else:
            raise GenError(f"DR-0007 row {n} disposition unrecognized: {disp!r}")
        typ = cells[4].replace("*", "").strip()
        if typ not in ("D", "S"):
            raise GenError(f"DR-0007 row {n} type not D/S: {typ!r}")
        if n in out:
            raise GenError(f"DR-0007 row {n} appears twice")
        out[n] = {"name": cells[1], "disposition": disp, "state": state, "type": typ}
    return out


def _row_context(root: Path) -> RowContext:
    """Load and validate everything the ten row graders share.

    Any pin mismatch, malformed table or incomplete grid raises GenError here,
    before a single row is graded."""
    sel = load_selection(root)
    sources: list[dict] = []
    rec = sel["circuit_record"]
    pvt_path = pinned(root, rec["files"]["pvt_csv"], "circuit_pvt_csv", sources)
    pinned(root, rec["files"]["record_md"], "circuit_record_md", sources)
    cc_path = pinned(root, rec["files"]["cc_tolerance_csv"], "circuit_cc_tolerance_csv", sources)
    dev = sel["device_context_record"]
    dev_path = pinned(root, dev["files"]["screening_csv"], "bare_device_screening_csv", sources)
    readme_rel = sel["spec_sources"]["target_table"]
    dr_rel = sel["spec_sources"]["ratification"]
    readme_path = unpinned(root, readme_rel, "target_table", sources)
    dr_path = unpinned(root, dr_rel, "ratification_record", sources)

    # design freshness
    fresh_checks = []
    stale = False
    for pin in rec["design_freshness_pins"]:
        p = root / pin["path"]
        if not p.is_file():
            raise GenError(f"design freshness pin target missing: {pin['path']}")
        actual = sha256_file(p)
        ok = actual == pin["sha256"]
        stale |= not ok
        fresh_checks.append({"path": pin["path"], "pinned_sha256": pin["sha256"],
                             "actual_sha256": actual, "matches": ok})
        sources.append({"role": "design_netlist_freshness", "path": pin["path"],
                        "sha256": actual, "pinned": True})
    evidence_state = "stale_against_design" if stale else "current"

    # spec tables
    readme_rows = parse_readme(readme_path.read_text(encoding="utf-8"))
    dr7 = parse_dr7(dr_path.read_text(encoding="utf-8"))
    if sorted(dr7) != list(range(1, len(EXPECTED_ROWS) + 1)):
        raise GenError(f"DR-0007 rows {sorted(dr7)} do not cover 1..{len(EXPECTED_ROWS)} exactly once")
    for r in readme_rows:
        d = dr7[r["id"]]
        if d["state"] != r["ratification"]:
            raise GenError(
                f"row {r['id']} ({r['parameter']}): README says {r['ratification']} "
                f"but DR-0007 disposition is {d['state']}")
        r["dr0007_disposition"] = d["disposition"]
        r["dr0007_type"] = "deterministic" if d["type"] == "D" else "statistical"

    # PVT data
    prow = read_csv(pvt_path)
    grid = {(r.get("corner"), r.get("temp_c"), r.get("res_section")) for r in prow}
    want = {(c, str(t), s) for c in CORNERS for t in TEMPS for s in RES}
    if len(prow) != len(want) or grid != want:
        raise GenError(
            f"PVT grid incomplete or malformed: {len(prow)} rows, "
            f"missing {sorted(want - grid)[:3]}..., unexpected {sorted(grid - want)[:3]}...")
    for i, r in enumerate(prow):
        for k in PVT_NUMERIC:
            num(r, k, f"pvt row {i + 2}")
        if r.get("line_reg_in_regulation") not in ("True", "False"):
            raise GenError(f"pvt row {i + 2}: line_reg_in_regulation not True/False")
    pvt_rel = rec["files"]["pvt_csv"]["path"]
    pid = [point_id(r) for r in prow]
    dcev = load_dc_informational(root, sel, rec, prow, sources)
    dc_rel = dcev["summary_path"]
    su = load_startup(root, sel, sources)
    r10 = load_row10(root, sel, rec, prow, sources)
    r7 = load_row7_envelope(root, sel, prow, dcev, sources)
    r5 = load_row5_envelope(root, sel, prow, dcev, sources)

    def dc_col(name, scale=1.0, valid=None):
        """(values, ambiguous-index-set) over the pvt row order. Invalid points
        stay in the data and are returned as the ambiguous set."""
        pts, bad = [], set()
        for i, r in enumerate(prow):
            vals, vflags = dcev["by_key"][(r["corner"], r["temp_c"], r["res_section"])]
            pts.append((vals[name] * scale, pid[i]))
            if valid is not None and not vflags[valid]:
                bad.add(i)
        return pts, bad

    def col(k):
        return [(num(r, k, "pvt"), pid[i]) for i, r in enumerate(prow)]

    bc = rec["bench_conditions"]
    ac_cond = bc["ac_loopgain_and_psrr"]

    ccw = cc_window(read_csv(cc_path))
    cc_tol_rel = rec["files"]["cc_tolerance_csv"]["path"]

    R = {r["id"]: r for r in readme_rows}

    # Row 7 quotes a superseded full-load Iq figure. Validating and anchoring
    # that statement is context work, not grading: doing it here keeps every
    # row grader a pure function of its context (#240).
    sup = sel["superseded_evidence"][0]
    sup_text = unpinned(root, sup["statement_source"], "superseded_evidence_statement", sources)
    if sup["quoted_substring"] not in sup_text.read_text(encoding="utf-8"):
        raise GenError(f"superseded evidence quote not found in {sup['statement_source']}")

    return RowContext(root=root, sel=sel, rec=rec, dev=dev, prow=prow, pid=pid,
                      bc=bc, ac_cond=ac_cond, R=R, dr_rel=dr_rel, pvt_rel=pvt_rel,
                      dc_rel=dc_rel, dev_path=dev_path, evidence_state=evidence_state,
                      stale=stale, fresh_checks=fresh_checks, sources=sources,
                      dcev=dcev, su=su, r10=r10, r7=r7, r5=r5, ccw=ccw, cc_tol_rel=cc_tol_rel,
                      col=col, dc_col=dc_col)


def _assemble_outputs(ctx: RowContext, rows: list) -> tuple[dict, dict]:
    """Run the completeness checks and assemble the report and envelope (the
    former tail of ``build``)."""
    sources = ctx.sources
    su = ctx.su

    # --- completeness ----------------------------------------------------
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # The four checks hard-coded True below are enforced upstream, in
    # _row_context and the loaders it calls: any violation raises GenError
    # (and main() writes a status:fail envelope) before this point, so
    # reaching here means they held. They are listed for the record.
    chk("all selected records exist and match their sha256 pins", True,
        f"{sum(1 for s in sources if s['pinned'])} pinned sources verified")
    chk("README target table: 10 rows, expected names and target text", True)
    chk("DR-0007 ratification table covers rows 1-10 exactly once and agrees with README", True)
    chk("PVT grid complete (5 process x 3 temperature x 3 resistor corner = 45 points, all numeric fields finite)", True)
    chk("DC informational summary: pinned, same record, 45 corners once each, finite, validity fields True/False, "
        "raw grids match inventory hashes", True)
    chk("row-7 graded envelope: pinned, whole clean 45-corner matrix, six limits-bearing "
        "measurements tagged dr0007-row7-iq, every (Vin, Iload) step ok, summary agrees "
        "with the report, agrees with the legacy columns at Vin 3.30 V", True)
    chk("row-7 envelope is current against the design netlists and the PDK pin", not ctx.r7["stale_components"],
        "the envelope's recorded design-netlist hashes and PDK pin projection match the tree" if not ctx.r7["stale_components"]
        else "stale against the design / PDK pin: " + ", ".join(ctx.r7["stale_components"]))
    if ctx.r5 is None:
        chk("row-5 graded envelope: no record selected; the gap is stated in the row and "
            "earns no envelope credit", True, "selection.json has no row5_envelope_evidence")
    else:
        chk("row-5 graded envelope: pinned, whole clean 45-corner matrix, six limits-bearing "
            "measurements tagged dr0007-row5-line-load-regulation, every named (Vin, Iload) step "
            "ok, strictly below target, summary agrees with the report, agrees with the offline "
            "DC columns", True)
        chk("row-5 envelope is current against the design netlists and the PDK pin",
            not ctx.r5["stale_components"],
            "the envelope's recorded design-netlist hashes and PDK pin projection match the tree"
            if not ctx.r5["stale_components"]
            else "stale against the design / PDK pin: " + ", ".join(ctx.r5["stale_components"]))
    chk("every target row appears exactly once", sorted(r["id"] for r in rows) == list(range(1, 11)),
        f"rows: {[r['id'] for r in rows]}")
    chk("every row carries an allowed verdict", all(r["verdict"] in ROW_VERDICTS for r in rows))
    chk("every row cites a source or an explicit unavailability reason",
        all(all(("source" in m and m["source"]) or m.get("reason") for m in r["metrics"]) for r in rows))
    chk("startup campaign: selected record, csv, manifest and every trace match their pins; no duplicate or "
        "unexpected point; manifest agrees with the csv", True,
        f"{su['n_requested']} requested points, {len(su['points'])} result rows")
    chk("startup campaign has a result row for every requested point", not su["missing"],
        f"{len(su['missing'])} of {su['n_requested']} requested points missing")
    chk("startup evidence is current against the design (core and error amplifier checked independently)",
        not su["stale_components"],
        "core and error-amplifier netlist hashes match the startup freshness pins" if not su["stale_components"]
        else "stale against the design: " + ", ".join(su["stale_components"]))
    chk("selected record is current against the design netlists", not ctx.stale,
        "design netlist hashes match the freshness pins" if not ctx.stale
        else "design netlist changed since the selected record: select a newer record")
    failures = [c for c in checks if not c["ok"]]
    complete = not failures

    tally: dict = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    ratified = [r["id"] for r in rows if r["ratification"]["state"] == "ratified"]

    report = {
        "schema_version": 1,
        "title": "sg13g2-ldo per-spec-row characterization report (T1 item 8)",
        "generator": {"path": "sim/characterization/generate.py", "version": GENERATOR_VERSION},
        "purpose_and_limits": [
            "This is a CHARACTERIZATION report: one aggregated, current artifact summarizing per-row performance and citing the record behind each verdict.",
            "Completeness is not compliance. The artifact can be complete and fresh while rows fail, are ambiguous, unmeasured or unimplemented; the envelope verdict reports artifact completeness only.",
            "Open (unratified) targets are not passing requirements; a numeric 'pass' on an open row is a measurement against a draft target at the stated conditions.",
            "All closed-loop numbers are SG13CMOS5L-branch evidence (DR-0007 'What evidence exists'); no closed-loop evidence exists on the SG13G2 branch.",
            "No post-layout (extracted) performance evidence exists for any row; layout reports in layout/ are DRC/LVS/ERC and carry no performance metrics.",
            "Row 9 (Startup) reports the explicitly selected committed startup campaign: measured failures are measured failures, missing or insufficient points are never passes, and the evaluation methodology is PROPOSED (DR-0009), not ratified. Row 9 stays Open.",
            "Row 10 (Stability) PM/GM verdicts follow the PROPOSED margin classification DR-0014, applied offline to the selected record's committed loop-gain traces: a miss inside the sweep is a fail, a pass needs a bounded sweep ceiling, everything else stays ambiguous with its reason. Row 10 stays Open.",
            "Other T1 items are not declared satisfied by this artifact.",
        ],
        "selection": {
            "file": "sim/characterization/selection.json",
            "sha256": sha256_file(ctx.root / "sim/characterization/selection.json"),
            "circuit_record_id": ctx.rec["id"],
            "experiment": ctx.rec["experiment"],
            "device_context_record_id": ctx.dev["id"],
            "startup_record_id": su["rid"],
            "startup_stage": su["cfg"]["stage"],
            "policy": ctx.sel["policy"],
        },
        "sources": sorted(sources, key=lambda s: (s["role"], s["path"])),
        "design_freshness": {"state": ctx.evidence_state, "basis": ctx.rec["design_freshness_basis"],
                             "pins": ctx.fresh_checks},
        "bench_conditions": ctx.bc,
        "cc_tolerance_window": ctx.ccw,
        "dc_informational_evidence": {
            "summary": ctx.dc_rel, "inventory": ctx.dcev["inventory_path"],
            "raw_dc_grids_verified": ctx.dcev["n_raw_grids"], "points": 45,
            "status": "informational only; rows 5 and 7 remain Open/unratified; not item-5 grading evidence",
        },
        "rows": rows,
        "summary": {
            "rows_total": len(rows),
            "rows_by_verdict": dict(sorted(tally.items())),
            "ratified_rows": ratified,
            "open_unratified_rows": [r["id"] for r in rows if r["id"] not in ratified],
            "rows_with_any_coverage_gap": [r["id"] for r in rows if r["coverage"]["gaps"]],
            "rows_with_full_coverage_of_target_as_written": [r["id"] for r in rows if r["coverage"]["state"] == "full"],
        },
        "completeness": {"status": "complete" if complete else "incomplete", "checks": checks,
                         "meaning": "Artifact completeness/freshness only -- NOT circuit spec compliance."},
    }
    report_bytes = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    report_hash = hashlib.sha256(report_bytes).hexdigest()

    envelope = {
        "schema_version": 1,
        "kind": "generic",
        "status": "pass" if complete else "fail",
        "summary": (
            "T1 item 8 characterization artifact: all 10 target-spec rows present once with explicit "
            "verdicts, pinned sources verified, evidence current against the design. Verdict covers "
            "artifact completeness/freshness only, NOT circuit spec compliance; row verdicts: "
            + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
        if complete else
        "T1 item 8 characterization artifact INCOMPLETE or STALE: "
        + "; ".join(c["check"] for c in failures),
        "source": f"sim/characterization/{REPORT_MD}",
        "t1_item": 8,
        "verdict_semantics": (
            "pass = the characterization artifact is complete and fresh (every target row present "
            "exactly once with an explicit state, every selected source verified against its pin, "
            "the PVT grid whole, the record current against the design netlists). It is NOT a claim "
            "that the circuit meets its spec: failing, ambiguous, unmeasured, unimplemented and "
            "unratified rows are listed as such in the report. klt does not read `source`; this "
            "repository's generator and CI verify the content."),
        "provenance": {
            "klt_version": None, "klayout_version": None, "pdk": None, "deck": None,
            "input": {"content_hash": f"sha256:{report_hash}", "role": "characterization-report"},
            "generator": {"path": "sim/characterization/generate.py", "version": GENERATOR_VERSION},
        },
    }
    return report, envelope


def build(root: Path) -> tuple[dict, dict, str]:
    """Return (report, envelope, markdown). Raises GenError on any hard error."""
    ctx = _row_context(root)
    rows = [
        row_1_input(ctx),
        row_2_output(ctx),
        row_3_load(ctx),
        row_4_dropout(ctx),
        row_5_regulation(ctx),
        row_6_psrr(ctx),
        row_7_iq(ctx),
        row_8_current_limit(ctx),
        row_9_startup(ctx),
        row_10_stability(ctx),
    ]
    report, envelope = _assemble_outputs(ctx, rows)
    md = render_md(report, envelope)
    return report, envelope, md


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #

def _fmt_at(at):
    if not at:
        return "-"
    base = f"{at['corner']}/{at['temp_c']}C/{at['res_section']}"
    if "vin_v" in at and "load_ma" in at:
        base += (f"/Vin {at['vin_v']:g}V/{at['load_ma']:g}mA/{at['cout_nf']:g}nF/"
                 f"ESR {at['esr_mohm']:g}mohm")
    elif "vin_v" in at:
        # row-7 envelope points: corner + supply, load state is in the metric
        base += f"/Vin {at['vin_v']}V"
    return base


def render_md(rep: dict, env: dict) -> str:
    L = []
    w = L.append
    w(f"# {rep['title']}")
    w("")
    w("<!-- GENERATED by sim/characterization/generate.py -- do not edit; CI regenerates and diffs. -->")
    w("")
    w(f"**Artifact completeness: {rep['completeness']['status'].upper()}** "
      f"(envelope status `{env['status']}`). This verdict is about the artifact, "
      "**not** about whether the circuit meets its spec.")
    w("")
    for s in rep["purpose_and_limits"]:
        w(f"- {s}")
    w("")
    w("## Selection and sources")
    w("")
    sel = rep["selection"]
    w(f"- Circuit record (explicitly selected, hash-pinned): `{sel['experiment']}` / `{sel['circuit_record_id']}`")
    w(f"- Bare-device context record: `{sel['device_context_record_id']}` (never used as a closed-loop measurement)")
    w(f"- Startup campaign (explicitly selected, hash-pinned, proposed methodology): `{sel['startup_record_id']}` stage `{sel['startup_stage']}`")
    w(f"- Selection file: `{sel['file']}` sha256 `{sel['sha256']}`")
    w(f"- Design freshness: **{rep['design_freshness']['state']}**")
    w("")
    w("| Role | Path | sha256 | Pinned |")
    w("|---|---|---|---|")
    for s in rep["sources"]:
        w(f"| {s['role']} | `{s['path']}` | `{s['sha256']}` | {'yes' if s['pinned'] else 'recorded'} |")
    w("")
    w("## Per-row summary")
    w("")
    w("| # | Parameter | Target | Ratification | Verdict | Coverage | Evidence |")
    w("|---|---|---|---|---|---|---|")
    for r in rep["rows"]:
        w(f"| {r['id']} | {r['parameter']} | {r['target']} | {r['ratification']['state']} "
          f"({r['ratification']['dr0007_type']}) | **{r['verdict']}** | {r['coverage']['state']} | {r['evidence_state']} |")
    w("")
    w("Verdict key: `pass_*` = measured metrics meet the bound at the stated conditions (not a compliance "
      "claim); `fail` = a measured point violates the bound; `ambiguous` = scalar not trustworthy at some "
      "points; `not_measured` = no current measurement; `not_implemented` = function absent from the design.")
    w("")
    w("## Rows in detail")
    for r in rep["rows"]:
        w("")
        w(f"### {r['id']}. {r['parameter']} -- {r['verdict']}")
        w("")
        w(f"- Target: {r['target']}; stretch: {r['stretch']}")
        w(f"- Ratification: {r['ratification']['state']} (README: {r['ratification']['readme_status']}; "
          f"DR-0007: {r['ratification']['dr0007_disposition']}, {r['ratification']['dr0007_type']})")
        if r["stretch_note"]:
            w(f"- Stretch: {r['stretch_note']}")
        for n in r["notes"]:
            w(f"- Note: {n}")
        if r["coverage"]["gaps"]:
            w(f"- Coverage of the row as written: {r['coverage']['state']}. Gaps:")
            for g in r["coverage"]["gaps"]:
                w(f"  - {g}")
        w("")
        if r.get("startup_campaign"):
            c = r["startup_campaign"]
            w("- **Startup campaign (measured; PROPOSED methodology, row stays Open; no ratification inferred)**")
            w(f"  - record `{c['record_id']}` stage `{c['stage']}` ({c['source']['record_md']}, {c['source']['csv']})")
            w(f"  - requested {c['requested_points']}, result rows {c['result_rows']}, evaluated {c['evaluated_points']}, "
              f"missing {c['missing_points']}, insufficient {c['insufficient_points']}; "
              f"csv verdicts pass {c['csv_verdicts']['pass']} / fail {c['csv_verdicts']['fail']} / "
              f"insufficient {c['csv_verdicts']['insufficient']}")
            w(f"  - {c['settled_within_3ms_but_failing_points']} of {c['settled_within_3ms_points']} points settle within 3 ms "
              "and still fail the proposed overshoot / monotonicity checks")
            w("  - failure reasons (points): " + ", ".join(f"{k} {v}" for k, v in c["failure_reasons_point_counts"].items()))
            for mp in c["missing"][:10]:
                w(f"  - missing point: {_fmt_at(mp)}")
            w(f"  - design freshness: **{c['design_freshness']['state']}**; "
              + "; ".join(f"{k} {'matches' if e['matches'] else 'DIFFERS'} (`{e['path']}`)"
                          for k, e in c["design_freshness"]["components"].items()))
            for label, e in c["extrema"].items():
                w(f"  - {label}: min {e['min']['value']:.6g} at {_fmt_at(e['min']['at'])}; "
                  f"max {e['max']['value']:.6g} at {_fmt_at(e['max']['at'])}")
            pm_ = c["proposed_methodology"]
            w(f"  - proposed methodology: band {pm_['band_v'][0]}-{pm_['band_v'][1]} V, settle <= {pm_['settle_limit_s']} s, "
              f"monotonic tolerance {pm_['monotonic_tolerance_v']} V ({pm_['reference']}); {pm_['note']}")
            w(f"  - {c['ratification']}")
            w("")
        for m in r["metrics"]:
            if "bound" not in m:
                w(f"- **{m['name']}**: {m['verdict']} -- {m['reason']}")
                if m.get("device_context"):
                    dc = m["device_context"]
                    w(f"  - device context ({dc['branch']}): max |Vsg| {dc['max_vsg_stress_v']} V, "
                      f"{dc['n_exceeding_3p3v_rating']}/{dc['n_device_points']} device points exceed the 3.3 V rating "
                      f"(source `{m['source']['record']}`)")
                continue
            b = m["bound"]
            wc = m["worst_case"]
            w(f"- **{m['name']}** ({m['unit']}): {m['verdict']}; bound {b['comparator']} {b['value']} {b['unit']}; "
              f"{m['n_pass']}/{m['n_points']} pass, {m['n_fail']} fail, {m['n_ambiguous']} ambiguous, "
              f"{m['n_censored_upper_bound']} censored upper bound")
            if wc:
                w(f"  - worst case {wc['value']} at {_fmt_at(wc['at'])}"
                  + (" (censored)" if m.get("worst_case_is_censored") else "")
                  + (f" (first of {wc['n_points_at_this_value']} points at this value)"
                     if wc["n_points_at_this_value"] > 1 else ""))
            w(f"  - conditions: {m['conditions']}")
            w(f"  - source: `{m['source']['record']}` column `{m['source']['column']}`")
            if m.get("observed_range"):
                w(f"  - observed range {m['observed_range']['min']}..{m['observed_range']['max']} {m['unit']}")
            if m.get("ambiguous_points"):
                w("  - ambiguous points: " + ", ".join(_fmt_at(p) for p in m["ambiguous_points"]))
            if m.get("reasons"):
                w("  - reasons (points): " + ", ".join(f"{k} {v}" for k, v in m["reasons"].items()))
            for line in m.get("detail", []):
                w(f"  - {line}")
            if "n_invalid" in m:
                w(f"  - validity: {m['n_points'] - m['n_invalid']} valid, {m['n_invalid']} invalid "
                  "(invalid points are counted, not dropped)")
            if m.get("precision_floor_uA") is not None:
                w(f"  - precision floor: print quantum 1e-10 A; solver-noise proxy {m['precision_floor_uA']} uA")
            if m.get("note"):
                w(f"  - note: {m['note']}")
    w("")
    w("## Completeness checks")
    w("")
    for c in rep["completeness"]["checks"]:
        w(f"- [{'x' if c['ok'] else ' '}] {c['check']}" + (f" -- {c['detail']}" if c["detail"] else ""))
    w("")
    w("## Regenerating")
    w("")
    w("```bash")
    w("python3 sim/characterization/generate.py          # regenerate report, markdown, envelope")
    w("python3 sim/characterization/generate.py --check  # verify the committed files reproduce exactly")
    w("```")
    w("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def render_bytes(report, envelope, md) -> dict[str, bytes]:
    return {
        REPORT_JSON: (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
        REPORT_MD: md.encode("utf-8"),
        ENVELOPE_JSON: (json.dumps(envelope, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    }


def failure_envelope(reason: str) -> bytes:
    env = {"schema_version": 1, "kind": "generic", "status": "fail",
           "summary": f"characterization generator error: {reason}",
           "source": f"sim/characterization/{REPORT_MD}", "t1_item": 8}
    return (json.dumps(env, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="regenerate in memory and fail on any difference from the committed files")
    ap.add_argument("--root", default=str(DEFAULT_ROOT),
                    help="repository root to read inputs from (default: this checkout)")
    ap.add_argument("--out", default=None,
                    help="directory for generated files (default: <root>/sim/characterization)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    out = Path(args.out).resolve() if args.out else root / "sim/characterization"

    try:
        report, envelope, md = build(root)
        files = render_bytes(report, envelope, md)
    except Exception as exc:  # noqa: BLE001 -- any failure, not just GenError, must clear a pass
        # GenError is the anticipated hard-error path; anything else (KeyError/TypeError
        # from a malformed selection.json, OSError, ...) is a generator bug or bad input
        # and must equally never leave a previously committed passing envelope behind.
        reason = str(exc) if isinstance(exc, GenError) else f"{type(exc).__name__}: {exc}"
        print(f"ERROR: {reason}", file=sys.stderr)
        if not isinstance(exc, GenError):
            traceback.print_exc(file=sys.stderr)
        if not args.check:
            out.mkdir(parents=True, exist_ok=True)
            (out / ENVELOPE_JSON).write_bytes(failure_envelope(reason))
            print(f"wrote a status:fail envelope to {out / ENVELOPE_JSON} "
                  "(no passing envelope is left behind)", file=sys.stderr)
        return 1

    if args.check:
        bad = []
        for name, data in files.items():
            p = out / name
            if not p.is_file():
                bad.append(f"{name}: missing")
            elif p.read_bytes() != data:
                bad.append(f"{name}: differs from regeneration (report drift or source-data drift)")
        committed_env = out / ENVELOPE_JSON
        if committed_env.is_file():
            try:
                ce = json.loads(committed_env.read_text(encoding="utf-8"))
                want = hashlib.sha256(files[REPORT_JSON]).hexdigest()
                got = ce.get("provenance", {}).get("input", {}).get("content_hash")
                if ce.get("status") == "pass" and got != f"sha256:{want}":
                    bad.append("envelope claims pass but its provenance hash does not match the regenerated report")
            except ValueError:
                bad.append(f"{ENVELOPE_JSON}: not valid JSON")
        if bad:
            print("characterization --check FAILED:", file=sys.stderr)
            for b in bad:
                print(f"  - {b}", file=sys.stderr)
            print("Regenerate with: python3 sim/characterization/generate.py "
                  "and review the diff.", file=sys.stderr)
            return 1
        if envelope["status"] != "pass":
            print("characterization --check: files reproduce, but the artifact is INCOMPLETE/STALE "
                  f"(envelope status {envelope['status']}): {envelope['summary']}", file=sys.stderr)
            return 1
        print("characterization --check OK: report, markdown and envelope reproduce exactly "
              f"(envelope {envelope['status']}; hash sha256:{hashlib.sha256(files[REPORT_JSON]).hexdigest()})")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    print(f"wrote {', '.join(files)} to {out} (envelope status: {envelope['status']})")
    return 0 if envelope["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
