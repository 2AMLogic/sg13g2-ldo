#!/usr/bin/env python3
"""Negative controls for row7_envelope.py (issue #317). stdlib only, offline.

The point of these tests is the same as test_row4_envelope.py's: the row-7
envelope cannot be made to look definitive by anything short of a whole,
clean, graded 45-corner matrix with every (Vin, Iload) step ok -- a dropped
corner, a duplicated coordinate, a failed step, an errored corner, an
unresolved derived figure, a relaxed limit, a tampered input must each flip
`definitive` to False or raise a check problem.  The request-shape tests pin
the graded quantity itself: the difference must live inside the request as a
derived expr (the issue's "the verdict must be `klt sim`'s own"), never as an
offline subtraction, and the tolerances that bound the difference's numerical
noise must be pinned in the request too.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import row7_envelope as ev  # noqa: E402
import row_envelope as re_  # noqa: E402


def full_report(n=ev.N_EXPECTED, worst=("ff", 125, "bcs"),
                nl_worst_ua=24.4930, fl_worst_ua=24.6614):
    """A synthetic all-pass 45-corner report in `klt sim`'s own shape, with
    step-scoped supply currents and the derived Iq figures both present.
    Nominal values are in the envelope's measured family: no-load ~22-25 uA,
    full-load supply current ~50.02-50.03 mA."""
    corners = []
    for i, (mos, temp, res) in enumerate(ev.coords()):
        nl = nl_worst_ua * 1e-6 if (mos, temp, res) == worst else 22.9e-6
        fl = fl_worst_ua * 1e-6 if (mos, temp, res) == worst else 23.0e-6
        meas = []
        for vn, vv in ev.VINS:
            for ln, lv in ev.LOADS:
                isup = nl if ln == "i0" else (fl + lv)
                meas.append({"name": f"{vn}_{ln}.isup_a", "value": isup,
                             "status": "pass", "step": f"{vn}_{ln}"})
        for vn, vv in ev.VINS:
            for ln, lv in ev.LOADS:
                name = f"iq_{ln}_{vn}_a"
                val = nl if ln == "i0" else fl
                meas.append({"name": name, "value": val, "status": "pass",
                             "derived_from": [f"{vn}_{ln}.isup_a"]})
        corners.append({
            "corner_id": ev.corner_id(mos, temp, res),
            "status": "pass",
            "diagnostics": [],
            "steps": [{"name": f"{vn}_{ln}", "kind": "op", "status": "ok"}
                      for vn, _ in ev.VINS for ln, _ in ev.LOADS],
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
        self.assertEqual(len(cs), 45)
        self.assertEqual(len(set(cs)), 45)
        self.assertEqual(ev.N_EXPECTED, 45)

    def test_six_steps_cover_the_row_window(self):
        steps = ev.analysis_steps()
        self.assertEqual(len(steps), 6)
        names = [s["name"] for s in steps]
        self.assertEqual(len(set(names)), 6)
        alters = {s["name"]: s["alter"] for s in steps}
        for vn, vv in ev.VINS:
            self.assertAlmostEqual(alters[f"{vn}_i0"]["Vin"], vv, places=12)
            self.assertAlmostEqual(alters[f"{vn}_i0"]["Iload"], 0.0, places=12)
            self.assertAlmostEqual(alters[f"{vn}_i50m"]["Vin"], vv, places=12)
            self.assertAlmostEqual(alters[f"{vn}_i50m"]["Iload"], 0.050, places=12)
        for s in steps:
            self.assertEqual(s["analysis"], {"kind": "op", "args": ""})
            self.assertEqual([m["name"] for m in s["measurements"]], ["isup_a"])
            self.assertNotIn("limits", s["measurements"][0])
            self.assertNotIn("spec_row", s["measurements"][0])
        self.assertEqual(sorted(v for _, v in ev.VINS), [2.97, 3.30, 3.63])

    def test_the_verdict_is_klt_sims_own(self):
        # The graded difference must be INSIDE the request as a derived expr
        # over the step results -- never a repo-side subtraction, and never a
        # `.meas` card referencing another measurement's result.
        meas = {m["name"]: m for m in ev.measurements()}
        self.assertEqual(len(meas), 6)
        for vn, vv in ev.VINS:
            self.assertEqual(meas[f"iq_i0_{vn}_a"]["expr"], f"{vn}_i0.isup_a")
            self.assertEqual(meas[f"iq_i50m_{vn}_a"]["expr"],
                             f"{vn}_i50m.isup_a - 0.05")
            for n in (f"iq_i0_{vn}_a", f"iq_i50m_{vn}_a"):
                self.assertEqual(meas[n]["limits"], {"max": 30e-6})
                self.assertEqual(meas[n]["spec_row"], ev.ROW7_ID)
                self.assertIn("expr", meas[n])
                self.assertNotIn("spice", meas[n])

    def test_thresholds_are_the_row_target_not_a_relaxation(self):
        # DR-0007 row 7: "< 30 uA at no load and at full load".
        for m in ev.measurements():
            self.assertEqual(m["limits"], {"max": ev.TARGET_IQ_A})
        self.assertEqual(ev.TARGET_IQ_A, 30e-6)
        self.assertEqual(ev.ROW7_ID, "dr0007-row7-iq")

    def test_solver_tolerances_and_print_precision_are_pinned(self):
        # The numerical-noise bound the record states is only honest while the
        # request itself pins the tolerances it is derived from.
        req = ev.request_obj("/osdi", ev.coords())
        self.assertEqual(req["options"]["ngspice_options"],
                         {"reltol": 1e-9, "abstol": 1e-15})
        self.assertEqual(req["options"]["ngspice_init"], ["set numdgt=12"])
        self.assertEqual(req["analysis_steps"], ev.analysis_steps())
        self.assertEqual(req["options"]["timeout_s"], 600)

    def test_noise_bound_is_stated_and_small_vs_the_limit(self):
        self.assertAlmostEqual(ev.NOISE_BOUND_A,
                               1e-9 * 0.050 + 30e-6 * 1e-9 + 1e-15, places=30)
        self.assertLess(ev.NOISE_BOUND_A / ev.TARGET_IQ_A, 1e-5)

    def test_full_matrix_excludes_nothing_probe_excludes_the_gaps(self):
        self.assertNotIn("exclude", ev.request_obj("/osdi", ev.coords()))
        probe = ev.request_obj("/osdi", ev.coords(probe=True))
        self.assertEqual(len(probe["exclude"]), 2)

    def test_request_files_are_a_pure_function_of_template_and_subs(self):
        subs = {"design_netlist_include": "../x.spice",
                "pdk_models_dir": "/m", "osdi_dir": "/o"}
        tmpl = "body @@DESIGN_NETLIST@@\n"
        a = ev.request_files(subs, ev.coords(), tmpl)
        b = ev.request_files(subs, ev.coords(), tmpl)
        self.assertEqual(a, b)
        self.assertIn("../x.spice", a["tb.spice"])
        self.assertNotIn("@@", a["tb.spice"])
        self.assertEqual(a["corners.lib"].count(".lib mos_"), 15)
        self.assertIn("/o/psp103.osdi", a["request.json"])
        req = json.loads(a["request.json"])
        self.assertEqual(len(req["analysis_steps"]), 6)
        # 6 graded derived figures + 6 ungraded step supply currents.
        self.assertEqual(len(req["measurements"]), 6)
        n_step_meas = sum(len(s["measurements"]) for s in req["analysis_steps"])
        self.assertEqual(n_step_meas, 6)


class SummaryVerdict(unittest.TestCase):
    def summ(self, report, prov=None):
        return ev.summarise_report(report, prov or PROV)[0]

    def test_clean_full_matrix_is_definitive(self):
        s = self.summ(full_report())
        self.assertTrue(s["definitive"])
        self.assertEqual(s["n_corners_reported"], 45)
        self.assertTrue(s["coordinates_exactly_once"])
        self.assertAlmostEqual(s["worst_noload"]["iq_ua"], 24.4930, places=6)
        self.assertAlmostEqual(s["worst_fullload"]["iq_ua"], 24.6614, places=6)
        self.assertAlmostEqual(s["margin_fullload_ua"], 30.0 - 24.6614, places=6)
        self.assertEqual(s["worst_fullload"]["mos"], "ff")
        self.assertEqual(s["worst_fullload"]["temp_c"], 125)

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
        s = self.summ(r)
        self.assertFalse(s["definitive"])

    def test_values_with_an_errored_corner_are_not_definitive(self):
        r = full_report()
        r["corners"][3]["status"] = "error"
        r["corners"][3]["diagnostics"] = [{"severity": "error",
                                           "code": "step_failed",
                                           "message": "analysis produced no plot"}]
        r["status"], r["passed"], r["errored"] = "error", 44, 1
        s = self.summ(r)
        self.assertEqual(s["error_diagnostics_total"], 1)
        self.assertFalse(s["definitive"])

    def test_a_failing_graded_measurement_is_not_definitive(self):
        r = full_report()
        c = r["corners"][7]
        for m in c["measurements"]:
            if m["name"] == "iq_i50m_v3v30_a":
                m["value"], m["status"] = 31.2e-6, "fail"
        r["status"], r["passed"], r["failed"] = "fail", 44, 1
        s = self.summ(r)
        self.assertFalse(s["all_graded_measurements_pass"])
        self.assertFalse(s["definitive"])
        self.assertAlmostEqual(s["worst_fullload"]["iq_ua"], 31.2, places=6)
        self.assertLess(s["margin_fullload_ua"], 0)

    def test_an_unresolved_derived_figure_is_not_definitive(self):
        # The derived-input-unavailable case: a step failed late and klt sim
        # reported the derived figure with no value rather than grading it.
        r = full_report()
        for m in r["corners"][11]["measurements"]:
            if m["name"] in ev.GRADED:
                m["value"], m["status"] = None, "error"
        s = self.summ(r)
        self.assertFalse(s["definitive"])

    def test_ungraded_matrix_is_not_definitive(self):
        r = full_report()
        r["coverage"]["measurements_with_limits"] = 0
        self.assertFalse(self.summ(r)["definitive"])

    def test_probe_record_is_never_definitive(self):
        prov = {"record_id": "p", "probe": True, "substitutions": {}}
        r = full_report()
        r["corners"] = [c for c in r["corners"]
                        if c["corner_id"] in {ev.corner_id(*x) for x in ev.coords(probe=True)}]
        r["corner_count"] = r["passed"] = len(r["corners"])
        s = self.summ(r, prov)
        self.assertEqual(s["n_corners_reported"], 2)
        self.assertTrue(s["probe"])
        self.assertFalse(s["definitive"])

    def test_summary_carries_the_noise_bound_and_exclusions(self):
        s = self.summ(full_report())
        self.assertIn("numerical_noise_bound_a", s)
        self.assertLess(s["numerical_noise_bound_a"], 1e-10)
        self.assertIn("reltol", s["numerical_noise_bound_note"])
        joined = " ".join(s["exclusions"])
        self.assertIn("0.90 V reference", joined)
        self.assertIn("IBIAS", joined)
        self.assertIn("#190", joined)
        md = ev.summary_md(s, ev.summarise_report(full_report(), PROV)[1], PROV)
        self.assertIn("Numerical-noise bound", md)
        self.assertIn("Exclusions this evidence must be read with", md)
        self.assertEqual(md, ev.summary_md(s, ev.summarise_report(full_report(), PROV)[1], PROV))


@unittest.skipUnless(os.path.isdir(ev.ROOT) and ev.records(),
                     "no committed row7-envelope record")
class CommittedRecords(unittest.TestCase):
    """Tamper controls run on a COPY: committed evidence is append-only."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="row7-envelope-test.")
        self.root = os.path.join(self.tmp, "row7-envelope")
        shutil.copytree(ev.ROOT, self.root)
        self._orig = ev.ROOT
        ev.ROOT = self.root

    def tearDown(self):
        ev.ROOT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def records(self):
        return ev.records()

    def test_committed_records_pass_their_own_check(self):
        problems = []
        for rid in self.records():
            ev.check_record(rid, problems)
        self.assertEqual(problems, [])

    def test_tampering_the_netlist_is_caught(self):
        rid = self.records()[0]
        with open(os.path.join(self.root, rid, "tb.spice"), "a") as f:
            f.write("* tampered\n")
        problems = []
        ev.check_record(rid, problems)
        self.assertTrue(any("tb.spice" in p for p in problems), problems)
        self.assertTrue(any("content_hash" in p for p in problems), problems)

    def test_relaxing_a_recorded_limit_is_caught(self):
        rid = self.records()[0]
        path = os.path.join(self.root, rid, "request.json")
        req = json.load(open(path))
        for m in req["measurements"]:
            if m["name"] in ev.GRADED:
                m["limits"] = {"max": 50e-6}
        json.dump(req, open(path, "w"), indent=1)
        problems = []
        ev.check_record(rid, problems)
        self.assertTrue(any("limits" in p for p in problems), problems)

    def test_perturbed_limit_makes_the_envelope_fail(self):
        # The issue's negative control: a perturbed limit (tightened, not
        # relaxed -- the direction a gate must still catch) makes the recorded
        # envelope's own summary report failing measurements: rebuild the
        # summary against a limit the measured values cannot meet.
        rid = self.records()[0]
        path = os.path.join(self.root, rid, "report.json")
        rep = json.load(open(path))
        for m in rep.get("measurements", []):
            if m["name"] in ev.GRADED:
                m["limits"] = {"max": 10e-6}   # below every measured value
        for c in rep["corners"]:
            for m in c["measurements"]:
                if m["name"] in ev.GRADED:
                    m["status"] = "fail"
        rep["status"], rep["passed"], rep["failed"] = "fail", 0, rep["corner_count"]
        json.dump(rep, open(path, "w"), indent=1)
        summ, _ = ev.summarise_report(rep, json.load(
            open(os.path.join(self.root, rid, "provenance.json"))))
        self.assertFalse(summ["all_graded_measurements_pass"])
        self.assertFalse(summ["definitive"])

    def test_corners_lib_tampering_is_caught(self):
        rid = self.records()[0]
        with open(os.path.join(self.root, rid, "corners.lib"), "a") as f:
            f.write("* tampered\n")
        problems = []
        ev.check_record(rid, problems)
        self.assertTrue(any("corners.lib" in p or "models_lib_sha256" in p
                            for p in problems), problems)

    def test_selected_record_is_definitive(self):
        # Whichever record characterization pins must be a whole, clean,
        # graded matrix; an incomplete or failing record must never be cited.
        rid = self.records()[-1]
        prov = json.load(open(os.path.join(self.root, rid, "provenance.json")))
        if prov.get("probe"):
            self.skipTest("latest record is a probe")
        summ, _ = ev.summarise_report(
            json.load(open(os.path.join(self.root, rid, "report.json"))), prov)
        self.assertTrue(summ["definitive"], "the newest non-probe record must "
                        "be definitive before characterization can pin it")


if __name__ == "__main__":
    unittest.main()
