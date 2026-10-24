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
    dce = sel["dc_informational_evidence"]
    rels |= {f["path"] for f in dce["files"].values()}
    st = sel["startup_evidence"]
    rels |= {f["path"] for f in st["files"].values()}
    rels |= {p["path"] for p in st["design_freshness_pins"].values()}
    inv = json.loads((REPO / dce["files"]["coverage_inventory_json"]["path"]).read_text())
    rels.add(inv["generator"]["path"])
    rels |= set(inv["inputs"]["raw_dc_grids"])
    r10 = sel["row10_margin_evidence"]
    rels |= {f["path"] for f in r10["files"].values()}
    r10doc = json.loads((REPO / r10["files"]["classification_json"]["path"]).read_text())
    rels |= set(r10doc["classifier"])
    import csv as _csv
    with (REPO / r10["files"]["classification_csv"]["path"]).open(newline="") as fh:
        rels |= {row["trace"] for row in _csv.DictReader(fh)}
    for r in rels:
        (dst / r).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / r, dst / r)
    # 17 MB of traces: link, never copy; tests that tamper a trace replace the link.
    tdir = dst / st["traces_dir"]
    tdir.parent.mkdir(parents=True, exist_ok=True)
    tdir.symlink_to(REPO / st["traces_dir"], target_is_directory=True)


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
        self.assertEqual(v[9], "fail")              # measured startup failures, not an absence claim
        self.assertEqual(v[10], "ambiguous")        # DR-0014: no committed trace bounds the sweep ceiling
        self.assertEqual(self.rows[4]["ratification"]["state"], "ratified")
        self.assertEqual(self.rows[2]["ratification"]["state"], "open_unratified")

    def test_row9_reports_measured_startup_failures(self):
        r = self.rows[9]
        self.assertEqual(r["ratification"]["state"], "open_unratified")
        c = r["startup_campaign"]
        self.assertEqual((c["requested_points"], c["evaluated_points"], c["missing_points"],
                          c["insufficient_points"]), (135, 135, 0, 0))
        self.assertEqual(c["csv_verdicts"], {"pass": 0, "fail": 135, "insufficient": 0})
        self.assertEqual(c["settled_within_3ms_points"], 135)
        self.assertEqual(c["settled_within_3ms_but_failing_points"], 135)
        self.assertEqual(c["design_freshness"]["state"], "current")
        self.assertEqual(set(c["design_freshness"]["components"]), {"core", "error_amp"})
        mx = c["extrema"]["start peak VOUT [V]"]["max"]
        self.assertEqual(mx["at"]["corner"], "ff")
        self.assertEqual(mx["at"]["vin_v"], 3.63)
        by = {m["source"]["column"]: m for m in r["metrics"]}
        self.assertEqual(by["start_settle_time_s"]["verdict"], "pass")   # numeric settling passes ...
        self.assertEqual(by["start_peak_vout_v"]["verdict"], "fail")     # ... but does not mask failures
        self.assertEqual(by["start_max_down_excursion_v"]["n_fail"], 135)
        self.assertNotIn("not_implemented", json.dumps(r))
        self.assertNotIn("No enable input", json.dumps(r))
        self.assertIn("proposed", json.dumps(r).lower())

    def test_row9_verdict_function(self):
        f = G.startup_row_verdict
        self.assertEqual(f(1, 0, 0, 10), "fail")
        self.assertEqual(f(1, 5, 5, 10), "fail")            # failure never masked by gaps
        self.assertEqual(f(0, 1, 0, 9), "not_measured")     # insufficient is never a pass
        self.assertEqual(f(0, 0, 1, 9), "not_measured")     # missing is never a pass
        self.assertEqual(f(0, 0, 0, 0), "not_measured")
        self.assertEqual(f(0, 0, 0, 135), "pass_partial_coverage")

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
        # Selected record 20261011-051956-eda9285 (G1 pull-down design, #89):
        # iq_a 2.47221724e-05 A at ss/125C/res_bcs. The #67 record
        # 20261010-025634-60a3e81 had 2.47221613e-05 A and the pre-EN record
        # 20260917-023832-7061e8f 2.47222854e-05 A at the same point.
        self.assertAlmostEqual(m["worst_case"]["value"], 24.7221724, places=6)
        fl = self.rows[7]["metrics"][1]
        self.assertEqual((fl["unit"], fl["verdict"], fl["n_points"], fl["n_invalid"]), ("uA", "pass", 45, 0))
        # #89 record; the #67 record had 24.8873 (one 1e-10 A quantization step).
        self.assertAlmostEqual(fl["worst_case"]["value"], 24.8874, places=6)
        self.assertEqual(fl["worst_case"]["at"], {"corner": "ff", "temp_c": 125, "res_section": "res_bcs"})
        self.assertIn("quantized at 1e-10 A", fl["note"])
        self.assertIn("NOT used", fl["note"])
        self.assertEqual(self.rows[7]["ratification"]["state"], "open_unratified")
        self.assertEqual(self.rows[7]["verdict"], "pass_partial_coverage")

    def test_row5_loaded_line_and_multi_vin_load_regulation(self):
        ms = {m["name"]: m for m in self.rows[5]["metrics"]}
        self.assertEqual(len(ms), 10)  # 2 legacy + 5 loads + 3 supplies
        line = [m for n, m in ms.items() if n.startswith("line regulation at ")]
        load = [m for n, m in ms.items() if n.startswith("load regulation 0-50 mA at Vin")]
        self.assertEqual((len(line), len(load)), (5, 3))
        for m in line + load:
            self.assertEqual((m["n_points"], m["n_invalid"], m["n_ambiguous"]), (45, 0, 0))
        w0 = ms["line regulation at 0 mA load (Vin 2.97-3.63 V)"]["worst_case"]
        # #89 record; the #67 record had 0.245757576 at the same point.
        self.assertAlmostEqual(w0["value"], 0.245772727, places=8)
        self.assertEqual(w0["at"], {"corner": "ff", "temp_c": 125, "res_section": "res_wcs"})
        w = ms["load regulation 0-50 mA at Vin = 2.97 V"]["worst_case"]
        # #89 record; the #67 record had 0.0228481926.
        self.assertAlmostEqual(w["value"], 0.0228476479, places=8)
        self.assertIn("legacy", [n for n in ms][0])
        self.assertEqual(self.rows[5]["ratification"]["state"], "open_unratified")
        self.assertEqual(self.rows[5]["verdict"], "pass_partial_coverage")
        self.assertEqual(self.rows[5]["coverage"]["state"], "partial")
        self.assertTrue(any("not continuous coverage" in g for g in self.rows[5]["coverage"]["gaps"]))

    def test_stability_dr0014_classification(self):
        pm, gm = self.rows[10]["metrics"]
        self.assertIn("DR-0014", pm["name"])
        self.assertIn("DR-0014", gm["name"])
        # Every committed trace ends near +1 dB at the 10 GHz ceiling (#128; it
        # was 100 MHz and rising for earlier records), so the ceiling premise
        # fails everywhere: nothing is scored as a pass.
        for m in (pm, gm):
            self.assertEqual((m["n_points"], m["n_pass"], m["n_fail"], m["n_ambiguous"]), (45, 0, 0, 45))
            self.assertEqual(m["reasons"], {"ceiling_unbounded": 45})
            self.assertEqual(m["verdict"], "ambiguous")
        mc = self.rows[10]["margin_classification"]
        self.assertEqual((mc["ceiling_bounded"], mc["multi_crossing_points"], mc["status"]), (0, 45, "proposed"))
        self.assertEqual(mc["sweep_ceiling_hz"], 1e10)
        # the superseded first-crossing reading is reported, not scored
        self.assertTrue(any("0 of 45 scored >= 45 deg, 45 unscored" in d for d in pm["detail"]))
        self.assertTrue(any("not a margin" in d for d in pm["detail"]))
        self.assertEqual(self.rows[10]["ratification"]["state"], "open_unratified")

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

    # --- DC informational evidence (rows 5 and 7) ----------------------------
    def selection(self):
        p = self.tmp / "sim/characterization/selection.json"
        return p, json.loads(p.read_text())

    def dc_summary(self):
        _, sel = self.selection()
        return self.tmp / sel["dc_informational_evidence"]["files"]["summary_csv"]["path"]

    def repin_dc(self, key="summary_csv"):
        p, sel = self.selection()
        f = sel["dc_informational_evidence"]["files"][key]
        f["sha256"] = G.sha256_file(self.tmp / f["path"])
        p.write_text(json.dumps(sel))

    def edit_summary(self, fn):
        s = self.dc_summary()
        before = s.read_text()
        after = "".join(fn(before.splitlines(keepends=True)))
        # A mutation that matches nothing (e.g. a literal from an older selected
        # record) would make the negative control vacuous.
        self.assertNotEqual(after, before, "summary mutation changed nothing")
        s.write_text(after)
        self.repin_dc()

    def assert_rejected(self, text):
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn(text, err)
        self.assertEqual(self.env_status(), "fail")

    def test_dc_summary_tamper_fails_pin(self):
        s = self.dc_summary()
        s.write_text(s.read_text().replace("0.167272727", "0.167272728", 1))
        self.assert_rejected("differ from pin")

    def test_dc_inventory_tamper_fails_pin(self):
        _, sel = self.selection()
        inv = self.tmp / sel["dc_informational_evidence"]["files"]["coverage_inventory_json"]["path"]
        inv.write_text(inv.read_text() + " ")
        self.assert_rejected("differ from pin")

    def test_dc_missing_selection_block_is_error(self):
        p, sel = self.selection()
        del sel["dc_informational_evidence"]
        p.write_text(json.dumps(sel))
        self.assert_rejected("dc_informational_evidence")

    def test_dc_record_id_mismatch_rejected(self):
        p, sel = self.selection()
        sel["dc_informational_evidence"]["circuit_record_id"] = "20260917-023832-7061e8f"
        p.write_text(json.dumps(sel))
        self.assert_rejected("selected circuit record")

    def test_dc_inventory_for_other_record_rejected(self):
        _, sel = self.selection()
        invp = self.tmp / sel["dc_informational_evidence"]["files"]["coverage_inventory_json"]["path"]
        inv = json.loads(invp.read_text())
        inv["inputs"]["record_csv"]["sha256"] = "0" * 64
        invp.write_text(json.dumps(inv))
        self.repin_dc("coverage_inventory_json")
        self.assert_rejected("does not match the selected record")

    def test_dc_inventory_design_mismatch_rejected(self):
        _, sel = self.selection()
        invp = self.tmp / sel["dc_informational_evidence"]["files"]["coverage_inventory_json"]["path"]
        inv = json.loads(invp.read_text())
        k = next(iter(inv["inputs"]["design_netlists"]))
        inv["inputs"]["design_netlists"][k] = "0" * 64
        invp.write_text(json.dumps(inv))
        self.repin_dc("coverage_inventory_json")
        self.assert_rejected("design freshness pins")

    def test_dc_raw_grid_tamper_rejected(self):
        _, sel = self.selection()
        invp = self.tmp / sel["dc_informational_evidence"]["files"]["coverage_inventory_json"]["path"]
        raw = next(iter(json.loads(invp.read_text())["inputs"]["raw_dc_grids"]))
        rp = self.tmp / raw
        rp.write_text(rp.read_text() + "\n")
        self.assert_rejected("raw DC grid bytes differ")

    def test_dc_missing_corner_rejected(self):
        self.edit_summary(lambda ls: ls[:-1])
        self.assert_rejected("corner set incomplete")

    def test_dc_duplicate_corner_rejected(self):
        self.edit_summary(lambda ls: ls + [ls[1]])
        self.assert_rejected("duplicate corner")

    def test_dc_non_finite_value_rejected(self):
        self.edit_summary(lambda ls: [ls[0], ls[1].replace("2.25169e-05", "nan", 1)] + ls[2:])
        self.assert_rejected("not finite")

    def test_dc_invalid_validity_field_rejected(self):
        self.edit_summary(lambda ls: [ls[0], ls[1].replace(",True,", ",Maybe,", 2)] + ls[2:])
        self.assert_rejected("must be True/False")

    def test_dc_wrong_units_schema_rejected(self):
        self.edit_summary(lambda ls: [ls[0].replace("iq_fullload_excl_load_a", "iq_fullload_excl_load_ua", 1)] + ls[1:])
        self.assert_rejected("columns differ")

    def test_dc_disagreement_with_pvt_csv_rejected(self):
        self.edit_summary(lambda ls: [ls[0], ls[1].replace(",2.24488956e-05,", ",2.34488956e-05,", 1)] + ls[2:])
        self.assert_rejected("disagrees with the pinned PVT csv")

    def test_dc_invalid_point_is_counted_never_dropped(self):
        # Flip the first row's full-load validity flag: still a complete grid, so the
        # run succeeds, but the point is ambiguous and blocks a clean pass.
        def flip(ls):
            cells = ls[1].rstrip("\n").split(",")
            cells[6] = "False"
            return [ls[0], ",".join(cells) + "\n"] + ls[2:]
        self.edit_summary(flip)
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 0, err)
        rep = json.loads((self.out / G.REPORT_JSON).read_text())
        r7 = next(r for r in rep["rows"] if r["id"] == 7)
        fl = r7["metrics"][1]
        self.assertEqual((fl["n_points"], fl["n_invalid"], fl["n_ambiguous"], fl["n_pass"]), (45, 1, 1, 44))
        self.assertEqual(fl["verdict"], "ambiguous")
        self.assertEqual(r7["verdict"], "ambiguous")

    def test_dc_over_bound_value_is_a_fail_not_dropped(self):
        self.edit_summary(lambda ls: [ls[0], ls[1].replace("2.25169e-05", "3.25169e-05", 1)] + ls[2:])
        rc, _, err = run_main("--root", str(self.tmp))
        # pvt agreement does not cover full-load Iq, so this is a valid but failing point
        self.assertEqual(rc, 0, err)
        rep = json.loads((self.out / G.REPORT_JSON).read_text())
        r7 = next(r for r in rep["rows"] if r["id"] == 7)
        self.assertEqual(r7["metrics"][1]["verdict"], "fail")
        self.assertEqual(r7["verdict"], "fail")
        self.assertAlmostEqual(r7["metrics"][1]["worst_case"]["value"], 32.5169, places=6)


class SweepCeilingTests(unittest.TestCase):
    """The row-10 text quotes the sweep ceiling read from the traces (#128)."""

    def test_fmt_hz(self):
        self.assertEqual(G._fmt_hz(1e8), "100 MHz")
        self.assertEqual(G._fmt_hz(1e10), "10 GHz")
        self.assertEqual(G._fmt_hz(1e3), "1 kHz")

    def test_ceiling_read_from_last_row_and_bad_traces_rejected(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        p = tmp / "t.csv"
        p.write_text(" 1.0e+00 0 1.0e+00 0 \n 1.0e+10 0 1.0e+10 0 \n")
        self.assertEqual(G._trace_ceiling_hz(p, "x"), 1e10)
        p.write_text("")
        with self.assertRaises(G.GenError):
            G._trace_ceiling_hz(p, "x")
        p.write_text(" 1.0 0 1.0 0 \n nan 0 nan 0 \n")
        with self.assertRaises(G.GenError):
            G._trace_ceiling_hz(p, "x")


class Row10NegativeControls(unittest.TestCase):
    """DR-0014 row-10 classification: every way the pinned classification can
    disagree with the record, its traces, its classifier or the target fails
    closed (and leaves no passing envelope)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        copy_inputs(self.tmp)
        self.selp = self.tmp / "sim/characterization/selection.json"

    def sel(self):
        return json.loads(self.selp.read_text())

    def path(self, key):
        return self.tmp / self.sel()["row10_margin_evidence"]["files"][key]["path"]

    def repin(self, key):
        sel = self.sel()
        f = sel["row10_margin_evidence"]["files"][key]
        f["sha256"] = G.sha256_file(self.tmp / f["path"])
        self.selp.write_text(json.dumps(sel))

    def edit_csv(self, fn):
        p = self.path("classification_csv")
        ls = p.read_text().splitlines(keepends=True)
        p.write_text("".join(fn(ls)))
        jp = self.path("classification_json")
        doc = json.loads(jp.read_text())
        doc["csv"]["sha256"] = G.sha256_file(p)
        jp.write_text(json.dumps(doc))
        self.repin("classification_csv")
        self.repin("classification_json")

    def set_field(self, row, field, value):
        def fn(ls):
            hdr = ls[0].rstrip("\n").split(",")
            cells = ls[row].rstrip("\n").split(",")
            cells[hdr.index(field)] = value
            return ls[:row] + [",".join(cells) + "\n"] + ls[row + 1:]
        self.edit_csv(fn)

    def rejected(self, text):
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1, err)
        self.assertIn(text, err)
        env = json.loads((self.tmp / "sim/characterization" / G.ENVELOPE_JSON).read_text())
        self.assertEqual(env["status"], "fail")

    def test_baseline_ok(self):
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 0, err)

    def test_missing_block(self):
        sel = self.sel()
        del sel["row10_margin_evidence"]
        self.selp.write_text(json.dumps(sel))
        self.rejected("row10_margin_evidence")

    def test_record_id_mismatch(self):
        sel = self.sel()
        sel["row10_margin_evidence"]["circuit_record_id"] = "20260917-023832-7061e8f"
        self.selp.write_text(json.dumps(sel))
        self.rejected("selected circuit record")

    def test_csv_tamper_fails_pin(self):
        p = self.path("classification_csv")
        p.write_text(p.read_text().replace("ambiguous", "pass", 1))
        self.rejected("differ from pin")

    def test_trace_tamper(self):
        import csv as _csv
        with self.path("classification_csv").open(newline="") as fh:
            tr = self.tmp / next(_csv.DictReader(fh))["trace"]
        tr.write_text(tr.read_text() + "\n")
        self.rejected("differs from its recorded sha256")

    def test_classifier_drift(self):
        doc = json.loads(self.path("classification_json").read_text())
        src = self.tmp / next(p for p in doc["classifier"] if p.endswith("ac_metrics.py"))
        src.write_text(src.read_text() + "\n# drift\n")
        self.rejected("classifier source")

    def test_bounds_changed(self):
        jp = self.path("classification_json")
        doc = json.loads(jp.read_text())
        doc["bounds"]["pm_deg"] = 40.0
        jp.write_text(json.dumps(doc))
        self.repin("classification_json")
        self.rejected("differ from the row-10 target")

    def test_pass_contradicting_its_number(self):
        self.set_field(1, "pm_verdict", "pass")
        self.set_field(1, "pm_deg", "44.9")
        self.rejected("contradicts pm_deg")

    def test_gm_pass_without_bounded_ceiling(self):
        # a first-crossing GM of 16.9 dB is not a pass without a ceiling bound
        self.set_field(1, "gm_verdict", "pass")
        self.rejected("GM verdict pass contradicts")

    def test_record_column_disagreement(self):
        self.set_field(1, "record_phase_margin_deg", "76.0")
        self.rejected("disagrees with the pinned PVT csv")

    def test_missing_corner(self):
        self.edit_csv(lambda ls: ls[:-1])
        self.rejected("corner set incomplete")

    def test_recorded_miss_is_never_upgraded(self):
        # Fed directly to the loader: a PVT row showing PM 40 deg (a miss) whose
        # classification is still ambiguous must be refused.
        self.set_field(1, "record_phase_margin_deg", "40.0")
        sel = self.sel()
        rec = sel["circuit_record"]
        prow = G.read_csv(self.tmp / rec["files"]["pvt_csv"]["path"])
        prow[0]["phase_margin_deg"] = "40.0"
        with self.assertRaises(G.GenError) as cm:
            G.load_row10(self.tmp, sel, rec, prow, [])
        self.assertIn("upgrades a recorded PM miss", str(cm.exception))


class StartupNegativeControls(unittest.TestCase):
    """Row 9 startup evidence: tampered/missing/stale/duplicate/missing-point/insufficient."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        copy_inputs(self.tmp)
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 0, err)
        self.out = self.tmp / "sim/characterization"
        self.selp = self.out / "selection.json"
        self.sel = json.loads(self.selp.read_text())
        self.st = self.sel["startup_evidence"]

    def path(self, key):
        return self.tmp / self.st["files"][key]["path"]

    def repin(self, key):
        self.st["files"][key]["sha256"] = G.sha256_file(self.path(key))
        self.selp.write_text(json.dumps(self.sel))

    def env_status(self):
        return json.loads((self.out / G.ENVELOPE_JSON).read_text())["status"]

    def rejected(self, text):
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn(text, err)
        self.assertEqual(self.env_status(), "fail")

    def edit_csv(self, fn):
        p = self.path("grid_csv")
        lines = p.read_text().splitlines(keepends=True)
        p.write_text("".join(fn(lines)))
        self.repin("grid_csv")

    def report9(self):
        rep = json.loads((self.out / G.REPORT_JSON).read_text())
        return rep, {r["id"]: r for r in rep["rows"]}[9]

    def test_baseline_check_passes(self):
        rc, _, err = run_main("--root", str(self.tmp), "--check")
        self.assertEqual(rc, 0, err)

    def test_missing_selection_block_is_error(self):
        del self.sel["startup_evidence"]
        self.selp.write_text(json.dumps(self.sel))
        self.rejected("startup_evidence")

    def test_missing_selected_file_is_error(self):
        self.path("grid_csv").unlink()
        self.rejected("selected record missing")

    def test_tampered_selected_csv_fails_pin(self):
        p = self.path("grid_csv")
        p.write_text(p.read_text().replace("fail", "pass", 1))
        self.rejected("differ from pin")

    def test_tampered_manifest_fails_pin(self):
        p = self.path("manifest_json")
        p.write_text(p.read_text() + " ")
        self.rejected("differ from pin")

    def test_tampered_record_md_fails_pin(self):
        p = self.path("record_md")
        p.write_text(p.read_text() + " ")
        self.rejected("differ from pin")

    def test_tampered_trace_is_error(self):
        tdir = self.tmp / self.st["traces_dir"]
        real = REPO / self.st["traces_dir"]
        tdir.unlink()
        shutil.copytree(real, tdir)
        victim = sorted(tdir.iterdir())[0]
        victim.write_bytes(victim.read_bytes()[:-8] + b"\0" * 8)
        self.rejected("trace")

    def test_missing_trace_is_error(self):
        tdir = self.tmp / self.st["traces_dir"]
        tdir.unlink()
        shutil.copytree(REPO / self.st["traces_dir"], tdir)
        sorted(tdir.iterdir())[0].unlink()
        self.rejected("trace file missing")

    def test_stale_core_hash_is_independent_and_fails_envelope(self):
        n = self.tmp / self.st["design_freshness_pins"]["core"]["path"]
        n.write_text(n.read_text() + "\n* edited after the campaign\n")
        rc, _, _ = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertEqual(self.env_status(), "fail")
        _rep, r9 = self.report9()
        fr = r9["startup_campaign"]["design_freshness"]
        self.assertEqual(fr["stale_components"], ["core"])
        self.assertTrue(fr["components"]["error_amp"]["matches"])
        self.assertEqual(r9["evidence_state"], "stale_against_design")

    def test_stale_error_amp_hash_is_independent_and_fails_envelope(self):
        n = self.tmp / self.st["design_freshness_pins"]["error_amp"]["path"]
        n.write_text(n.read_text() + "\n* edited after the campaign\n")
        rc, _, _ = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertEqual(self.env_status(), "fail")
        rep, r9 = self.report9()
        fr = r9["startup_campaign"]["design_freshness"]
        self.assertEqual(fr["state"], "stale_against_design")
        self.assertEqual(fr["stale_components"], ["error_amp"])
        self.assertTrue(fr["components"]["core"]["matches"])
        self.assertEqual(r9["evidence_state"], "stale_against_design")

    def test_stale_startup_pin_alone_fails_envelope(self):
        # Legacy record stays current; only the startup pin for the error amp moves.
        self.st["design_freshness_pins"]["error_amp"]["sha256"] = "0" * 64
        self.selp.write_text(json.dumps(self.sel))
        rc, _, _ = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertEqual(self.env_status(), "fail")
        rep, r9 = self.report9()
        self.assertEqual(rep["design_freshness"]["state"], "current")
        self.assertEqual(r9["startup_campaign"]["design_freshness"]["stale_components"], ["error_amp"])

    def test_core_pin_disagreeing_with_manifest_is_error(self):
        self.st["design_freshness_pins"]["core"]["sha256"] = "0" * 64
        self.selp.write_text(json.dumps(self.sel))
        self.rejected("source_sha256")

    def test_duplicate_point_is_error(self):
        self.edit_csv(lambda ls: ls + [ls[1]])
        self.rejected("duplicate campaign point")

    def test_unexpected_point_is_error(self):
        self.edit_csv(lambda ls: ls[:1] + [ls[1].replace(",ff,-40,bcs,2.97,", ",ff,-40,bcs,2.5,", 1)] + ls[2:])
        self.rejected("outside the selected requested grid")

    def test_missing_point_is_reported_and_fails_envelope(self):
        self.edit_csv(lambda ls: ls[:-1])
        rc, _, _ = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertEqual(self.env_status(), "fail")
        rep, r9 = self.report9()
        c = r9["startup_campaign"]
        self.assertEqual((c["requested_points"], c["evaluated_points"], c["missing_points"]), (135, 134, 1))
        self.assertEqual(len(c["missing"]), 1)
        self.assertEqual(rep["completeness"]["status"], "incomplete")
        self.assertEqual(r9["verdict"], "fail")      # measured failures still reported as failures
        self.assertEqual(r9["ratification"]["state"], "open_unratified")

    def test_insufficient_trace_is_counted_never_a_pass(self):
        def blank(ls):
            hdr = ls[0].rstrip("\n").split(",")
            row = ls[1].rstrip("\n").split(",")
            keep = {"point", "mos", "temp", "res", "vin", "load_ma", "cout_nf", "esr_mohm", "tmax_ns", "group"}
            new = [v if h in keep else "" for h, v in zip(hdr, row)]
            new[hdr.index("verdict")] = "insufficient"
            new[hdr.index("reasons")] = "trace too short"
            return [ls[0], ",".join(new) + "\n"] + ls[2:]
        self.edit_csv(blank)
        rc, _, err = run_main("--root", str(self.tmp))
        # the manifest still says 135 evaluated: disagreement is a hard error, not a pass
        self.assertEqual(rc, 1)
        self.assertIn("disagrees with the pinned csv", err)
        self.assertEqual(self.env_status(), "fail")

    def test_insufficient_with_consistent_manifest_is_not_pass(self):
        def blank(ls):
            hdr = ls[0].rstrip("\n").split(",")
            row = ls[1].rstrip("\n").split(",")
            keep = {"point", "mos", "temp", "res", "vin", "load_ma", "cout_nf", "esr_mohm", "tmax_ns", "group"}
            new = [v if h in keep else "" for h, v in zip(hdr, row)]
            new[hdr.index("verdict")] = "insufficient"
            new[hdr.index("reasons")] = "trace too short"
            return [ls[0], ",".join(new) + "\n"] + ls[2:]
        self.edit_csv(blank)
        mp = self.path("manifest_json")
        man = json.loads(mp.read_text())
        man.update({"evaluated": 134, "insufficient": 1, "fail": 134})
        mp.write_text(json.dumps(man))
        self.repin("manifest_json")
        rc, _, err = run_main("--root", str(self.tmp))
        self.assertEqual(rc, 0, err)
        rep, r9 = self.report9()
        c = r9["startup_campaign"]
        self.assertEqual((c["evaluated_points"], c["insufficient_points"]), (134, 1))
        self.assertTrue(any("insufficient" in g for g in r9["coverage"]["gaps"]))
        self.assertNotIn(r9["verdict"], ("pass_partial_coverage", "pass_full_coverage"))

    def test_all_pass_but_insufficient_is_not_a_pass(self):
        self.assertEqual(G.startup_row_verdict(0, 1, 0, 134), "not_measured")

    def test_csv_pass_contradicting_metric_is_error(self):
        def flip(ls):
            hdr = ls[0].rstrip("\n").split(",")
            row = ls[1].rstrip("\n").split(",")
            row[hdr.index("verdict")] = "pass"
            return [ls[0], ",".join(row) + "\n"] + ls[2:]
        self.edit_csv(flip)
        mp = self.path("manifest_json")
        man = json.loads(mp.read_text())
        man.update({"pass": 1, "fail": 134})
        mp.write_text(json.dumps(man))
        self.repin("manifest_json")
        self.rejected("contradicts a measured metric")

    def test_measured_failure_despite_settling_within_3ms(self):
        rep, r9 = self.report9()
        c = r9["startup_campaign"]
        self.assertEqual(c["settled_within_3ms_but_failing_points"], c["settled_within_3ms_points"])
        by = {m["source"]["column"]: m for m in r9["metrics"]}
        self.assertEqual(by["start_settle_time_s"]["verdict"], "pass")
        self.assertEqual(r9["verdict"], "fail")


if __name__ == "__main__":
    unittest.main()
