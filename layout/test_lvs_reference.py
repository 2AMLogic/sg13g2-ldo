"""Offline tests for layout/lvs_reference.py (issue #114).

Stdlib-only: ``common_sg13cmos5l`` imports ``klayout.db`` at module level, but
``lvs_reference`` only reads plain constants from it, so a stub ``klayout``
package is injected when the real one is not installed. Run:
    python3 -m unittest discover -s layout -p 'test_*.py' -v
"""
import importlib
import pathlib
import sys
import tempfile
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import klayout.db  # noqa: F401
except ImportError:  # CI job has no klayout
    _pkg = types.ModuleType("klayout")
    _db = types.ModuleType("klayout.db")
    _pkg.db = _db
    sys.modules["klayout"] = _pkg
    sys.modules["klayout.db"] = _db

lr = importlib.import_module("lvs_reference")

FIXTURE = """\
* fixture
.subckt top A B VSS
XM1 A B VSS VSS sg13_hv_nmos w=5u l=1u ng=1 m=3
XM2 A B VSS VSS sg13_hv_pmos w=2800u l=0.5u ng=1 m=1
XR1 A B VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7
Xsub B A VSS sub
.ends

.subckt sub P Q GND
XMi Q P GND GND sg13_hv_nmos w=20u l=1u ng=1 m=1
XC1 P Q cap_cmomi w=170e-6 l=30e-6 mmin=1
.ends
"""


def write(text: str) -> pathlib.Path:
    d = tempfile.mkdtemp(prefix="lvsref-test-")
    p = pathlib.Path(d) / "n.spice"
    p.write_text(text)
    return p


class RhighTests(unittest.TestCase):
    def test_hand_computed_values(self):
        # 8 stripes: 8*25.43 + 7*0.18 = 204.70 um; /1 um * 1360 ohm/sq
        deck, pdk = lr.rhigh_reference_ohms(1.0, 25.43, 7)
        self.assertAlmostEqual(deck, 204.70 * 1360.0, places=3)
        # matches the committed reference comments (one decimal)
        self.assertEqual(f"{deck:.1f}", "278392.0")
        self.assertEqual(f"{pdk:.1f}", "300443.6")

    def test_bend_count_matters(self):
        d0, p0 = lr.rhigh_reference_ohms(1.0, 25.43, 0)
        d7, p7 = lr.rhigh_reference_ohms(1.0, 25.43, 7)
        self.assertAlmostEqual(d0, 25.43 * 1360.0, places=3)
        self.assertGreater(d7, 8 * d0)  # bends add ps length
        self.assertNotAlmostEqual(d7, 8 * 25.43 * 1360.0, places=1)
        self.assertGreater(p7, p0)

    def test_pdk_exceeds_deck(self):
        deck, pdk = lr.rhigh_reference_ohms(1.0, 28.81, 39)
        self.assertGreater(pdk, deck)


class UmTests(unittest.TestCase):
    def test_literals(self):
        self.assertEqual(lr._um("2800u"), 2800.0)
        self.assertAlmostEqual(lr._um("28.81e-6"), 28.81)


class ParseTests(unittest.TestCase):
    def test_parse(self):
        s = lr.parse_subckts(write(FIXTURE))
        self.assertEqual(set(s), {"top", "sub"})
        self.assertEqual(s["top"]["ports"], ["A", "B", "VSS"])
        inst, nodes, model, params = s["top"]["instances"][0]
        self.assertEqual((inst, nodes, model), ("XM1", ["A", "B", "VSS", "VSS"], "sg13_hv_nmos"))
        self.assertEqual(params["m"], "3")
        self.assertEqual(params["w"], "5u")

    def test_no_subckt_rejected(self):
        with self.assertRaises(SystemExit):
            lr.parse_subckts(write("* nothing here\n"))


class FlattenTests(unittest.TestCase):
    def setUp(self):
        self.s = lr.parse_subckts(write(FIXTURE))

    def test_ports_mapped_and_params_preserved(self):
        flat = lr.flatten(self.s, "top")
        by = {f[0]: f for f in flat}
        self.assertEqual(set(by), {"XM1", "XM2", "XR1", "XMi", "XC1"})
        # sub ports P,Q,GND bound to caller nets B,A,VSS
        self.assertEqual(by["XMi"][1], ["A", "B", "VSS", "VSS"])
        self.assertEqual(by["XC1"][1], ["B", "A"])
        self.assertEqual(by["XMi"][3]["w"], "20u")
        self.assertEqual(by["XC1"][3]["w"], "170e-6")

    def test_internal_nets_keep_names(self):
        self.s["sub"]["instances"][0] = ("XMi", ["Q", "P", "GND", "INT"], "sg13_hv_nmos", {})
        flat = {f[0]: f for f in lr.flatten(self.s, "top")}
        self.assertEqual(flat["XMi"][1][3], "INT")

    def test_unknown_model_rejected(self):
        self.s["top"]["instances"].append(("Xz", ["A"], "mystery", {}))
        with self.assertRaises(SystemExit):
            lr.flatten(self.s, "top")

    def test_nested_hierarchy_rejected(self):
        self.s["deep"] = {"ports": ["X"], "instances": [("Xd", ["X"], "sub", {})]}
        self.s["top"]["instances"].append(("Xdeep", ["A"], "deep", {}))
        with self.assertRaises(SystemExit):
            lr.flatten(self.s, "top")

    def test_port_count_mismatch_rejected(self):
        self.s["top"]["instances"][-1] = ("Xsub", ["B", "A"], "sub", {})
        with self.assertRaises(ValueError):
            lr.flatten(self.s, "top")


class RenderTests(unittest.TestCase):
    def render(self, text=FIXTURE):
        p = write(text)
        # render() prints a repo-relative source path; stage the fixture there
        orig = lr.REPO_ROOT
        lr.REPO_ROOT = p.parent
        try:
            return lr.render(p, "cell", "top")
        finally:
            lr.REPO_ROOT = orig

    def test_render_cards(self):
        out = self.render()
        lines = out.splitlines()
        self.assertIn(".SUBCKT cell A B VSS", lines)
        self.assertIn(".ENDS cell", lines)
        # m folded into W: 3 x 5u = 15u; X prefix replaced by M
        self.assertIn("MM1 A B VSS VSS nfet L=1U W=15U", lines)
        self.assertIn("MM2 A B VSS VSS pfet L=0.5U W=2800U", lines)
        self.assertIn("RR1 A B VSS 278392.0 rhigh", lines)
        self.assertIn("XC1 B A cap_cmomi PARAMS: W=170 L=30", lines)
        self.assertTrue(any("folded" in ln and "m=3" in ln for ln in lines))

    def test_negative_control_mutation_changes_output(self):
        base = self.render()
        self.assertNotEqual(base, self.render(FIXTURE.replace("m=3", "m=2")))
        self.assertNotEqual(base, self.render(FIXTURE.replace("b=7", "b=6")))
        self.assertNotEqual(base, self.render(FIXTURE.replace("w=2800u", "w=2801u")))

    def test_dropped_device_model_rejected(self):
        with self.assertRaises(SystemExit):
            self.render(FIXTURE.replace("sg13_hv_pmos", "sg13_lv_pmos"))


if __name__ == "__main__":
    unittest.main()
