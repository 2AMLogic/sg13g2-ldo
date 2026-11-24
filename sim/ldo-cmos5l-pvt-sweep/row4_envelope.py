#!/usr/bin/env python3
"""Graded `klt sim` corner-matrix envelope for the RATIFIED row 4 (issue #55).

T1 item 5 asks for a corner-matrix run graded against a ratified spec row.
Everything this directory had before was a *measurement* run: `run_sweep.sh
--batch` and `dropout_campaign.py` do submit real `klt sim` requests, but
those requests declare no `limits`, so the pass/fail verdict was computed by
this repo's own Python afterwards.  `klt signoff` cannot grade that, and
hand-wrapping a reduced CSV into a sim-shaped envelope would be a synthesized
success.  This script closes the gap the only honest way: it declares the
ratified row-4 requirement as `limits` **inside the request**, so the
per-corner and whole-matrix verdict in the emitted report is `klt sim`'s own.

What is graded (DR-0007 row 4, "Dropout @ 50 mA < 300 mV worst corner"),
using the LEGACY measurement definition that row was ratified with
(`dc_metrics.dropout_v_50ma`: the lowest Vin whose VOUT is still within 1 %
of the fixed 1.8 V target, minus that 1.8 V target):

  vout_at_dropout_limit_v  .meas dc FIND v(vout) AT=2.100   limits min 1.782
      The requirement read literally: with VIN at 1.800 + 0.300 V the output
      is still within 1 % of target.  No abscissa interpolation.
  vin_1pct_loss_v          .meas dc WHEN v(vout)=1.782 RISE=1  limits max 2.1
      The measured dropout edge itself.  dropout = value - 1.800 V.  Equal to
      the requirement above by construction, measured from the other axis, so
      a `.meas` quirk in one cannot pass unnoticed in both.
  vout_nominal_v           .meas dc FIND v(vout) AT=3.300     (NO limits)
      Liveness / the regulated output the legacy definition is referenced
      against.  Deliberately UNGRADED: row 2 (output accuracy) is Open under
      DR-0007 and must not acquire a gate here.

Both thresholds are literal numbers because `klt sim` requires that: a `.meas
WHEN` threshold cannot name another `.meas` result, so DR-0012's
own-regulated-output reference (0.99 x VOUT(Vin=3.30 V), per corner) is NOT
expressible in a request *of this scalar-analysis shape*.  That is a real
tool gap, disclosed in signoff/README.md, and it is why this envelope grades
the legacy ratified quantity rather than DR-0012's (still PROPOSED) one.
Row 7's driver shows the other half of the story: quantities that ARE
combinations of solves are expressible as `analysis_steps[]` derived `expr`
measurements (klayout-tools #2482), which is how `row7_envelope.py` grades
Iq-by-difference without any repo-side verdict.

Since issue #317 the row-agnostic half of this bench (the 45-point grid, the
request skeleton, the corners.lib renderer, the submit flow, the offline
record checks and -- since #358 -- the signoff item-5 citation resolver)
lives in `row_envelope.py`, shared with `row5_envelope.py` and
`row7_envelope.py`.  This driver owns the measurements, thresholds and
summary text; its citation rules are the row id and record directory passed
to the shared resolver.  The committed records still reproduce byte for
byte; in particular corners.lib's first line still names THIS file (see
row_envelope.py's header for why that must never move).

Scope: SG13CMOS5L schematic-level only.  Nothing here evidences an Open row
or the SG13G2 branch (DR-0018).

No .control block: the fleet runner applies `options.osdi_preload` itself
(observed 2026-11-14, runner klt 0.9.0 / ngspice-47 per the report's
`environment.remote`; job klt-sim-b7598358f812 is the run that proved it), so a
deck-side `.control pre_osdi` block loads each binary a second time and every
corner comes back `osdi_load_failed` -- with plausible-looking measurement
values beside it, which is why summarise_report() refuses to call a record
definitive while any corner carries an error-severity diagnostic.

    row4_envelope.py submit                 # mint a new record, run it on the
                                            # EDA batch fleet, write the envelope
    row4_envelope.py submit --probe         # the same, 2 corners, for a capacity
                                            # / toolchain probe (never cited)
    row4_envelope.py submit --dry-run       # build the request dir and validate it
    row4_envelope.py check                  # offline, stdlib-only (CI): every
                                            # committed record reproduces and
                                            # self-verifies
    row4_envelope.py summarise <record-id>  # rewrite that record's summary files

Append-only: `submit` mints a NEW timestamped record id and refuses to touch
an existing one.  SPICE never runs locally here -- this is a 45-point grid and
dispatch hosts submit grids to the fleet (CLAUDE.md host rules).
"""
import json
import os
import sys

import row_envelope as re_

HERE = re_.HERE
REPO = re_.REPO
TEMPLATE = "sim/ldo-cmos5l-pvt-sweep/testbench/tb_row4_envelope_cmos5l.spice.tmpl"
DESIGN_NETLIST = "design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"
ROOT = os.path.join(HERE, "row4-envelope")

# DR-0007 row 4, verbatim: "Dropout @ 50 mA  < 300 mV worst corner".
VOUT_TARGET_V = 1.800
LOSS_FRACTION = 0.01
TARGET_DROPOUT_V = 0.300
LOAD_A = 0.050
V_THR_V = 1.782                 # (1 - LOSS_FRACTION) * VOUT_TARGET_V
VIN_LIMIT_V = 2.100             # VOUT_TARGET_V + TARGET_DROPOUT_V
VIN_AXIS = "Vin 1.70 3.63 0.005"
VIN_REF_V = 3.300

# The spec-row id this envelope's graded measurements are tagged with
# (`measurements[].spec_row`, klayout-tools#3778). `klt signoff` item 5 DERIVES
# a citation's row coverage from these tags instead of trusting the manifest,
# so row 4 is credited only while a tagged, limited, passing measurement exists
# -- and the nine Open rows, declared in the manifest's `spec_rows` and covered
# by nothing, keep item 5 `unmet / partial_coverage` by the grader's own
# arithmetic. The id must match the manifest's `spec_rows["5"][].id`.
ROW4_ID = "dr0007-row4-dropout"

# Re-exported grid constants: one 45-point PVT grid, one spelling (tests and
# both drivers read these).
MOS = re_.MOS
RES = re_.RES
CAP = re_.CAP
TEMPS = re_.TEMPS
N_EXPECTED = re_.N_EXPECTED
PROBE_COORDS = re_.PROBE_COORDS
PDK = re_.PDK
PDK_PIN = re_.PDK_PIN
PDK_PIN_KEYS = re_.PDK_PIN_KEYS
PDK_PIN_PROJECTION_FIELD = re_.PDK_PIN_PROJECTION_FIELD
OSDI_ORDER = re_.OSDI_ORDER
Error = re_.Error

# The committed files whose bytes decide what was simulated. Their sha256 goes
# into every record's provenance.json, and `check` re-hashes them against the
# working tree FOR THE CITED RECORD, so a design-netlist or template edit makes
# the citation go stale loudly instead of silently describing a different
# circuit. This generator is deliberately NOT in the list: it is re-verified by
# byte-reproduction of the request and summary files, which is stronger than a
# hash (a hash only says "unchanged"; reproduction says "these exact bytes come
# out of the code that is committed now").
INPUTS = [TEMPLATE, DESIGN_NETLIST,
          "design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice",
          "sim/tools/render_deck.py"]

# The corners.lib header. Byte-critical: the first line names THIS driver and
# the fleet report pins those bytes (row_envelope.py's header explains why the
# shared renderer takes the header as an argument instead of hardcoding it).
HEADER_LINES = [
    "* generated by sim/ldo-cmos5l-pvt-sweep/row4_envelope.py:",
]

GRADED = ["vout_at_dropout_limit_v", "vin_1pct_loss_v"]
UNGRADED = ["vout_nominal_v"]


coords = re_.coords
section_of = re_.section_of
corner_id = re_.corner_id
tb_text = re_.tb_text
sha256_file = re_.sha256_file
resolve_env = re_.resolve_env
write_or_check = re_.write_or_check
f9 = re_.f9


# Thin wrappers, not aliases: the tests (and the drivers) rebind this module's
# REPO / ROOT globals to throwaway copies, so every path that must follow them
# is resolved at CALL time through these wrappers instead of through
# row_envelope's own module globals.


def pdk_pin_projection_sha256(path=None):
    return re_.pdk_pin_projection_sha256(path or os.path.join(REPO, PDK_PIN))


def records(root=None):
    return re_.records(root or ROOT)


def stale_inputs(rid):
    return re_.stale_inputs(REPO, ROOT, rid, INPUTS)


def corners_lib_text(models_dir, cs):
    return re_.corners_lib_text(models_dir, cs, HEADER_LINES)


def measurements():
    return [
        {"name": "vout_at_dropout_limit_v",
         "spice": ".meas dc vout_at_dropout_limit_v FIND v(vout) AT=2.100",
         "unit": "V",
         "limits": {"min": V_THR_V},
         "spec_row": ROW4_ID},
        {"name": "vin_1pct_loss_v",
         "spice": f".meas dc vin_1pct_loss_v WHEN v(vout)={V_THR_V:.3f} RISE=1",
         "unit": "V",
         "limits": {"max": VIN_LIMIT_V},
         "spec_row": ROW4_ID},
        # Untagged and ungraded on purpose: row 2 (output accuracy) is Open, so
        # this must neither carry a gate nor claim coverage of any row.
        {"name": "vout_nominal_v",
         "spice": f".meas dc vout_nominal_v FIND v(vout) AT={VIN_REF_V:.3f}",
         "unit": "V"},
    ]


def request_obj(osdi_dir, cs):
    return re_.request_skeleton(cs, "analysis",
                                {"kind": "dc", "args": VIN_AXIS},
                                measurements(), osdi_dir)


def request_files(subs, cs, template_text):
    """The three request-dir files, as {name: text}. Deterministic."""
    return re_.request_files(subs, cs, template_text, HEADER_LINES, request_obj)


def design_netlist_include(depth):
    """The repo-relative `.include` target for a request dir `depth` levels
    below the repo root (row4-envelope/<record-id>/ is 4)."""
    return re_.design_netlist_include(depth, DESIGN_NETLIST)


# --------------------------------------------------------------------------- #
# summary (pure: report.json + provenance.json -> bytes)
# --------------------------------------------------------------------------- #

def summarise_report(report, prov):
    def dropout_field(c, meas):
        vin = meas.get("vin_1pct_loss_v", {}).get("value")
        return {"dropout_v": None if vin is None else vin - VOUT_TARGET_V}

    summ, points, base = re_.summarise_corners(
        report, prov, graded=GRADED, ungraded=UNGRADED, point_fields=dropout_field)
    resolved = [p for p in points if p["dropout_v"] is not None]
    summ["target_dropout_v"] = TARGET_DROPOUT_V
    summ["vout_target_v"] = VOUT_TARGET_V
    if resolved:
        w = max(resolved, key=lambda p: p["dropout_v"])
        summ["worst_corner"] = {k: w[k] for k in ("corner_id", "mos", "temp_c", "res_section",
                                                  "dropout_v", "vin_1pct_loss_v",
                                                  "vout_at_dropout_limit_v")}
        summ["worst_dropout_v"] = w["dropout_v"]
        summ["margin_to_target_v"] = TARGET_DROPOUT_V - w["dropout_v"]
        summ["series_resistance_equivalent_ohm"] = summ["margin_to_target_v"] / LOAD_A
        summ["grid_bracket_v"] = 0.005
        summ["worst_dropout_upper_bound_v"] = w["dropout_v"] + 0.005
    summ["definitive"] = bool(base and len(resolved) == N_EXPECTED)
    return summ, points


def summary_md(summ, points, prov):
    rid = summ["record_id"]
    L = [f"# Row-4 graded `klt sim` corner-matrix envelope `{rid}`", "",
         "DR-0007 row 4, **Dropout @ 50 mA < 300 mV worst corner** -- the one ratified",
         "row of the target spec. The verdict below is `klt sim`'s own: both graded",
         "measurements carry `limits` in `request.json`, so each corner's pass/fail and",
         "the matrix verdict (`status`) are computed by the tool, not by this repo.", "",
         "Measurement definition: the LEGACY row-4 quantity DR-0007 ratified --",
         f"the lowest Vin whose VOUT is still within {LOSS_FRACTION*100:.0f} % of the fixed",
         f"{VOUT_TARGET_V:.3f} V target, minus that target. DR-0012's own-regulated-output",
         "reference is PROPOSED and is not expressible as a `klt sim` request (a `.meas`",
         "`WHEN` threshold must be a literal); see `signoff/README.md`.", ""]
    if summ["probe"]:
        L += ["> **PROBE RECORD.** A capacity / toolchain probe over "
              f"{summ['n_expected']} coordinates, not the ratified matrix. Never cited.", ""]
    L += [f"- Corners: {summ['n_corners_reported']}/{summ['n_expected']} reported, "
          f"every coordinate exactly once: {summ['coordinates_exactly_once']}.",
          f"- Envelope `status`: **{summ['envelope_status']}** "
          f"(passed {summ['passed']}, failed {summ['failed']}, errored {summ['errored']}, "
          f"inconclusive {summ['inconclusive']}).",
          f"- Corner status counts: {summ['corner_status_counts']}; "
          f"error-severity diagnostics: {summ['error_diagnostics_total']}.",
          f"- Graded measurements (`coverage.measurements_with_limits` = "
          f"{summ['measurements_with_limits']}): {', '.join(summ['graded_measurements'])}; "
          f"all pass: {summ['all_graded_measurements_pass']}.",
          f"- Definitive worst-corner claim permitted: **{summ['definitive']}** (requires the "
          f"whole {N_EXPECTED}-coordinate matrix reported, resolved, graded and clean)."]
    if "worst_corner" in summ:
        w = summ["worst_corner"]
        L += ["",
              f"- Worst corner: `{w['mos']}` / {w['temp_c']} C / `{w['res_section']}` "
              f"(`{w['corner_id']}`): dropout {w['dropout_v']*1000:.2f} mV "
              f"(`vin_1pct_loss_v` {w['vin_1pct_loss_v']:.5f} V - {VOUT_TARGET_V:.3f} V), "
              f"VOUT at the {VIN_LIMIT_V:.3f} V limit {w['vout_at_dropout_limit_v']:.5f} V.",
              f"- Margin to the {TARGET_DROPOUT_V*1000:.0f} mV target: "
              f"{summ['margin_to_target_v']*1000:.2f} mV = "
              f"{summ['margin_to_target_v']*1000:.2f} mV / {LOAD_A*1000:.0f} mA = "
              f"{summ['series_resistance_equivalent_ohm']:.3f} ohm series resistance, before "
              "any parasitic extraction.",
              f"- Conservative read: the Vin axis is {summ['grid_bracket_v']*1000:.0f} mV, so the "
              f"worst dropout's grid upper bound is {summ['worst_dropout_upper_bound_v']*1000:.2f} mV, "
              f"still under {TARGET_DROPOUT_V*1000:.0f} mV."]
    L += ["", "## Per-corner", "",
          "| corner | status | dropout (mV) | `vin_1pct_loss_v` (V) | "
          "`vout_at_dropout_limit_v` (V) | `vout_nominal_v` (V) |", "|---|---|---|---|---|---|"]
    for p in points:
        d = "" if p["dropout_v"] is None else f"{p['dropout_v']*1000:.2f}"
        L.append(f"| `{p['corner_id']}` | {p['corner_status']} | {d} | "
                 f"{f9(p['vin_1pct_loss_v'])} | {f9(p['vout_at_dropout_limit_v'])} | "
                 f"{f9(p['vout_nominal_v'])} |")
    L += ["", "## Provenance", ""]
    for k, v in sorted(prov.items()):
        if k == "input_sha256":
            continue
        L.append(f"- {k}: `{json.dumps(v, sort_keys=True)}`" if isinstance(v, (dict, list))
                 else f"- {k}: {v}")
    L += ["", "Input sha256:", ""]
    for k, v in sorted(prov.get("input_sha256", {}).items()):
        L.append(f"- `{k}`: `{v}`")
    L += ["", f"Machine summary: `row4-envelope.json`; the graded envelope itself: "
          f"`report.json`; the request that produced it: `request.json`, `tb.spice`, "
          f"`corners.lib`.", ""]
    return "\n".join(L)


def summary_files(record_dir):
    return re_.summary_files(record_dir, "row4", summarise_report, summary_md)


# --------------------------------------------------------------------------- #
# submit
# --------------------------------------------------------------------------- #

def cmd_submit(a):
    def prov_extra(rid, probe):
        return {
            "ratified_row": "DR-0007 row 4 (Dropout @ 50 mA < 300 mV worst corner)",
            "measurement_definition": "legacy dropout_v_50ma (1 % loss vs the fixed "
                                      "1.800 V target); DR-0012's own-V_reg reference is "
                                      "PROPOSED and not expressible as a klt sim request",
            "input_sha256": {p: sha256_file(os.path.join(re_.REPO, p)) for p in INPUTS},
        }
    return re_.submit_record(
        a, slug="row4", root=ROOT, template_rel=TEMPLATE,
        design_netlist_rel=DESIGN_NETLIST, header_lines=HEADER_LINES,
        request_files_fn=request_files, summary_files_fn=summary_files,
        invocation_fmt="python3 sim/ldo-cmos5l-pvt-sweep/row4_envelope.py submit{probe}",
        prov_extra=prov_extra)


def cmd_summarise(a):
    return re_.summarise_cmd(a, ROOT, summary_files)


# --------------------------------------------------------------------------- #
# check (offline, stdlib-only, no PDK and no simulator -- this is the CI gate)
# --------------------------------------------------------------------------- #

def cited_record():
    """(record_id, pinned content_hash) from signoff/sg13g2-ldo.json item 5, or
    (None, None) when item 5 is uncited.

    Item 5 is a multi-citation item: the entry is a LIST of members, each
    optionally naming the `spec_rows` it covers. Exactly one member is a
    row4-envelope record today; a second one (another row, another bench) is
    the expected growth path and is not this script's business, so only the
    row4-envelope member is resolved here. The parser itself is shared with
    the row-5/row-7 drivers (row_envelope.cited_item5_record, #358).
    """
    return re_.cited_item5_record(REPO, ROOT, ROW4_ID, "row4")


def check_record(rid, problems):
    record_dir = os.path.join(ROOT, rid)
    if not os.path.exists(os.path.join(record_dir, "provenance.json")):
        problems.append(f"{rid}: no provenance.json")
        return None
    summ, prov = re_.check_request_and_summary(
        record_dir, rid, problems, slug="row4",
        request_files_fn=request_files, template_rel=TEMPLATE,
        summary_files_fn=summary_files)
    re_.check_hash_pins(record_dir, rid, problems, slug="row4",
                        tail=f"row4-envelope/{rid}/tb.spice")
    re_.check_declared_gates(record_dir, rid, problems,
                             measurements_fn=measurements, graded=GRADED,
                             row_id=ROW4_ID, slug="row4")
    return summ


def check_spec_rows(problems):
    """The manifest's item-5 `spec_rows` must still describe DR-0007: ten rows,
    row 4 the only ratified one. Without this, flipping one `ratified: false`
    to `true` in the manifest would quietly turn an Open row into covered-or-
    uncovered arithmetic the grader treats as ratifiable -- a spec relaxation
    made in a JSON file rather than in a decision record."""
    m = json.load(open(os.path.join(REPO, "signoff", "sg13g2-ldo.json")))
    rows = (m.get("spec_rows") or {}).get("5")
    if not isinstance(rows, list):
        problems.append("signoff manifest declares no spec_rows['5']; item 5 would then "
                        "grade on the cited envelope alone and read as full coverage")
        return
    ids = [r.get("id") for r in rows if isinstance(r, dict)]
    if len(ids) != 10 or len(set(ids)) != 10:
        problems.append(f"spec_rows['5'] declares {len(ids)} rows ({len(set(ids))} "
                        "distinct); DR-0007's target spec has exactly 10")
    if ROW4_ID not in ids:
        problems.append(f"spec_rows['5'] does not declare {ROW4_ID}")
    ratified = sorted(r["id"] for r in rows
                      if isinstance(r, dict) and r.get("ratified", True))
    if ratified != [ROW4_ID]:
        problems.append(f"spec_rows['5'] marks {ratified} ratified; DR-0007 ratifies "
                        f"row 4 only ({ROW4_ID}). Ratifying a row is a decision record, "
                        "not a manifest edit")


def cmd_check(a):
    problems = []
    rids = records(ROOT)
    if not rids:
        problems.append("no record under sim/ldo-cmos5l-pvt-sweep/row4-envelope/")
    summaries = {rid: check_record(rid, problems) for rid in rids}

    check_spec_rows(problems)
    cited = re_.check_item5_citation(REPO, ROOT, ROW4_ID, "row4", summaries,
                                     problems, stale_inputs)
    for p in problems:
        print("row4_envelope: " + p, file=sys.stderr)
    if problems:
        return 1
    print(f"row4_envelope: OK -- {len(rids)} record(s) reproduce and self-verify"
          + (f"; signoff item 5 cites {cited}" if cited else ""))
    return 0


def main():
    return re_.run_cli(__doc__, "row4", cmd_submit, cmd_check, cmd_summarise)


if __name__ == "__main__":
    sys.exit(main())
