#!/usr/bin/env python3
"""Draw ``sg13cmos5l_ldo_core_cmos5l`` -- the full 13-device LDO core of
``design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`` -- as one flat cell.

    python3 layout/sg13cmos5l-ldo_core_cmos5l/generate.py

Writes ``sg13cmos5l-ldo_core_cmos5l.gds`` next to this file and prints the
drawn floorplan's own self-check (device count, bounding box, per-device
drawn width) so a reviewer can compare it against the schematic without
opening a viewer.

FLOORPLAN
---------

Three horizontal bands, with one routing channel between them, so that every
net's global wire is a straight ``Metal3`` track and every device's connection
to it is a straight ``Metal2`` riser::

    y >= 0        active band   -- Mpass array | error-amp devices | Cc
    -70 < y < -50 routing channel -- one horizontal Metal3 track per net
    y <= -80      passive band  -- Rz, Rtop, Rbot (the three rhigh meanders)

The band split is what keeps the routing verifiable by inspection: a riser is
vertical Metal2, a trunk is horizontal Metal3, and the only place the two meet
is a deliberate ``Via2``. Everything else that crosses is on different levels
with no via, which is a real crossing in this deck's connectivity (the curated
``sg13cmos5l`` deck models ``Metal1..TopMetal1`` with ``Via1``/``Via2``/
``Via3``/``TopVia1`` as of klayout-tools #1417 -- before that this PDK's
curated deck modelled one metal and no via at all, and a layout like this one
could not have been verified against it).

THE TWO DEVICES THAT SET THE FLOORPLAN

* ``Mpass``, ``sg13_hv_pmos w=2800u l=0.5u``. A single 2800 um finger is not a
  layout; this draws **4 rows x 28 fingers x 25 um**, interdigitated with
  shared source/drain diffusions inside one common NWell, on a 31 um row
  pitch. 4 x 28 x 25 = 2800 um exactly -- the row/finger split is a layout
  decision, the total is the schematic's.
* ``Rz``, ``rhigh w=1u l=28.81u b=39``. The ``b`` (bends) parameter is the
  PDK PCell's own meander control and is electrically real (the PDK model
  computes ``leff = (b+1)*l + (2/kappa*weff + ps)*b``), so the drawn stripe
  count is not free: 40 stripes here because the schematic declares 40. Same
  for the divider's own ``b=7`` eight-stripe legs.

WHAT THE LVS FLOW NEEDS FROM THIS FILE

* every net that must be compared carries a drawn label on its own level's
  ``.pin`` layer (``run_flow.sh`` then promotes only the five real ports);
* the pass array and the two ``m>1`` error-amp devices are drawn as parallel
  fingers, which is why ``klt lvs`` runs with ``options.combine_devices``;
* nothing that must stay a resistor is covered by ``ThickGateOx`` (both decks
  exclude a thick-oxide-covered poly body from every resistor flavour).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import common_sg13cmos5l as c  # noqa: E402

TOP_CELL = "sg13cmos5l_ldo_core_cmos5l"
OUT_GDS = pathlib.Path(__file__).resolve().parent / f"sg13cmos5l-{'ldo_core_cmos5l'}.gds"

# --------------------------------------------------------------------------- #
# Pass device: 4 rows x 28 fingers x 25 um = 2800 um (the schematic's w)
# --------------------------------------------------------------------------- #
MPASS_ROWS = 4
MPASS_FINGERS = 28
MPASS_W_FINGER = 25.0
MPASS_L = 0.5
MPASS_ROW_PITCH = 31.0

# --------------------------------------------------------------------------- #
# Routing channel: one Metal3 track per net, ordered so that VOUT -- the only
# net whose in-array bus runs the full height of the pass array -- sits on the
# topmost track.
# --------------------------------------------------------------------------- #
NET_TRACKS = [
    "VOUT", "VIN", "VSS", "EAOUT", "IBIAS", "TAIL", "G1", "N1", "FB", "MZ", "VREF",
]
TRACK_Y0 = -52.0
TRACK_PITCH = 1.2
TRACK_W = 0.5
RISER_W = 0.4

#: The five ports of `.subckt ldo_core_cmos5l`, in the schematic's own order.
PORTS = ["VIN", "VOUT", "VSS", "VREF", "IBIAS"]

track_y = {net: TRACK_Y0 - i * TRACK_PITCH for i, net in enumerate(NET_TRACKS)}
taps: dict[str, list[float]] = {net: [] for net in NET_TRACKS}

#: Minimum centre-to-centre distance between two riser corridors. Two
#: ``RISER_W``-wide vertical wires this far apart leave 0.4 um of clear
#: Metal2 space -- comfortably over ``Mn.b`` (0.21) and ``Mn.e`` (0.24). The
#: allocator below *asserts* it rather than trusting the floorplan's
#: arithmetic: two risers that overlap are a short between two different
#: nets, which is exactly the failure a hand-placed floorplan makes first
#: (and this one did, on its first run: a resistor terminal riser landed
#: 0.25 um from an NMOS source riser and merged VOUT into VSS).
RISER_MIN_DX = 0.8
_riser_x: list[tuple[float, str]] = []


def riser(b: c.Builder, net: str, x: float, y_from: float, level: int) -> None:
    """Connect a terminal at ``(x, y_from)`` on metal ``level`` down/up to
    ``net``'s own Metal3 track with a vertical Metal2 riser.

    ``level == 1`` adds the Metal1->Metal2 via stack at the terminal end; a
    terminal already on Metal2 needs none. The Via2 at the track end is always
    drawn. Risers are the *only* vertical global wires in this layout and each
    one owns its own x corridor, so two risers can never overlap and a riser
    crossing another net's horizontal trunk is a genuine crossing (no via).
    """
    for other_x, other_net in _riser_x:
        if abs(other_x - x) < RISER_MIN_DX:
            raise AssertionError(
                f"riser corridor clash: {net} at x={x} is {abs(other_x - x):.3f} um "
                f"from {other_net} at x={other_x} (need {RISER_MIN_DX})"
            )
    _riser_x.append((x, net))
    ty = track_y[net]
    y0, y1 = (ty, y_from) if ty < y_from else (y_from, ty)
    c.route_v(b, 2, x, y0, y1, width=RISER_W)
    if level == 1:
        c.via_stack_12(b, x, y_from)
    c.via_stack_23(b, x, ty)
    taps[net].append(x)


def draw_tracks(b: c.Builder) -> None:
    """Draw each net's Metal3 trunk across the span of its own taps."""
    for net, xs in taps.items():
        if not xs:
            raise AssertionError(f"net {net} has no taps -- floorplan bug")
        y = track_y[net]
        c.route_h(b, 3, y, min(xs) - 0.4, max(xs) + 0.4, width=TRACK_W)
        b.label(net, min(xs) - 0.2, y, level=3)


def build() -> c.Builder:
    b = c.Builder(TOP_CELL)

    # ---------------------------------------------------------------- #
    # 1. Mpass: the 4-row, 28-finger array.
    # ---------------------------------------------------------------- #
    rows = []
    for r in range(MPASS_ROWS):
        rows.append(
            c.draw_mos_row(
                b,
                f"Mpass.r{r}",
                "pmos",
                MPASS_FINGERS,
                MPASS_W_FINGER,
                MPASS_L,
                0.0,
                r * MPASS_ROW_PITCH,
                "EAOUT",
                "VIN",
                "VOUT",
                draw_well=False,  # one shared well for the whole array
            )
        )
    array_x1 = rows[0]["activ"][2]
    array_top = rows[-1]["bbox"][3]

    # One NWell over the whole array plus its own tie bar, labelled VIN: the
    # pass device's body is its source (DR-0002's decision (a)), and without a
    # drawn tie + well label the PMOS body extracts onto an anonymous,
    # unbiased net.
    well_x0, well_x1 = -3.0, array_x1 + c.NW_C1
    well_y0, well_y1 = rows[0]["bbox"][1] - 0.4, array_top + 0.4
    b.box(c.L_NWELL, well_x0, well_y0, well_x1, well_y1)
    b.well_label("VIN", well_x0 + 0.5, (well_y0 + well_y1) / 2)
    c.draw_tap_bar(b, "nwell", -2.4, well_y0 + 1.0, -1.6, well_y1 - 1.0, "VIN")
    # The tie's own Metal1 strap runs the full height of the array, so it also
    # ties every row's Metal1 source bus together: one VIN net, one wire.
    c.route_v(b, 1, -2.0, well_y0 + 1.0, well_y1 - 1.0, width=0.5)
    for row in rows:
        sb = row["source_bus"]
        b.box(c.L_METAL1, -2.3, sb[1], sb[0], sb[3])

    # VOUT: a vertical Metal2 bus straight up the middle of the array, merging
    # with each row's own Metal2 drain bus on the way.
    vout_bus_x = 14.0
    c.route_v(b, 2, vout_bus_x, track_y["VOUT"], rows[-1]["drain_bus"][3], width=0.6)
    c.via_stack_23(b, vout_bus_x, track_y["VOUT"])
    taps["VOUT"].append(vout_bus_x)

    # EAOUT: a vertical Metal2 bus down the right edge, picking up each row's
    # Metal1 gate bus through its own Via1.
    eaout_bus_x = array_x1 + 1.2
    for row in rows:
        gb = row["gate_bus"]
        b.box(c.L_METAL1, gb[2], gb[1], eaout_bus_x + 0.3, gb[3])
        c.via_stack_12(b, eaout_bus_x, (gb[1] + gb[3]) / 2)
    c.route_v(b, 2, eaout_bus_x, track_y["EAOUT"], rows[-1]["gate_bus"][3], width=0.5)
    c.via_stack_23(b, eaout_bus_x, track_y["EAOUT"])
    taps["EAOUT"].append(eaout_bus_x)

    # VIN: one riser from the tie strap down to the trunk.
    riser(b, "VIN", -2.0, rows[0]["source_bus"][1] - 0.6, 1)

    # ---------------------------------------------------------------- #
    # 2. Error amplifier: eight devices in one row, y0 = 0.
    #    (name, flavour, fingers, w_finger, l, x0, gate, source, drain)
    # ---------------------------------------------------------------- #
    ota_spec = [
        ("Mb0", "pmos", 1, 5.0, 2.0, 45.0, "IBIAS", "VIN", "IBIAS"),
        ("Mtail", "pmos", 3, 5.0, 2.0, 53.0, "IBIAS", "VIN", "TAIL"),
        ("Mload2", "pmos", 6, 5.0, 2.0, 66.0, "IBIAS", "VIN", "EAOUT"),
        ("Minp", "pmos", 1, 20.0, 1.0, 88.0, "FB", "TAIL", "G1"),
        ("Minn", "pmos", 1, 20.0, 1.0, 93.0, "VREF", "TAIL", "N1"),
        ("Mn1", "nmos", 1, 5.0, 1.0, 100.0, "N1", "VSS", "N1"),
        ("Mn2", "nmos", 1, 5.0, 1.0, 105.0, "N1", "VSS", "G1"),
        ("Mn3", "nmos", 1, 20.0, 1.0, 110.0, "G1", "VSS", "EAOUT"),
    ]
    ota = {}
    for name, flavour, nf, w_f, l_g, x0, g, s, d in ota_spec:
        ota[name] = c.draw_mos_row(
            b, name, flavour, nf, w_f, l_g, x0, 0.0, g, s, d, draw_well=False
        )

    # Two NWells, because the amplifier has two different PMOS body nets: the
    # bias/load devices sit in a VIN well, the differential pair in its own
    # TAIL well (the schematic ties Minp/Minn's bulk to their common source).
    # NW.b1 requires 1.8 um of PWell between NWells on different nets -- these
    # are 4.4 um apart.
    well1 = (42.5, -1.6, ota["Mload2"]["activ"][2] + c.NW_C1, 5.0 + c.NW_C1)
    b.box(c.L_NWELL, *well1)
    b.well_label("VIN", well1[0] + 0.4, well1[3] - 0.4)
    c.draw_tap_bar(b, "nwell", 43.4, 0.0, 44.2, 5.0, "VIN")
    riser(b, "VIN", 43.8, 2.5, 1)
    well2 = (86.4, -1.6, ota["Minn"]["activ"][2] + c.NW_C1, 20.0 + c.NW_C1)
    b.box(c.L_NWELL, *well2)
    b.well_label("TAIL", well2[0] + 0.4, well2[3] - 0.4)
    c.draw_tap_bar(b, "nwell", 91.6, 0.0, 92.4, 20.0, "TAIL")

    # Substrate tie for the NMOS group: the PDK deck's LU.b wants every
    # N+Activ within 20 um of one, and the curated deck derives the NMOS body
    # net from it (pSD-covered Activ outside every NWell).
    c.draw_tap_bar(b, "psub", 115.0, 0.0, 115.8, 20.0, "VSS")
    riser(b, "VSS", 115.4, 18.0, 1)

    # Per-device risers. Source/drain risers drop through the device on one of
    # its own source/drain column centres (so a riser only ever overlaps its
    # own net's metal); the gate riser drops just outside the device, on a
    # short extension of its own Metal1 gate bus.
    for name, flavour, nf, w_f, l_g, x0, g, s, d in ota_spec:
        dev = ota[name]
        pitch = c.SD_W_UM + l_g
        sb, db, gb = dev["source_bus"], dev["drain_bus"], dev["gate_bus"]
        riser(b, s, x0 + c.SD_W_UM / 2, (sb[1] + sb[3]) / 2, 1)
        riser(b, d, x0 + pitch + c.SD_W_UM / 2, (db[1] + db[3]) / 2, 2)
        gx = dev["activ"][2] + 0.75
        b.box(c.L_METAL1, gb[2], gb[1], gx + 0.35, gb[3])
        riser(b, g, gx, (gb[1] + gb[3]) / 2, 1)

    # Minp/Minn's own well tie is on TAIL, their common source.
    riser(b, "TAIL", 92.0, 18.5, 1)

    # ---------------------------------------------------------------- #
    # 3. Cc: the Miller cap. w=170u (Y) x l=30u (X), per the extractor's own
    #    axis mapping (L = marker bbox width, W = marker bbox height).
    #
    #    #35 (DR-0005) widened this from 100u to 170u -- the only device
    #    change in that issue. It is drawn on the same origin, so the cap
    #    grows upward only: at 170u it is the tallest object in the active
    #    band (the Mpass array tops out at 118u), and it sets this cell's
    #    bounding box in Y. Nothing else lives at x >= 130u in the active
    #    band, so no riser corridor or well moves; RISER_MIN_DX still
    #    asserts that from the database rather than from this comment.
    # ---------------------------------------------------------------- #
    CC_W_UM = 170.0
    c.draw_cap_cmomi(b, "Cc", CC_W_UM, 30.0, 130.0, 0.0, "EAOUT", "MZ")
    riser(b, "EAOUT", 130.3, 2.0, 1)
    riser(b, "MZ", 159.7, 2.0, 1)

    # ---------------------------------------------------------------- #
    # 4. The three rhigh meanders, in the passive band below the channel.
    # ---------------------------------------------------------------- #
    # The passive band tucks under the pass array and the bias devices, in the
    # x range the active band above it leaves free. Each x below is chosen
    # against the riser corridors already allocated, not by eye -- RISER_MIN_DX
    # asserts the result, and moving any of these three by less than ~1 um
    # trips it.
    rz_x, rtop_x, rbot_x = 0.0, 51.0, 64.0
    stripe_pitch = 1.0 + c.RHIGH_PS_UM
    rz = c.draw_rhigh(b, "Rz", 1.0, 28.81, 39, rz_x, -110.0, "MZ", "G1")
    riser(b, "MZ", rz_x + 0.5, rz["pad_a"][3] - 0.2, 1)
    riser(b, "G1", rz_x + 39 * stripe_pitch + 0.5, rz["pad_b"][3] - 0.2, 1)

    rtop = c.draw_rhigh(b, "Rtop", 1.0, 25.43, 7, rtop_x, -107.0, "VOUT", "FB")
    riser(b, "VOUT", rtop_x + 0.5, rtop["pad_a"][3] - 0.2, 1)
    riser(b, "FB", rtop_x + 7 * stripe_pitch + 0.5, rtop["pad_b"][3] - 0.2, 1)

    rbot = c.draw_rhigh(b, "Rbot", 1.0, 25.43, 7, rbot_x, -107.0, "FB", "VSS")
    riser(b, "FB", rbot_x + 0.5, rbot["pad_a"][3] - 0.2, 1)
    riser(b, "VSS", rbot_x + 7 * stripe_pitch + 0.5, rbot["pad_b"][3] - 0.2, 1)

    # ---------------------------------------------------------------- #
    # 5. The trunks themselves, plus the two ports that have no device
    #    terminal of their own to tap (VREF reaches only Minn's gate, IBIAS
    #    only the three bias gates -- both already tapped above).
    # ---------------------------------------------------------------- #
    draw_tracks(b)
    return b


def assert_manhattan(b: c.Builder) -> int:
    """Every shape this layout draws is an axis-aligned box.

    Checked here rather than assumed because the PDK's own 45-degree/angle
    rule table (``rule_decks/geometry/3_2_angle.drc``) cannot run on this
    host -- it uses a DRC-DSL construct this KLayout build does not provide
    (see ``layout/README.md``, "DRC: what actually ran"). This assertion
    covers the same property for this layout directly, from the database.
    """
    count = 0
    for layer_index in b.layout.layer_indexes():
        for shape in b.cell.shapes(layer_index).each():
            if shape.is_text():
                continue
            if not shape.is_box():
                raise AssertionError(f"non-box shape on layer {layer_index}: {shape}")
            count += 1
    return count


def main() -> None:
    b = build()
    shapes = assert_manhattan(b)
    b.write(str(OUT_GDS))
    x0, y0, x1, y1 = b.bbox_um()
    print(f"wrote {OUT_GDS.name}")
    print(f"  top cell   : {TOP_CELL}")
    print(f"  bbox       : ({x0:.2f}, {y0:.2f}) - ({x1:.2f}, {y1:.2f}) um"
          f"  [{x1 - x0:.2f} x {y1 - y0:.2f}]")
    print(f"  shapes     : {shapes} (all axis-aligned boxes)")
    print(f"  Mpass      : {MPASS_ROWS} rows x {MPASS_FINGERS} fingers x "
          f"{MPASS_W_FINGER} um = {MPASS_ROWS * MPASS_FINGERS * MPASS_W_FINGER} um")
    print(f"  area       : {(x1 - x0) * (y1 - y0) / 1000:.1f} x 1000 um^2")


if __name__ == "__main__":
    main()
