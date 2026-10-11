"""Tests for startup_campaign.py planning logic (issue #69): grid size,
request grouping, load resistor mapping, binding-point selection. No
simulator or network."""
import argparse
import csv
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import startup_campaign as sc  # noqa: E402


class Plan(unittest.TestCase):
    def test_grid_is_135_unique_points_in_3_requests(self):
        pts = sc.grid_points()
        self.assertEqual(len(pts), 135)
        self.assertEqual(len({sc.point_id(p) for p in pts}), 135)
        groups = sc.build_groups(pts)
        self.assertEqual(len(groups), 15)
        self.assertEqual([len(g) for g in groups], [9] * 15)
        for g in groups:
            self.assertEqual(len({sc.section(p) for p in g}), 1)
            self.assertEqual(len({p['temp'] for p in g}), 3)
            self.assertEqual(len({p['vin'] for p in g}), 3)

    def test_load_resistor(self):
        self.assertEqual(sc.load_resistor("1"), "1800")
        self.assertEqual(sc.load_resistor("50"), "36")
        self.assertIsNone(sc.load_resistor("0"))

    def test_ext_is_8_per_binding_point(self):
        b = [dict(sc.NOMINAL), dict(sc.NOMINAL, mos="ss", temp=125)]
        ext = sc.ext_points(b)
        self.assertEqual(len(ext), 16)
        self.assertEqual(len({sc.point_id(p) for p in ext}), 16)
        self.assertEqual({p["load_ma"] for p in ext}, {"0", "50"})
        self.assertEqual({p["cout_nf"] for p in ext}, {330, 4700})
        self.assertEqual({p["esr_mohm"] for p in ext}, {0, 500})

    def test_halfstep_caps_timestep(self):
        h = sc.halfstep_points([dict(sc.NOMINAL)])
        self.assertEqual(h[0]["tmax_ns"], 500)
        self.assertEqual(sc.tran_args(500), "500n 15m 0 500n")
        self.assertEqual(sc.tran_args(1000), "1000n 15m 0 1000n")

    def test_render_body_has_no_placeholder(self):
        p = dict(sc.NOMINAL, esr_mohm=500, load_ma="50", vin=3.63)
        b = sc.render_body(p, "d.spice", "p.cir")
        self.assertNotIn("@@", b)
        self.assertIn("Rload VOUT 0 36", b)
        self.assertIn("Resr COUT_ESR 0 500e-3", b)
        self.assertIn("Vin VIN 0 dc 3.63", b)
        self.assertIn("pwl(0 0 1m 0 1.001m 1 7m 1 7.001m 0 9m 0 9.001m 1 15m 1)", b)
        b0 = sc.render_body(dict(sc.NOMINAL, load_ma="0"), "d.spice", "p.cir")
        self.assertNotIn("\nRload", b0)
        self.assertNotIn("Resr", b0)

    def test_binding_selection_dedupes_and_flags_nonpass(self):
        def row(mos, v, over, st, exc, off, verdict="pass"):
            return {"mos": mos, "temp": "27", "res": "typ", "vin": v, "verdict": verdict,
                    "start_overshoot_v": over, "start_settle_time_s": st,
                    "start_max_down_excursion_v": exc, "off_vout_max_v": off}
        rows = [row("tt", "3.30", "0.01", "0.001", "0", "0"),
                row("ff", "3.63", "0.30", "0.0005", "0.1", "0"),
                row("ss", "2.97", "0.02", "", "0", "0", verdict="insufficient")]
        b = sc.binding_points(rows)
        keys = [(x["point"]["mos"], x["point"]["vin"]) for x in b]
        self.assertEqual(keys, [("ff", 3.63), ("ss", 2.97)])  # unsettled ranks worst
        self.assertIn("peak overshoot", b[0]["why"])


class Recollect(unittest.TestCase):
    """recollect re-evaluates committed traces into a NEW record (issue #130)
    without touching the source record."""

    def setUp(self):
        import test_startup_eval as tse
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        self.rec = os.path.join(root, "records")
        tdir = os.path.join(self.rec, "OLD-startup-grid.traces")
        os.makedirs(tdir)
        os.makedirs(os.path.join(root, "startup", "OLD", "grid"))
        json.dump({"requested": 2, "groups": []},
                  open(os.path.join(root, "startup", "OLD", "grid", "plan.json"), "w"))
        for n in ("tmpl", "design.spice"):
            open(os.path.join(root, n), "w").write(n)
        tr = tse._edge_trace()
        sc.write_trace(os.path.join(tdir, "p0.csv.gz"), tr)
        sha = sc.sha256_file(os.path.join(tdir, "p0.csv.gz"))
        cols = ["point", "mos", "temp", "res", "vin", "trace_file", "trace_sha256",
                "samples", "verdict", "off_supply_current_a", "reasons"]
        with open(os.path.join(self.rec, "OLD-startup-grid.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerow({"point": "p0", "mos": "tt", "temp": "27", "res": "typ", "vin": "3.30",
                        "trace_file": "OLD-startup-grid.traces/p0.csv.gz", "trace_sha256": sha,
                        "samples": len(tr["t"]), "verdict": "pass",
                        "off_supply_current_a": "2.8e-05"})
            w.writerow({"point": "p1", "mos": "ss", "temp": "27", "res": "typ", "vin": "3.30",
                        "verdict": "insufficient", "reasons": "no rawfile"})
        json.dump({"rid": "OLD", "stage": "grid", "requested": 2, "engines": ["ngspice-46"],
                   "runner_klt": ["0.5.0"], "client_klt": "klt x", "jobs": [], "osdi_sha256": {},
                   "pdk_pinned_commit": "a", "pdk_installed_commit": "a",
                   "source_sha256": {"startup_eval.py": "oldhash"}},
                  open(os.path.join(self.rec, "OLD-startup-grid.manifest.json"), "w"))
        open(os.path.join(self.rec, "OLD-startup-grid.md"), "w").write("old md\n")
        self.saved = (sc.HERE, sc.REPO, sc.TEMPLATE, sc.DESIGN)
        sc.HERE = root
        sc.REPO = root
        sc.TEMPLATE = os.path.join(root, "tmpl")
        sc.DESIGN = os.path.join(root, "design.spice")
        for n in ("startup_eval.py", "startup_campaign.py"):
            open(os.path.join(root, n), "w").write(n)
        self.addCleanup(lambda: (setattr(sc, "HERE", self.saved[0]), setattr(sc, "REPO", self.saved[1]),
                                 setattr(sc, "TEMPLATE", self.saved[2]), setattr(sc, "DESIGN", self.saved[3])))

    def _snap(self):
        return {n: open(os.path.join(self.rec, n), "rb").read() for n in os.listdir(self.rec)
                if os.path.isfile(os.path.join(self.rec, n))}

    def test_recollect_new_record_old_bytes_untouched(self):
        before = self._snap()
        tpath = os.path.join(self.rec, "OLD-startup-grid.traces", "p0.csv.gz")
        tbytes = open(tpath, "rb").read()
        a = argparse.Namespace(stage="grid", rid="NEW", source_rid="OLD")
        self.assertEqual(sc.cmd_recollect(a), 0)
        after = self._snap()
        for n, b in before.items():
            self.assertEqual(after[n], b)
        self.assertEqual(open(tpath, "rb").read(), tbytes)
        self.assertEqual(sorted(set(after) - set(before)),
                         ["NEW-startup-grid.csv", "NEW-startup-grid.manifest.json", "NEW-startup-grid.md"])
        rows = list(csv.DictReader(open(os.path.join(self.rec, "NEW-startup-grid.csv"))))
        self.assertEqual(rows[0]["trace_file"], "OLD-startup-grid.traces/p0.csv.gz")
        self.assertEqual(rows[0]["verdict"], "pass")
        self.assertEqual(float(rows[0]["off_supply_current_a"]), 2e-6)   # not the stale 2.8e-05
        self.assertEqual(rows[1]["verdict"], "insufficient")
        m = json.load(open(os.path.join(self.rec, "NEW-startup-grid.manifest.json")))
        self.assertEqual(m["rid"], "NEW")
        self.assertEqual(m["recollected_from"]["rid"], "OLD")
        self.assertEqual(m["recollected_from"]["source_evaluator_sha256"], "oldhash")
        self.assertEqual(m["recollected_from"]["traces_dir"], "records/OLD-startup-grid.traces")
        self.assertEqual((m["rows"], m["pass"], m["insufficient"]), (2, 1, 1))

    def test_recollect_refuses_overwrite_same_rid_and_tampered_trace(self):
        with self.assertRaises(sc.CampaignError):
            sc.cmd_recollect(argparse.Namespace(stage="grid", rid="OLD", source_rid="OLD"))
        sc.cmd_recollect(argparse.Namespace(stage="grid", rid="NEW", source_rid="OLD"))
        with self.assertRaises(sc.CampaignError):
            sc.cmd_recollect(argparse.Namespace(stage="grid", rid="NEW", source_rid="OLD"))
        with open(os.path.join(self.rec, "OLD-startup-grid.traces", "p0.csv.gz"), "ab") as f:
            f.write(b"x")
        with self.assertRaises(sc.CampaignError):
            sc.cmd_recollect(argparse.Namespace(stage="grid", rid="NEW2", source_rid="OLD"))


if __name__ == "__main__":
    unittest.main()
