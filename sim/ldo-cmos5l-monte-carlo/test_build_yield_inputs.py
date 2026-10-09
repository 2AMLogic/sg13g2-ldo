"""Offline tests for build_yield_inputs.py and the `klt yield` contract this
campaign relies on (issue #56).

Run:  python3 -m unittest sim/ldo-cmos5l-monte-carlo/test_build_yield_inputs.py

The `klt yield` cases need a klt whose klt_yield_native extension imports
(set KLT=/path/to/klt; default `klt` on PATH). They skip -- loudly, with the
reason -- when it is absent, e.g. on a host where klayout-tools[yield] does
not resolve (klayout-tools#2900).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_yield_inputs as b  # noqa: E402

LIM = {"min": 1.764, "max": 1.836}
KLT = os.environ.get("KLT", "klt")


def corner(proc, temp, idx, value, status="pass", cstatus="pass", supply=None):
    sup = supply or {}
    sid = "/".join(f"{v:.3f}V" for v in sup.values()) or "novdd"
    return {
        "corner_id": f"{proc}/{sid}/{temp}C/mc{idx}",
        "process": proc,
        "supply_v": sup,
        "temperature_c": temp,
        "status": cstatus,
        "measurements": [{"name": "vout_v", "value": value, "status": status}],
        "monte_carlo": {"sample_index": idx},
    }


def report(corners):
    return {"measurements": [{"name": "vout_v", "unit": "V", "limits": LIM}],
            "corners": corners}


class SplitTests(unittest.TestCase):
    def test_split_by_population_keeps_order_and_values(self):
        r = report([corner("tt", 27, 1, 1.80), corner("ss", 125, 0, 1.79),
                    corner("tt", 27, 0, 1.81)])
        d, nc = b.build(r, None, "vout_v", 0.99, "")
        self.assertEqual(list(d), ["tt_27C", "ss_125C"])
        m = d["tt_27C"]["measurements"][0]
        self.assertEqual(m["samples"], [1.81, 1.80])
        self.assertEqual(m["source_corners"], ["tt/novdd/27C"])
        self.assertEqual(m["limits"], {"min": 1.764, "max": 1.836, "target_yield": 0.99})
        self.assertEqual(nc, {})

    def test_failures_stay_visible_and_accounted(self):
        r = report([
            corner("tt", 27, 0, None, status="error", cstatus="error"),
            corner("tt", 27, 1, float("nan")),
            corner("tt", 27, 2, 1.80, status="inconclusive"),
            corner("tt", 27, 3, 1.80, cstatus="inconclusive"),
            corner("tt", 27, 4, 1.80),
            corner("tt", 27, 5, "1.80"),  # non-numeric -> null, never coerced
        ])
        pops = b.split_report(r, "vout_v")
        p = pops["tt/novdd/27C"]
        self.assertEqual(p["samples"], [None, None, 1.80, None])
        self.assertEqual((p["nulls"], p["inconclusive"], p["draws"]), (3, 2, 6))

    def test_null_policy_failed_unmeasurable(self):
        r = report([corner("tt", 27, 0, None, status="error"), corner("tt", 27, 1, 1.8)])
        m = b.build(r, None, "vout_v", 0.99, "", "failed_unmeasurable")[0]["tt_27C"]["measurements"][0]
        self.assertEqual(m["samples"], [1.8])
        self.assertEqual(m["failed_unmeasurable"], 1)

    def test_deterministic_corners_ignored(self):
        c = corner("tt", 27, 0, 1.8)
        del c["monte_carlo"]
        self.assertEqual(b.split_report(report([c]), "vout_v"), {})

    def test_duplicate_sample_index_refused(self):
        r = report([corner("tt", 27, 0, 1.8), corner("tt", 27, 0, 1.81)])
        with self.assertRaises(SystemExit):
            b.split_report(r, "vout_v")

    def test_negative_control_attached_and_standalone(self):
        r = report([corner("tt", 27, 0, 1.80), corner("ss", 125, 0, 1.79)])
        nc = report([corner("tt", 27, 0, 1.86, supply={"vref": 0.93})])
        d, ncd = b.build(r, nc, "vout_v", 0.99, "forced")
        att = d["tt_27C"]["measurements"][0]["negative_control"]
        self.assertEqual(att["samples"], [1.86])
        self.assertIn("tt/0.930V/27C", att["description"])
        self.assertNotIn("negative_control", d["ss_125C"]["measurements"][0])
        self.assertEqual(list(ncd), ["tt_27C_vref0.93V"])
        self.assertEqual(ncd["tt_27C_vref0.93V"]["measurements"][0]["samples"], [1.86])


def _klt_yield_available():
    if not shutil.which(KLT):
        return False, f"{KLT} not on PATH"
    doc = {"measurements": [{"name": "v", "samples": [1.0, 1.1], "limits": {"min": 0}}]}
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "s.json"
        p.write_text(json.dumps(doc))
        r = subprocess.run([KLT, "yield", str(p), "--format", "json"],
                           capture_output=True, text=True)
    if r.returncode == 1 and "klt_yield_native" in (r.stdout + r.stderr):
        return False, "klt_yield_native not importable (klayout-tools#2900)"
    return True, ""


_OK, _WHY = _klt_yield_available()


@unittest.skipUnless(_OK, _WHY)
class KltYieldContractTests(unittest.TestCase):
    """Boundary classification and verdicts are klt yield's job; pin them for
    THIS row's limits so a tool change that moves them is caught."""

    def run_yield(self, entry):
        entry = {"name": "vout_v", "limits": dict(LIM), **entry}
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "s.json"
            p.write_text(json.dumps({"measurements": [entry]}))
            r = subprocess.run([KLT, "yield", str(p), "--format", "json"],
                               capture_output=True, text=True)
        return r.returncode, json.loads(r.stdout)

    def test_inclusive_bounds_and_out_of_window(self):
        rc, d = self.run_yield({"samples": [1.764, 1.836, 1.80, 1.7639999, 1.8360001]})
        self.assertEqual(d["measurements"][0]["yield"]["empirical"]["estimate"], 3 / 5)

    def test_nulls_counted_as_errored_and_disclosed(self):
        rc, d = self.run_yield({"samples": [1.80, 1.79, 1.81, None, None]})
        m = d["measurements"][0]
        self.assertEqual((m["errored"], m["n"]), (2, 3))
        self.assertTrue(any("errored" in w for w in m["warnings"]))

    def test_failed_unmeasurable_counts_against_yield(self):
        rc, d = self.run_yield({"samples": [1.80, 1.79, 1.81], "failed_unmeasurable": 1})
        self.assertEqual(d["measurements"][0]["yield"]["empirical"]["estimate"], 3 / 4)

    def test_known_bad_population_fails_target_and_is_detected(self):
        good = [1.80 + 0.001 * ((i % 21) - 10) for i in range(400)]
        bad = [v + 0.06 for v in good]
        lim = dict(LIM, target_yield=0.99)
        rc, d = self.run_yield({"samples": bad, "limits": lim})
        self.assertEqual((rc, d["status"]), (3, "fail"))
        rc, d = self.run_yield({"samples": good, "limits": lim,
                                "negative_control": {"samples": bad, "description": "t"}})
        self.assertEqual((rc, d["status"]), (0, "pass"))
        self.assertEqual(d["measurements"][0]["negative_control"]["verdict"], "detected")


if __name__ == "__main__":
    unittest.main()
