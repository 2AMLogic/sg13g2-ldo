"""Tests for sim/tools/render_deck.py, the single @@TOKEN@@ renderer (issue #236).

Three layers, matching the acceptance gate of #236:

1.  Semantics: full substitution, the fail-loudly leftover guard, and the
    deliberate behavioural change vs the old `sed -e "s|...|...|g"` chains
    (values containing `|`, `&` or a backslash are substituted verbatim
    where sed mangled them) -- asserted against sed itself, not just stated.
2.  Sed byte-identity: every pre-#236 render site's substitution chain is
    frozen below as ordered (token, value) data; for every real template
    that site rendered, the old mechanism (a sed -e chain built from the
    same data, exactly the command shape the shell scripts used) and the
    new renderer must produce byte-identical output. This is the "decks do
    not move" gate, re-proven on every CI run.
3.  CLI: the shell-callable form used by the converted .sh sites.

Offline and stdlib-only: no simulator, no PDK.
    python3 -m unittest discover -s sim/tools -p 'test_render_deck.py' -v
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_deck as rd  # noqa: E402

PVT = HERE.parent / "ldo-cmos5l-pvt-sweep"
PDS = HERE.parent / "pass-device-screening"

# Representative real values: the resolved paths and section names the
# scripts substitute at run time. Byte-identity does not depend on which
# representative values are used (substitution is per-token replacement),
# but real ones keep the oracle honest about shapes (paths, comments).
PDK_ROOT = "/home/ubuntu/GitHub/sg13cmos5l-stdcells/pdks/ihp-open-pdk"
OSDI = f"{PDK_ROOT}/ihp-sg13cmos5l/libs.tech/ngspice/osdi"
DESIGN = "design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"


def sed_render(template_text, pairs):
    """The pre-#236 mechanism: a sed -e chain over the template, one
    `s|@@KEY@@|value|g` expression per token, in the site's own order."""
    argv = ["sed"]
    for key, value in pairs:
        argv += ["-e", f"s|@@{key}@@|{value}|g"]
    return subprocess.run(argv, input=template_text, text=True,
                          capture_output=True, check=True).stdout


class Semantics(unittest.TestCase):
    def test_full_substitution(self):
        out = rd.render("* @@A@@ @@B@@\nX @@A@@\n", {"A": "1|2", "B": "x&y"})
        self.assertEqual(out, "* 1|2 x&y\nX 1|2\n")

    def test_unsupplied_token_raises_and_names_it(self):
        with self.assertRaises(rd.RenderError) as cm:
            rd.render("@@A@@ @@MISSING@@\n", {"A": "1"})
        self.assertIn("MISSING", str(cm.exception))

    def test_stray_marker_raises_even_non_token_shaped(self):
        with self.assertRaises(rd.RenderError):
            rd.render("no tokens, but a stray @@ here\n", {})

    def test_empty_value_is_allowed(self):
        self.assertEqual(rd.render("@@E@@\n", {"E": ""}), "\n")

    def test_bad_key_rejected(self):
        with self.assertRaises(rd.RenderError):
            rd.render("x", {"BAD-KEY": "1"})

    def test_pipe_ampersand_backslash_verbatim_where_sed_cannot(self):
        """The deliberate behavioural change (#236): the old sed chains
        treat |, & and \ in VALUES as sed syntax -- `|` collides with the
        s||| delimiter and makes the chain die, `&` and \ are silently
        mangled into the match / dropped; str.replace substitutes all of
        them verbatim."""
        tmpl = "@@V@@\n"
        for value in ("x&y", r"back\slash", "one&two\\\\"):
            self.assertEqual(rd.render(tmpl, {"V": value}), value + "\n")
            self.assertNotEqual(sed_render(tmpl, [("V", value)]), value + "\n")
        with self.assertRaises(subprocess.CalledProcessError):
            sed_render(tmpl, [("V", "a|b")])
        self.assertEqual(rd.render(tmpl, {"V": "a|b"}), "a|b\n")

    def test_token_in_value_follows_order_like_sed(self):
        # A value that itself contains a later token substitutes the same
        # way the sequential sed -e chain did.
        tmpl = "@@A@@ @@B@@\n"
        pairs = [("A", "@@B@@"), ("B", "9")]
        self.assertEqual(rd.render(tmpl, dict(pairs)), sed_render(tmpl, pairs))


class SedByteIdentity(unittest.TestCase):
    """Old sed chain vs render_deck.render, per site, on the real templates.

    Each SITES entry freezes a pre-#236 site: its templates and its ordered
    (token, value) substitution list, copied from the sed chain as it stood
    at a5c0a61a (the commit #236 converted). Extra tokens a template does
    not declare are kept: substituting them was (and is) a no-op, and the
    frozen order is the chain's own.
    """

    SITES = {
        # run_sweep.sh --check-env: one deck per bench, both CSV tokens
        # substituted into every template (the AC pair is a no-op for
        # tb_dcsweep and vice versa).
        "run_sweep --check-env": (
            [PVT / "testbench" / f"tb_{b}_cmos5l.spice.tmpl" for b in ("dcsweep", "loopgain", "psrr")],
            [("PDK_ROOT", PDK_ROOT), ("PDK", "ihp-sg13cmos5l"), ("OSDI_DIR", OSDI),
             ("MOS_SECTION", "mos_tt"), ("RES_SECTION", "res_typ"), ("CAP_SECTION", "cap_typ"),
             ("TEMP", "27"), ("LG_AC_MAX", "100meg"), ("CC_W", "nominal (--check-env)"),
             ("LOAD_A", "0.001"), ("COUT_F", "1u"), ("COUT_BOTTOM", "0"),
             ("ESR_LINE", "* ESR=0 (--check-env)"), ("DESIGN_NETLIST", DESIGN),
             ("DC_CSV", "/tmp/check_dcsweep_dc.csv"), ("AC_CSV", "/tmp/check_loopgain_ac.csv")]),
        # run_sweep.sh gen_netlist: per-bench CSV token (extra_sed), a
        # worst-case point (ss/125C/res_bcs) with a real series ESR.
        "run_sweep gen_netlist (dcsweep)": (
            [PVT / "testbench" / "tb_dcsweep_cmos5l.spice.tmpl"],
            [("PDK_ROOT", PDK_ROOT), ("PDK", "ihp-sg13cmos5l"), ("OSDI_DIR", OSDI),
             ("MOS_SECTION", "mos_ss"), ("RES_SECTION", "res_bcs"), ("CAP_SECTION", "cap_typ"),
             ("TEMP", "125"), ("LG_AC_MAX", "100meg"), ("CC_W", "170u (nominal)"),
             ("DESIGN_NETLIST", DESIGN), ("LOAD_A", "0.05"), ("COUT_F", "4.7u"),
             ("COUT_BOTTOM", "COUT_ESR"), ("ESR_LINE", "Resr COUT_ESR 0 500e-3"),
             ("DC_CSV", "corners/ID/dcsweep_ss_125c_rbcs_dc.csv")]),
        "run_sweep gen_netlist (loopgain|psrr)": (
            [PVT / "testbench" / f"tb_{b}_cmos5l.spice.tmpl" for b in ("loopgain", "psrr")],
            [("PDK_ROOT", PDK_ROOT), ("PDK", "ihp-sg13cmos5l"), ("OSDI_DIR", OSDI),
             ("MOS_SECTION", "mos_ss"), ("RES_SECTION", "res_bcs"), ("CAP_SECTION", "cap_typ"),
             ("TEMP", "125"), ("LG_AC_MAX", "100meg"), ("CC_W", "170u (nominal)"),
             ("DESIGN_NETLIST", DESIGN), ("LOAD_A", "0.05"), ("COUT_F", "4.7u"),
             ("COUT_BOTTOM", "COUT_ESR"), ("ESR_LINE", "Resr COUT_ESR 0 500e-3"),
             ("AC_CSV", "corners/ID/loopgain_ss_125c_rbcs_ac.csv")]),
        # run_loopgain2.sh render_deck: the three campaign benches at the
        # campaign's own ceiling and ESR comment.
        "run_loopgain2.sh render_deck": (
            [PVT / "testbench" / f"tb_{b}_cmos5l.spice.tmpl"
             for b in ("loopgain", "loopgain2v", "loopgain2i")],
            [("PDK_ROOT", PDK_ROOT), ("PDK", "ihp-sg13cmos5l"), ("OSDI_DIR", OSDI),
             ("MOS_SECTION", "mos_ff"), ("RES_SECTION", "res_wcs"), ("CAP_SECTION", "cap_typ"),
             ("TEMP", "-40"), ("LG_AC_MAX", "10g"), ("CC_W", "170u (nominal)"),
             ("DESIGN_NETLIST", DESIGN), ("LOAD_A", "0.001"), ("COUT_F", "1u"),
             ("COUT_BOTTOM", "0"),
             ("ESR_LINE", "* ESR=0: Cout wired directly to ground (campaign default)"),
             ("AC_CSV", "corners/ID/loopgain2v_ff_-40c_rwcs_ac.csv")]),
        # run_e1op.sh render_deck: DC-only bench, no LG_AC_MAX token.
        "run_e1op.sh render_deck": (
            [PVT / "testbench" / "tb_e1op_cmos5l.spice.tmpl"],
            [("PDK_ROOT", PDK_ROOT), ("PDK", "ihp-sg13cmos5l"), ("OSDI_DIR", OSDI),
             ("MOS_SECTION", "mos_tt"), ("RES_SECTION", "res_typ"), ("CAP_SECTION", "cap_typ"),
             ("TEMP", "27"), ("CC_W", "170u (nominal)"), ("DESIGN_NETLIST", DESIGN),
             ("LOAD_A", "0.001"), ("COUT_F", "1u"), ("COUT_BOTTOM", "0"),
             ("ESR_LINE", "* ESR=0: Cout wired directly to ground (all four E1 points)"),
             ("DC_CSV", "corners/ID/val_e1op_dc.csv")]),
        # pass-device-screening/run_sweep.sh: --check-env and the dropout
        # branch of run_point share one chain; the stress branch omits DC_CSV.
        "pass-device-screening --check-env / dropout": (
            [PDS / "testbench" / f"tb_{b}_pmos.spice.tmpl" for b in ("dropout", "stress")],
            [("PDK_ROOT", "/home/ubuntu/share/pdk"), ("PDK", "ihp-sg13g2"),
             ("OSDI_DIR", "/home/ubuntu/share/pdk/ihp-sg13g2/libs.tech/ngspice/osdi"),
             ("MOS_SECTION", "mos_tt"), ("TEMP", "27"), ("W", "1u"), ("L", "0.5u"),
             ("DC_CSV", "/tmp/check_dropout_dc.csv")]),
        "pass-device-screening stress": (
            [PDS / "testbench" / "tb_stress_pmos.spice.tmpl"],
            [("PDK_ROOT", "/home/ubuntu/share/pdk"), ("PDK", "ihp-sg13g2"),
             ("OSDI_DIR", "/home/ubuntu/share/pdk/ihp-sg13g2/libs.tech/ngspice/osdi"),
             ("MOS_SECTION", "mos_fs"), ("TEMP", "125"), ("W", "300u"), ("L", "0.5u")]),
        # startup_campaign.py render_body: six str.replace tokens.
        "startup_campaign.py render_body": (
            [PVT / "testbench" / "tb_startup_cmos5l.spice.tmpl"],
            [("DESIGN_NETLIST", DESIGN), ("VIN_V", "3.63"),
             ("RLOAD_LINE", "Rload VOUT 0 36"), ("COUT_BOTTOM", "COUT_ESR"),
             ("COUT_F", "4700n"), ("ESR_LINE", "Resr COUT_ESR 0 500e-3")]),
        # dropout_campaign.py: dict + str.replace loop, nine tokens.
        "dropout_campaign.py": (
            [PVT / "testbench" / "tb_dropout_cmos5l.spice.tmpl"],
            [("PDK_ROOT", PDK_ROOT), ("PDK", "ihp-sg13cmos5l"), ("OSDI_DIR", OSDI),
             ("MOS_SECTION", "mos_fs"), ("RES_SECTION", "res_wcs"), ("CAP_SECTION", "cap_typ"),
             ("TEMP", "125"), ("DESIGN_NETLIST", DESIGN),
             ("DC_CSV", "corners/ID/dcsweep_fs_125c_rwcs_dc.csv")]),
    }

    def test_every_site_renders_byte_identically_to_its_old_sed_chain(self):
        n_decks = 0
        for site, (templates, pairs) in self.SITES.items():
            for tmpl in templates:
                with self.subTest(site=site, template=tmpl.name):
                    text = tmpl.read_text(encoding="utf-8")
                    old = sed_render(text, pairs)
                    new = rd.render(text, dict(pairs))
                    self.assertEqual(old, new)
                    n_decks += 1
        self.assertGreater(n_decks, 10)

    def test_frozen_sites_leave_no_placeholder(self):
        # Every frozen mapping covers its templates: the universal guard
        # (#236) holds for the values the sites actually pass.
        for site, (templates, pairs) in self.SITES.items():
            for tmpl in templates:
                text = tmpl.read_text(encoding="utf-8")
                rd.render(text, dict(pairs))  # raises on any leftover


class Cli(unittest.TestCase):
    def test_renders_file_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            tmpl = os.path.join(d, "t.tmpl")
            out = os.path.join(d, "out.spice")
            with open(tmpl, "w") as f:
                f.write("* @@A@@ @@B@@\n")
            rc = subprocess.run(
                [sys.executable, str(HERE / "render_deck.py"), tmpl, out, "A=1|2", "B=x&y"],
                capture_output=True, text=True)
            self.assertEqual(rc.returncode, 0, rc.stderr)
            with open(out) as f:
                self.assertEqual(f.read(), "* 1|2 x&y\n")

    def test_leftover_token_fails_loudly(self):
        with tempfile.TemporaryDirectory() as d:
            tmpl = os.path.join(d, "t.tmpl")
            out = os.path.join(d, "out.spice")
            with open(tmpl, "w") as f:
                f.write("@@A@@ @@FORGOTTEN@@\n")
            rc = subprocess.run(
                [sys.executable, str(HERE / "render_deck.py"), tmpl, out, "A=1"],
                capture_output=True, text=True)
            self.assertEqual(rc.returncode, 1)
            self.assertIn("FORGOTTEN", rc.stderr)
            self.assertFalse(os.path.exists(out))

    def test_missing_template_and_bad_kv_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.spice")
            rc = subprocess.run(
                [sys.executable, str(HERE / "render_deck.py"), os.path.join(d, "nope"), out, "A=1"],
                capture_output=True, text=True)
            self.assertEqual(rc.returncode, 1)
            with open(os.path.join(d, "t.tmpl"), "w") as f:
                f.write("@@A@@\n")
            rc = subprocess.run(
                [sys.executable, str(HERE / "render_deck.py"), os.path.join(d, "t.tmpl"), out, "A"],
                capture_output=True, text=True)
            self.assertEqual(rc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
