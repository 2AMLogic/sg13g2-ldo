#!/usr/bin/env python3
"""Negative controls for the E1 reducer (issue #158). stdlib only.

Every way the E1 reduction could silently lie is exercised here against
synthetic fixtures: a missing export, a truncated/ragged export, a nonfinite
value, a drifted sweep axis, sign-convention mistakes (a negative ids, an
off-device drawing real current, a reversed rail), a broken KCL, an
out-of-regulation VOUT, a wrong column contract (template wrdata tokens vs
the reducer's QUANTITIES), and record-md determinism. The happy path is
exercised against a synthetic-but-physically-consistent fixture.
"""
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import e1_oppoints as e  # noqa: E402


def _op_fixture(seed_vout=1.80031344, load_a=0.001, idiv=4.8162e-6):
    """A physically consistent operating point (values from a real tt/27C
    probe of the same deck; the identity is what matters here)."""
    op = {t: 0.0 for t in e.QUANTITIES}
    op["v(vout)"] = seed_vout
    op["v(eaout)"] = 2.6181
    op["v(fb)"] = seed_vout / 2
    op["v(fbamp)"] = seed_vout / 2
    op["v(vref)"] = 0.9
    op["v(en)"] = 3.3
    op["v(ibias)"] = 1.4701
    op["v(xamp.g1)"] = 0.6586
    op["v(xamp.mz)"] = 0.6585
    op["v(xamp.n1)"] = 0.7001
    op["v(xamp.tail)"] = 1.7303
    op["v(xamp.enb)"] = 0.0
    op["v(reptop)"] = seed_vout
    op["i(vdivsense)"] = idiv
    op["i(vin)"] = -(load_a + 2.48e-5)
    op["i(vbreak)"] = 0.0
    ids_pass = load_a + idiv
    op["@n.xmpass.nsg13_hv_pmos[ids]"] = ids_pass
    op["@n.xmpass.nsg13_hv_pmos[gm]"] = 1.12e-2
    op["@n.xmpass.nsg13_hv_pmos[gds]"] = 4.2e-5
    op["@n.xmpass.nsg13_hv_pmos[cgs]"] = -8.0e-11
    op["@n.xmpass.nsg13_hv_pmos[cgd]"] = -6.0e-12
    op["@n.xmpass.nsg13_hv_pmos[cdd]"] = -1.26e-15
    op["@n.xmpass.nsg13_hv_pmos[vth]"] = -0.72
    for d in ("xmen", "xmbdis"):
        op[f"@n.{d}.nsg13_hv_pmos[ids]"] = 3.2e-10
        op[f"@n.{d}.nsg13_hv_pmos[gm]"] = 1e-9
        op[f"@n.{d}.nsg13_hv_pmos[gds]"] = 1e-9
    for d in ("xamp.xmb0", "xamp.xmtail", "xamp.xmload2",
              "xamp.xminp", "xamp.xminn", "xamp.xminvp"):
        op[f"@n.{d}.nsg13_hv_pmos[gm]"] = 3.4e-5
        op[f"@n.{d}.nsg13_hv_pmos[gds]"] = 2.5e-6
    op["@n.xamp.xmb0.nsg13_hv_pmos[ids]"] = 2.0e-6
    op["@n.xamp.xmtail.nsg13_hv_pmos[ids]"] = 6.03e-6
    op["@n.xamp.xmload2.nsg13_hv_pmos[ids]"] = 1.2e-5
    op["@n.xamp.xminp.nsg13_hv_pmos[ids]"] = 3.01e-6
    op["@n.xamp.xminn.nsg13_hv_pmos[ids]"] = 3.02e-6
    op["@n.xamp.xminvp.nsg13_hv_pmos[ids]"] = 4.9e-12
    for d in ("xamp.xmn1", "xamp.xmn2", "xamp.xmn3", "xamp.xminvn", "xamp.xmpd"):
        op[f"@n.{d}.nsg13_hv_nmos[gm]"] = 1.4e-4
        op[f"@n.{d}.nsg13_hv_nmos[gds]"] = 1.0e-6
    op["@n.xamp.xmn1.nsg13_hv_nmos[ids]"] = 3.02e-6
    op["@n.xamp.xmn2.nsg13_hv_nmos[ids]"] = 3.01e-6
    op["@n.xamp.xmn3.nsg13_hv_nmos[ids]"] = 1.2e-5
    op["@n.xamp.xminvn.nsg13_hv_nmos[ids]"] = 1.1e-11
    op["@n.xamp.xmpd.nsg13_hv_nmos[ids]"] = 2.6e-12
    op["@n.xamp.xmn3.nsg13_hv_nmos[cgs]"] = -2.0e-14
    op["@n.xamp.xmn3.nsg13_hv_nmos[cgd]"] = -5.0e-15
    return op


def _write_export(path, op, sweep=(3.299, 3.3, 3.301), drop=(), nan_at=None,
                  nvals=None):
    """Write one wrdata-shaped export: (x, value) pairs per token."""
    with open(path, "w") as fh:
        for x in sweep:
            cells = []
            for k, tok in enumerate(e.QUANTITIES):
                v = op.get(tok, 0.0)
                if tok in drop:
                    cells += [f"{x:.8e}"]
                elif nan_at == tok:
                    cells += [f"{x:.8e}", f"{float('nan'):.8e}"]
                else:
                    cells += [f"{x:.8e}", f"{v:.8e}"]
            if nvals is not None:
                cells = cells[:nvals]
            fh.write(" ".join(cells) + "\n")


class TokensContract(unittest.TestCase):
    def test_template_wrdata_matches_reducer_contract(self):
        """The template's wrdata line IS the reducer's QUANTITIES (deck and
        reducer cannot drift)."""
        tmpl = os.path.join(HERE, "testbench", "tb_e1op_cmos5l.spice.tmpl")
        line = None
        for ln in open(tmpl):
            if ln.startswith("wrdata "):
                line = ln
        self.assertIsNotNone(line, "template has no wrdata line")
        toks = line.split()[2:]
        self.assertEqual(toks, e.QUANTITIES)

    def test_save_card_covers_every_wrdata_token(self):
        """Every wrdata token must be in the .save card: the fleet's klt 0.5.0
        runner emits no `save all`, so an unsaved token (a node voltage, a
        source current) does not exist in the rawfile -- the runner's liveness
        .meas and the CSV rebuild would both fail."""
        tmpl = os.path.join(HERE, "testbench", "tb_e1op_cmos5l.spice.tmpl")
        save_set = wrdata = None
        for ln in open(tmpl):
            if ln.startswith(".save "):
                save_set = set(ln.split()[1:])
            elif ln.startswith("wrdata "):
                wrdata = set(ln.split()[2:])
        self.assertIsNotNone(save_set, "template has no .save card")
        self.assertIsNotNone(wrdata, "template has no wrdata line")
        self.assertEqual(wrdata - save_set, set(),
                         "wrdata tokens not in the .save card")

    def test_no_poisonous_save_names(self):
        """The bare [id] and [vbs] spellings create zero-length vectors and
        break ngspice's rawfile write -- they must never appear in the
        .save card or the wrdata line (header prose that documents the
        hazard is fine)."""
        tmpl = os.path.join(HERE, "testbench", "tb_e1op_cmos5l.spice.tmpl")
        cards = [ln for ln in open(tmpl)
                 if ln.startswith(".save ") or ln.startswith("wrdata ")]
        self.assertEqual(len(cards), 2, "expected exactly one .save and one wrdata line")
        for ln in cards:
            for t in ln.split()[1:]:
                self.assertFalse(t.endswith("[id]") or t.endswith("[vbs]"),
                                 f"poisonous save name in a card: {t}")


class CheckExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.op = _op_fixture()

    def tearDown(self):
        self.tmp.cleanup()

    def test_happy_path(self):
        p = os.path.join(self.tmp.name, "ok_dc.csv")
        _write_export(p, self.op)
        self.assertEqual(e.check_export(p), 2 * len(e.QUANTITIES))

    def test_missing_row_rejected(self):
        p = os.path.join(self.tmp.name, "short_dc.csv")
        _write_export(p, self.op, sweep=(3.299, 3.3))
        with self.assertRaises(ValueError):
            e.check_export(p)

    def test_ragged_row_rejected(self):
        p = os.path.join(self.tmp.name, "ragged_dc.csv")
        _write_export(p, self.op, nvals=10)
        with self.assertRaises(ValueError):
            e.check_export(p)

    def test_nonfinite_rejected(self):
        p = os.path.join(self.tmp.name, "nan_dc.csv")
        _write_export(p, self.op, nan_at="v(vout)")
        with self.assertRaises(ValueError):
            e.check_export(p)

    def test_drifted_axis_rejected(self):
        p = os.path.join(self.tmp.name, "axis_dc.csv")
        _write_export(p, self.op, sweep=(3.0, 3.3, 3.6))
        with self.assertRaises(ValueError):
            e.check_export(p)


class ReduceChecks(unittest.TestCase):
    """reduce_point's circuit-level checks must catch every silent lie."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _reduce(self, **kw):
        p6 = [p for p in e.POINTS if p[0] == "P6"][0]
        op = kw.pop("op", _op_fixture())
        p = os.path.join(self.tmp.name, "p6_dc.csv")
        _write_export(p, op, **kw)
        row, failed = e.reduce_point(p6, p, op["v(vout)"], e.CC_F_NOMINAL)
        return row, failed

    def test_happy_path_all_checks_pass(self):
        row, failed = self._reduce()
        self.assertEqual(failed, [])
        self.assertEqual(row["check:all_ok"], "True")
        # derived quantities consistent with the fixture's identity
        ro = float(row["derived:ro_pass_ohm"])
        self.assertAlmostEqual(ro, 1.0 / 4.2e-5, delta=1.0)
        r_leg = float(row["derived:r_leg_ohm"])
        self.assertAlmostEqual(r_leg, (1.80031344 / 2) / 4.8162e-6, delta=1.0)
        va = float(row["derived:va_equiv_pass_V"])
        self.assertAlmostEqual(va, (0.001 + 4.8162e-6) / 4.2e-5, delta=0.01)

    def test_negative_ids_is_a_sign_mistake(self):
        op = _op_fixture()
        op["@n.xmpass.nsg13_hv_pmos[ids]"] = -1.0048e-3  # an invented PMOS sign
        row, failed = self._reduce(op=op)
        self.assertIn("signs", failed)
        self.assertIn("@n.xmpass.nsg13_hv_pmos[ids]", row["note"])

    def test_conducting_device_reported_off_is_caught(self):
        op = _op_fixture()
        op["@n.xamp.xmtail.nsg13_hv_pmos[ids]"] = 0.0  # tail "off": impossible
        row, failed = self._reduce(op=op)
        self.assertIn("signs", failed)

    def test_off_device_drawing_real_current_is_caught(self):
        op = _op_fixture()
        op["@n.xmen.nsg13_hv_pmos[ids]"] = 5.0e-6  # Men conducting: EN wiring broke
        row, failed = self._reduce(op=op)
        self.assertIn("signs", failed)

    def test_reversed_rail_is_caught(self):
        op = _op_fixture()
        op["i(vin)"] = +2.5e-5  # rail "absorbing": source-branch sign flipped
        row, failed = self._reduce(op=op)
        self.assertIn("signs", failed)

    def test_broken_kcl_is_caught(self):
        op = _op_fixture()
        op["@n.xmpass.nsg13_hv_pmos[ids]"] = 0.9e-3  # 100 uA of current vanishes
        row, failed = self._reduce(op=op)
        self.assertIn("kcl", failed)
        self.assertIn("KCL at VOUT", row["note"])

    def test_break_current_is_caught(self):
        op = _op_fixture()
        op["i(vbreak)"] = 1e-9  # the FB/FBAMP break is drawing current
        row, failed = self._reduce(op=op)
        self.assertIn("vbreak", failed)

    def test_out_of_regulation_is_caught(self):
        row, failed = self._reduce(op=_op_fixture(seed_vout=1.2))
        self.assertIn("regulation", failed)

    def test_liveness_mismatch_is_caught(self):
        p6 = [p for p in e.POINTS if p[0] == "P6"][0]
        op = _op_fixture()
        p = os.path.join(self.tmp.name, "p6_dc.csv")
        _write_export(p, op)
        row, failed = e.reduce_point(p6, p, 1.5, e.CC_F_NOMINAL)
        self.assertIn("liveness", failed)

    def test_pole_estimates_are_finite_and_labelled_estimates(self):
        row, failed = self._reduce()
        self.assertEqual(failed, [])
        for col in ("derived:est_f_pole_vout_hz", "derived:est_f_pole_eaout_hz",
                    "derived:est_f_pole_g1_hz"):
            v = float(row[col])
            self.assertTrue(math.isfinite(v) and v > 0, col)
        # and the CSV header names them estimates
        self.assertIn("derived:est_f_pole_vout_hz", e.CSV_FIELDS)


class ReduceCli(unittest.TestCase):
    def test_missing_export_refuses_to_reduce(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = e.cmd_reduce(argparse_namespace(
                record="NO_SUCH_RECORD", corners_dir=os.path.join(tmp, "x"),
                out_csv=os.path.join(tmp, "o.csv"),
                out_json=os.path.join(tmp, "o.json"), cc_f=e.CC_F_NOMINAL))
            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(os.path.join(tmp, "o.csv")))

    def test_nonfinite_export_refuses_to_reduce(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir = os.path.join(tmp, "corners")
            os.makedirs(cdir)
            for pt in e.POINTS:
                op = _op_fixture()
                _write_export(os.path.join(cdir, e.point_id(pt) + "_dc.csv"),
                              op, nan_at="v(vout)")
            rc = e.cmd_reduce(argparse_namespace(
                record="X", corners_dir=cdir, out_csv=os.path.join(tmp, "o.csv"),
                out_json=os.path.join(tmp, "o.json"), cc_f=e.CC_F_NOMINAL))
            self.assertEqual(rc, 2)


def argparse_namespace(**kw):
    import argparse
    return argparse.Namespace(**kw)


if __name__ == "__main__":
    unittest.main()
