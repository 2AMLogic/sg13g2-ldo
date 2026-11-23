#!/usr/bin/env python3
"""Unit tests and negative controls for the E4 override contract (issue
#315). stdlib only: no PDK, no simulator.

The two failure modes the issue names -- an override that does not reach
the deck, and an R_div override that changes only one of XRtop/XRbot -- are
each exercised as a NEGATIVE CONTROL: the test builds the offending text and
asserts the contract refuses it. The happy path renders a real deck from
each committed template (text substitution only) and asserts that the
overridden lines are the ones the deck carries -- for the PSRR bench
through its .include alone, for the flattened benches through both the
.include and the deck's own lines.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import e4_divider_cc as e  # noqa: E402
import render_deck  # noqa: E402

COMMITTED = os.path.join(HERE, "..", "..", "design", "sg13cmos5l", "netlist",
                         "ldo_core_cmos5l.spice")
W065, L05 = e.CC_LEVELS["0.65x"], e.RDIV_LEVELS["0.5x"]


def _template(bench):
    return os.path.join(HERE, "testbench", f"tb_{bench}_cmos5l.spice.tmpl")


def _render(bench, out, design_copy, csv_path):
    """Render one committed template to `out` with the P5 / run_e4.sh
    substitutions (paths are arbitrary: nothing here is simulated)."""
    with open(_template(bench), encoding="utf-8") as fh:
        text = fh.read()
    mapping = {
        "PDK_ROOT": "/pdk", "PDK": "ihp-sg13cmos5l", "OSDI_DIR": "/osdi",
        "MOS_SECTION": "mos_ss", "RES_SECTION": "res_wcs", "CAP_SECTION": "cap_typ",
        "TEMP": "125", "LG_AC_MAX": e.LG_AC_MAX, "CC_W": "170e-6",
        "DESIGN_NETLIST": design_copy, "LOAD_A": "0", "COUT_F": "3.45u",
        "COUT_BOTTOM": "0", "ESR_LINE": "* ESR=0: Cout wired directly to ground",
        "AC_CSV": csv_path, "DC_CSV": csv_path,
    }
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_deck.render(text, mapping))


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class ContractLines(unittest.TestCase):
    """The lines the contract owns must be where it says, in the committed
    netlist and in the templates that flatten or replicate them."""

    def test_levels_are_the_issue_values(self):
        self.assertEqual(e.CC_LEVELS, {"1x": "170e-6", "0.65x": "110.5e-6"})
        self.assertEqual(e.RDIV_LEVELS, {"1x": "25.43e-6", "0.5x": "12.715e-6"})
        self.assertAlmostEqual(0.65 * 170.0, 110.5)
        self.assertAlmostEqual(0.5 * 25.43, 12.715)

    def test_contract_lines_are_in_the_committed_netlist(self):
        with open(COMMITTED, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual([cw for _, cw, _ in e._cc_widths(text)], [e.CC_NOMINAL_W])
        self.assertIn("XCc OUT MZ cap_cmomi w=170e-6 l=30e-6 mmin=1 mmax=4 feed=double subblock=0 m=1 mm_ok=1", text)
        for inst in e.CORE_LEGS:
            self.assertEqual(e._count_line(text, e.DIVIDER_LEGS[inst]), 1, inst)
        for inst in ("XRrep_top", "XRrep_bot"):
            self.assertEqual(e._count_line(text, e.DIVIDER_LEGS[inst]), 0, inst)

    def test_flattened_and_replica_legs_are_in_the_templates(self):
        for bench, legs in e.BENCH_DECK_LEGS.items():
            with open(_template(bench), encoding="utf-8") as fh:
                text = fh.read()
            for inst in e.DIVIDER_LEGS:
                self.assertEqual(e._count_line(text, e.DIVIDER_LEGS[inst]),
                                 1 if inst in legs else 0, f"{bench}/{inst}")

    def test_psrr_instantiates_the_core_whole(self):
        with open(_template("psrr"), encoding="utf-8") as fh:
            self.assertIn("Xtop VIN VOUT 0 VREF IBIAS VIN ldo_core_cmos5l", fh.read())


class OverrideContract(unittest.TestCase):
    def setUp(self):
        with open(COMMITTED, encoding="utf-8") as fh:
            self.src = fh.read()
        self.lines = self.src.splitlines()

    def _diff(self, out):
        return [(a, b) for a, b in zip(self.lines, out.splitlines()) if a != b]

    def test_1x_1x_is_the_committed_bytes(self):
        self.assertEqual(e.overridden_design_netlist(self.src, e.CC_NOMINAL_W, e.RDIV_NOMINAL_L),
                         self.src)

    def test_cc_override_changes_exactly_the_xcc_line(self):
        out = e.overridden_design_netlist(self.src, W065, e.RDIV_NOMINAL_L)
        committed = [ln for ln in self.lines if ln.startswith("XCc OUT MZ cap_cmomi ")]
        self.assertEqual(self._diff(out), [
            (committed[0], committed[0].replace("w=170e-6", "w=110.5e-6"))])
        self.assertEqual(len(out.splitlines()), len(self.lines))

    def test_rdiv_override_changes_both_legs_and_only_them(self):
        out = e.overridden_design_netlist(self.src, e.CC_NOMINAL_W, L05)
        self.assertEqual(sorted(self._diff(out)), sorted([
            (e.DIVIDER_LEGS["XRtop"], "XRtop VOUT FB VSS rhigh w=1e-6 l=12.715e-6 m=1 b=7"),
            (e.DIVIDER_LEGS["XRbot"], "XRbot FB VSS VSS rhigh w=1e-6 l=12.715e-6 m=1 b=7")]))
        self.assertIn("XCc OUT MZ cap_cmomi w=170e-6 l=30e-6", out)
        self.assertIn("XRz MZ G1 VSS rhigh w=1e-6 l=28.81e-6 m=1 b=39", out)

    def test_negative_control_cc_noop_is_refused(self):
        drifted = self.src.replace("XCc OUT MZ cap_cmomi w=170e-6", "XCc OUT MZ cap_cmomi w=150e-6")
        with self.assertRaises(e.OverrideError):
            e.overridden_design_netlist(drifted, W065, e.RDIV_NOMINAL_L)

    def test_negative_control_rdiv_one_leg_only_is_refused(self):
        """XRbot's line drifted: a substitution that would move XRtop alone
        -- and with it the divider ratio -- must not go through."""
        drifted = self.src.replace(e.DIVIDER_LEGS["XRbot"],
                                   "XRbot FB VSS VSS rhigh w=1e-6 l=24e-6 m=1 b=7")
        with self.assertRaises(e.OverrideError):
            e.overridden_design_netlist(drifted, e.CC_NOMINAL_W, L05)
        self.assertNotIn("l=12.715e-6", drifted)

    def test_negative_control_rdiv_noop_is_refused(self):
        drifted = self.src
        for inst in e.CORE_LEGS:
            drifted = drifted.replace(e.DIVIDER_LEGS[inst], e.DIVIDER_LEGS[inst].replace("l=25.43e-6", "l=24e-6"))
        with self.assertRaises(e.OverrideError):
            e.subst_rdiv(drifted, L05, e.CORE_LEGS)

    def test_rdiv_is_refused_at_1x_when_a_leg_drifted(self):
        drifted = self.src.replace(e.DIVIDER_LEGS["XRtop"], "XRtop VOUT FB VSS rhigh w=1e-6 l=25.4e-6 m=1 b=7")
        with self.assertRaises(e.OverrideError):
            e.subst_rdiv(drifted, e.RDIV_NOMINAL_L, e.CORE_LEGS)

    def test_subst_rdiv_with_no_legs_is_identity_even_off_nominal(self):
        self.assertEqual(e.subst_rdiv("XRz\n", L05, ()), "XRz\n")


class DesignCopyCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.before = _sha(COMMITTED)

    def tearDown(self):
        self.assertEqual(_sha(COMMITTED), self.before, "the committed netlist was written")
        self.tmp.cleanup()

    def test_copy_is_written_and_source_untouched(self):
        out = os.path.join(self.tmp.name, "copy.spice")
        self.assertEqual(e.main(["design-copy", COMMITTED, out, "--w", W065, "--l", L05]), 0)
        with open(out, encoding="utf-8") as fh:
            copy = fh.read()
        self.assertIn("w=110.5e-6 l=30e-6", copy)
        self.assertIn("l=12.715e-6 m=1 b=7", copy)

    def test_1x_1x_copy_equals_the_committed_bytes(self):
        out = os.path.join(self.tmp.name, "one_x.spice")
        self.assertEqual(e.main(["design-copy", COMMITTED, out, "--w", e.CC_NOMINAL_W,
                                  "--l", e.RDIV_NOMINAL_L]), 0)
        self.assertEqual(_sha(out), self.before)

    def test_writing_over_the_committed_netlist_is_refused(self):
        self.assertEqual(e.main(["design-copy", COMMITTED, COMMITTED, "--w", e.CC_NOMINAL_W,
                                  "--l", e.RDIV_NOMINAL_L]), 4)


class VerifyDeck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        with open(COMMITTED, encoding="utf-8") as fh:
            self.src = fh.read()

    def tearDown(self):
        self.tmp.cleanup()

    def _copy(self, w, l):
        text = e.overridden_design_netlist(self.src, w, l)
        path = os.path.join(self.d, f"copy_{w}_{l}.spice")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path, text

    def _deck(self, bench, copy_path, patched, w, l):
        deck = os.path.join(self.d, f"{bench}_{w}_{l}.spice")
        _render(bench, deck, copy_path, os.path.join(self.d, "x.csv"))
        if patched:
            with open(deck, encoding="utf-8") as fh:
                text = e.subst_rdiv(fh.read(), l, e.BENCH_DECK_LEGS[bench])
            with open(deck, "w", encoding="utf-8") as fh:
                fh.write(text)
        with open(deck, encoding="utf-8") as fh:
            return fh.read()

    def test_every_bench_verifies_at_1x_1x(self):
        copy, text = self._copy(e.CC_NOMINAL_W, e.RDIV_NOMINAL_L)
        for bench in e.BENCHES:
            e.verify_deck(self._deck(bench, copy, True, e.CC_NOMINAL_W, e.RDIV_NOMINAL_L),
                          text, bench, e.CC_NOMINAL_W, e.RDIV_NOMINAL_L)

    def test_every_bench_verifies_at_0p5x_0p65x_when_patched(self):
        copy, text = self._copy(W065, L05)
        for bench in e.BENCHES:
            deck = self._deck(bench, copy, True, W065, L05)
            e.verify_deck(deck, text, bench, W065, L05)
            self.assertEqual([cw for _, cw, _ in e._cc_widths(text)], [W065])
            for inst in e.BENCH_DECK_LEGS[bench]:
                self.assertIn(e.DIVIDER_LEGS[inst].replace("l=25.43e-6", "l=12.715e-6"), deck)

    def test_negative_control_unpatched_flattened_legs_are_refused(self):
        """The loop-gain deck whose .include names the 0.5x copy while its own
        XRtop/XRbot lines stayed nominal: the override did not reach the deck."""
        copy, text = self._copy(e.CC_NOMINAL_W, L05)
        deck = self._deck("loopgain", copy, False, e.CC_NOMINAL_W, L05)
        self.assertIn(".include \"" + copy + "\"", deck)
        with self.assertRaises(e.OverrideError) as cm:
            e.verify_deck(deck, text, "loopgain", e.CC_NOMINAL_W, L05)
        self.assertIn("did not reach the deck", str(cm.exception))

    def test_negative_control_unpatched_replica_is_refused(self):
        copy, text = self._copy(e.CC_NOMINAL_W, L05)
        deck = self._deck("e1op", copy, False, e.CC_NOMINAL_W, L05)
        with self.assertRaises(e.OverrideError):
            e.verify_deck(deck, text, "e1op", e.CC_NOMINAL_W, L05)

    def test_negative_control_stale_replica_with_patched_legs_is_refused(self):
        """Flattened legs moved, the replica did not: i(vdivsense) would
        report the nominal divider while the circuit runs the 0.5x one."""
        copy, text = self._copy(e.CC_NOMINAL_W, L05)
        deck = self._deck("e1op", copy, False, e.CC_NOMINAL_W, L05)
        deck = e.subst_rdiv(deck, L05, ("XRtop", "XRbot"))
        with self.assertRaises(e.OverrideError):
            e.verify_deck(deck, text, "e1op", e.CC_NOMINAL_W, L05)

    def test_negative_control_deck_including_the_committed_netlist_is_refused(self):
        """A deck whose .include names the committed (unsubstituted) netlist
        while the point claims an override."""
        copy, text = self._copy(e.CC_NOMINAL_W, L05)
        deck = self._deck("psrr", COMMITTED, True, e.CC_NOMINAL_W, L05)
        with self.assertRaises(e.OverrideError):
            e.verify_deck(deck, text, "psrr", e.CC_NOMINAL_W, L05)

    def test_negative_control_unoverridden_cc_in_the_copy_is_refused(self):
        copy, _ = self._copy(e.CC_NOMINAL_W, e.RDIV_NOMINAL_L)
        deck = self._deck("psrr", copy, True, e.CC_NOMINAL_W, e.RDIV_NOMINAL_L)
        with self.assertRaises(e.OverrideError):
            e.verify_deck(deck, self.src, "psrr", W065, e.RDIV_NOMINAL_L)

    def test_psrr_carries_the_override_through_the_include_only(self):
        copy, text = self._copy(W065, L05)
        deck = self._deck("psrr", copy, True, W065, L05)
        for inst in e.DIVIDER_LEGS:
            self.assertNotIn(inst + " ", deck)
        self.assertIn("XCc", text)
        e.verify_deck(deck, text, "psrr", W065, L05)

    def test_patch_deck_cli_patches_and_verifies(self):
        copy, text = self._copy(W065, L05)
        deck = os.path.join(self.d, "cli.spice")
        _render("e1op", deck, copy, os.path.join(self.d, "x.csv"))
        self.assertEqual(e.main(["patch-deck", deck, "--bench", "e1op", "--design", copy,
                                  "--w", W065, "--l", L05]), 0)
        with open(deck, encoding="utf-8") as fh:
            out = fh.read()
        for inst in e.BENCH_DECK_LEGS["e1op"]:
            self.assertEqual(e._count_line(out, e.DIVIDER_LEGS[inst].replace("l=25.43e-6", "l=12.715e-6")), 1)
        self.assertNotIn("l=25.43e-6", out)

    def test_patch_deck_cli_refuses_a_drifted_deck(self):
        """A template edit that moved a flattened leg's text: the patch is
        refused (exit 4) and the deck is left as rendered."""
        copy, _ = self._copy(e.CC_NOMINAL_W, L05)
        deck = os.path.join(self.d, "drift.spice")
        _render("loopgain", deck, copy, os.path.join(self.d, "x.csv"))
        with open(deck, encoding="utf-8") as fh:
            drifted = fh.read().replace(e.DIVIDER_LEGS["XRbot"],
                                        "XRbot FB VSS VSS rhigh w=1e-6 l=25.43e-6 m=2 b=7")
        with open(deck, "w", encoding="utf-8") as fh:
            fh.write(drifted)
        self.assertEqual(e.main(["patch-deck", deck, "--bench", "loopgain", "--design", copy,
                                  "--w", e.CC_NOMINAL_W, "--l", L05]), 4)
        with open(deck, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), drifted)


class Readings(unittest.TestCase):
    """The reading functions, against the committed same-vintage P5 traces
    (no simulator): the values DR-0015's table row P5 prints."""

    STEM = os.path.join(HERE, "corners", e.BASELINE_RID)

    def test_loopgain_reading_of_the_committed_p5(self):
        r = e.loopgain_reading(os.path.join(self.STEM, f"loopgain_{e.BASELINE_STEM}_ac.csv"))
        self.assertAlmostEqual(r["lg:f_ug_hz"], 1052.0, delta=0.5)
        self.assertAlmostEqual(r["lg:pm_deg"], 17.61, delta=0.01)
        self.assertAlmostEqual(r["lg:gm_db"], 64.26, delta=0.01)
        self.assertEqual(r["lg:n_0db_crossings"], 1)
        self.assertEqual(r["lg:pm_verdict"], "fail")
        self.assertEqual(r["lg:gm_verdict"], "ambiguous")
        self.assertEqual(r["lg:gm_reasons"], "ceiling_unbounded")
        self.assertAlmostEqual(r["lg:gain_db_1khz"], 0.85, delta=0.01)

    def test_psrr_reading_of_the_committed_p5(self):
        r = e.psrr_reading(os.path.join(self.STEM, f"psrr_{e.BASELINE_STEM}_ac.csv"))
        self.assertAlmostEqual(r["psrr:db_1khz"], 43.55, delta=0.01)
        self.assertAlmostEqual(r["psrr:db_100khz"], 92.53, delta=0.01)
        self.assertAlmostEqual(r["psrr:notch_db"], 43.31, delta=0.01)
        self.assertAlmostEqual(r["psrr:notch_hz"], 1122.0, delta=1.0)

    def test_psrr_axis_problems(self):
        good = os.path.join(self.STEM, f"psrr_{e.BASELINE_STEM}_ac.csv")
        self.assertEqual(e.psrr_axis_problems(good), [])
        with tempfile.TemporaryDirectory() as d:
            with open(good) as fh:
                rows = [ln for ln in fh if ln.strip()]
            short = os.path.join(d, "short.csv")
            with open(short, "w") as fh:
                fh.writelines(rows[:-1])
            self.assertEqual(len(e.psrr_axis_problems(short)), 1)
            ragged = os.path.join(d, "ragged.csv")
            with open(ragged, "w") as fh:
                fh.writelines(rows[:-1] + [rows[-1].rstrip("\n") + " 1.0\n"])
            self.assertEqual(len(e.psrr_axis_problems(ragged)), 1)
            self.assertTrue(e.psrr_axis_problems(os.path.join(d, "missing.csv")))

    def test_baseline_reading_loads(self):
        b = e._baseline_reading()
        self.assertAlmostEqual(b["base:lg:f_ug_hz"], 1052.0, delta=0.5)
        self.assertAlmostEqual(b["base:psrr:notch_hz"], 1122.0, delta=1.0)


class ModelsLoaded(unittest.TestCase):
    """The model-load gate reads the batch provenance: a job whose verified
    preload is incomplete, or a log carrying osdi_load_failed, is refused."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.corners = os.path.join(self.tmp.name, "corners")
        self.prov = os.path.join(self.corners, "_batch")
        os.makedirs(self.prov)
        self.staged = {f"{n}.osdi": f"{i:064x}" for i, n in enumerate(
            ["psp103", "psp103_nqs", "mosvar", "r3_cmc", "cap_cmomi", "cap_cmomf"])}
        self.jobs = [{"group": "g00_a", "job_id": "klt-sim-0",
                      "osdi_preload_verified": dict(self.staged)},
                     {"group": "g01_b", "job_id": "klt-sim-1",
                      "osdi_preload_verified": dict(self.staged)}]
        with open(os.path.join(self.prov, "points.tsv"), "w") as fh:
            fh.write("point_id\tgroup\tprocess\ttemperature_c\n")
            fh.write("a\tg00_a\tmos_ss__res_wcs__cap_typ\t125\n")
            fh.write("b\tg01_b\tmos_ss__res_wcs__cap_typ\t125\n")
        for pid in ("a", "b"):
            with open(os.path.join(self.corners, f"{pid}.log"), "w") as fh:
                fh.write("Doing analysis at TEMP = 125\nngspice-47 done\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _flush(self):
        with open(os.path.join(self.prov, "backend.json"), "w") as fh:
            json.dump({"staged_osdi_sha256": self.staged, "jobs": self.jobs}, fh)

    def test_all_loaded(self):
        self._flush()
        self.assertEqual(e.models_loaded(self.corners), {"a": (True, ""), "b": (True, "")})

    def test_osdi_load_failed_in_the_log_is_refused(self):
        self._flush()
        with open(os.path.join(self.corners, "a.log"), "a") as fh:
            fh.write("Error: Library inputs/psp103.osdi couldn't be loaded!\n")
        got = e.models_loaded(self.corners)
        self.assertFalse(got["a"][0])
        self.assertIn("couldn't be loaded", got["a"][1])
        self.assertTrue(got["b"][0])

    def test_incomplete_preload_is_refused(self):
        self.jobs[1]["osdi_preload_verified"] = {k: v for k, v in self.staged.items()
                                                if k != "cap_cmomi.osdi"}
        self._flush()
        got = e.models_loaded(self.corners)
        self.assertFalse(got["b"][0])
        self.assertIn("cap_cmomi.osdi not reported preloaded", got["b"][1])

    def test_preloaded_digest_mismatch_is_refused(self):
        self.jobs[1]["osdi_preload_verified"]["psp103.osdi"] = "f" * 64
        self._flush()
        got = e.models_loaded(self.corners)
        self.assertFalse(got["b"][0])
        self.assertIn("psp103.osdi preload sha256 != staged", got["b"][1])

    def test_missing_log_or_job_is_refused(self):
        self._flush()
        os.remove(os.path.join(self.corners, "a.log"))
        self.jobs = self.jobs[1:]
        self._flush()
        got = e.models_loaded(self.corners)
        self.assertIn("no log", got["a"][1])
        self.assertIn("no job record for group g00_a", got["a"][1])
        self.assertTrue(got["b"][0])

    def test_no_provenance_means_no_point_is_trusted(self):
        shutil.rmtree(self.prov)
        self.assertEqual(e.models_loaded(self.corners), {})


class DeckProvenance(unittest.TestCase):
    """The fleet-side proof that the override is what the worker simulated:
    the report's closure digest for the copy equals a fresh re-derivation,
    the submitted tb.spice carries the bench's own legs, the corner passed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.corners = os.path.join(self.tmp.name, "corners")
        self.prov = os.path.join(self.corners, "_batch")
        os.makedirs(self.prov)
        with open(COMMITTED, encoding="utf-8") as fh:
            committed = fh.read()
        self.committed_sha = hashlib.sha256(committed.encode("utf-8")).hexdigest()
        self.groups = {}
        rows = ["point_id\tgroup\tprocess\ttemperature_c\n"]
        for rdiv, cc in e.POINTS:
            key = e.point_key(rdiv, cc)
            text = e.overridden_design_netlist(committed, e.CC_LEVELS[cc], e.RDIV_LEVELS[rdiv])
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            for bench in e.BENCHES:
                pid = e.point_id(bench, key)
                g = f"g_{pid}"
                d = os.path.join(self.prov, g)
                os.makedirs(d)
                self.groups[pid] = (d, e.design_copy_name(key), sha, bench, e.RDIV_LEVELS[rdiv])
                rows.append(f"{pid}\t{g}\tmos_ss__res_wcs__cap_typ\t125\n")
        with open(os.path.join(self.prov, "points.tsv"), "w") as fh:
            fh.writelines(rows)
        for pid, (d, name, sha, bench, l) in self.groups.items():
            self._write_group(pid, name, sha, bench, l)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_group(self, pid, name, sha, bench, l, status="pass", diags=None, legs_at=None):
        d = self.groups[pid][0]
        with open(os.path.join(d, "report.json"), "w") as fh:
            json.dump({"corners": [{"process": "mos_ss__res_wcs__cap_typ", "temperature_c": 125,
                                    "status": status, "diagnostics": diags or []}],
                       "environment": {"netlist_closure": [{"path": "/x/" + name, "sha256": sha}]}},
                      fh)
        legs = "\n".join(e.DIVIDER_LEGS[i].replace("l=" + e.RDIV_NOMINAL_L, "l=" + (legs_at or l))
                         for i in e.BENCH_DECK_LEGS[bench]) + "\n"
        with open(os.path.join(d, "tb.spice"), "w") as fh:
            fh.write(f'.include "/abs/{name}"\n{legs}.end\n')

    def _all_ok(self):
        got = e.deck_provenance("r", self.corners)
        self.assertEqual(len(got), 12)
        return got

    def test_happy_path_all_decks_verified(self):
        got = self._all_ok()
        self.assertTrue(all(ok for ok, _ in got.values()), got)

    def test_negative_control_nominal_copy_staged_is_refused(self):
        """The worker staged the committed (nominal) netlist although the
        point claims 0.5x: the closure digest is the committed one."""
        pid = e.point_id("psrr", e.point_key("0.5x", "1x"))
        d, name, _sha, bench, l = self.groups[pid]
        self._write_group(pid, name, self.committed_sha, bench, l)
        got = self._all_ok()
        self.assertFalse(got[pid][0])
        self.assertIn("not the re-derived override", got[pid][1])

    def test_negative_control_unpatched_tb_legs_are_refused(self):
        pid = e.point_id("loopgain", e.point_key("0.5x", "0.65x"))
        d, name, sha, bench, l = self.groups[pid]
        self._write_group(pid, name, sha, bench, l, legs_at=e.RDIV_NOMINAL_L)
        got = self._all_ok()
        self.assertFalse(got[pid][0])
        self.assertIn("does not carry XRtop at l=12.715e-6", got[pid][1])

    def test_negative_control_errored_corner_is_refused(self):
        pid = e.point_id("e1op", e.point_key("1x", "0.65x"))
        d, name, sha, bench, l = self.groups[pid]
        self._write_group(pid, name, sha, bench, l, status="error",
                          diags=[{"severity": "error", "code": "osdi_load_failed"}])
        got = self._all_ok()
        self.assertFalse(got[pid][0])

    def test_no_provenance_is_not_trusted(self):
        shutil.rmtree(self.prov)
        self.assertEqual(e.deck_provenance("r", self.corners), {})


class PointIds(unittest.TestCase):
    def test_ids_start_with_the_bench_prefix(self):
        for bench in e.BENCHES:
            self.assertTrue(e.point_id(bench, "rdiv1x_cc1x").startswith(bench + "_"))

    def test_keys_avoid_dots(self):
        self.assertEqual(e.point_key("0.5x", "0.65x"), "rdiv0p5x_cc0p65x")
        self.assertEqual([e.point_key(a, b) for a, b in e.POINTS],
                         ["rdiv1x_cc1x", "rdiv1x_cc0p65x", "rdiv0p5x_cc1x", "rdiv0p5x_cc0p65x"])


if __name__ == "__main__":
    unittest.main()
