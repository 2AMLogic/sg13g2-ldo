"""Offline tests for layout/pex_check.py (issues #172, #312). Run:
    python3 -m unittest discover -s layout -p 'test_*.py' -v
"""
import copy
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pex_check  # noqa: E402

_SIM = HERE.parent / "sim" / "ldo-cmos5l-pvt-sweep"
sys.path.insert(0, str(_SIM))
import row4_envelope as r4  # noqa: E402

NAMES = r4.GRADED + r4.UNGRADED
COORDS = r4.coords()


def _write(tmp, name, data=b"x"):
    p = tmp / name
    p.write_bytes(data if isinstance(data, bytes) else data.encode())
    return p


def _sha(path):
    import hashlib
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _bare_sha(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _measured_report(netlist, gds, design):
    """A minimal, valid measured row-4 report pinned to the given files."""
    rows = []
    for c in COORDS:
        cid = r4.corner_id(*c)
        for m in NAMES:
            rows.append({"corner_id": cid, "measurement": m, "spec_row": m,
                         "schematic_value": 1.0, "extracted_value": 1.001,
                         "delta_pct": 0.1, "status": "pass"})
    return {
        "schema_version": 2,
        "status": "pass",
        "layout": {"path": "layout/sg13cmos5l-ldo_core_cmos5l/sg13cmos5l-ldo_core_cmos5l.gds",
                   "scope": "repo"},
        "netlist": {"path": "layout/sg13cmos5l-ldo_core_cmos5l/sg13cmos5l-ldo_core_cmos5l.pex.spice",
                    "scope": "repo"},
        "reference_netlist": {"path": "design/sg13cmos5l/netlist/ldo_core_cmos5l.spice",
                              "scope": "repo"},
        "reference_netlist_sha256": _sha(design),
        "extraction": {"deck": "sg13cmos5l", "netlist_sha256": _bare_sha(netlist)},
        "measurement": {"mode": "testbench"},
        "testbenches": [{"request": {"path": ".klt/pex-row4-request/request.json",
                                     "scope": "repo"},
                         "corner_count": len(COORDS),
                         "measurement_names": list(NAMES)}],
        "corner_count": len(COORDS),
        "delta": rows,
        "passed": len(rows), "failed": 0, "errored": 0,
        "pin_count_mismatch": None, "flat_dut_mismatch": None,
        "pin_order_mismatch": None, "backend_failure": None, "unfinished": [],
        "body_bias": {"status": "biased"},
        "provenance": {"klt_version": "0.9.3.dev4946+ge71a053f4521",
                       "input": {"content_hash": _sha(gds), "role": "layout"}},
    }


class ExtractOnlyTests(unittest.TestCase):
    def test_check_passes_and_perturb_breaks_it(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            net = _write(tmp, "dut.spice", ".subckt D A B\nR1 A B 2.0\n.ends D\n")
            rep = tmp / "report.json"
            rep.write_text(json.dumps(
                {"measurement": {"mode": "extract-only"},
                 "extraction": {"netlist_sha256": _bare_sha(net),
                                "device_count": 1, "net_count": 2},
                 "body_bias": {"status": "biased"},
                 "provenance": {"klt_version": "0.9.2"}}))
            self.assertEqual(pex_check.check(rep, net), 0)
            perturbed = tmp / "perturbed.spice"
            self.assertEqual(pex_check.perturb(net, perturbed), 0)
            self.assertNotEqual(net.read_bytes(), perturbed.read_bytes())
            self.assertEqual(pex_check.check(rep, perturbed), 1)

    def test_check_rejects_wrong_mode(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            net = _write(tmp, "dut.spice", ".subckt D A B\nR1 A B 2.0\n.ends D\n")
            rep = tmp / "report.json"
            rep.write_text(json.dumps(
                {"measurement": {"mode": "testbench"},
                 "extraction": {"netlist_sha256": _bare_sha(net),
                                "device_count": 1, "net_count": 2},
                 "body_bias": {"status": "biased"},
                 "provenance": {"klt_version": "0.9.2"}}))
            self.assertEqual(pex_check.check(rep, net), 1)


class Row4Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.net = _write(self.tmp, "dut.spice", "R1 A B 2.0\n")
        self.gds = _write(self.tmp, "lay.gds", b"\x00gds")
        self.des = _write(self.tmp, "design.spice", ".subckt ldo_core_cmos5l\n.ends\n")
        self.rep = self.tmp / "row4.json"
        self.doc = _measured_report(self.net, self.gds, self.des)
        self.write()

    def tearDown(self):
        self._tmp.cleanup()

    def write(self):
        self.rep.write_text(json.dumps(self.doc))

    def run_check(self):
        return pex_check.check_row4(self.rep, self.net, self.gds, self.des)

    def test_valid_report_passes(self):
        self.assertEqual(self.run_check(), 0)

    def _assert_one_drift(self, mutate):
        doc = copy.deepcopy(self.doc)
        mutate(doc)
        self.rep.write_text(json.dumps(doc))
        self.assertEqual(self.run_check(), 1)

    def test_rejects_extract_only_mode(self):
        self._assert_one_drift(lambda d: d.__setitem__("measurement", {"mode": "extract-only"}))

    def test_rejects_not_checked_status(self):
        self._assert_one_drift(lambda d: d.__setitem__("status", "not_checked"))

    def test_rejects_failed_binding(self):
        self._assert_one_drift(
            lambda d: d.__setitem__("pin_count_mismatch", {"subcircuit": "x"}))

    def test_rejects_unfinished_leg(self):
        self._assert_one_drift(lambda d: d.__setitem__("unfinished", [{"side": "extracted"}]))

    def test_rejects_unbiased_body(self):
        self._assert_one_drift(
            lambda d: d.__setitem__("body_bias", {"status": "unbiased"}))

    def test_rejects_drifted_netlist(self):
        self.net.write_text("R1 A B 3.0\n")
        self.assertEqual(self.run_check(), 1)

    def test_rejects_drifted_gds(self):
        self.gds.write_bytes(b"\x00gds!")
        self.assertEqual(self.run_check(), 1)

    def test_rejects_drifted_design_netlist(self):
        self.des.write_text(".subckt other\n.ends\n")
        self.assertEqual(self.run_check(), 1)

    def test_rejects_missing_corner(self):
        def drop(d):
            kept = [r for r in d["delta"]
                    if r["corner_id"] != r4.corner_id(*COORDS[0])]
            d.__setitem__("delta", kept)
        self._assert_one_drift(drop)

    def test_rejects_duplicate_coordinate(self):
        def dup(d):
            d["delta"].append(copy.deepcopy(d["delta"][0]))
        self._assert_one_drift(dup)

    def test_rejects_unexpected_measurement(self):
        def extra(d):
            row = copy.deepcopy(d["delta"][0])
            row["measurement"] = row["spec_row"] = "iq_uavg_ma"
            d["delta"].append(row)
        self._assert_one_drift(extra)

    def test_rejects_non_numeric_extracted_value(self):
        def nullify(d):
            d["delta"][0]["extracted_value"] = None
        self._assert_one_drift(nullify)

    def test_rejects_error_status_row(self):
        def err(d):
            d["delta"][0]["status"] = "error"
        self._assert_one_drift(err)

    def test_rejects_wrong_measurement_names(self):
        self._assert_one_drift(
            lambda d: d["testbenches"][0].__setitem__("measurement_names", ["gain_db"]))

    def test_limit_miss_grades_fail_but_check_passes(self):
        doc = copy.deepcopy(self.doc)
        doc["status"] = "fail"
        doc["failed"] = 1
        doc["passed"] = len(doc["delta"]) - 1
        doc["delta"][0]["status"] = "fail"
        self.rep.write_text(json.dumps(doc))
        self.assertEqual(self.run_check(), 0)


if __name__ == "__main__":
    unittest.main()
