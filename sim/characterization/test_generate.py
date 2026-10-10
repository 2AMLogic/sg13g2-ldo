#!/usr/bin/env python3
"""Focused tests + negative controls for generate.py. Stdlib unittest only.

  python3 -m unittest discover -s sim/characterization -p 'test_*.py'

Negative controls run the real generator against a throwaway COPY of the
inputs (never the working tree), so the committed records are untouched.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate as G  # noqa: E402

REPO = G.DEFAULT_ROOT


def pid(i):
    return {"corner": "tt", "temp_c": i, "res_section": "res_typ"}


def run_main(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = G.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def copy_inputs(dst: Path) -> None:
    sel = json.loads((REPO / "sim/characterization/selection.json").read_text())
    rels = {"sim/characterization/selection.json", "README.md",
            sel["spec_sources"]["ratification"],
            sel["superseded_evidence"][0]["statement_source"]}
    rec = sel["circuit_record"]
    rels |= {f["path"] for f in rec["files"].values()}
    rels |= {p["path"] for p in rec["design_freshness_pins"]}
    rels |= {f["path"] for f in sel["device_context_record"]["files"].values()}
    for r in rels:
        (dst / r).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / r, dst / r)


class MetricTests(unittest.TestCase):
    def test_lt_pass_retains_worst_condition(self):
        pts = [(0.1, pid(1)), (0.24, pid(2)), (0.2, pid(3))]
        m = G.metric("d", "V", "lt", 0.3, "c", "r", pts, "cond")
        self.assertEqual(m["verdict"], "pass")
        self.assertEqual(m["worst_case"]["value"], 0.24)
        self.assertEqual(m["worst_case"]["at"], pid(2))

    def test_fail_when_any_point_violates(self):
        pts = [(50.0, pid(1)), (44.0, pid(2))]
        m = G.metric("pm", "deg", "ge", 45.0, "c", "r", pts, "cond")
        self.assertEqual((m["verdict"], m["n_fail"]), ("fail", 1))
        self.assertEqual(m["worst_case"]["value"], 44.0)

    def test_ambiguous_points_are_not_scored_and_block_pass(self):
        pts = [(60.0, pid(1)), (-170.0, pid(2)), (70.0, pid(3))]
        m = G.metric("pm", "deg", "ge", 45.0, "c", "r", pts, "cond", ambiguous={1})
        self.assertEqual(m["verdict"], "ambiguous")
        self.assertEqual((m["n_pass"], m["n_fail"], m["n_ambiguous"]), (2, 0, 1))
        self.assertEqual(m["ambiguous_points"], [pid(2)])

    def test_censored_points_counted_and_kept_as_upper_bounds(self):
        pts = [(0.2, pid(1)), (0.2, pid(2)), (0.24, pid(3))]
        m = G.metric("d", "V", "lt", 0.3, "c", "r", pts, "cond", censored={0, 1})
        self.assertEqual(m["n_censored_upper_bound"], 2)
        self.assertEqual(m["verdict"], "pass")

    def test_cc_window_contiguous_and_intersected(self):
        def r(x, res, ok):
            return {"cc_x_nominal": str(x), "res_section": res, "all_ok": str(ok),
                    "corner": "ss", "temp_c": "125"}
        rows = [r(0.5, "a", False), r(0.7, "a", True), r(1.0, "a", True), r(1.5, "a", True), r(2.0, "a", False),
                r(0.5, "b", True), r(0.7, "b", False), r(1.0, "b", True), r(1.5, "b", True), r(2.0, "b", True)]
        w = G.cc_window(rows)
        # b has a hole at 0.7 so its contiguous run starts at 1.0; a ends at 1.5
        self.assertEqual((w["low_x_nominal"], w["high_x_nominal"]), (1.0, 1.5))

    def test_non_numeric_field_is_a_hard_error(self):
        with self.assertRaises(G.GenError):
            G.num({"x": "abc"}, "x", "ctx")
        with self.assertRaises(G.GenError):
            G.num({"x": "nan"}, "x", "ctx")
        with self.assertRaises(G.GenError):
            G.num({}, "x", "ctx")


class SpecTableTests(unittest.TestCase):
    def setUp(self):
        self.readme = (REPO / "README.md").read_text(encoding="utf-8")

    def test_readme_parses_ten_rows_with_ratification_state(self):
        rows = G.parse_readme(self.readme)
        self.assertEqual(len(rows), 10)
        self.assertEqual([r["ratification"] for r in rows].count("ratified"), 1)
        self.assertEqual(rows[3]["parameter"], "Dropout @ 50 mA")

    def test_changed_target_text_is_refused(self):
        bad = self.readme.replace("< 300 mV worst corner", "< 250 mV worst corner")
        with self.assertRaises(G.GenError):
            G.parse_readme(bad)

    def test_unknown_status_is_refused(self):
        target = "RATIFIED as a shared target (stretch not ratified)"
        self.assertIn(target, self.readme)  # guard: the mutation must actually apply
        bad = self.readme.replace(target, "DRAFT")
        with self.assertRaises(G.GenError):
            G.parse_readme(bad)

    def test_dr7_parses_all_rows_once(self):
        dr = G.parse_dr7((REPO / "spec/decision-records/DR-0007-target-spec-row-ratification.md").read_text(encoding="utf-8"))
        self.assertEqual(sorted(dr), list(range(1, 11)))
        self.assertEqual(dr[2]["type"], "S")
        self.assertEqual(dr[4]["state"], "ratified")


class GeneratedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.env, cls.md = G.build(REPO)
        cls.rows = {r["id"]: r for r in cls.report["rows"]}

    def test_every_row_exactly_once(self):
        self.assertEqual(sorted(self.rows), list(range(1, 11)))
        self.assertEqual(len(self.report["rows"]), 10)

    def test_classifications(self):
        v = {i: r["verdict"] for i, r in self.rows.items()}
        self.assertEqual(v[1], "not_measured")      # bare device is not a circuit measurement
        self.assertEqual(v[4], "pass_full_coverage")
        self.assertEqual(v[8], "not_implemented")
        self.assertEqual(v[9], "not_implemented")
        self.assertEqual(v[10], "ambiguous")        # multi-crossing AC points not scored
        self.assertEqual(self.rows[4]["ratification"]["state"], "ratified")
        self.assertEqual(self.rows[2]["ratification"]["state"], "open_unratified")

    def test_row1_device_context_not_substituted(self):
        ctx = [m for m in self.rows[1]["metrics"] if m.get("context_only")]
        self.assertEqual(len(ctx), 1)
        self.assertEqual(ctx[0]["verdict"], "not_measured")

    def test_dropout_censoring_preserved(self):
        m = self.rows[4]["metrics"][0]
        self.assertEqual(m["n_censored_upper_bound"], 36)
        self.assertEqual(m["worst_case"]["value"], 0.24)
        self.assertFalse(m["worst_case_is_censored"])

    def test_iq_unit_conversion_and_missing_full_load(self):
        m = self.rows[7]["metrics"][0]
        self.assertEqual(m["unit"], "uA")
        # Selected record 20261010-025634-60a3e81 (EN design, PR #87):
        # iq_a 2.47221613e-05 A at ss/125C/res_bcs. The pre-EN record
        # 20260917-023832-7061e8f had 2.47222854e-05 A at the same point.
        self.assertAlmostEqual(m["worst_case"]["value"], 24.7221613, places=6)
        self.assertEqual(self.rows[7]["metrics"][1]["verdict"], "not_measured")
        self.assertIn("superseded", self.rows[7]["metrics"][1]["reason"])

    def test_stability_ambiguous_crossings_preserved(self):
        m = self.rows[10]["metrics"][0]
        self.assertEqual((m["n_ambiguous"], m["n_pass"]), (15, 30))
        self.assertEqual(len(m["ambiguous_points"]), 15)

    def test_psrr_stretch_and_conditions_retained(self):
        m = self.rows[6]["metrics"][0]
        self.assertIn("Cout = 1 uF", m["conditions"])
        self.assertIn("not met", self.rows[6]["stretch_note"])

    def test_envelope_contract(self):
        e = self.env
        self.assertEqual((e["schema_version"], e["kind"], e["t1_item"]), (1, "generic", 8))
        self.assertEqual(e["status"], "pass")
        self.assertTrue(e["provenance"]["input"]["content_hash"].startswith("sha256:"))
        self.assertIn("NOT circuit spec compliance", e["summary"])

    def test_deterministic_twice(self):
        a = G.render_bytes(*G.build(REPO))
        b = G.render_bytes(*G.build(REPO))
        self.assertEqual(a, b)

    def test_committed_files_reproduce(self):
        files = G.render_bytes(self.report, self.env, self.md)
        for name, data in files.items():
            self.assertEqual((REPO / "sim/characterization" / name).read_bytes(), data, name)


class NegativeControls(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        copy_inputs(self.tmp)
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 0, err)
        self.out = self.tmp / "sim/characterization"

    def env_status(self):
        return json.loads((self.out / G.ENVELOPE_JSON).read_text())["status"]

    def pvt(self):
        sel = json.loads((self.tmp / "sim/characterization/selection.json").read_text())
        return self.tmp / sel["circuit_record"]["files"]["pvt_csv"]["path"]

    def test_baseline_check_passes(self):
        rc, _, err = run_main("--root", str(self.tmp), "--check")
        self.assertEqual(rc, 0, err)

    def test_remove_selected_record_fails_and_clears_pass(self):
        self.pvt().unlink()
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn("selected record missing", err)
        self.assertEqual(self.env_status(), "fail")
        rc, _, err = run_main("--root", str(self.tmp), "--check")
        self.assertEqual(rc, 1)

    def test_corrupt_numeric_field_fails_pin(self):
        p = self.pvt()
        p.write_text(p.read_text().replace("1.80025256", "1.90025256", 1))
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn("differ from pin", err)
        self.assertEqual(self.env_status(), "fail")

    def test_corrupt_numeric_field_even_if_repinned_is_rejected(self):
        # Attacker/accident also updates the pin: non-numeric content still fails.
        p = self.pvt()
        p.write_text(p.read_text().replace("1.80025256", "NOTANUMBER", 1))
        selp = self.tmp / "sim/characterization/selection.json"
        sel = json.loads(selp.read_text())
        sel["circuit_record"]["files"]["pvt_csv"]["sha256"] = G.sha256_file(p)
        selp.write_text(json.dumps(sel))
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn("not numeric", err)
        self.assertEqual(self.env_status(), "fail")

    def test_change_source_bytes_of_record_md(self):
        md = next(self.tmp.glob("sim/ldo-cmos5l-pvt-sweep/records/*.md"))
        md.write_text(md.read_text() + "\ntamper\n")
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn("differ from pin", err)

    def test_tamper_with_report_detected_by_check(self):
        rp = self.out / G.REPORT_JSON
        rp.write_text(rp.read_text().replace('"pass_full_coverage"', '"fail"', 1))
        rc, _, err = run_main("--root", str(self.tmp), "--check")
        self.assertEqual(rc, 1)
        self.assertIn("differs from regeneration", err)

    def test_tamper_with_envelope_status_detected(self):
        ep = self.out / G.ENVELOPE_JSON
        e = json.loads(ep.read_text())
        e["provenance"]["input"]["content_hash"] = "sha256:" + "0" * 64
        ep.write_text(json.dumps(e, indent=2) + "\n")
        rc, _, err = run_main("--root", str(self.tmp), "--check")
        self.assertEqual(rc, 1)

    def test_source_data_drift_in_spec_detected_by_check(self):
        rd = self.tmp / "README.md"
        rd.write_text(rd.read_text().replace("OPEN — unratified (no 0 mA dynamic evidence)",
                                             "OPEN — unratified (edited)", 1))
        rc, _, err = run_main("--root", str(self.tmp), "--check")
        self.assertEqual(rc, 1)
        self.assertIn("differs from regeneration", err)

    def test_readme_dr_ratification_disagreement_is_error(self):
        rd = self.tmp / "README.md"
        target = "RATIFIED as a shared target (stretch not ratified)"
        text = rd.read_text()
        self.assertIn(target, text)  # guard: the mutation must actually apply
        rd.write_text(text.replace(target, "OPEN — unratified (x)", 1))
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn("DR-0007 disposition", err)

    def test_stale_design_makes_envelope_fail_not_pass(self):
        n = self.tmp / "design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice"
        n.write_text(n.read_text() + "\n* design edited after the record\n")
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertEqual(self.env_status(), "fail")
        rep = json.loads((self.out / G.REPORT_JSON).read_text())
        self.assertEqual(rep["design_freshness"]["state"], "stale_against_design")
        self.assertEqual(rep["completeness"]["status"], "incomplete")
        self.assertTrue(all(r["evidence_state"] != "current" for r in rep["rows"] if r["id"] in (2, 3, 4, 5, 6, 10)))

    def test_incomplete_grid_is_error(self):
        p = self.pvt()
        lines = p.read_text().splitlines(keepends=True)
        p.write_text("".join(lines[:-1]))
        selp = self.tmp / "sim/characterization/selection.json"
        sel = json.loads(selp.read_text())
        sel["circuit_record"]["files"]["pvt_csv"]["sha256"] = G.sha256_file(p)
        selp.write_text(json.dumps(sel))
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn("grid incomplete", err)

    def test_malformed_selection_missing_key_fails_and_clears_pass(self):
        # Not a GenError path: a missing key raises KeyError inside build().
        # The committed passing envelope must still be replaced by status:fail.
        self.assertEqual(self.env_status(), "pass")
        selp = self.tmp / "sim/characterization/selection.json"
        sel = json.loads(selp.read_text())
        del sel["circuit_record"]["design_freshness_pins"]
        selp.write_text(json.dumps(sel))
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn("KeyError", err)
        self.assertIn("design_freshness_pins", err)
        env = json.loads((self.out / G.ENVELOPE_JSON).read_text())
        self.assertEqual(env["status"], "fail")
        self.assertIn("design_freshness_pins", env["summary"])
        rc, _, err = run_main("--root", str(self.tmp), "--check")
        self.assertEqual(rc, 1)

    def test_malformed_selection_not_json_fails_and_clears_pass(self):
        selp = self.tmp / "sim/characterization/selection.json"
        selp.write_text("{ not json")
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertEqual(self.env_status(), "fail")


if __name__ == "__main__":
    unittest.main()
