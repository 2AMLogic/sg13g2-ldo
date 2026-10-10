"""Offline tests for layout/erc_ties.py (issue #114). Run:
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

import erc_ties  # noqa: E402

DOC = {
    "taps": [
        {"kind": "nwell", "net": "VIN", "tap_boxes": [[0.0, 0.0, 1.0, 2.0]]},
        {"kind": "nwell", "net": "TAIL", "tap_boxes": [[5.0, 0.0, 6.0, 2.0]]},
        {"kind": "substrate", "net": "VSS", "tap_boxes": [[9.0, 0.0, 10.0, 2.0]],
         "well_boxes": [[8.0, -1.0, 11.0, 3.0]]},
    ]
}


class TiesTests(unittest.TestCase):
    def test_derivation(self):
        ties = erc_ties.ties_from_taps(DOC)
        self.assertEqual([t["name"] for t in ties],
                         ["nwell_tie_VIN", "nwell_tie_TAIL", "substrate_tie_VSS"])
        nw, _, sub = ties[0], ties[1], ties[2]
        self.assertEqual(nw["well_layer"], "31/0")
        self.assertEqual(nw["well_requires_boxes"], nw["tap_boxes"])
        self.assertEqual(nw["tap_requires"], ["7/0"])
        self.assertEqual(sub["well_layer"], None)
        self.assertEqual(sub["well_boxes"], [[8.0, -1.0, 11.0, 3.0]])
        self.assertEqual(sub["tap_requires"], ["14/0"])
        self.assertNotIn("well_boxes", nw)
        self.assertEqual(sub["net"], "VSS")

    def test_empty(self):
        self.assertEqual(erc_ties.ties_from_taps({"taps": []}), [])

    def test_missing_kind_rejected(self):
        with self.assertRaises(KeyError):
            erc_ties.ties_from_taps({"taps": [{"net": "X", "tap_boxes": []}]})

    def test_substrate_without_well_boxes_rejected(self):
        bad = {"taps": [{"kind": "substrate", "net": "VSS", "tap_boxes": []}]}
        with self.assertRaises(KeyError):
            erc_ties.ties_from_taps(bad)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp(prefix="erc-ties-test-"))
        self.doc = self.d / "taps.json"
        self.doc.write_text(json.dumps(DOC))
        self.spec = self.d / "spec.json"
        self.spec.write_text(json.dumps({"ties": erc_ties.ties_from_taps(DOC)}))

    def run_main(self, *args):
        return erc_ties.main(["erc_ties.py", *args])

    def test_check_passes_on_matching_spec(self):
        self.assertEqual(self.run_main("--check", str(self.doc), str(self.spec)), 0)

    def test_negative_control_moved_tap_fails_check(self):
        moved = copy.deepcopy(DOC)
        moved["taps"][1]["tap_boxes"] = [[5.5, 0.0, 6.5, 2.0]]
        self.doc.write_text(json.dumps(moved))
        self.assertEqual(self.run_main("--check", str(self.doc), str(self.spec)), 1)

    def test_negative_control_mutate_output_is_rejected(self):
        out = self.d / "mut.json"
        self.assertEqual(self.run_main("--mutate", str(self.doc), str(self.spec), str(out)), 0)
        self.assertNotEqual(json.loads(out.read_text())["ties"],
                            erc_ties.ties_from_taps(DOC))
        self.assertEqual(self.run_main("--check", str(self.doc), str(out)), 1)

    def test_unknown_mode(self):
        self.assertEqual(self.run_main("--bogus", str(self.doc), str(self.spec)), 2)


if __name__ == "__main__":
    unittest.main()
