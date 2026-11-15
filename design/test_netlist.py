"""Offline tests for the helpers in design/netlist.py (issues #114, #176).

No xschem, PDK or klt needed: ``check_invariants`` is driven on a small
temporary design directory of ``.sch``/``.sym`` fixtures and netlist
strings, and ``run_klt_netlist`` is driven with a faked ``subprocess.run``
so the export command's parity gates (``--erc``, ``--no-provenance-header``,
the design-authoritative ``--pdk``) are pinned without a real toolchain.
The live parity evidence itself (byte-identical netlists, ERC negative
controls) is recorded in issue #176, not here. Run:
    python3 -m unittest discover -s design -p 'test_*.py' -v
"""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_pending_integration_exempts_only_the_named_cell(self):
        import dataclasses
        d = dataclasses.replace(self.make(), pending_integration={"sub": "#190"})
        self.assertEqual(nl.check_invariants(d, self.netlists(top=top_netlist(instantiate=False))), [])

    def test_pending_integration_still_checks_pins(self):
        import dataclasses
        d = dataclasses.replace(self.make(sub_schs=["B", "A"]), pending_integration={"sub": "#190"})
        fails = nl.check_invariants(d, self.netlists(top=top_netlist(instantiate=False)))
        self.assertTrue(any("symbol pins and schematic ports disagree" in f for f in fails))

    def test_pending_integration_stale_entry_fails(self):
        import dataclasses
        d = dataclasses.replace(self.make(), pending_integration={"sub": "#190"})
        fails = nl.check_invariants(d, self.netlists())
        self.assertEqual(len(fails), 1)
        self.assertIn("remove the entry", fails[0])

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


class KltExporterTests(unittest.TestCase):
    """run_klt_netlist's command contract, with subprocess.run faked."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="netlist-klt-test-"))
        # failure messages and the header build repo-relative paths; root
        # them at the fixture (same pattern as InvariantTests.make)
        saved = nl.REPO_ROOT
        nl.REPO_ROOT = self.dir
        self.addCleanup(setattr, nl, "REPO_ROOT", saved)
        self.sch = self.dir / "cell.sch"
        self.sch.write_text("v {}\n")
        self.outdir = self.dir / "out"
        self.outdir.mkdir()
        self.pdk = nl.Pdk(root=pathlib.Path("/pdk-root"), variant="ihp-sg13g2",
                          source="test")

    def fake_run(self, rc=0, stdout="", stderr=""):
        return mock.Mock(returncode=rc, stdout=stdout, stderr=stderr)

    def test_command_carries_the_parity_gates(self):
        with mock.patch.object(nl.subprocess, "run",
                               return_value=self.fake_run()) as run:
            (self.outdir / "cell.spice").write_text(".subckt cell A B\n.ends\n")
            nl.run_klt_netlist(self.sch, self.outdir, self.pdk)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[0:3], ["klt", "netlist", str(self.sch)])
        for flag in ("--erc", "--no-provenance-header", "--rcfile",
                     "--pdk", "--pdk-root"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--pdk") + 1], "ihp-sg13g2")
        self.assertEqual(cmd[cmd.index("--pdk-root") + 1], "/pdk-root")

    def test_nonzero_exit_is_export_error(self):
        with mock.patch.object(nl.subprocess, "run",
                               return_value=self.fake_run(rc=1)):
            with self.assertRaises(nl.ExportError) as ctx:
                nl.run_klt_netlist(self.sch, self.outdir, self.pdk)
        self.assertIn("exit 1", str(ctx.exception))

    def test_erc_backstop_regex_triggers_on_scraped_diagnostics(self):
        # klt exits non-zero on --erc findings today; this pins the local
        # backstop -- a diagnostic the regex knows must fail the export even
        # if some klt/xschem vintage exits 0 while printing it (#176).
        with mock.patch.object(nl.subprocess, "run",
                               return_value=self.fake_run(stdout="undriven node: OUT\n")):
            with self.assertRaises(nl.ExportError):
                nl.run_klt_netlist(self.sch, self.outdir, self.pdk)

    def test_success_returns_header_plus_normalized_body(self):
        body = (f"** sch_path: {nl.REPO_ROOT}/design/cell.sch   \n"
                ".subckt cell A B\n.ends\n")
        with mock.patch.object(nl.subprocess, "run",
                               return_value=self.fake_run()):
            (self.outdir / "cell.spice").write_text(body)
            text = nl.run_klt_netlist(self.sch, self.outdir, self.pdk)
        self.assertTrue(text.startswith(
            "* cell -- generated by design/netlist.py from"))
        self.assertNotIn(str(nl.REPO_ROOT), text)
        self.assertIn(".subckt cell A B\n", text)

    def test_missing_schematic(self):
        with self.assertRaises(nl.ExportError):
            nl.run_klt_netlist(self.dir / "nope.sch", self.outdir, self.pdk)


if __name__ == "__main__":
    unittest.main()
