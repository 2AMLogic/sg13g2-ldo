"""Offline tests for the pure helpers in design/netlist.py (issue #114).

No xschem or PDK: ``check_invariants`` is driven on a small temporary design
directory of ``.sch``/``.sym`` fixtures and netlist strings. Run:
    python3 -m unittest discover -s design -p 'test_*.py' -v
"""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import netlist as nl  # noqa: E402


def sym(pins):
    body = "".join(f"B 5 0 0 1 1 {{name={p} dir=inout}}\n" for p in pins)
    return "v {xschem version=3.4.7 file_version=1.3\n}\n" + body


def sch(pins):
    return "".join(f"C {{iopin.sym}} 0 {i} 0 0 {{name=p{i} lab={p}}}\n"
                   for i, p in enumerate(pins))


TOP_PORTS = ["VIN", "VOUT", "VSS"]
SUB_PORTS = ["A", "B"]


def top_netlist(sub_nets="VIN VOUT", top_ports=TOP_PORTS, instantiate=True):
    inst = f"Xamp {sub_nets} sub\n" if instantiate else ""
    return (f".subckt top {' '.join(top_ports)}\n"
            f"XR1 VIN VOUT VSS rhigh w=1u\n{inst}.ends\n")


def sub_netlist(ports=SUB_PORTS):
    return f".subckt sub {' '.join(ports)}\nXR2 A B B rhigh w=1u\n.ends\n"


class HelperTests(unittest.TestCase):
    def test_subckt_ports(self):
        text = sub_netlist() + top_netlist()
        self.assertEqual(nl.subckt_ports(text, "sub"), SUB_PORTS)
        self.assertEqual(nl.subckt_ports(text, "top"), TOP_PORTS)

    def test_subckt_ports_missing(self):
        with self.assertRaises(nl.ExportError):
            nl.subckt_ports(sub_netlist(), "nope")

    def test_instance_lines(self):
        text = top_netlist() + "xTwo A B sub\nR1 A B sub\n"
        found = nl.instance_lines(text, "sub")
        self.assertEqual([t[0] for t in found], ["Xamp", "xTwo"])  # R-card and rhigh excluded
        self.assertEqual(found[0][1:-1], ["VIN", "VOUT"])
        self.assertEqual(nl.instance_lines(text, "absent"), [])


class InvariantTests(unittest.TestCase):
    def make(self, top_syms=TOP_PORTS, top_schs=TOP_PORTS, sub_syms=SUB_PORTS,
             sub_schs=SUB_PORTS, sub_sym_present=True):
        d = pathlib.Path(tempfile.mkdtemp(prefix="netlist-test-"))
        # failure messages print repo-relative paths; root them at the fixture
        saved = nl.REPO_ROOT
        nl.REPO_ROOT = d
        self.addCleanup(setattr, nl, "REPO_ROOT", saved)
        (d / "top.sym").write_text(sym(top_syms))
        (d / "top.sch").write_text(sch(top_schs))
        if sub_sym_present:
            (d / "sub.sym").write_text(sym(sub_syms))
        (d / "sub.sch").write_text(sch(sub_schs))
        return nl.Design(name="t", dir=d, top_cell="top",
                         expected_top_ports=list(TOP_PORTS), variant="x")

    def netlists(self, **kw):
        return {"top": kw.get("top", top_netlist()), "sub": kw.get("sub", sub_netlist())}

    def test_clean(self):
        self.assertEqual(nl.check_invariants(self.make(), self.netlists()), [])

    def test_top_port_order_drift(self):
        bad = top_netlist(top_ports=["VOUT", "VIN", "VSS"])
        fails = nl.check_invariants(self.make(top_syms=["VOUT", "VIN", "VSS"],
                                              top_schs=["VOUT", "VIN", "VSS"]),
                                    self.netlists(top=bad))
        self.assertEqual(len(fails), 1)
        self.assertIn("top-level pinout drifted", fails[0])

    def test_top_port_missing(self):
        bad = top_netlist(top_ports=["VIN", "VOUT"])
        fails = nl.check_invariants(self.make(top_syms=["VIN", "VOUT"], top_schs=["VIN", "VOUT"]),
                                    self.netlists(top=bad))
        self.assertTrue(any("top-level pinout drifted" in f for f in fails))

    def test_missing_symbol(self):
        fails = nl.check_invariants(self.make(sub_sym_present=False), self.netlists())
        self.assertTrue(any("sub" in f and "not instantiable" in f for f in fails))

    def test_symbol_vs_schematic_disagree(self):
        fails = nl.check_invariants(self.make(sub_schs=["B", "A"]), self.netlists())
        self.assertTrue(any("symbol pins and schematic ports disagree" in f for f in fails))

    def test_symbol_vs_subckt_order(self):
        fails = nl.check_invariants(self.make(), self.netlists(sub=sub_netlist(["B", "A"])))
        self.assertTrue(any("symbol pin order does not match" in f for f in fails))

    def test_subcell_not_instantiated(self):
        fails = nl.check_invariants(self.make(),
                                    self.netlists(top=top_netlist(instantiate=False)))
        self.assertEqual(fails, ["sub: not instantiated in top"])

    def test_instance_net_count_mismatch(self):
        for nets in ("VIN", "VIN VOUT VSS"):
            fails = nl.check_invariants(self.make(),
                                        self.netlists(top=top_netlist(sub_nets=nets)))
            self.assertEqual(len(fails), 1)
            self.assertIn("has 2 ports", fails[0])

    def test_one_bad_instance_among_several(self):
        top = top_netlist() + "Xbad VIN sub\n"
        fails = nl.check_invariants(self.make(), self.netlists(top=top))
        self.assertEqual(len(fails), 1)
        self.assertIn("Xbad", fails[0])


if __name__ == "__main__":
    unittest.main()
