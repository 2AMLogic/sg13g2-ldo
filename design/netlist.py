#!/usr/bin/env python3
"""Export ngspice netlists from this repo's xschem sources (issue #6,
T1 item 1: design sources; extended for the SG13CMOS5L branch by issue #20).

    python3 design/netlist.py            # regenerate design/netlist/*.spice
    python3 design/netlist.py --check    # verify committed netlists are current
    python3 design/netlist.py --cell ldo_erramp_placeholder -v

    # the SG13CMOS5L branch (design/sg13cmos5l/, issue #20):
    python3 design/netlist.py --design sg13cmos5l
    python3 design/netlist.py --design sg13cmos5l --check -v

There are two **designs** (see ``DESIGNS`` below), one per PDK branch: the
original ``sg13g2`` design in ``design/`` and the ``sg13cmos5l`` design in
``design/sg13cmos5l/``. A design bundles its source directory, its top
cell, that top cell's expected port list, and the PDK variant it must be
netlisted against -- so ``--design`` is the only flag needed to switch
branches, and neither branch can be netlisted against the other's PDK by
accident. ``--design sg13g2`` is the default, so every pre-#20 invocation
(including ``.github/workflows/ci.yml``'s) behaves exactly as before.

Every ``<design dir>/*.sch`` cell netlists **as a ``.subckt``** (never a
flat deck), with xschem's electrical rule check enabled (``xschem netlist
-erc``), into ``<design dir>/netlist/<cell>.spice``:

* ``ldo_core.spice`` carries the whole hierarchy -- ``ldo_core`` plus every
  sub-circuit it instantiates (currently just ``ldo_erramp_placeholder``).
* ``ldo_erramp_placeholder.spice`` is that sub-circuit on its own, so a
  future amp-only testbench can target it in isolation.

...and correspondingly ``ldo_core_cmos5l.spice`` /
``ldo_erramp_cmos5l.spice`` for the SG13CMOS5L design.

The export is deterministic: absolute paths xschem records in ``sch_path``/
``sym_path`` comments are rewritten repo-relative, so the same sources
produce byte-identical netlists on any machine. ``--check`` re-runs the
export into a temporary directory and diffs it against what is committed;
it fails if the committed netlists are stale, if the export is not
reproducible, if xschem's own ERC reports a problem, or if the pinout/
port-order invariants below are broken.

This repo has no ``sim/`` harness yet (this issue is T1 item 1 only --
schematic sources and their netlist, not verification; ``sim/`` stays an
empty placeholder), so PDK discovery and the xschem invocation are
self-contained in this one file rather than imported from a shared module,
unlike 2AMLogic/gf180-ldo's ``design/netlist.py``, which delegates both to
``sim/harness/pdk.py`` and ``sim/harness/xschem_export.py``. The
control-flow *pattern* here (export, ERC-failure detection by scraping
xschem's own stdout/stderr since a clean run prints nothing but a broken
one does not reliably signal failure through the exit code alone across
xschem versions, path normalization, --check diff mode, pinout invariants)
is adapted from that file -- this is infrastructure/tooling, not circuit
content, and is explicitly not covered by this issue's clean-room mandate
on the schematic itself (see design/ldo_core.sch's own header note and
design/README.md). The SG13G2 PDK-discovery search order below instead
matches this fleet's own sg13g2-bandgap/sg13g2-pll ``sim/env.sh`` and
``design/xschemrc`` convention (``PDK_ROOT``/``PDK`` env vars, then the
usual open_pdks-shaped search roots), so every SG13G2 canary in the fleet
agrees on how the PDK is found.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

DESIGN_DIR = Path(__file__).resolve().parent
REPO_ROOT = DESIGN_DIR.parent
XSCHEMRC = DESIGN_DIR / "xschemrc"

DEFAULT_VARIANT = "ihp-sg13g2"

# Search roots used when PDK_ROOT is not set, in the same order
# design/xschemrc and this fleet's sg13g2-bandgap/sg13g2-pll sim/env.sh
# already use, so every tool in the repo (and across the fleet) agrees.
BUILTIN_SEARCH_ROOTS = (
    "/usr/share/pdk",
    "/usr/local/share/pdk",
    "~/share/pdk",
    "~/.ciel",
    "~/.volare",
)

INSTALL_HINT = """\
PDK not found.

Fetch the pinned IHP-Open-PDK release (see spec/porting-plan.md's "Sources
and their limits" for the pinned v0.3.0 tag/checksum this repo targets),
e.g. via klayout-tools' scripts/fetch-ihp-sg13g2.sh, then either:

    export PDK_ROOT=/path/to/pdk-root PDK=ihp-sg13g2   # pdk-root/ihp-sg13g2/libs.tech/...

NOTE for the SG13CMOS5L branch (--design sg13cmos5l): ihp-sg13cmos5l's MOS
symbols and HV model cards are *relative symlinks* into a sibling
ihp-sg13g2 checkout, so an ihp-sg13cmos5l-only install has them dangling
and a missing device will look like a missing symbol rather than a missing
sibling PDK. Install both variants under the same PDK_ROOT. See
spec/decision-records/DR-0002-sg13cmos5l-device-topology.md, "Dispatch
hazard carried forward" (2AMLogic/2am#544).

...or install it under one of the usual open_pdks-shaped search roots this
script already checks: /usr/share/pdk, /usr/local/share/pdk, ~/share/pdk,
~/.ciel, ~/.volare.
"""

SUBCKT_RE = re.compile(r"^\.subckt\s+(\S+)\s*(.*)$", re.IGNORECASE)
SYM_PIN_RE = re.compile(r"^B\s+\d+\s+\S+\s+\S+\s+\S+\s+\S+\s*\{(.*)\}\s*$")
SCH_PIN_RE = re.compile(r"^C\s+\{(?:i|o|io)pin\.sym\}\s+.*?\{(.*)\}\s*$")

# xschem exits 0 in some versions even when its own ERC/connectivity checks
# fail (they are printed, not always reflected in the exit code), so grep
# stdout+stderr for the failure classes it emits during netlisting:
# undriven/floating nodes, shorted nodes/pins, and missing symbols (a
# silently-unresolved reference nets everything under an auto-generated
# name instead of erroring).
ERC_FAILURE_RE = re.compile(
    r"(undriven node|open net|shorted output node|instance pin shorted|"
    r"symbol not found|IS MISSING)",
    re.IGNORECASE,
)


class PdkNotFound(RuntimeError):
    """Raised when no usable PDK install can be located."""


class ExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class Design:
    """One PDK branch's schematic sources, as a self-contained unit.

    ``dir`` holds the ``.sch``/``.sym`` pairs and gets a ``netlist/``
    subdirectory; ``top_cell`` is the cell whose hierarchy carries
    everything else; ``expected_top_ports`` is the interface invariant
    ``--check`` enforces; ``variant`` is the PDK directory name this
    design's symbols resolve against (``sg13g2_pr/`` vs
    ``sg13cmos5l_pr/`` references are not interchangeable, so the variant
    belongs to the design, not to the invocation).
    """

    name: str
    dir: Path
    top_cell: str
    expected_top_ports: list[str]
    variant: str

    @property
    def netlist_dir(self) -> Path:
        return self.dir / "netlist"

    def sch(self, cell: str) -> Path:
        return self.dir / f"{cell}.sch"

    def sym(self, cell: str) -> Path:
        return self.dir / f"{cell}.sym"


# The interfaces issues #6 (sg13g2) and #20 (sg13cmos5l) establish. Not a
# "ratified spec" claim (no spec/target-spec.md exists yet -- see
# design/README.md) -- but a change here is a deliberate interface change,
# not an accidental one, and this check is what makes that true.
DESIGNS: dict[str, Design] = {
    "sg13g2": Design(
        name="sg13g2",
        dir=DESIGN_DIR,
        top_cell="ldo_core",
        expected_top_ports=["VIN", "VOUT", "VSS", "VREF"],
        variant="ihp-sg13g2",
    ),
    # Issue #20, phase 2/4 of the SG13CMOS5L port (#12). IBIAS is the one
    # added port: the real two-stage OTA that replaces the SG13G2 branch's
    # ideal-VCVS placeholder needs a bias reference, and
    # spec/decision-records/DR-0002-sg13cmos5l-device-topology.md leaves
    # the bias scheme to this phase. See design/README.md.
    "sg13cmos5l": Design(
        name="sg13cmos5l",
        dir=DESIGN_DIR / "sg13cmos5l",
        top_cell="ldo_core_cmos5l",
        expected_top_ports=["VIN", "VOUT", "VSS", "VREF", "IBIAS"],
        variant="ihp-sg13cmos5l",
    ),
}

DEFAULT_DESIGN = "sg13g2"


@dataclass(frozen=True)
class Pdk:
    root: Path       # the search root (contains the variant dir)
    variant: str      # ihp-sg13g2
    source: str       # how we found it (for provenance)

    @property
    def path(self) -> Path:
        return self.root / self.variant

    @property
    def xschem_dir(self) -> Path:
        return self.path / "libs.tech" / "xschem"

    @property
    def ngspice_dir(self) -> Path:
        return self.path / "libs.tech" / "ngspice"


def _expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path)))


def _is_valid_variant_dir(path: Path) -> bool:
    return (path / "libs.tech" / "ngspice").is_dir() and (
        path / "libs.tech" / "xschem"
    ).is_dir()


def find_pdk(variant: str | None = None) -> Pdk:
    """Locate a PDK install for ``variant``, or raise :class:`PdkNotFound`.

    ``variant`` comes from the selected :class:`Design` (or ``--pdk-variant``)
    and is authoritative when given -- a design's symbols reference a
    specific ``<variant>_pr/`` library, so the environment must not be able
    to silently swap it. ``PDK``/``PDK_ROOT`` in the environment still pick
    the *install root*, and ``PDK`` still supplies the variant for a bare
    call with no design selected.
    """
    variant = variant or os.environ.get("PDK") or DEFAULT_VARIANT

    tried: list[str] = []

    pdk_root = os.environ.get("PDK_ROOT")
    if pdk_root:
        root = _expand(pdk_root)
        path = root / variant
        tried.append(str(path))
        if _is_valid_variant_dir(path):
            return Pdk(root=root, variant=variant, source="PDK_ROOT")

    for candidate in BUILTIN_SEARCH_ROOTS:
        root = _expand(candidate)
        path = root / variant
        tried.append(str(path))
        if _is_valid_variant_dir(path):
            return Pdk(root=root, variant=variant, source=f"search_root:{candidate}")

    raise PdkNotFound(
        "Looked for PDK variant %r in:\n  %s\n\n%s"
        % (variant, "\n  ".join(tried), INSTALL_HINT)
    )


def cells(design: Design) -> list[str]:
    """All cells in the design dir, top level first then the rest alphabetically."""
    names = sorted(p.stem for p in design.dir.glob("*.sch"))
    if design.top_cell not in names:
        raise ExportError(f"{design.sch(design.top_cell)} is missing")
    return [design.top_cell] + [n for n in names if n != design.top_cell]


def xschem_env(pdk: Pdk, design: Design) -> dict[str, str]:
    env = dict(os.environ)
    env["PDK_ROOT"] = str(pdk.root)
    env["PDK"] = pdk.variant
    env["XSCHEM_USER_LIBRARY_PATH"] = str(design.dir)
    return env


def normalize(text: str) -> str:
    """Make xschem output machine-independent (and therefore diffable)."""
    text = text.replace(str(REPO_ROOT) + os.sep, "")
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.rstrip("\n") + "\n"


def run_xschem_netlist(sch: Path, outdir: Path, env: dict[str, str]) -> str:
    """Run xschem headless (batch, ERC on) on ``sch``, return normalized netlist text."""
    if not sch.is_file():
        raise ExportError(f"no such cell: {sch}")
    cmd = [
        "xschem",
        "-x",  # no X11: batch
        "-q",  # quit when done
        "-r",  # no tclreadline (stdin/stdout may be redirected)
        "--rcfile", str(XSCHEMRC),
        "-o", str(outdir),
        str(sch),
        "--command", "xschem netlist -erc",
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    produced = outdir / f"{sch.stem}.spice"
    noisy = proc.stdout + proc.stderr
    erc_problem = ERC_FAILURE_RE.search(noisy)
    if proc.returncode != 0 or not produced.is_file() or erc_problem:
        raise ExportError(
            f"xschem failed for {sch.stem} (exit {proc.returncode})\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    header = (
        f"* {sch.stem} -- generated by design/netlist.py from "
        f"{sch.relative_to(REPO_ROOT)}\n"
        f"* Do not edit: edit the schematic and re-run the export.\n"
    )
    return header + normalize(produced.read_text())


def symbol_pins(design: Design, cell: str) -> list[str] | None:
    """Pin names, in order, from <design>/<cell>.sym (None if there is no symbol)."""
    sym = design.sym(cell)
    if not sym.is_file():
        return None
    pins: list[str] = []
    for line in sym.read_text().splitlines():
        match = SYM_PIN_RE.match(line)
        if not match:
            continue
        attrs = match.group(1)
        name = re.search(r"\bname=(\S+)", attrs)
        if name:
            pins.append(name.group(1))
    return pins


def schematic_ports(design: Design, cell: str) -> list[str]:
    """Port names, in order, from the ipin/opin/iopin instances in <cell>.sch."""
    ports: list[str] = []
    for line in design.sch(cell).read_text().splitlines():
        match = SCH_PIN_RE.match(line)
        if not match:
            continue
        lab = re.search(r"\blab=(\S+)", match.group(1))
        if lab:
            ports.append(lab.group(1))
    return ports


def subckt_ports(netlist: str, cell: str) -> list[str]:
    for line in netlist.splitlines():
        match = SUBCKT_RE.match(line.strip())
        if match and match.group(1) == cell:
            return match.group(2).split()
    raise ExportError(f".subckt {cell} not found in its own netlist")


def instance_lines(netlist: str, cell: str) -> list[list[str]]:
    """Instance lines of `cell` inside the top-level .subckt block."""
    found = []
    for line in netlist.splitlines():
        tokens = line.split()
        if len(tokens) >= 2 and tokens[0].lower().startswith("x") and tokens[-1] == cell:
            found.append(tokens)
    return found


def check_invariants(design: Design, netlists: dict[str, str]) -> list[str]:
    """Pinout / port-order invariants. Returns a list of failure messages."""
    failures: list[str] = []
    top_cell = design.top_cell

    top_ports = subckt_ports(netlists[top_cell], top_cell)
    if top_ports != design.expected_top_ports:
        failures.append(
            f"{design.name}: top-level pinout drifted from the established "
            f"interface:\n"
            f"    expected: {design.expected_top_ports}\n"
            f"    netlist:  {top_ports}\n"
            f"  (see design/README.md and DESIGNS in this file)"
        )

    for cell, netlist in netlists.items():
        ports = subckt_ports(netlist, cell)
        pins = symbol_pins(design, cell)
        if pins is None:
            failures.append(
                f"{cell}: no {design.sym(cell).relative_to(REPO_ROOT)} -- "
                f"cell is not instantiable"
            )
            continue
        sch_pins = schematic_ports(design, cell)
        if pins != sch_pins:
            failures.append(
                f"{cell}: symbol pins and schematic ports disagree.\n"
                f"    {cell}.sym:  {pins}\n"
                f"    {cell}.sch:  {sch_pins}\n"
                f"  xschem netlists the ports from the symbol, so this silently\n"
                f"  miswires or drops a port on every instantiation of the cell."
            )
        if pins != ports:
            failures.append(
                f"{cell}: symbol pin order does not match the exported .subckt.\n"
                f"    {cell}.sym:  {pins}\n"
                f"    .subckt:    {ports}"
            )

    top = netlists[top_cell]
    for cell in netlists:
        if cell == top_cell:
            continue
        instances = instance_lines(top, cell)
        if not instances:
            failures.append(f"{cell}: not instantiated in {top_cell}")
            continue
        width = len(subckt_ports(netlists[cell], cell))
        for tokens in instances:
            nets = tokens[1:-1]
            if len(nets) != width:
                failures.append(
                    f"{top_cell}: instance {tokens[0]} of {cell} connects "
                    f"{len(nets)} nets, but {cell} has {width} ports"
                )
    return failures


def run(
    design: Design,
    check: bool,
    only: str | None,
    verbose: bool,
    variant: str | None = None,
) -> int:
    try:
        pdk = find_pdk(variant or design.variant)
    except PdkNotFound as exc:
        print(f"design/netlist.py: {exc}", file=sys.stderr)
        return 2
    env = xschem_env(pdk, design)

    wanted = [only] if only else cells(design)
    netlists: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="sg13g2-ldo-netlist-") as tmp:
        outdir = Path(tmp)
        for cell in wanted:
            sch = design.sch(cell)
            netlists[cell] = run_xschem_netlist(sch, outdir, env)
            if verbose:
                print(f"  netlisted {cell} (PDK: {pdk.path}, via {pdk.source})")

    if only:
        # A single-cell run cannot evaluate the cross-cell invariants.
        failures: list[str] = []
    else:
        failures = check_invariants(design, netlists)

    status = 0
    if check:
        for cell, text in netlists.items():
            committed = design.netlist_dir / f"{cell}.spice"
            if not committed.is_file():
                failures.append(f"{committed.relative_to(REPO_ROOT)} is missing")
                continue
            have = committed.read_text()
            if have != text:
                diff = "\n".join(
                    difflib.unified_diff(
                        have.splitlines(),
                        text.splitlines(),
                        fromfile=f"committed/{cell}.spice",
                        tofile=f"regenerated/{cell}.spice",
                        lineterm="",
                    )
                )
                failures.append(
                    f"{cell}: committed netlist is stale or the export is not "
                    f"reproducible:\n{diff}"
                )
    else:
        design.netlist_dir.mkdir(parents=True, exist_ok=True)
        for cell, text in netlists.items():
            target = design.netlist_dir / f"{cell}.spice"
            target.write_text(text)
            print(f"wrote {target.relative_to(REPO_ROOT)}")

    if failures:
        print("\nFAIL:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        status = 1
    elif check:
        print(
            f"OK: {len(netlists)} netlist(s) reproduce byte-for-byte, ERC is clean, "
            f"and the pinout invariants hold."
        )
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export ngspice netlists from this repo's xschem sources.",
    )
    parser.add_argument(
        "--design",
        choices=sorted(DESIGNS),
        default=DEFAULT_DESIGN,
        help="which PDK branch to netlist: 'sg13g2' (design/, ihp-sg13g2) or "
             "'sg13cmos5l' (design/sg13cmos5l/, ihp-sg13cmos5l). "
             f"Default: {DEFAULT_DESIGN}.",
    )
    parser.add_argument(
        "--pdk-variant",
        help="override the PDK variant directory the selected design is "
             "netlisted against (escape hatch for a non-standard install; "
             "the design's own variant is used by default)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; verify the committed netlists are current and the "
             "pinout invariants hold",
    )
    parser.add_argument(
        "--cell",
        help="export a single cell (skips the cross-cell invariant checks)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run(
            design=DESIGNS[args.design],
            check=args.check,
            only=args.cell,
            verbose=args.verbose,
            variant=args.pdk_variant,
        )
    except ExportError as exc:
        print(f"design/netlist.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
