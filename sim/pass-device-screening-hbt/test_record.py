#!/usr/bin/env python3
"""Offline fixture tests for gen_decks.py / record.py (issue #139). Stdlib only."""
import json
import pathlib
import tempfile
import unittest

import gen_decks as G
import record as R

HERE = pathlib.Path(__file__).resolve().parent


def fake_report(dev, bench, unreach_030=False, drop=None):
    """A minimal klt-sim-shaped report with plausible values for every measurement."""
    pol, _ = G.DEVICES[dev]
    _text, meas = (G.servo if bench == "servo" else G.vcesweep)(dev, pol, G.DEVICES[dev][1])
    corners = []
    for proc in G.PROCESS:
        for t in G.TEMPS_C:
            ms = []
            for name, _s, unit in meas:
                v = 1.0e-4
                if bench == "servo":
                    if name.startswith("ic_"):
                        tag = name[3:]
                        tgt = G_target(tag)
                        v = tgt * (0.5 if unreach_030 and tag.endswith("v030") else 1.0)
                    elif name.startswith("ib_"):
                        tag = name[3:]
                        # beta 500 at Vce 1.0, rising with Vce (Early-like)
                        vce = {"v030": 0.3, "v100": 1.0, "v150": 1.5, "v183": 1.83}.get(tag.split("_")[-1], 1.0)
                        v = G_target(tag) / (500.0 * (1 + vce / 100.0))
                    elif name.startswith("vb_"):
                        v = 0.9
                else:
                    v = 0.2 if name.startswith("vce_") else (0.9 if name.startswith("vb_") else 0.3)
                if drop == name:
                    v = None
                ms.append({"name": name, "value": v, "unit": unit})
            corners.append({"corner_id": f"{proc}/novdd/{t}C", "process": proc, "temperature_c": t,
                            "status": "pass", "measurements": ms, "diagnostics": []})
    return {"status": "pass", "corners": corners,
            "environment": {"engine": "ngspice", "engine_version": "46", "models_lib_sha256": "ab",
                            "netlist_sha256": f"{dev}{bench}",
                            "remote": {"provider": "aws-batch-fleet", "job_id": f"j-{dev}-{bench}"}},
            "provenance": {"klt_version": "0.7.0"}}


def G_target(tag):
    if tag.startswith("cell_"):
        return G.CELL_IC[tag[5:]]
    return int(tag.split("_")[0][1:]) * 1e-3


def write_record(root, **kw):
    rec = root / "20260101-000000-abc1234"
    (rec / "raw").mkdir(parents=True)
    for dev in G.DEVICES:
        for bench in G.BENCHES:
            (rec / "raw" / f"{dev}-{bench}.sim.json").write_text(json.dumps(fake_report(dev, bench, **kw)))
    return rec


class GenDecks(unittest.TestCase):
    def test_committed_decks_match_generator(self):
        self.assertEqual(G.main(["--check"]), 0)

    def test_measurement_names_unique_and_declared_in_netlist(self):
        for dev, (pol, spec) in G.DEVICES.items():
            for bench, fn in (("servo", G.servo), ("vcesweep", G.vcesweep)):
                text, meas = fn(dev, pol, spec)
                names = [m[0] for m in meas]
                self.assertEqual(len(names), len(set(names)), (dev, bench))
                for _n, spice, _u in meas:
                    self.assertTrue(spice.startswith(".meas dc "))

    def test_every_npn_is_isothermal(self):
        for dev, (pol, spec) in G.DEVICES.items():
            if pol == "npn":
                self.assertIn("selft=0", spec)


class Record(unittest.TestCase):
    def test_roundtrip_and_check(self):
        with tempfile.TemporaryDirectory() as d:
            rec = write_record(pathlib.Path(d))
            self.assertEqual(R.cmd_analyse(rec), 0)
            self.assertEqual(R.cmd_check(rec), 0)

    def test_csv_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            rec = write_record(pathlib.Path(d))
            R.cmd_analyse(rec)
            p = pathlib.Path(f"{rec}.csv")
            p.write_text(p.read_text().replace("npn13G2,", "npn13g2,", 1))
            self.assertEqual(R.cmd_check(rec), 1)

    def test_raw_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            rec = write_record(pathlib.Path(d))
            R.cmd_analyse(rec)
            f = rec / "raw" / "npn13G2-servo.sim.json"
            rep = json.loads(f.read_text())
            rep["corners"][0]["measurements"][0]["value"] *= 2
            f.write_text(json.dumps(rep))
            self.assertEqual(R.cmd_check(rec), 1)

    def test_missing_raw_report_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            rec = write_record(pathlib.Path(d))
            (rec / "raw" / "pnpMPA-vcesweep.sim.json").unlink()
            with self.assertRaises(SystemExit):
                R.cmd_analyse(rec)

    def test_unreached_target_is_blank_not_a_number(self):
        with tempfile.TemporaryDirectory() as d:
            rec = write_record(pathlib.Path(d), unreach_030=True)
            rows = R.rows_for(R.load_raw(rec))
            r = next(x for x in rows if x["device"] == "npn13G2" and x["load_ma"] == 50)
            self.assertEqual(r["ib_a_v030"], "")
            self.assertEqual(r["beta_v030"], "")
            self.assertAlmostEqual(float(r["ic_frac_v030"]), 0.5)
            self.assertNotEqual(r["ib_a_v150"], "")

    def test_missing_witness_fails_sanity_and_check(self):
        with tempfile.TemporaryDirectory() as d:
            rec = write_record(pathlib.Path(d), drop="ic_l50_v150")
            raw = R.load_raw(rec)
            fails = [s for s in R.sanity(raw, R.rows_for(raw)) if s.startswith("FAIL")]
            self.assertTrue(any("npn13G2/servo" in s for s in fails))
            R.cmd_analyse(rec)
            self.assertEqual(R.cmd_check(rec), 1)

    def test_early_voltage_and_iq_fraction(self):
        with tempfile.TemporaryDirectory() as d:
            rec = write_record(pathlib.Path(d))
            rows = R.rows_for(R.load_raw(rec))
            r = next(x for x in rows if x["device"] == "npn13G2" and x["load_ma"] == 50)
            # beta ~ 500*(1+Vce/100): Early voltage ~ 100 V
            self.assertAlmostEqual(float(r["early_v_1p0_1p5"]), 100.0, delta=1.0)
            ib = 0.05 / (500.0 * 1.015)
            self.assertAlmostEqual(float(r["ib_frac_iq30_v150"]), ib / 30e-6, delta=0.01 * ib / 30e-6)

    def test_preflight_gate(self):
        with tempfile.TemporaryDirectory() as d:
            good = pathlib.Path(d) / "g.json"
            good.write_text(json.dumps(fake_report("npn13G2", "servo")))
            self.assertEqual(R.cmd_preflight(good), 0)
            bad = pathlib.Path(d) / "b.json"
            rep = fake_report("npn13G2", "servo")
            rep["corners"][0]["diagnostics"].append({"code": "singular_matrix", "message": "x"})
            bad.write_text(json.dumps(rep))
            self.assertEqual(R.cmd_preflight(bad), 1)


if __name__ == "__main__":
    unittest.main()
