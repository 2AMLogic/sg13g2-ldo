#!/usr/bin/env python3
"""Negative controls for row5_envelope.py (issue #319). stdlib only, offline.

The row-5 (line / load regulation) envelope cannot be made to look definitive
by anything short of a whole, clean, graded 45-corner matrix with every named
(Vin, Iload) step run once: a dropped corner, a duplicate coordinate, a failed
or repeated step, an errored corner, an unresolved derived figure, a relaxed
limit, a tampered input, or a value AT the strict target (the pinned grader's
`max` is inclusive) must each flip `definitive` to False or raise a check
problem.  Two controls push values through klt's own grading function when the
pinned klt is importable; CI requires that they run.
"""
import contextlib
import copy
import io
import json
import math
import os
import shutil
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import row5_envelope as ev  # noqa: E402

try:                                    # the pinned klt's own grader, when installed
    import klayout_tools.sim as real_grader
except Exception:                       # noqa: BLE001 -- optional in stdlib-only runs
    real_grader = None

NOMINAL = {n: (0.2 if n in ev.LINE_GRADED else 0.02) for n in ev.GRADED}


def full_report(n=ev.N_EXPECTED):
    """A synthetic all-pass 45-corner report in `klt sim`'s own shape."""
    corners = []
    for mos, temp, res in ev.coords():
        meas = []
        for (vn, _), (ln, _) in ev._operating_points():
            meas.append({"name": f"{vn}_{ln}.vout_v", "value": 1.8, "status": "pass",
                         "step": f"{vn}_{ln}"})
        for name in ev.GRADED:
            meas.append({"name": name, "value": NOMINAL[name], "status": "pass"})
        corners.append({
            "corner_id": ev.corner_id(mos, temp, res), "status": "pass",
            "diagnostics": [],
            "steps": [{"name": s, "kind": "op", "status": "ok"} for s in ev.STEP_NAMES],
            "measurements": meas,
        })
    corners = corners[:n]
    return {
        "schema_version": 3, "netlist": "tb.spice", "status": "pass",
        "corner_count": len(corners), "passed": len(corners), "failed": 0,
        "errored": 0, "inconclusive": 0,
        "coverage": {"measurements_with_limits": len(ev.GRADED)},
        "measurements": [{"name": m["name"], "limits": m.get("limits")}
                         for m in ev.measurements()],
        "corners": corners,
    }


PROV = {"record_id": "test-record", "probe": False, "substitutions": {}}


class RequestShape(unittest.TestCase):
    def test_matrix_is_45_distinct_coordinates(self):
        cs = ev.coords()
        self.assertEqual((len(cs), len(set(cs)), ev.N_EXPECTED), (45, 45, 45))

    def test_eight_steps_each_set_both_vin_and_iload(self):
        steps = ev.analysis_steps()
        self.assertEqual(len(steps), 8)
        self.assertEqual(len({s["name"] for s in steps}), 8)
        self.assertEqual(sorted(s["name"] for s in steps), ev.STEP_NAMES)
        alters = {s["name"]: (s["alter"]["Vin"], s["alter"]["Iload"]) for s in steps}
        self.assertEqual(alters, {
            "v2v97_i0": (2.97, 0.0), "v2v97_i25m": (2.97, 0.025), "v2v97_i50m": (2.97, 0.05),
            "v3v30_i0": (3.30, 0.0), "v3v30_i50m": (3.30, 0.05),
            "v3v63_i0": (3.63, 0.0), "v3v63_i25m": (3.63, 0.025), "v3v63_i50m": (3.63, 0.05)})
        for s in steps:
            self.assertEqual(set(s["alter"]), {"Vin", "Iload"})
            self.assertEqual(s["analysis"], {"kind": "op", "args": ""})
            self.assertEqual([m["name"] for m in s["measurements"]], ["vout_v"])
            self.assertNotIn("limits", s["measurements"][0])
            self.assertNotIn("spec_row", s["measurements"][0])

    def test_graded_figures_are_derived_exprs_with_the_row_limits(self):
        meas = {m["name"]: m for m in ev.measurements()}
        self.assertEqual(sorted(meas), sorted(ev.GRADED))
        for ln in ("i0", "i25m", "i50m"):
            m = meas[f"line_{ln}_mvpv"]
            self.assertEqual(m["expr"], f"1000 * abs(v3v63_{ln}.vout_v - v2v97_{ln}.vout_v) / 0.66")
            self.assertEqual(m["limits"], {"max": 5.0})
        for vn in ("v2v97", "v3v30", "v3v63"):
            m = meas[f"load_{vn}_pct"]
            self.assertEqual(m["expr"], f"100 * abs({vn}_i0.vout_v - {vn}_i50m.vout_v) / {vn}_i0.vout_v")
            self.assertEqual(m["limits"], {"max": 1.0})
        for m in meas.values():
            self.assertEqual(m["spec_row"], "dr0007-row5-line-load-regulation")
            self.assertNotIn("spice", m)

    def test_line_and_load_cover_three_conditions_each(self):
        self.assertEqual(len(ev.LINE_GRADED), 3)
        self.assertEqual(len(ev.LOAD_GRADED), 3)

    def test_solver_tolerances_are_pinned_and_never_called_a_bound(self):
        req = ev.request_obj("/osdi", ev.coords())
        self.assertEqual(req["options"]["ngspice_options"], {"reltol": 1e-9, "abstol": 1e-15})
        self.assertEqual(req["options"]["ngspice_init"], ["set numdgt=12"])
        s = ev.summarise_report(full_report(), PROV)[0]
        self.assertIn("NOT an error bound", s["solver_convergence_setting_note"])

    def test_probe_excludes_the_gaps_and_full_matrix_excludes_nothing(self):
        self.assertNotIn("exclude", ev.request_obj("/osdi", ev.coords()))
        self.assertEqual(len(ev.request_obj("/osdi", ev.coords(probe=True))["exclude"]), 2)

    def test_the_corners_lib_header_names_this_driver(self):
        self.assertEqual(ev.HEADER_LINES[0],
                         "* generated by sim/ldo-cmos5l-pvt-sweep/row5_envelope.py:")

    def test_request_files_are_a_pure_function_of_template_and_subs(self):
        subs = {"design_netlist_include": "../x.spice", "pdk_models_dir": "/m", "osdi_dir": "/o"}
        a = ev.request_files(subs, ev.coords(), "body @@DESIGN_NETLIST@@\n")
        self.assertEqual(a, ev.request_files(subs, ev.coords(), "body @@DESIGN_NETLIST@@\n"))
        self.assertNotIn("@@", a["tb.spice"])
        self.assertEqual(len(json.loads(a["request.json"])["analysis_steps"]), 8)


class SummaryVerdict(unittest.TestCase):
    def summ(self, report, prov=None):
        return ev.summarise_report(report, prov or PROV)[0]

    def set_graded(self, r, name, value, idx=5):
        for m in r["corners"][idx]["measurements"]:
            if m["name"] == name:
                m["value"] = value
                m["status"] = "pass"      # klt sim's inclusive `max` grades it so

    def test_clean_full_matrix_is_definitive(self):
        s = self.summ(full_report())
        self.assertTrue(s["definitive"])
        self.assertEqual(s["n_corners_reported"], 45)
        self.assertEqual(s["worst_line"]["target"], 5.0)
        self.assertEqual(s["worst_load"]["target"], 1.0)

    def test_a_dropped_corner_is_not_definitive(self):
        s = self.summ(full_report(n=44))
        self.assertFalse(s["definitive"])
        self.assertFalse(s["coordinates_exactly_once"])

    def test_a_duplicated_coordinate_is_not_definitive(self):
        r = full_report()
        r["corners"].append(copy.deepcopy(r["corners"][0]))
        r["corner_count"] = r["passed"] = len(r["corners"])
        s = self.summ(r)
        self.assertFalse(s["coordinates_exactly_once"])
        self.assertFalse(s["definitive"])

    def test_a_failed_step_is_not_definitive(self):
        r = full_report()
        r["corners"][3]["steps"][2]["status"] = "error"
        self.assertFalse(self.summ(r)["definitive"])

    def test_an_errored_corner_is_not_definitive(self):
        r = full_report()
        r["corners"][3]["status"] = "error"
        r["corners"][3]["diagnostics"] = [{"severity": "error", "code": "step_failed",
                                           "message": "analysis produced no plot"}]
        r["status"], r["passed"], r["errored"] = "error", 44, 1
        s = self.summ(r)
        self.assertEqual(s["error_diagnostics_total"], 1)
        self.assertFalse(s["definitive"])

    def test_a_failing_line_figure_is_not_definitive(self):
        r = full_report()
        for m in r["corners"][7]["measurements"]:
            if m["name"] == "line_i50m_mvpv":
                m["value"], m["status"] = 6.1, "fail"
        r["status"], r["passed"], r["failed"] = "fail", 44, 1
        s = self.summ(r)
        self.assertFalse(s["all_graded_measurements_pass"])
        self.assertFalse(s["definitive"])
        self.assertEqual(s["worst_line"]["value"], 6.1)

    def test_a_failing_load_figure_is_not_definitive(self):
        r = full_report()
        for m in r["corners"][7]["measurements"]:
            if m["name"] == "load_v3v63_pct":
                m["value"], m["status"] = 1.3, "fail"
        s = self.summ(r)
        self.assertFalse(s["definitive"])
        self.assertEqual(s["worst_load"]["value"], 1.3)

    def test_an_unresolved_derived_figure_is_not_definitive(self):
        # A missing graded value (derived input unavailable) can never complete the envelope.
        for victim in ev.GRADED:
            r = full_report()
            for m in r["corners"][11]["measurements"]:
                if m["name"] == victim:
                    m["value"], m["status"] = None, "error"
            self.assertFalse(self.summ(r)["definitive"], victim)

    def test_a_graded_figure_removed_from_a_corner_is_not_definitive(self):
        r = full_report()
        r["corners"][4]["measurements"] = [m for m in r["corners"][4]["measurements"]
                                           if m["name"] != "load_v2v97_pct"]
        self.assertFalse(self.summ(r)["definitive"])

    def test_ungraded_matrix_is_not_definitive(self):
        r = full_report()
        r["coverage"]["measurements_with_limits"] = 0
        self.assertFalse(self.summ(r)["definitive"])

    def test_line_value_exactly_at_5_mv_per_v_is_not_credited(self):
        # DR-0007 row 5 is a strict "< 5 mV/V"; the tool's inclusive max reports pass.
        r = full_report()
        self.set_graded(r, "line_i25m_mvpv", 5.0)
        s = self.summ(r)
        self.assertTrue(s["all_graded_measurements_pass"])      # the tool's status is preserved
        self.assertFalse(s["all_graded_strictly_below_target"])
        self.assertFalse(s["definitive"])
        r = full_report()
        self.set_graded(r, "line_i25m_mvpv", math.nextafter(5.0, 0.0))
        self.assertTrue(self.summ(r)["definitive"])

    def test_load_value_exactly_at_1_percent_is_not_credited(self):
        r = full_report()
        self.set_graded(r, "load_v3v30_pct", 1.0)
        s = self.summ(r)
        self.assertTrue(s["all_graded_measurements_pass"])
        self.assertFalse(s["all_graded_strictly_below_target"])
        self.assertFalse(s["definitive"])
        r = full_report()
        self.set_graded(r, "load_v3v30_pct", math.nextafter(1.0, 0.0))
        self.assertTrue(self.summ(r)["definitive"])

    def test_zero_load_line_point_noise_is_still_graded_by_magnitude(self):
        # Edge: at 0 mA the difference is the smallest; a negative-signed noise value
        # is graded through abs() in the expression, so the summary never sees a sign.
        for m in ev.measurements():
            if m["name"] == "line_i0_mvpv":
                self.assertIn("abs(", m["expr"])
        r = full_report()
        self.set_graded(r, "line_i0_mvpv", 1e-12)
        self.assertTrue(self.summ(r)["definitive"])

    def test_one_step_repeated_eight_times_is_not_definitive(self):
        r = full_report()
        r["corners"][2]["steps"] = [copy.deepcopy(r["corners"][2]["steps"][0]) for _ in range(8)]
        self.assertFalse(self.summ(r)["definitive"])

    def test_a_missing_named_step_is_not_definitive(self):
        r = full_report()
        r["corners"][2]["steps"][3]["name"] = r["corners"][2]["steps"][0]["name"]
        self.assertFalse(self.summ(r)["definitive"])

    def test_a_graded_measurement_repeated_in_a_corner_is_not_definitive(self):
        r = full_report()
        c = r["corners"][4]
        c["measurements"].append(copy.deepcopy(c["measurements"][-1]))
        self.assertFalse(self.summ(r)["definitive"])

    def test_a_graded_declaration_missing_or_repeated_in_the_report_is_not_definitive(self):
        r = full_report()
        r["measurements"] = [m for m in r["measurements"] if m["name"] != "load_v3v63_pct"]
        s = self.summ(r)
        self.assertFalse(s["graded_declarations_exactly_once"])
        self.assertFalse(s["definitive"])
        r = full_report()
        r["measurements"].append(copy.deepcopy(r["measurements"][0]))
        self.assertFalse(self.summ(r)["definitive"])

    def test_probe_record_is_never_definitive(self):
        prov = {"record_id": "p", "probe": True, "substitutions": {}}
        r = full_report()
        keep = {ev.corner_id(*x) for x in ev.coords(probe=True)}
        r["corners"] = [c for c in r["corners"] if c["corner_id"] in keep]
        r["corner_count"] = r["passed"] = len(r["corners"])
        s = self.summ(r, prov)
        self.assertEqual(s["n_corners_reported"], 2)
        self.assertFalse(s["definitive"])

    def test_summary_states_the_remaining_qualifications(self):
        s = self.summ(full_report())
        joined = " ".join(s["qualifications"])
        self.assertIn("0.90 V reference", joined)
        self.assertIn("discrete sampling", joined)
        self.assertIn("accuracy window", joined)
        self.assertIn("row 2", joined)
        md = ev.summary_md(s, ev.summarise_report(full_report(), PROV)[1], PROV)
        self.assertIn("Remaining qualifications", md)
        self.assertIn("NOT demonstrated by this envelope", md)
        self.assertIn("Solver convergence setting (not an error bound)", md)


@unittest.skipUnless(real_grader is not None,
                     "klayout_tools.sim not importable (pinned klt not installed)")
class RealGrader(unittest.TestCase):
    def test_known_violation_gets_a_failing_verdict_from_the_tools_own_grader(self):
        # Negative control: a value over the declared limit must grade `fail`
        # through klt's own per-measurement function, never one this test sets.
        for m in ev.measurements():
            over = m["limits"]["max"] * 1.5
            status, _margin, _diag = real_grader._grade_measurement_value(m, over)
            self.assertEqual(status, "fail", m["name"])
            ok, _a, _b = real_grader._grade_measurement_value(m, m["limits"]["max"] * 0.5)
            self.assertEqual(ok, "pass", m["name"])

    def test_equality_passes_klt_but_the_summary_refuses_strict_credit(self):
        r = full_report()
        for m in ev.measurements():
            status = real_grader._grade_measurement_value(m, m["limits"]["max"])[0]
            self.assertEqual(status, "pass", "klt's `max` is inclusive")
            rr = copy.deepcopy(r)
            for x in rr["corners"][0]["measurements"]:
                if x["name"] == m["name"]:
                    x["value"], x["status"] = m["limits"]["max"], status
            self.assertFalse(ev.summarise_report(rr, PROV)[0]["definitive"], m["name"])


@unittest.skipUnless(os.path.isdir(ev.ROOT) and ev.records(),
                     "no committed row5-envelope record")
class CommittedRecords(unittest.TestCase):
    """Tamper controls run on a COPY: committed evidence is append-only."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="row5-envelope-test.")
        self.root = os.path.join(self.tmp, "row5-envelope")
        shutil.copytree(ev.ROOT, self.root)
        self._orig = ev.ROOT
        ev.ROOT = self.root

    def tearDown(self):
        ev.ROOT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def full_records(self):
        return [r for r in ev.records() if not r.endswith("-probe")]

    def test_committed_records_pass_their_own_check(self):
        problems = []
        for rid in ev.records():
            ev.check_record(rid, problems)
        self.assertEqual(problems, [])

    def test_the_cited_record_is_a_definitive_full_matrix(self):
        rid = ev.selected_record()
        if rid is None:
            self.skipTest("selection.json cites no row-5 record")
        self.assertIn(rid, ev.records())
        summ = ev.check_record(rid, [])
        self.assertTrue(summ["definitive"])
        self.assertFalse(summ["probe"])

    def test_tampering_the_netlist_is_caught(self):
        rid = self.full_records()[0]
        with open(os.path.join(self.root, rid, "tb.spice"), "a") as f:
            f.write("* tampered\n")
        problems = []
        ev.check_record(rid, problems)
        self.assertTrue(any("content_hash" in p for p in problems), problems)

    def test_relaxing_a_recorded_limit_is_caught(self):
        rid = self.full_records()[0]
        path = os.path.join(self.root, rid, "request.json")
        req = json.load(open(path))
        for m in req["measurements"]:
            m["limits"] = {"max": m["limits"]["max"] * 2}
        json.dump(req, open(path, "w"), indent=1)
        problems = []
        ev.check_record(rid, problems)
        self.assertTrue(any("limits" in p for p in problems), problems)

    def test_a_dropped_spec_row_tag_is_caught(self):
        rid = self.full_records()[0]
        path = os.path.join(self.root, rid, "request.json")
        req = json.load(open(path))
        del req["measurements"][0]["spec_row"]
        json.dump(req, open(path, "w"), indent=1)
        problems = []
        ev.check_record(rid, problems)
        self.assertTrue(any("spec_row" in p for p in problems), problems)

    def test_a_graded_declaration_removed_from_the_report_is_caught(self):
        rid = self.full_records()[0]
        path = os.path.join(self.root, rid, "report.json")
        rep = json.load(open(path))
        rep["measurements"] = [m for m in rep["measurements"] if m["name"] not in ev.GRADED]
        json.dump(rep, open(path, "w"), indent=1)
        problems = []
        ev.check_record(rid, problems)
        self.assertTrue(any("exactly once" in p for p in problems), problems)


@unittest.skipUnless(os.path.isdir(ev.ROOT) and ev.records(),
                     "no committed row5-envelope record")
class SignoffItem5Coupling(unittest.TestCase):
    """The signoff-manifest side of the row-5 citation (issue #358).

    `klt signoff` pins tb.spice, and a `--probe` record's tb.spice is
    byte-identical to the full matrix's -- the issue's evidence table -- so
    repointing item 5 at anything but the committed definitive record
    grades identically unless the driver's own offline check refuses it.
    Every control runs on a scratch repo + record tree; committed evidence
    is append-only.
    """

    RID = "20261123-213711-06bd6576"             # the committed definitive record
    PROBE = "20261123-213537-06bd6576-probe"     # its 2-corner probe sibling

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="row5-item5-test.")
        self.repo = os.path.join(self.tmp, "repo")
        # the record tree at its repo-relative path, so the citation's
        # path shape is exercised for real
        self.root = os.path.join(self.repo, "sim", "ldo-cmos5l-pvt-sweep",
                                 "row5-envelope")
        os.makedirs(os.path.dirname(self.root))
        shutil.copytree(ev.ROOT, self.root)
        # every file cmd_check reads through REPO
        for rel in [ev.PDK_PIN, "signoff/sg13g2-ldo.json",
                    "sim/characterization/selection.json"] + list(ev.INPUTS):
            dst = os.path.join(self.repo, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(ev.REPO, rel), dst)
        self._repo, self._root = ev.REPO, ev.ROOT
        ev.REPO, ev.ROOT = self.repo, self.root
        self.stderr = ""

    def tearDown(self):
        ev.REPO, ev.ROOT = self._repo, self._root
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manifest(self):
        return json.load(open(os.path.join(self.repo, "signoff", "sg13g2-ldo.json")))

    def write_manifest(self, m):
        json.dump(m, open(os.path.join(self.repo, "signoff", "sg13g2-ldo.json"), "w"),
                  indent=2)

    def prefix(self):
        return os.path.relpath(ev.ROOT, ev.REPO).replace(os.sep, "/") + "/"

    def cite(self, rid, rows=None, content_hash=None, file=None, append=True,
             omit_rows=False):
        m = self.manifest()
        members = m["evidence"]["5"]
        members = members if isinstance(members, list) else [members]
        if not append:
            members = []
        tb = os.path.join(self.root, rid, "tb.spice")
        member = {
            "file": file or (self.prefix() + rid + "/report.json"),
            "content_hash": content_hash or (
                "sha256:" + ev.sha256_file(tb) if os.path.exists(tb)
                else "sha256:" + "0" * 64),
        }
        if not omit_rows:
            member["rows"] = [ev.ROW5_ID] if rows is None else rows
        members.append(member)
        m["evidence"]["5"] = members
        self.write_manifest(m)

    def drop_row5_members(self):
        m = self.manifest()
        members = m["evidence"]["5"]
        m["evidence"]["5"] = [x for x in (members if isinstance(members, list)
                                          else [members])
                              if not str(x.get("file", "")).startswith(self.prefix())]
        self.write_manifest(m)

    def check(self):
        self.stdout = io.StringIO()
        with contextlib.redirect_stderr(io.StringIO()) as err, \
                contextlib.redirect_stdout(self.stdout):
            rc = ev.cmd_check(types.SimpleNamespace())
        self.stderr = err.getvalue()
        return rc

    def make_non_definitive(self):
        """A scratch copy of the definitive record that self-verifies but
        fails its matrix -- a legitimate failed run, refused only as a
        citation."""
        rid = "99991231-235959-failrun"
        shutil.copytree(os.path.join(self.root, self.RID), os.path.join(self.root, rid))
        path = os.path.join(self.root, rid, "report.json")
        rep = json.load(open(path))
        rep["status"], rep["passed"], rep["failed"] = "fail", 44, 1
        rep["netlist"]["path"] = self.prefix() + rid + "/tb.spice"
        for c in rep["corners"]:
            c["status"] = "fail"
            for m in c["measurements"]:
                if m["name"] in ev.GRADED:
                    m["status"], m["value"] = "fail", 6.0
        json.dump(rep, open(path, "w"), indent=1)
        prov_path = os.path.join(self.root, rid, "provenance.json")
        prov = json.load(open(prov_path))
        prov["record_id"] = rid
        json.dump(prov, open(prov_path, "w"), indent=1, sort_keys=True)
        files, _ = ev.summary_files(os.path.join(self.root, rid))
        for name, text in files.items():
            with open(os.path.join(self.root, rid, name), "w") as f:
                f.write(text)
        return rid

    def test_uncited_item5_passes_and_resolves_to_nothing(self):
        # main's shape before #318 lands: item 5 without a row-5 member
        # must leave the check green and the resolver at (None, None).
        self.drop_row5_members()
        self.assertEqual(ev.cited_record(), (None, None))
        self.assertEqual(self.check(), 0)
        self.assertIn("cites no row5-envelope record", self.stderr)

    def test_well_formed_citation_of_the_definitive_record_passes(self):
        self.cite(self.RID)
        self.assertEqual(ev.cited_record(),
                         (self.RID, "sha256:" + ev.sha256_file(
                             os.path.join(self.root, self.RID, "tb.spice"))))
        self.assertEqual(self.check(), 0)
        self.assertIn("signoff item 5 cites " + self.RID, self.stdout.getvalue())

    def test_probe_record_cited_is_refused(self):
        # The probe's tb.spice is byte-identical to the full matrix's, so
        # the pin itself matches; only the summary's verdict refuses it.
        self.cite(self.PROBE)
        self.assertEqual(self.check(), 1)
        self.assertIn("not definitive", self.stderr)
        self.assertNotIn("content_hash", self.stderr)

    def test_non_definitive_record_cited_is_refused(self):
        self.cite(self.make_non_definitive())
        self.assertEqual(self.check(), 1)
        self.assertIn("not definitive", self.stderr)

    def test_foreign_rows_is_refused(self):
        self.cite(self.RID, rows=["dr0007-row4-dropout"])
        with self.assertRaises(ev.Error):
            ev.cited_record()
        self.assertEqual(self.check(), 1)
        self.assertIn("declares rows", self.stderr)

    def test_missing_rows_is_refused(self):
        self.cite(self.RID, omit_rows=True)
        with self.assertRaises(ev.Error):
            ev.cited_record()
        self.assertEqual(self.check(), 1)
        self.assertIn("declares rows", self.stderr)

    def test_duplicate_driver_member_is_refused(self):
        self.cite(self.RID)
        self.cite(self.RID)
        with self.assertRaises(ev.Error):
            ev.cited_record()
        self.assertEqual(self.check(), 1)
        self.assertIn("exactly one", self.stderr)

    def test_wrong_content_hash_pin_is_refused(self):
        # the issue's third evidence row: pinning report.json's sha256
        self.cite(self.RID, content_hash="sha256:" + ev.sha256_file(
            os.path.join(self.root, self.RID, "report.json")))
        self.assertEqual(self.check(), 1)
        self.assertIn("content_hash", self.stderr)

    def test_uncommitted_record_cited_is_refused(self):
        self.cite("20260101-000000-nope")
        self.assertEqual(self.check(), 1)
        self.assertIn("not committed", self.stderr)

    def test_wrong_file_shape_is_refused(self):
        self.cite(self.RID, file=self.prefix() + self.RID + "/request.json")
        with self.assertRaises(ev.Error):
            ev.cited_record()
        self.assertEqual(self.check(), 1)
        self.assertIn("must be", self.stderr)

    def test_nested_record_id_path_is_refused(self):
        self.cite("a/b", content_hash="sha256:" + "0" * 64)
        with self.assertRaises(ev.Error):
            ev.cited_record()
        self.assertEqual(self.check(), 1)
        self.assertIn("must be", self.stderr)

    def test_tampered_tb_spice_on_the_cited_record_is_refused(self):
        self.cite(self.RID)
        with open(os.path.join(self.root, self.RID, "tb.spice"), "a") as f:
            f.write("* tampered\n")
        self.assertEqual(self.check(), 1)
        self.assertIn("content_hash", self.stderr)

    def test_stale_input_on_the_cited_record_is_refused(self):
        self.cite(self.RID)
        with open(os.path.join(self.repo, "design/sg13cmos5l/netlist/"
                            "ldo_erramp_cmos5l.spice"), "a") as f:
            f.write("* touched\n")
        self.assertEqual(self.check(), 1)
        self.assertIn("changed since the run", self.stderr)

    def test_the_selection_json_side_stays_active(self):
        # AC: the item-8 selection check must survive the item-5 addition --
        # a selection.json id that is not a committed record still fails.
        sel_path = os.path.join(self.repo, "sim", "characterization",
                                "selection.json")
        sel = json.load(open(sel_path))
        sel["row5_envelope_evidence"]["id"] = "20260101-000000-nope"
        json.dump(sel, open(sel_path, "w"), indent=2)
        self.assertEqual(self.check(), 1)
        self.assertIn("selection.json cites row-5 record", self.stderr)


if __name__ == "__main__":
    unittest.main()
