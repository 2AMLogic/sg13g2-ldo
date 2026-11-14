#!/usr/bin/env python3
"""Negative controls for row4_envelope.py (issue #55). stdlib only, offline.

The point of these tests is that the row-4 envelope cannot be made to look
definitive by anything short of a whole, clean, graded 45-point matrix:
every way a real run has degraded -- a dropped corner, a duplicated
coordinate, a corner that reported values but errored (the osdi double-load
failure mode), an unreached `.meas`, a relaxed limit, a tampered input --
must flip `definitive` to False or raise a check problem.
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
import row4_envelope as ev  # noqa: E402


def full_report(n=ev.N_EXPECTED, dropout_v=0.20, worst=("ss", 125, "typ"), worst_v=0.237):
    """A synthetic all-pass 45-corner report in `klt sim`'s own shape."""
    corners = []
    for mos, temp, res in ev.coords():
        d = worst_v if (mos, temp, res) == worst else dropout_v
        vin = ev.VOUT_TARGET_V + d
        corners.append({
            "corner_id": ev.corner_id(mos, temp, res),
            "status": "pass",
            "diagnostics": [],
            "measurements": [
                {"name": "vout_at_dropout_limit_v", "value": 1.7999, "status": "pass"},
                {"name": "vin_1pct_loss_v", "value": vin, "status": "pass"},
                {"name": "vout_nominal_v", "value": 1.80014, "status": "pass"},
            ],
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
        self.assertEqual(sorted({c[0] for c in cs}), sorted(ev.MOS))
        self.assertEqual(sorted({c[1] for c in cs}), sorted(ev.TEMPS))
        self.assertEqual(sorted({c[2] for c in cs}), sorted(ev.RES))

    def test_thresholds_are_the_ratified_target_not_a_relaxation(self):
        # DR-0007 row 4: "< 300 mV worst corner", 1 % loss vs the fixed 1.8 V.
        self.assertAlmostEqual(ev.V_THR_V, (1 - ev.LOSS_FRACTION) * ev.VOUT_TARGET_V, places=12)
        self.assertAlmostEqual(ev.VIN_LIMIT_V, ev.VOUT_TARGET_V + ev.TARGET_DROPOUT_V, places=12)
        self.assertEqual(ev.TARGET_DROPOUT_V, 0.300)

    def test_graded_and_ungraded_measurements(self):
        lim = {m["name"]: m.get("limits") for m in ev.measurements()}
        self.assertEqual(lim["vout_at_dropout_limit_v"], {"min": ev.V_THR_V})
        self.assertEqual(lim["vin_1pct_loss_v"], {"max": ev.VIN_LIMIT_V})
        # Row 2 (output accuracy) is Open under DR-0007: no gate may appear.
        self.assertIsNone(lim["vout_nominal_v"])
        for name in ev.UNGRADED:
            self.assertNotIn(name, ev.GRADED)

    def test_only_the_graded_pair_claims_row_4(self):
        tags = {m["name"]: m.get("spec_row") for m in ev.measurements()}
        self.assertEqual(tags["vout_at_dropout_limit_v"], ev.ROW4_ID)
        self.assertEqual(tags["vin_1pct_loss_v"], ev.ROW4_ID)
        # An Open row must never be claimed as covered.
        self.assertIsNone(tags["vout_nominal_v"])
        self.assertIn("row4", ev.ROW4_ID)

    def test_meas_thresholds_are_literal_numbers(self):
        # `klt sim` refuses a non-literal `.meas WHEN` threshold, and a card
        # naming another measurement would be the unexpressible DR-0012 form.
        cards = {m["name"]: m["spice"] for m in ev.measurements()}
        self.assertIn("WHEN v(vout)=1.782", cards["vin_1pct_loss_v"])
        self.assertIn("AT=2.100", cards["vout_at_dropout_limit_v"])
        for card in cards.values():
            self.assertNotIn("vout_nominal_v)", card.replace(".meas dc vout_nominal_v", ""))

    def test_full_matrix_excludes_nothing_probe_excludes_the_gaps(self):
        self.assertNotIn("exclude", ev.request_obj("/osdi", ev.coords()))
        probe = ev.request_obj("/osdi", ev.coords(probe=True))
        # 2 sections x 2 temps = 4 cells, 2 wanted -> 2 excluded.
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

    def test_design_netlist_include_depth(self):
        self.assertEqual(ev.design_netlist_include(4),
                         "../../../../" + ev.DESIGN_NETLIST)


class SummaryVerdict(unittest.TestCase):
    def summ(self, report, prov=None):
        return ev.summarise_report(report, prov or PROV)[0]

    def test_clean_full_matrix_is_definitive(self):
        s = self.summ(full_report())
        self.assertTrue(s["definitive"])
        self.assertEqual(s["n_corners_reported"], 45)
        self.assertTrue(s["coordinates_exactly_once"])
        self.assertAlmostEqual(s["worst_dropout_v"], 0.237, places=9)
        self.assertAlmostEqual(s["margin_to_target_v"], 0.063, places=9)
        self.assertAlmostEqual(s["series_resistance_equivalent_ohm"], 0.063 / 0.050, places=9)
        self.assertEqual(s["worst_corner"]["mos"], "ss")
        self.assertEqual(s["worst_corner"]["temp_c"], 125)

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

    def test_values_with_an_errored_corner_are_not_definitive(self):
        # The real failure mode: every .meas produced a plausible value, but
        # the corner errored (osdi_load_failed from a double pre_osdi load).
        r = full_report()
        r["corners"][3]["status"] = "error"
        r["corners"][3]["diagnostics"] = [{"severity": "error", "code": "osdi_load_failed",
                                           "message": "could not be loaded"}]
        r["status"], r["passed"], r["errored"] = "error", 44, 1
        s = self.summ(r)
        self.assertEqual(s["error_diagnostics_total"], 1)
        self.assertFalse(s["definitive"])

    def test_a_failing_graded_measurement_is_not_definitive(self):
        r = full_report()
        c = r["corners"][7]
        for m in c["measurements"]:
            if m["name"] == "vin_1pct_loss_v":
                m["value"], m["status"] = 2.4, "fail"
        r["status"], r["passed"], r["failed"] = "fail", 44, 1
        s = self.summ(r)
        self.assertFalse(s["all_graded_measurements_pass"])
        self.assertFalse(s["definitive"])
        # ... and the worst corner is the failing one, not hidden.
        self.assertAlmostEqual(s["worst_dropout_v"], 0.6, places=9)
        self.assertLess(s["margin_to_target_v"], 0)

    def test_an_unreached_meas_is_not_definitive(self):
        r = full_report()
        for m in r["corners"][11]["measurements"]:
            if m["name"] == "vin_1pct_loss_v":
                m["value"], m["status"] = None, "unavailable"
        s = self.summ(r)
        self.assertFalse(s["definitive"])
        self.assertIsNone([p for p in ev.summarise_report(r, PROV)[1]
                           if p["corner_id"] == r["corners"][11]["corner_id"]][0]["dropout_v"])

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

    def test_summary_markdown_is_deterministic(self):
        r = full_report()
        s, pts = ev.summarise_report(r, PROV)
        self.assertEqual(ev.summary_md(s, pts, PROV), ev.summary_md(s, pts, PROV))
        self.assertIn("Dropout @ 50 mA < 300 mV", ev.summary_md(s, pts, PROV))


@unittest.skipUnless(os.path.isdir(ev.ROOT), "no committed row4-envelope record")
class CommittedRecords(unittest.TestCase):
    """Tamper controls run on a COPY: committed evidence is append-only."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="row4-envelope-test.")
        self.root = os.path.join(self.tmp, "row4-envelope")
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
        path = os.path.join(self.root, rid, "tb.spice")
        with open(path, "a") as f:
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
            if m["name"] == "vin_1pct_loss_v":
                m["limits"] = {"max": 9.0}
        json.dump(req, open(path, "w"), indent=1)
        problems = []
        ev.check_record(rid, problems)
        self.assertTrue(any("limits" in p for p in problems), problems)

    def test_corners_lib_tampering_is_caught(self):
        rid = self.records()[0]
        with open(os.path.join(self.root, rid, "corners.lib"), "a") as f:
            f.write("* tampered\n")
        problems = []
        ev.check_record(rid, problems)
        self.assertTrue(any("corners.lib" in p or "models_lib_sha256" in p
                            for p in problems), problems)


if __name__ == "__main__":
    unittest.main()


class ManifestCoupling(unittest.TestCase):
    """The manifest side of the citation: a relaxation there must fail too."""

    MANIFEST = os.path.join(ev.REPO, "signoff", "sg13g2-ldo.json")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="row4-manifest-test.")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "signoff"))
        shutil.copy(self.MANIFEST, os.path.join(self.repo, "signoff", "sg13g2-ldo.json"))
        self._repo = ev.REPO
        ev.REPO = self.repo

    def tearDown(self):
        ev.REPO = self._repo
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manifest(self):
        return json.load(open(os.path.join(self.repo, "signoff", "sg13g2-ldo.json")))

    def write(self, m):
        json.dump(m, open(os.path.join(self.repo, "signoff", "sg13g2-ldo.json"), "w"),
                  indent=2)

    def test_committed_manifest_declares_dr0007_as_ratified(self):
        problems = []
        ev.check_spec_rows(problems)
        self.assertEqual(problems, [])

    def test_ratifying_an_open_row_in_the_manifest_is_caught(self):
        m = self.manifest()
        for row in m["spec_rows"]["5"]:
            if row["id"] == "dr0007-row2-output":
                row["ratified"] = True
        self.write(m)
        problems = []
        ev.check_spec_rows(problems)
        self.assertTrue(any("ratifies row 4 only" in p for p in problems), problems)

    def test_dropping_the_row_declaration_is_caught(self):
        m = self.manifest()
        del m["spec_rows"]
        self.write(m)
        problems = []
        ev.check_spec_rows(problems)
        self.assertTrue(any("declares no spec_rows" in p for p in problems), problems)

    def test_dropping_a_row_is_caught(self):
        m = self.manifest()
        m["spec_rows"]["5"] = m["spec_rows"]["5"][:9]
        self.write(m)
        problems = []
        ev.check_spec_rows(problems)
        self.assertTrue(any("exactly 10" in p for p in problems), problems)

    def test_citation_claiming_another_row_is_caught(self):
        m = self.manifest()
        m["evidence"]["5"][0]["rows"] = ["dr0007-row4-dropout", "dr0007-row6-psrr"]
        self.write(m)
        with self.assertRaises(ev.Error):
            ev.cited_record()

    def test_uncited_item5_resolves_to_nothing(self):
        m = self.manifest()
        del m["evidence"]["5"]
        self.write(m)
        self.assertEqual(ev.cited_record(), (None, None))
