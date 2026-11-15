"""Tests for sweep_report.py -- the post-processing that writes every recorded number.

Two layers, both offline and stdlib-only (no simulator, no PDK), so CI's
`unittest discover -s sim/ldo-cmos5l-pvt-sweep` collects them:

1. **Reproduction against landed records.** Every full-grid record in
   `records/` is regenerated from its OWN committed raw bench CSVs under
   `corners/<record-id>/` and byte-compared to the committed artifacts. The
   inputs are real ngspice `wrdata` exports and the expected outputs are
   artifacts that landed before this module existed, so nothing here is
   circular: the generator never meets its own output. This is the gate that
   makes the issue #223 extraction checkable -- a behaviour change anywhere in
   the aggregation shows up as a byte diff in a record.

2. **Unit tests for the artifact writers**, with the three shared parsers
   (`dc_metrics`, `loopgain_metrics`, `psrr_metrics`) stubbed out. Those
   parsers have their own suites (`test_dc_grid.py`, `test_ac_metrics.py`);
   what is exercised here is the half this module owns -- aggregation, the
   pass/fail flags, the delta arithmetic and the markdown.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import sweep_report as sr  # noqa: E402

RECORDS_DIR = os.path.join(HERE, "records")
CORNERS_DIR = os.path.join(HERE, "corners")

# The grid every landed full-grid record was run over.
STD_AXES = {
    "corners": ["tt", "ss", "ff", "sf", "fs"],
    "temps": ["-40", "27", "125"],
    "res_labels": ["typ", "bcs", "wcs"],
    "cc_tol_widths": ["85e-6", "110e-6", "130e-6", "170e-6", "220e-6",
                      "259e-6", "340e-6"],
    "cc_nominal_w": "170e-6",
}

# record id -> the baseline it was compared against, plus whether its
# committed markdown fragment is still byte-comparable.
GATED_RECORDS = {
    "20260917-023832-7061e8f": {
        "baseline": "20260916-210331-9d3ace1",
        # Its five CSVs reproduce byte-for-byte. Its markdown fragment does
        # not, and did not before issue #223 either: the spec table gained a
        # "DR-0007 status" column after this record landed, so the committed
        # fragment is one generator revision older than the current prose.
        # The numbers in it are unchanged -- only the table's shape moved.
        "md": False,
    },
    "20261010-025634-60a3e81": {"baseline": "20260917-023832-7061e8f", "md": True},
    "20261011-051956-eda9285": {"baseline": "20261010-025634-60a3e81", "md": True},
    "20261011-060305-bcc60e2": {"baseline": "20261010-025634-60a3e81", "md": True},
    "20261011-070111-5391c68": {"baseline": "20261010-025634-60a3e81", "md": True},
    "20261012-042925-c53f0177": {"baseline": "20261010-025634-60a3e81", "md": True},
    "20261012-060932-c53f0177": {"baseline": "20261010-025634-60a3e81", "md": True},
}

# Records this generator can no longer regenerate, with the reason. Not a
# waiver list to grow casually: a record lands here only when the generator
# has gained an artifact the record never had.
UNGATED_RECORDS = {
    "20260916-210331-9d3ace1":
        "predates the Cc value-tolerance sweep (issue #35 / DR-0005), so no "
        "`.cc-tolerance.csv` was ever written for it and its markdown "
        "fragment predates the labelled-baseline heading",
}

ARTIFACT_SUFFIXES = (".csv", ".sensitivity.csv", ".delta.csv",
                     ".cc-tolerance.csv", ".divider-attribution.csv")


def _link_corners(src, dst):
    """Mirror a committed corners directory with symlinks.

    The run writes `_dc_grid_errors.tsv` INTO its corners directory, so the
    reproduction must never be pointed at the committed tree. Symlinks keep
    the inputs byte-identical without copying ~10 MB per record.
    """
    os.mkdir(dst)
    for name in os.listdir(src):
        path = os.path.join(src, name)
        if os.path.isfile(path):
            os.symlink(path, os.path.join(dst, name))


def _regenerate(record_id, baseline_id, out_dir, axes=STD_AXES):
    """Run the module exactly as run_sweep.sh does, into `out_dir`."""
    cdir = os.path.join(out_dir, "corners")
    _link_corners(os.path.join(CORNERS_DIR, record_id), cdir)
    # _before_after_delta.md is an OUTPUT that also lives in corners/; drop
    # the symlink to the committed one so the run cannot write through it.
    os.remove(os.path.join(cdir, "_before_after_delta.md"))
    recs = os.path.join(out_dir, "records")
    os.mkdir(recs)
    argv = [
        "--corners-dir", cdir,
        "--csv-out", os.path.join(recs, f"{record_id}.csv"),
        "--sens-csv-out", os.path.join(recs, f"{record_id}.sensitivity.csv"),
        "--baseline-csv", os.path.join(RECORDS_DIR, f"{baseline_id}.csv"),
        "--delta-csv-out", os.path.join(recs, f"{record_id}.delta.csv"),
        "--cmp-md-out", os.path.join(cdir, "_before_after_delta.md"),
        "--cc-nominal-w", axes["cc_nominal_w"],
    ]
    for corner in axes["corners"]:
        argv += ["--corner", corner]
    for temp in axes["temps"]:
        argv += ["--temp", temp]
    for rlabel in axes["res_labels"]:
        argv += ["--res-label", rlabel]
    for width in axes["cc_tol_widths"]:
        argv += ["--cc-tol-width", width]
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        rc = sr.main(argv)
    return rc, recs, os.path.join(cdir, "_before_after_delta.md")


def _read(path):
    with open(path, "rb") as f:
        return f.read()


class LandedRecordsReproduce(unittest.TestCase):
    """The issue #223 extraction gate: raw committed data -> committed record."""

    def test_every_post_processed_record_is_gated_or_excluded(self):
        """A new record cannot land without joining the gate or stating why.

        Every record carrying a `.delta.csv` was written by this generator, so
        every one of them must be reproducible or explicitly accounted for.
        """
        found = sorted(
            name[:-len(".delta.csv")] for name in os.listdir(RECORDS_DIR)
            if name.endswith(".delta.csv"))
        self.assertTrue(found, "no post-processed record found to check")
        for record_id in found:
            with self.subTest(record_id):
                self.assertIn(
                    record_id, set(GATED_RECORDS) | set(UNGATED_RECORDS),
                    f"record {record_id} was written by sweep_report.py but is "
                    "neither byte-gated in GATED_RECORDS nor excluded with a "
                    "reason in UNGATED_RECORDS")
        self.assertEqual(set(GATED_RECORDS) & set(UNGATED_RECORDS), set())
        for record_id in UNGATED_RECORDS:
            self.assertIn(record_id, found, f"stale exclusion: {record_id}")

    def test_gated_records_have_their_inputs_committed(self):
        for record_id, spec in GATED_RECORDS.items():
            with self.subTest(record_id):
                self.assertTrue(os.path.isdir(os.path.join(CORNERS_DIR, record_id)))
                self.assertTrue(os.path.isfile(
                    os.path.join(RECORDS_DIR, f"{spec['baseline']}.csv")))

    def test_artifacts_reproduce_byte_for_byte(self):
        for record_id, spec in GATED_RECORDS.items():
            with self.subTest(record_id):
                tmp = tempfile.mkdtemp()
                try:
                    rc, recs, md = _regenerate(record_id, spec["baseline"], tmp)
                    self.assertEqual(rc, 0)
                    for suffix in ARTIFACT_SUFFIXES:
                        name = f"{record_id}{suffix}"
                        committed = os.path.join(RECORDS_DIR, name)
                        self.assertTrue(os.path.isfile(committed), name)
                        self.assertEqual(
                            _read(os.path.join(recs, name)), _read(committed),
                            f"{name} did not regenerate byte-for-byte from "
                            f"corners/{record_id}/")
                    if spec["md"]:
                        self.assertEqual(
                            _read(md),
                            _read(os.path.join(
                                CORNERS_DIR, record_id,
                                "_before_after_delta.md")),
                            f"corners/{record_id}/_before_after_delta.md did "
                            "not regenerate byte-for-byte")
                finally:
                    shutil.rmtree(tmp)

    def test_regenerated_fragment_is_what_the_record_md_inlines(self):
        """The fragment is pasted verbatim into the record, so reproducing it
        reproduces that section of the record itself."""
        for record_id, spec in GATED_RECORDS.items():
            if not spec["md"]:
                continue
            with self.subTest(record_id):
                tmp = tempfile.mkdtemp()
                try:
                    _, _, md = _regenerate(record_id, spec["baseline"], tmp)
                    with open(md) as f:
                        fragment = f.read()
                    with open(os.path.join(RECORDS_DIR, f"{record_id}.md")) as f:
                        self.assertIn(fragment, f.read())
                finally:
                    shutil.rmtree(tmp)


class StubbedParsers(unittest.TestCase):
    """Base class: the three shared parsers answer from a path->dict table."""

    def setUp(self):
        self.dc = {}
        self.lg = {}
        self.ps = {}
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        for name, table in (("dc_metrics", self.dc),
                            ("loopgain_metrics", self.lg),
                            ("psrr_metrics", self.ps)):
            original = getattr(sr, name)
            self.addCleanup(setattr, sr, name, original)
            setattr(sr, name, self._lookup(table))

    @staticmethod
    def _lookup(table):
        return lambda path: table.get(os.path.basename(path))

    def path(self, name):
        return os.path.join(self.tmp, name)


class WriteCsv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_none_becomes_empty_cell_and_extras_are_dropped(self):
        path = os.path.join(self.tmp, "o.csv")
        sr.write_csv(path, ["a", "b", "c"],
                     [{"a": 1, "b": None, "c": 3, "zzz": "dropped"},
                      {"a": 0}])
        with open(path, newline="") as f:
            self.assertEqual(f.read(), "a,b,c\r\n1,,3\r\n0,,\r\n")

    def test_missing_key_is_empty_not_the_string_none(self):
        path = os.path.join(self.tmp, "o.csv")
        sr.write_csv(path, ["a", "b"], [{"a": "x"}])
        with open(path) as f:
            self.assertNotIn("None", f.read())


class Fmt(unittest.TestCase):
    def test_missing_value_reads_n_a(self):
        self.assertEqual(sr.fmt(None, 1.0, 2), "n/a")
        self.assertEqual(sr.fmt(None, 1.0, 2, signed=True), "n/a")

    def test_scale_and_decimals(self):
        self.assertEqual(sr.fmt(1.2345e-5, 1e6, 3), "12.345")
        self.assertEqual(sr.fmt(48403.676411697685, 1e-3, 2), "48.40")

    def test_signed_keeps_the_sign_on_a_positive_delta(self):
        self.assertEqual(sr.fmt(2.5, 1.0, 2, signed=True), "+2.50")
        self.assertEqual(sr.fmt(-2.5, 1.0, 2, signed=True), "-2.50")
        self.assertEqual(sr.fmt(0.0, 1.0, 2, signed=True), "+0.00")


class DerivedPaths(unittest.TestCase):
    def test_cc_tolerance_csv_sits_beside_the_main_csv(self):
        self.assertEqual(sr.cctol_csv_path("records/20261012-060932.csv"),
                         "records/20261012-060932.cc-tolerance.csv")

    def test_attribution_csv_sits_beside_the_delta_csv(self):
        self.assertEqual(sr.attr_csv_path("records/20261012-060932.delta.csv"),
                         "records/20261012-060932.divider-attribution.csv")


class MainRecordArtifact(StubbedParsers):
    def test_one_row_per_grid_point_in_axis_order(self):
        rows, errors = sr.collect_main_rows(self.tmp, ["tt", "ss"],
                                            ["27", "125"], ["typ", "bcs"])
        self.assertEqual(errors, {})
        self.assertEqual(
            [(r["corner"], r["temp_c"], r["res_section"]) for r in rows],
            [("tt", "27", "res_typ"), ("tt", "27", "res_bcs"),
             ("tt", "125", "res_typ"), ("tt", "125", "res_bcs"),
             ("ss", "27", "res_typ"), ("ss", "27", "res_bcs"),
             ("ss", "125", "res_typ"), ("ss", "125", "res_bcs")])

    def test_metrics_from_all_three_benches_merge_into_one_row(self):
        self.dc["dcsweep_tt_27c_rtyp_dc.csv"] = {"iq_a": 1e-5,
                                                 "vout_at_vinmax_by_load": "bulky"}
        self.lg["loopgain_tt_27c_rtyp_ac.csv"] = {"phase_margin_deg": 61.0}
        self.ps["psrr_tt_27c_rtyp_ac.csv"] = {"psrr_db_1khz": 59.6}
        rows, _ = sr.collect_main_rows(self.tmp, ["tt"], ["27"], ["typ"])
        self.assertEqual(rows[0]["iq_a"], 1e-5)
        self.assertEqual(rows[0]["phase_margin_deg"], 61.0)
        self.assertEqual(rows[0]["psrr_db_1khz"], 59.6)

    def test_the_bulky_per_load_vector_is_never_carried_into_a_row(self):
        self.dc["dcsweep_tt_27c_rtyp_dc.csv"] = {"vout_at_vinmax_by_load": [1, 2]}
        rows, _ = sr.collect_main_rows(self.tmp, ["tt"], ["27"], ["typ"])
        self.assertNotIn("vout_at_vinmax_by_load", rows[0])

    def test_an_invalid_grid_contributes_no_metrics_and_keeps_its_reason(self):
        """Issue #120's contract: never a nearest-point numeric summary."""
        self.dc["dcsweep_tt_27c_rtyp_dc.csv"] = {"error": "truncated grid",
                                                 "iq_a": 999.0}
        self.lg["loopgain_tt_27c_rtyp_ac.csv"] = {"phase_margin_deg": 61.0}
        rows, errors = sr.collect_main_rows(self.tmp, ["tt"], ["27"], ["typ"])
        self.assertNotIn("iq_a", rows[0])
        self.assertEqual(rows[0]["phase_margin_deg"], 61.0)  # AC is unaffected
        self.assertEqual(errors, {"dcsweep_tt_27c_rtyp": "truncated grid"})

    def test_missing_bench_files_leave_the_cells_empty(self):
        rows, errors = sr.collect_main_rows(self.tmp, ["tt"], ["27"], ["typ"])
        self.assertEqual(errors, {})
        path = self.path("o.csv")
        sr.write_main_csv(path, rows)
        with open(path) as f:
            body = f.read().splitlines()
        self.assertEqual(body[0].split(",")[:3], ["corner", "temp_c", "res_section"])
        self.assertEqual(body[1], "tt,27,res_typ" + "," * (len(sr.MAIN_FIELDNAMES) - 3))


class DcGridErrorSidecar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_no_sidecar_when_every_grid_is_valid(self):
        self.assertIsNone(sr.write_dc_grid_errors(self.tmp, {}))
        self.assertEqual(os.listdir(self.tmp), [])

    def test_sidecar_and_stderr_line_per_invalid_grid(self):
        err = io.StringIO()
        with redirect_stderr(err):
            path = sr.write_dc_grid_errors(
                self.tmp, {"dcsweep_tt_27c_rtyp": "invalid DC grid: truncated"})
        self.assertEqual(os.path.basename(path), "_dc_grid_errors.tsv")
        with open(path) as f:
            self.assertEqual(f.read(),
                             "dcsweep_tt_27c_rtyp\tinvalid DC grid: truncated\n")
        # run_sweep.sh greps this exact prefix to fold the point into
        # failed_points.
        self.assertIn("run_sweep.sh: INVALID DC GRID dcsweep_tt_27c_rtyp: "
                      "invalid DC grid: truncated", err.getvalue())


class SensitivityArtifact(StubbedParsers):
    def test_cc_value_then_resistor_corner_points_in_order(self):
        rows = sr.collect_sens_rows(self.tmp)
        self.assertEqual([(r["sweep"], r["point"]) for r in rows],
                         [("cc_value", "0.5x"), ("cc_value", "1x"),
                          ("cc_value", "2x"), ("res_corner", "bcs"),
                          ("res_corner", "typ"), ("res_corner", "wcs")])

    def test_each_point_reads_its_own_loopgain_bench(self):
        self.lg["loopgain_ccsens_1x_tt_27c_ac.csv"] = {"phase_margin_deg": 61.0}
        self.lg["loopgain_ressens_wcs_tt_27c_ac.csv"] = {"phase_margin_deg": 58.0}
        rows = {(r["sweep"], r["point"]): r for r in sr.collect_sens_rows(self.tmp)}
        self.assertEqual(rows[("cc_value", "1x")]["phase_margin_deg"], 61.0)
        self.assertEqual(rows[("res_corner", "wcs")]["phase_margin_deg"], 58.0)
        self.assertNotIn("phase_margin_deg", rows[("cc_value", "2x")])


class CcToleranceArtifact(StubbedParsers):
    PASSING = {"phase_margin_deg": 60.0, "gain_margin_db": 20.0}
    PASSING_PSRR = {"psrr_db_1khz": 59.0, "psrr_db_100khz": 34.0}

    def _rows(self, lg, ps, width="170e-6", nominal=170e-6):
        for rlabel in ("bcs", "wcs"):
            self.lg[f"loopgain_cctol_{width}_ss_125c_r{rlabel}_ac.csv"] = dict(lg)
            self.ps[f"psrr_cctol_{width}_ss_125c_r{rlabel}_ac.csv"] = dict(ps)
        return sr.collect_cctol_rows(self.tmp, [width], nominal)

    def test_both_binding_sections_at_ss_125c(self):
        rows = self._rows(self.PASSING, self.PASSING_PSRR)
        self.assertEqual([(r["corner"], r["temp_c"], r["res_section"]) for r in rows],
                         [("ss", 125, "res_bcs"), ("ss", 125, "res_wcs")])

    def test_x_nominal_is_the_width_over_the_nominal(self):
        rows = self._rows(self.PASSING, self.PASSING_PSRR, width="85e-6")
        self.assertAlmostEqual(rows[0]["cc_x_nominal"], 0.5)

    def test_all_ok_only_when_every_spec_row_passes(self):
        rows = self._rows(self.PASSING, self.PASSING_PSRR)
        self.assertTrue(all(r["all_ok"] for r in rows))
        for key, failing in (("phase_margin_deg", 44.9),
                             ("gain_margin_db", 9.9)):
            with self.subTest(key):
                rows = self._rows(dict(self.PASSING, **{key: failing}),
                                  self.PASSING_PSRR)
                self.assertFalse(rows[0]["all_ok"])
                self.assertFalse(rows[0]["pm_ok" if key == "phase_margin_deg"
                                         else "gm_ok"])
        for key, failing, flag in (("psrr_db_1khz", 50.0, "psrr_1khz_ok"),
                                   ("psrr_db_100khz", 20.0, "psrr_100khz_ok")):
            with self.subTest(key):
                rows = self._rows(self.PASSING,
                                  dict(self.PASSING_PSRR, **{key: failing}))
                self.assertFalse(rows[0][flag], "the spec row is a strict >")
                self.assertFalse(rows[0]["all_ok"])

    def test_a_missing_metric_fails_its_flag_rather_than_raising(self):
        rows = self._rows({}, {})
        self.assertEqual(
            [rows[0][k] for k in ("pm_ok", "gm_ok", "psrr_1khz_ok",
                                  "psrr_100khz_ok", "all_ok")],
            [False] * 5)

    def test_a_width_failing_one_section_is_a_failing_width(self):
        rows = [{"cc_w": "85e-6", "all_ok": True},
                {"cc_w": "85e-6", "all_ok": False},
                {"cc_w": "170e-6", "all_ok": True},
                {"cc_w": "170e-6", "all_ok": True}]
        ok, bad = sr.cctol_widths_verdict(rows, ["85e-6", "170e-6"])
        self.assertEqual((ok, bad), (["170e-6"], ["85e-6"]))

    def test_a_width_with_no_rows_counts_as_passing_by_vacuous_truth(self):
        """Pins the inherited behaviour rather than an improvement on it.

        `all()` over an empty list is True, so a width present in the axis but
        absent from the rows is reported inside the tolerance window. It is
        unreachable as wired: `collect_cctol_rows` emits a row per binding
        section for every width it is given, and the markdown is rendered from
        that same width list, so `by_w` is never short a width. Changing it
        would be a behaviour change, which issue #223's extraction is not.
        """
        ok, bad = sr.cctol_widths_verdict([], ["85e-6"])
        self.assertEqual((ok, bad), (["85e-6"], []))

    def test_as_wired_every_width_in_the_axis_has_its_rows(self):
        """The precondition that makes the vacuous-truth case unreachable."""
        widths = ["85e-6", "170e-6"]
        rows = sr.collect_cctol_rows(self.tmp, widths, 170e-6)
        self.assertEqual(sorted({r["cc_w"] for r in rows}), sorted(widths))
        self.assertEqual(len(rows), len(widths) * len(sr.CCTOL_RES_LABELS))


class DeltaArtifact(unittest.TestCase):
    AFTER = [{"corner": "tt", "temp_c": "27", "res_section": "res_typ",
              "phase_margin_deg": 61.0, "iq_a": 1.1e-5}]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _baseline(self, text):
        path = os.path.join(self.tmp, "base.csv")
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_a_missing_baseline_file_gives_no_before_cells(self):
        self.assertEqual(sr.read_baseline(os.path.join(self.tmp, "nope.csv")), {})

    def test_unparseable_and_absent_columns_read_as_missing(self):
        path = self._baseline("corner,temp_c,res_section,phase_margin_deg\n"
                              "tt,27,res_typ,\n")
        row = sr.read_baseline(path)[("tt", "27", "res_typ")]
        self.assertIsNone(row["phase_margin_deg"])
        self.assertIsNone(row["iq_a"])  # column not in the baseline at all

    def test_a_sectionless_baseline_row_defaults_to_res_typ(self):
        """The #21/#25 records held the resistor axis at res_typ."""
        path = self._baseline("corner,temp_c,phase_margin_deg\ntt,27,55.0\n")
        self.assertEqual(list(sr.read_baseline(path)), [("tt", "27", "res_typ")])

    def test_delta_is_after_minus_before(self):
        path = self._baseline("corner,temp_c,res_section,phase_margin_deg\n"
                              "tt,27,res_typ,55.0\n")
        rows = sr.collect_delta_rows(sr.read_baseline(path),
                                     sr.index_after(self.AFTER),
                                     ["tt"], ["27"], ["typ"])
        pm = [r for r in rows if r["metric"] == "phase_margin_deg"][0]
        self.assertEqual((pm["before"], pm["after"]), (55.0, 61.0))
        self.assertAlmostEqual(pm["delta"], 6.0)

    def test_a_missing_before_cell_is_no_delta_never_a_zero_delta(self):
        rows = sr.collect_delta_rows({}, sr.index_after(self.AFTER),
                                     ["tt"], ["27"], ["typ"])
        pm = [r for r in rows if r["metric"] == "phase_margin_deg"][0]
        self.assertIsNone(pm["before"])
        self.assertIsNone(pm["delta"])
        self.assertEqual(sr.fmt(pm["delta"], 1.0, 2, signed=True), "n/a")

    def test_every_metric_appears_at_every_grid_point(self):
        rows = sr.collect_delta_rows({}, sr.index_after(self.AFTER),
                                     ["tt", "ss"], ["27", "125"], ["typ"])
        self.assertEqual(len(rows), 2 * 2 * 1 * len(sr.METRICS))

    def test_a_point_absent_from_this_run_still_gets_its_rows(self):
        rows = sr.collect_delta_rows({}, {}, ["tt"], ["27"], ["typ"])
        self.assertEqual(len(rows), len(sr.METRICS))
        self.assertTrue(all(r["after"] is None for r in rows))


class DividerAttributionArtifact(StubbedParsers):
    def test_delta_is_rhigh_minus_behavioural_per_key(self):
        self.lg["loopgain_divattr_tt_27c_rtyp_ac.csv"] = {
            "phase_margin_deg": 55.0, "gain_margin_db": 18.0, "dc_gain_db": 120.0}
        after = sr.index_after([{"corner": "tt", "temp_c": "27",
                                 "res_section": "res_typ",
                                 "phase_margin_deg": 61.0,
                                 "gain_margin_db": 20.0}])
        row = sr.collect_attr_rows(self.tmp, after, ["tt"], ["27"], ["typ"])[0]
        self.assertEqual(row["phase_margin_deg_behavioural_divider"], 55.0)
        self.assertEqual(row["phase_margin_deg_rhigh_divider"], 61.0)
        self.assertAlmostEqual(row["phase_margin_deg_divider_delta"], 6.0)
        # dc_gain_db has a behavioural side but no rhigh side -> no delta.
        self.assertEqual(row["dc_gain_db_behavioural_divider"], 120.0)
        self.assertIsNone(row["dc_gain_db_rhigh_divider"])
        self.assertIsNone(row["dc_gain_db_divider_delta"])

    def test_a_missing_behavioural_bench_yields_no_delta(self):
        after = sr.index_after([{"corner": "tt", "temp_c": "27",
                                 "res_section": "res_typ",
                                 "phase_margin_deg": 61.0}])
        row = sr.collect_attr_rows(self.tmp, after, ["tt"], ["27"], ["typ"])[0]
        self.assertIsNone(row["phase_margin_deg_behavioural_divider"])
        self.assertIsNone(row["phase_margin_deg_divider_delta"])


class MarkdownFragment(unittest.TestCase):
    def _render(self, writer, *args):
        buf = io.StringIO()
        writer(buf, *args)
        return buf.getvalue()

    def test_delta_table_reports_the_largest_absolute_change(self):
        rows = [{"corner": "tt", "temp_c": "27", "res_section": "res_typ",
                 "metric": "phase_margin_deg", "before": 55.0, "after": 61.0,
                 "delta": 6.0},
                {"corner": "ss", "temp_c": "125", "res_section": "res_bcs",
                 "metric": "phase_margin_deg", "before": 50.0, "after": 42.0,
                 "delta": -8.0}]
        out = self._render(sr._write_delta_tables, rows, "20261010-025634-60a3e81")
        self.assertIn("### Phase margin (deg)", out)
        self.assertIn("Largest change across all 2 compared points: "
                      "**-8.00 deg**", out)
        self.assertIn("before (`20261010-025634-60a3e81`)", out)
        self.assertIn("| `ss` / 125C / `res_bcs` | 50.00 | 42.00 | -8.00 |", out)

    def test_delta_table_omits_the_largest_change_line_when_nothing_compared(self):
        out = self._render(sr._write_delta_tables, [], "base")
        self.assertNotIn("Largest change", out)
        for _key, heading, unit, _s, _d, _h in sr.METRICS:
            self.assertIn(f"### {heading} ({unit})", out)

    def test_spec_section_marks_only_dropout_as_ratified(self):
        out = self._render(sr._write_spec_section, [], "records/x.csv")
        self.assertIn("| Dropout @ 50mA < 300 mV | ratified (gate) |", out)
        self.assertIn("| Phase margin >= 45 deg | Open (informational) |", out)

    def test_spec_section_states_a_clean_grid(self):
        rows = [{"corner": "tt", "temp_c": "27", "res_section": "res_typ",
                 "phase_margin_deg": 61.0}]
        out = self._render(sr._write_spec_section, rows, "records/x.csv")
        self.assertIn("| Phase margin >= 45 deg | Open (informational) | 1 | "
                      "**0** | -- |", out)
        self.assertIn("Every spec row above is met at every point in this grid.",
                      out)

    def test_spec_section_names_the_worst_failing_point(self):
        rows = [{"corner": "tt", "temp_c": "27", "res_section": "res_typ",
                 "phase_margin_deg": 44.0},
                {"corner": "ss", "temp_c": "125", "res_section": "res_bcs",
                 "phase_margin_deg": 40.28}]
        out = self._render(sr._write_spec_section, rows, "records/x.csv")
        self.assertIn("| Phase margin >= 45 deg | Open (informational) | 2 | "
                      "**2** | `ss`/125C/`res_bcs` = 40.28 deg |", out)
        self.assertIn("**Targets NOT met at every point in this grid", out)
        self.assertIn("- Phase margin >= 45 deg -- fails at 2 of 2 points; "
                      "worst `ss`/125C/`res_bcs` = 40.28 deg", out)
        self.assertIn("`records/x.csv`", out)

    def test_load_regulation_takes_its_worst_point_from_the_high_end(self):
        """Every other spec row is a lower bound or a ceiling whose worst case
        is the minimum; load regulation's worst case is the maximum."""
        rows = [{"corner": "tt", "temp_c": "27", "res_section": "res_typ",
                 "load_reg_pct": 1.5},
                {"corner": "ss", "temp_c": "125", "res_section": "res_bcs",
                 "load_reg_pct": 9.0}]
        out = self._render(sr._write_spec_section, rows, "records/x.csv")
        self.assertIn("worst `ss`/125C/`res_bcs` = 9.0000 %", out)

    def test_points_with_no_value_are_not_counted_as_evaluated(self):
        rows = [{"corner": "tt", "temp_c": "27", "res_section": "res_typ"}]
        out = self._render(sr._write_spec_section, rows, "records/x.csv")
        self.assertIn("| Phase margin >= 45 deg | Open (informational) | 0 | "
                      "**0** | -- |", out)

    def test_cctol_section_reports_the_window_and_its_failing_ends(self):
        rows = [{"cc_w": "85e-6", "cc_x_nominal": 0.5, "res_section": "res_bcs",
                 "phase_margin_deg": 40.29, "gain_margin_db": 29.66,
                 "psrr_db_1khz": 59.61, "psrr_db_100khz": 33.67,
                 "all_ok": False},
                {"cc_w": "170e-6", "cc_x_nominal": 1.0, "res_section": "res_bcs",
                 "phase_margin_deg": 60.0, "gain_margin_db": 20.0,
                 "psrr_db_1khz": 59.0, "psrr_db_100khz": 34.0,
                 "all_ok": True}]
        out = self._render(sr._write_cctol_section, rows,
                           ["85e-6", "170e-6"], "170e-6", 170e-6,
                           "records/x.cc-tolerance.csv")
        self.assertIn("| `85e-6` | 0.50x | `res_bcs` | 40.29 | 29.66 | 59.61 "
                      "| 33.67 | **NO** |", out)
        self.assertIn("| `170e-6` | 1.00x | `res_bcs` | 60.00 | 20.00 | 59.00 "
                      "| 34.00 | yes |", out)
        self.assertIn("Every swept width from `170e-6` to `170e-6` meets every "
                      "spec row", out)
        self.assertIn("tolerates a MoM-cap value from x1.00 to x1.00", out)
        self.assertIn("Widths that do NOT hold every row at both binding "
                      "corners: `85e-6`", out)
        self.assertIn("`records/x.cc-tolerance.csv`", out)

    def test_cctol_section_omits_the_window_when_no_width_passes(self):
        rows = [{"cc_w": "85e-6", "cc_x_nominal": 0.5, "res_section": "res_bcs",
                 "all_ok": False}]
        out = self._render(sr._write_cctol_section, rows, ["85e-6"], "170e-6",
                           170e-6, "records/x.cc-tolerance.csv")
        self.assertNotIn("Every swept width from", out)
        self.assertIn("Widths that do NOT hold every row", out)

    def test_attribution_section_tabulates_the_divider_deltas(self):
        rows = [{"corner": "tt", "temp_c": "27", "res_section": "res_typ",
                 "phase_margin_deg_behavioural_divider": 55.0,
                 "phase_margin_deg_rhigh_divider": 61.0,
                 "phase_margin_deg_divider_delta": 6.0,
                 "gain_margin_db_divider_delta": -1.5,
                 "dc_gain_db_divider_delta": None}]
        out = self._render(sr._write_attribution_section, rows,
                           "records/x.divider-attribution.csv")
        self.assertIn("| `tt` / 27C / `res_typ` | 55.00 | 61.00 | +6.00 "
                      "| -1.50 | n/a |", out)
        self.assertIn("`records/x.divider-attribution.csv`", out)


class CommandLine(unittest.TestCase):
    REQUIRED = ["--corners-dir", "c", "--csv-out", "o.csv",
                "--sens-csv-out", "s.csv", "--baseline-csv", "b.csv",
                "--delta-csv-out", "d.delta.csv", "--cmp-md-out", "m.md",
                "--cc-nominal-w", "170e-6"]
    AXES = ["--corner", "tt", "--temp", "27", "--res-label", "typ"]

    def parse(self, extra=()):
        return sr.build_parser().parse_args(self.REQUIRED + self.AXES + list(extra))

    def test_axes_are_repeatable_and_keep_their_order(self):
        args = self.parse(["--corner", "ss", "--temp", "125",
                           "--res-label", "bcs"])
        self.assertEqual(args.corner, ["tt", "ss"])
        self.assertEqual(args.temp, ["27", "125"])
        self.assertEqual(args.res_label, ["typ", "bcs"])

    def test_a_negative_temperature_is_a_value_not_an_option(self):
        self.assertEqual(self.parse(["--temp", "-40"]).temp, ["27", "-40"])

    def test_the_cc_tolerance_sweep_is_optional(self):
        self.assertIsNone(self.parse().cc_tol_width)
        self.assertEqual(self.parse(["--cc-tol-width", "85e-6"]).cc_tol_width,
                         ["85e-6"])

    def test_a_missing_axis_is_a_usage_error_not_a_shifted_column(self):
        """The failure the 11 positional arguments could not catch."""
        for drop in ("--corner", "--temp", "--res-label"):
            with self.subTest(drop):
                argv = list(self.REQUIRED)
                for flag, value in zip(self.AXES[::2], self.AXES[1::2]):
                    if flag != drop:
                        argv += [flag, value]
                with self.assertRaises(SystemExit) as cm, \
                        redirect_stderr(io.StringIO()):
                    sr.build_parser().parse_args(argv)
                self.assertEqual(cm.exception.code, 2)

    def test_every_output_path_is_required(self):
        for drop in ("--corners-dir", "--csv-out", "--sens-csv-out",
                     "--baseline-csv", "--delta-csv-out", "--cmp-md-out",
                     "--cc-nominal-w"):
            with self.subTest(drop):
                argv = list(self.AXES)
                for flag, value in zip(self.REQUIRED[::2], self.REQUIRED[1::2]):
                    if flag != drop:
                        argv += [flag, value]
                with self.assertRaises(SystemExit) as cm, \
                        redirect_stderr(io.StringIO()):
                    sr.build_parser().parse_args(argv)
                self.assertEqual(cm.exception.code, 2)


class RunSweepWiring(unittest.TestCase):
    """run_sweep.sh must keep invoking the module it was extracted into."""

    def setUp(self):
        with open(os.path.join(HERE, "run_sweep.sh")) as f:
            self.sh = f.read()

    def test_the_heredoc_is_gone(self):
        self.assertNotIn("<<'PYEOF'", self.sh)

    def test_the_module_is_invoked_with_the_axis_flags(self):
        self.assertIn('python3 "${SCRIPT_DIR}/sweep_report.py"', self.sh)
        for flag in ("--corners-dir", "--csv-out", "--sens-csv-out",
                     "--baseline-csv", "--delta-csv-out", "--cmp-md-out",
                     "--cc-nominal-w"):
            self.assertIn(flag, self.sh, flag)
        for flag in ("--corner", "--temp", "--res-label", "--cc-tol-width"):
            self.assertIn(f'REPORT_AXES+=({flag} ', self.sh, flag)

    def test_the_sweep_script_dir_env_hack_is_gone_from_this_call(self):
        self.assertNotIn("SWEEP_SCRIPT_DIR", self.sh)

    def test_ci_discovers_this_directory(self):
        with open(os.path.join(HERE, "..", "..", ".github/workflows/ci.yml")) as f:
            self.assertIn(
                "python3 -m unittest discover -s sim/ldo-cmos5l-pvt-sweep "
                "-p 'test_*.py'", f.read())


if __name__ == "__main__":
    unittest.main()
