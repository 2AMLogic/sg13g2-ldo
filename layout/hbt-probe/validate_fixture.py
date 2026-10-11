#!/usr/bin/env python3
"""Fixture validator for the layout/hbt-probe vendor witness (issue #150).

The vendored `npn13G2.gds` / `npn13G2.cdl` pair is the IHP-Open-PDK LVS unit
fixture for the `npn13G2` HBT, byte-identical to upstream
IHP-GmbH/IHP-Open-PDK commit `5e6d592e4002946a4616f798c357f0f3c06cf3b6`
(`ihp-sg13g2/libs.tech/klayout/tech/lvs/testing/testcases/unit/bjt_devices/`).
Its content contract — verified here so a malformed input can never masquerade
as an upstream extraction gap:

  GDS: exactly one cell, named `npn13G2`, DBU 0.001 um, nonempty bounding box
       `(-11650,-27234; 25050,3780)` DBU.
  CDL: one `.SUBCKT npn13G2` block carrying exactly three four-terminal
       `Q<C> <C> <B> <E> sub! npn13G2 le=900.0n we=70.00n m=<1|2|4>` cards —
       collector/base/emitter plus the distinct `sub!` substrate node, and
       multiplicities 1/2/4.

The GDS half needs `klayout.db`; the CDL half is plain text. `hbt_probe.py`
runs the full validator in `--record`/`--run`; the stdlib-only `--check` mode
instead pins the fixture bytes by sha256 and checks the CDL text directly.

Standalone use (needs the klayout Python module):

    python3 validate_fixture.py [DIR]   # DIR defaults to this script's dir
"""

from __future__ import annotations

import pathlib
import re
import sys

TOP = "npn13G2"
DBU_UM = 0.001
BBOX_DBU = (-11650, -27234, 25050, 3780)
MODEL = "npn13G2"
MULTIPLICITIES = (1, 2, 4)

_Q_RE = re.compile(
    r"^(?P<name>Q\d+)\s+(?P<c>\S+)\s+(?P<b>\S+)\s+(?P<e>\S+)\s+(?P<sub>\S+)\s+"
    r"(?P<model>\S+)\s+le=(?P<le>\S+)\s+we=(?P<we>\S+)\s+m=(?P<m>\d+)\s*$"
)


class FixtureError(Exception):
    """The vendored fixture does not meet its documented content contract."""


def _validate_gds(gds_path: pathlib.Path) -> None:
    try:
        import klayout.db as kdb
    except ImportError as e:  # pragma: no cover - environment error, not a fixture error
        raise FixtureError(
            f"the klayout Python module is required to validate {gds_path.name} "
            "(--check instead attests the fixture by its pinned sha256)"
        ) from e
    ly = kdb.Layout()
    try:
        ly.read(str(gds_path))
    except Exception as e:
        raise FixtureError(f"{gds_path.name}: not a readable GDS stream: {e}") from e
    tops = [c.name for c in ly.top_cells()]
    if tops != [TOP]:
        raise FixtureError(f"{gds_path.name}: top cell(s) {tops} != ['{TOP}']")
    cells = [c.name for c in ly.each_cell()]
    if cells != [TOP]:
        raise FixtureError(f"{gds_path.name}: expected the single vendor cell, got {cells}")
    if ly.dbu != DBU_UM:
        raise FixtureError(f"{gds_path.name}: DBU {ly.dbu} != {DBU_UM}")
    bbox = ly.top_cells()[0].bbox()
    got = (bbox.left, bbox.bottom, bbox.right, bbox.top)
    if got != BBOX_DBU:
        raise FixtureError(
            f"{gds_path.name}: bbox {got} DBU != documented {BBOX_DBU} DBU"
            " -- the fixture is not byte-identical to the pinned IHP source"
        )


def _validate_cdl(cdl_path: pathlib.Path) -> list[dict]:
    text = cdl_path.read_text(encoding="utf-8")
    body = None
    for m in re.finditer(
        r"^\s*\.SUBCKT\s+(?P<top>\S+)(?P<body>.*?)^\s*\.ENDS\s*$",
        text,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    ):
        if m.group("top").lower() == TOP.lower():
            if body is not None:
                raise FixtureError(f"{cdl_path.name}: multiple .SUBCKT {TOP} blocks")
            body = m.group("body")
    if body is None:
        raise FixtureError(f"{cdl_path.name}: no .SUBCKT {TOP} block")
    cards = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        m = _Q_RE.match(line)
        if not m:
            raise FixtureError(f"{cdl_path.name}: non-Q or malformed card in {TOP}: {line!r}")
        d = m.groupdict()
        if d["model"] != MODEL:
            raise FixtureError(f"{cdl_path.name}: card {d['name']} model {d['model']} != {MODEL}")
        if d["sub"] != "sub!":
            raise FixtureError(
                f"{cdl_path.name}: card {d['name']} substrate node {d['sub']!r} != 'sub!'"
            )
        if d["le"] != "900.0n" or d["we"] != "70.00n":
            raise FixtureError(
                f"{cdl_path.name}: card {d['name']} geometry le={d['le']} we={d['we']}"
                " != le=900.0n we=70.00n"
            )
        if int(d["m"]) not in MULTIPLICITIES:
            raise FixtureError(
                f"{cdl_path.name}: card {d['name']} multiplicity {d['m']} not in {MULTIPLICITIES}"
            )
        cards.append(
            {
                "name": d["name"],
                "terminals": [d["c"], d["b"], d["e"], d["sub"]],
                "le": d["le"],
                "we": d["we"],
                "m": int(d["m"]),
            }
        )
    if [c["m"] for c in cards] != list(MULTIPLICITIES):
        raise FixtureError(
            f"{cdl_path.name}: expected exactly {len(MULTIPLICITIES)} Q cards with"
            f" multiplicities {list(MULTIPLICITIES)}, got {[c['m'] for c in cards]}"
        )
    return cards


def validate(gds_path: pathlib.Path, cdl_path: pathlib.Path) -> list[dict]:
    """Validate both halves; return the parsed CDL Q cards on success."""
    _validate_gds(gds_path)
    return _validate_cdl(cdl_path)


def main(argv: list[str]) -> int:
    here = pathlib.Path(__file__).resolve().parent
    base = pathlib.Path(argv[1]).resolve() if len(argv) > 1 else here
    try:
        cards = validate(base / "npn13G2.gds", base / "npn13G2.cdl")
    except FixtureError as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    print(f"OK fixture contract holds: {TOP}, {len(cards)} Q cards, m={[c['m'] for c in cards]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
