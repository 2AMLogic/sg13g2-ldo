#!/usr/bin/env python3
"""Negative controls for the E3 Cc-width probe (issue #219). stdlib only.

The centre of gravity is AC 6's negative control: an override that does not
reach the deck must FAIL, loudly. The failure modes exercised here against
synthetic fixtures (and against the committed design netlist, where a check
is cheap and read-only):

  * the width table agrees with run_sweep.sh's own Cc block AND with the
    committed design netlist's XCc line -- the three copies of the contract
    (ccprobe.py, run_sweep.sh, the design) cannot drift;
  * subst_cc_width() replaces only XCc's w= token, returns the input
    unchanged for 1x, and RAISES -- never a silent no-op -- on a drifted
    nominal width, a renamed node, an absent line, a second occurrence or an
    unknown label (the Python equivalent of run_sweep.sh subst_cc_width's
    exit-4 FATAL);
  * the point ids cannot collide across the three Cc labels;
  * the f_ug-vs-Cc slope machinery reports the branch premise honestly
    (unequal crossing counts -> not single-branch -> the probe does not
    discriminate) and the slope arithmetic on synthetic responses;
  * the like-for-like gate passes when nothing moved and fails with named
    reasons when the metrics move beyond the stated bounds;
  * the committed baseline traces still match their pinned sha256/16;
  * the pinned loop-gain template still carries every placeholder the
    driver renders.
"""
import math
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ccprobe as c  # noqa: E402
import ac_metrics as am  # noqa: E402


# ---- shared contract functions (also called by run_ccprobe.sh at runtime) - #
def width_table_matches_run_sweep():
    """ccprobe.CC_WIDTHS / CC_NOMINAL_W must equal run_sweep.sh's own Cc
    block (the shell table is the contract of record; this module mirrors it
    so the substitution is unit-testable)."""
    with open(os.path.join(HERE, "run_sweep.sh"), encoding="utf-8") as fh:
        sh = fh.read()
    m = re.search(r'^CC_NOMINAL_W="([^"]+)"', sh, re.M)
    if not m or m.group(1) != c.CC_NOMINAL_W:
        raise AssertionError(
            f"CC_NOMINAL_W drifted: run_sweep.sh has {m and m.group(1)!r}, "
            f"ccprobe.py has {c.CC_NOMINAL_W!r}")
    block = re.search(r"declare -A CC_WIDTHS=\(([^)]*)\)", sh, re.M)
    if not block:
        raise AssertionError("run_sweep.sh lost its declare -A CC_WIDTHS block")
    shell_table = dict(re.findall(r'\["([^"]+)"\]="([^"]+)"', block.group(1)))
    if shell_table != c.CC_WIDTHS:
        raise AssertionError(
            f"CC_WIDTHS drifted: run_sweep.sh has {shell_table}, "
            f"ccprobe.py has {c.CC_WIDTHS}")


def nominal_width_tracks_design_netlist():
    """CC_NOMINAL_W must still be what the committed design netlist draws:
    exactly one XCc line, matching the token this contract substitutes (the
    same invariant run_sweep.sh's subst_cc_width enforces with its exit-4
    FATAL -- here it is asserted, not armed)."""
    with open(c.DESIGN_NETLIST, encoding="utf-8") as fh:
        text = fh.read()
    n = text.count(c.XCc_TOKEN)
    if n != 1:
        raise AssertionError(
            f"design netlist {c.DESIGN_NETLIST} carries {n} occurrences of "
            f"the expected XCc prefix ({c.XCc_TOKEN!r}); CC_NOMINAL_W/CC_L "
            "have drifted from the design")


def driver_record_naming_uses_bench():
    """run_ccprobe.sh must address its record files as
    records/<rid>.<ccprobe.BENCH>.{csv,md,manifest.tsv} -- the names
    ccprobe.py check / record-md / _pdk_provenance read back -- by deriving
    the tag from this module, never by hardcoding a second copy of it (the
    2026-11-23 first campaign run wrote .ccprobe.csv while record-md read
    .loopgain_ccprobe.csv and crashed; this assert keeps that class of drift
    out)."""
    with open(os.path.join(HERE, "run_ccprobe.sh"), encoding="utf-8") as fh:
        sh = fh.read()
    for suffix in ("csv", "md", "manifest.tsv"):
        if re.search(rf'RECORD_ID}}\.{suffix}"', sh) or f'"{c.BENCH}.{suffix}"' in sh:
            raise AssertionError(
                f"run_ccprobe.sh hardcodes a record filename for .{suffix}; "
                "it must derive all record names from ccprobe.BENCH")
    for needle in (f"${{RECORD_ID}}.${{BENCH}}.csv", f"${{RECORD_ID}}.${{BENCH}}.md",
                   f"${{RECORD_ID}}.${{BENCH}}.manifest.tsv"):
        if needle not in sh:
            raise AssertionError(
                f"run_ccprobe.sh lost the {needle} record-path derivation")


# ---- fixtures -------------------------------------------------------------- #
def _trace_fixture(path, f_ug=1.05e6, dc_db=60.0, slope_db_per_dec=-20.0,
                   phase_at_ug=-135.0, fmin=1.0, fmax=1e9, ppd=20):
    """A synthetic single-pole loop-gain trace in the 4-column wrdata layout
    (f, dB, f, deg): gain capped at dc_db, rolling off at slope_db_per_dec
    through 0 dB at f_ug (deliberately NOT on the log grid, so no sample
    sits exactly at 0 dB), phase ramping linearly in log-f through
    phase_at_ug there and continuing past it far enough to cross -180 deg
    (so the GM machinery has a critical crossing to read)."""
    rate = phase_at_ug / math.log10(f_ug / fmin)   # deg per decade
    rows = []
    n = int(ppd * math.log10(fmax / fmin))
    for i in range(n + 1):
        f = fmin * (fmax / fmin) ** (i / n)
        db = min(dc_db, -slope_db_per_dec * math.log10(f_ug / f))
        deg = rate * math.log10(f / fmin)
        rows.append(f"{f:.8e} {db:.8e} {f:.8e} {deg:.8e}")
    with open(path, "w") as fh:
        fh.write("\n".join(rows) + "\n")
    return path


def _row_for(trace_path, label="1x"):
    return c.reduce_point(label, trace_path)


class WidthTableContract(unittest.TestCase):
    def test_width_table_matches_run_sweep(self):
        width_table_matches_run_sweep()

    def test_nominal_width_tracks_design_netlist(self):
        nominal_width_tracks_design_netlist()

    def test_driver_record_naming_uses_bench(self):
        driver_record_naming_uses_bench()

    def test_design_netlist_substitutes_cleanly_for_all_labels(self):
        with open(c.DESIGN_NETLIST, encoding="utf-8") as fh:
            text = fh.read()
        for lab in c.CC_LABELS:
            out = c.subst_cc_width(text, lab)
            diff = [(a, b) for a, b in zip(text.splitlines(), out.splitlines())
                    if a != b]
            self.assertEqual(len(diff), 0 if lab == "1x" else 1,
                             f"label {lab}: {len(diff)} lines changed")
        self.assertEqual(c.subst_cc_width(text, "1x"), text)


class SubstitutionContract(unittest.TestCase):
    """AC 6: the override, and its negative controls."""

    def setUp(self):
        self.nominal = (
            "* some header\n"
            "XMpass VOUT EAOUT VIN VIN sg13_hv_pmos w=2800u l=0.5u ng=1 m=1\n"
            "XRtop VOUT FB VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7\n"
            "XCc OUT MZ cap_cmomi w=170e-6 l=30e-6 mmin=1 mmax=4 feed=double"
            " subblock=0 m=1 mm_ok=1\n"
            "Xamp FBAMP VREF EAOUT VIN VSS IBIAS EN ldo_erramp_cmos5l\n"
            ".end\n")

    def test_happy_path_changes_only_the_w_token(self):
        out = c.subst_cc_width(self.nominal, "0.5x")
        self.assertIn("XCc OUT MZ cap_cmomi w=85e-6 l=30e-6", out)
        # every other byte, including XCc's trailing parameters, untouched
        self.assertIn("w=85e-6 l=30e-6 mmin=1 mmax=4 feed=double subblock=0"
                      " m=1 mm_ok=1", out)
        self.assertIn("XMpass VOUT EAOUT VIN VIN sg13_hv_pmos w=2800u l=0.5u",
                      out)
        changed = [(a, b) for a, b in zip(self.nominal.splitlines(),
                                          out.splitlines()) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertNotIn("w=170e-6", out)

    def test_2x_doubles_the_width(self):
        out = c.subst_cc_width(self.nominal, "2x")
        self.assertIn("XCc OUT MZ cap_cmomi w=340e-6 l=30e-6", out)

    def test_1x_is_byte_identical(self):
        self.assertEqual(c.subst_cc_width(self.nominal, "1x"), self.nominal)

    def test_negctl_drifted_nominal_width_raises(self):
        """THE negative control: a deck whose XCc width has drifted (here
        w=200e-6) must RAISE -- an override applied to it would not reach
        the deck, and simulating it three times would silently produce the
        nominal netlist."""
        drifted = self.nominal.replace("w=170e-6", "w=200e-6")
        with self.assertRaises(c.CcSubstitutionError):
            c.subst_cc_width(drifted, "0.5x")

    def test_negctl_renamed_node_raises(self):
        renamed = self.nominal.replace("XCc OUT MZ", "XCc VOUT MZ")
        with self.assertRaises(c.CcSubstitutionError):
            c.subst_cc_width(renamed, "2x")

    def test_negctl_absent_line_raises(self):
        absent = "\n".join(ln for ln in self.nominal.splitlines()
                           if not ln.startswith("XCc")) + "\n"
        with self.assertRaises(c.CcSubstitutionError):
            c.subst_cc_width(absent, "0.5x")

    def test_negctl_second_occurrence_raises(self):
        twice = self.nominal + self.nominal
        with self.assertRaises(c.CcSubstitutionError):
            c.subst_cc_width(twice, "0.5x")

    def test_unknown_label_raises(self):
        with self.assertRaises(c.CcSubstitutionError):
            c.subst_cc_width(self.nominal, "3x")

    def test_subst_subcommand_fails_with_exit_4(self):
        """The CLI mirror of run_sweep.sh's exit-4 FATAL."""
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            drifted = os.path.join(tmp, "drifted.spice")
            with open(drifted, "w") as fh:
                fh.write(self.nominal.replace("w=170e-6", "w=200e-6"))
            rc = subprocess.call(
                [sys.executable, os.path.join(HERE, "ccprobe.py"), "subst",
                 drifted, os.path.join(tmp, "out.spice"), "2x"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(rc, 4, "drifted deck must exit 4, not 0")
            self.assertFalse(os.path.exists(os.path.join(tmp, "out.spice")))


class PointIdContract(unittest.TestCase):
    def test_three_distinct_ids(self):
        ids = [c.point_id(lab) for lab in c.CC_LABELS]
        self.assertEqual(len(set(ids)), 3, f"point ids collide: {ids}")

    def test_id_shape_carries_the_cc_suffix(self):
        self.assertEqual(
            c.point_id("0.5x"),
            "loopgain_ccprobe_dyn_ff_-40c_rwcs_i50000ua_c330nf_e0mohm_cc0.5x")
        self.assertTrue(c.point_id("1x").endswith("_cc1x"))
        self.assertTrue(c.point_id("2x").endswith("_cc2x"))

    def test_ids_start_with_a_batch_backend_bench_prefix(self):
        """batch_backend.py (hash-pinned) dispatches on the id prefix
        whitelist; the campaign ids must stay under the loopgain_ stem."""
        import batch_backend as bb
        for lab in c.CC_LABELS:
            self.assertEqual(bb.bench_of(c.point_id(lab)), "loopgain")

    def test_unknown_label_refuses(self):
        with self.assertRaises(c.CcSubstitutionError):
            c.point_id("10x")

    def test_cc_factor_levels(self):
        self.assertEqual(c.cc_factor("0.5x"), 0.5)
        self.assertEqual(c.cc_factor("1x"), 1.0)
        self.assertEqual(c.cc_factor("2x"), 2.0)


class SlopeAndBranch(unittest.TestCase):
    """The slope arithmetic + AC 5's branch premise, on synthetic rows."""

    @staticmethod
    def _rows(f_ugs, crossings=(2, 2, 2)):
        rows = []
        for lab, f, n in zip(c.CC_LABELS, f_ugs, crossings):
            rows.append({"cc_label": lab, "unity_gain_freq_hz": f,
                         "n_0db_crossings": n})
        return rows

    def test_inverse_proportion_reads_minus_one(self):
        # f_ug proportional to Cc^-1 (a Cc-side pole moving with the cap)
        rows = self._rows([4e6, 2e6, 1e6])  # 0.5x -> 2x halves f_ug each step
        s = c.slope(rows)
        self.assertTrue(s["single_branch"])
        self.assertAlmostEqual(s["slope"], -1.0, places=9)

    def test_cc_insensitive_reads_near_zero(self):
        # f_ug fixed by a gate-side pole independent of Cc
        rows = self._rows([2e6, 2e6, 2e6])
        s = c.slope(rows)
        self.assertTrue(s["single_branch"])
        self.assertAlmostEqual(s["slope"], 0.0, places=9)

    def test_unequal_crossing_counts_is_not_single_branch(self):
        rows = self._rows([4e6, 2e6, 1e6], crossings=(2, 2, 1))
        s = c.slope(rows)
        self.assertFalse(s["single_branch"])
        self.assertEqual(s["n_0db_crossings"],
                         {"0.5x": 2, "1x": 2, "2x": 1})

    def test_missing_crossings_give_no_slope(self):
        rows = self._rows([None, 2e6, None])
        s = c.slope(rows)
        self.assertIsNone(s["slope"])


class LikeForLikeGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.trace = _trace_fixture(os.path.join(self.tmp.name, "one_x_ac.csv"))

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _base_from(row, trace_path):
        base = dict(row)
        base["trace_path_abs"] = trace_path
        return base

    def test_gate_passes_when_nothing_moved(self):
        row = _row_for(self.trace)
        ok, reasons, details = c.like_for_like_check(
            row, self._base_from(row, self.trace))
        self.assertTrue(ok, f"reasons: {reasons}")
        self.assertEqual(reasons, [])
        self.assertEqual(details["max_abs_db_diff"], 0.0)

    def test_gate_fails_with_named_reasons_when_metrics_move(self):
        row = _row_for(self.trace)
        base = self._base_from(row, self.trace)
        base["phase_margin_deg"] += 5.0     # > 1 deg bound
        base["gain_margin_db"] += 2.0       # > 1 dB bound
        base["unity_gain_freq_hz"] *= 1.1   # > 2 % bound
        base["n_0db_crossings"] += 1        # crossing count differs
        ok, reasons, _ = c.like_for_like_check(row, base)
        self.assertFalse(ok)
        self.assertIn("crossing_count_differs", " ".join(reasons))

    def test_gate_fails_when_the_trace_itself_moves(self):
        """Same metrics, different bytes: the whole-trace dB bound is what
        catches a deck that changed shape without moving the scalars."""
        row = _row_for(self.trace)
        other = _trace_fixture(os.path.join(self.tmp.name, "other_ac.csv"),
                               dc_db=40.0)
        ok, reasons, details = c.like_for_like_check(
            row, self._base_from(row, other))
        self.assertFalse(ok)
        self.assertTrue(any(r.startswith("trace_diff_") for r in reasons),
                        f"reasons: {reasons}")
        self.assertGreater(details["max_abs_db_diff"], 1.0)

    def test_committed_baselines_match_their_pins(self):
        """The pinned baseline traces exist under this tree and still hash to
        the pinned prefixes (a moved or edited baseline fails here)."""
        for which in (c.BASELINE_DR0015, c.BASELINE_SAME_VINTAGE):
            path = os.path.join(HERE, which["trace"])
            self.assertTrue(os.path.isfile(path),
                            f"committed baseline trace missing: {path}")
            self.assertEqual(c._sha256_16(path), which["trace_sha256_16"],
                             f"baseline trace moved: {path}")


class MetricsWiring(unittest.TestCase):
    def test_reduce_row_carries_metrics_and_dr0014_reading(self):
        """AC 3's wiring: the row carries the extractor's metrics (first 0 dB
        crossing + the worst-crossing phase + the crossing count) and the
        UNCHANGED DR-0014 classification -- never a hand-read verdict."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _trace_fixture(os.path.join(tmp, "t_ac.csv"), f_ug=1.05e6)
            row = _row_for(p, "2x")
            cls = am.classify_margins(p)
        self.assertEqual(row["point_id"], c.point_id("2x"))
        self.assertEqual(row["cc_label"], "2x")
        self.assertEqual(row["n_0db_crossings"], 1)
        self.assertAlmostEqual(row["unity_gain_freq_hz"], 1.05e6, delta=2e3)
        self.assertAlmostEqual(row["phase_margin_deg"], 45.0, delta=0.1)
        # the verdict must be the committed reading of the SAME trace
        # (ac_metrics.classify_margins), not a hand-read one
        self.assertEqual(row["dr0014_pm_verdict"], cls["pm"]["verdict"])
        self.assertEqual(row["dr0014_gm_verdict"], cls["gm"]["verdict"])
        self.assertEqual(row["dr0014_nyquist_class"], cls["nyquist"]["class"])
        self.assertAlmostEqual(row["dr0014_gm_value_db"],
                               cls["gm"]["value_db"], places=6)

    def test_reduce_row_keys_are_never_silently_dropped(self):
        """The CSV writer ignores unknown keys, so every key reduce_point
        emits must be a declared CSV field (a new field must widen
        CSV_FIELDS, not vanish from the record)."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _trace_fixture(os.path.join(tmp, "t_ac.csv"))
            row = _row_for(p, "1x")
        # trace_path is host-absolute and intentionally not a record column
        # (it would make the committed record checkout-path-bound).
        self.assertNotIn("trace_path", c.CSV_FIELDS)
        undeclared = set(row) - set(c.CSV_FIELDS) - {"trace_path"}
        self.assertFalse(undeclared, f"undeclared row keys: {undeclared}")

    def test_cmd_reduce_adds_the_comparison_columns(self):
        """cmd_reduce's added columns (the AC 4 comparisons) are declared
        too, so the 1x row survives the CSV round-trip."""
        for k in ("lfl_ok", "lfl_reasons", "lfl_max_abs_db_diff",
                  "vs_samev_f_ug_delta_hz", "vs_samev_pm_delta_deg",
                  "vs_samev_gm_delta_db", "vs_dr0015_f_ug_delta_hz",
                  "vs_dr0015_pm_delta_deg", "vs_dr0015_gm_delta_db"):
            self.assertIn(k, c.CSV_FIELDS)


class DeckContract(unittest.TestCase):
    """The pinned loop-gain template must still carry every placeholder the
    driver renders (a template edit that drops one silently breaks the
    campaign's decks)."""

    def test_placeholders_present(self):
        with open(os.path.join(HERE, "testbench",
                               "tb_loopgain_cmos5l.spice.tmpl"),
                  encoding="utf-8") as fh:
            tmpl = fh.read()
        for ph in ("@@CC_W@@", "@@DESIGN_NETLIST@@", "@@LG_AC_MAX@@",
                   "@@AC_CSV@@", "@@LOAD_A@@", "@@COUT_F@@",
                   "@@COUT_BOTTOM@@", "@@ESR_LINE@@", "@@MOS_SECTION@@",
                   "@@RES_SECTION@@", "@@CAP_SECTION@@", "@@TEMP@@",
                   "@@PDK_ROOT@@", "@@PDK@@", "@@OSDI_DIR@@"):
            self.assertIn(ph, tmpl, f"template lost placeholder {ph}")
        self.assertIn("ac dec 20 1 @@LG_AC_MAX@@", tmpl)
        self.assertIn('.include "@@DESIGN_NETLIST@@"', tmpl)

    def test_campaign_uses_the_single_injection_loopgain_bench(self):
        """E3 reuses the committed single-injection bench -- no new template,
        so the bench the fleet runs is the one every committed loop-gain
        record was made with."""
        self.assertFalse(os.path.exists(
            os.path.join(HERE, "testbench", "tb_ccprobe_cmos5l.spice.tmpl")),
            "E3 must reuse tb_loopgain_cmos5l.spice.tmpl, not a new bench")


if __name__ == "__main__":
    unittest.main()
