"""Shared ``klayout.db`` drawing primitives for this repo's **SG13CMOS5L**
layouts (issue #28, phase 4a of the SG13CMOS5L port tracked by #12).

This is the first layout code in this repository: before #28 ``layout/`` held
nothing but a placeholder README. Everything here is written against the
**SG13CMOS5L PDK's own sources** -- its KLayout layer-properties file, its
PyCell (``sg13cmos5l_pycell_lib``) device code, its ``techParams`` table and
its own DRC rule decks -- cited per constant below. It is deliberately *not*
a copy of another repo's SG13G2 or bandgap drawing module: the device menu
this LDO needs (a 2800 um multi-row HV PMOS array, a 40-stripe meandered
``rhigh``, a ``cap_cmomi`` MoM capacitor) has no counterpart there, and the
`klt` deck this targets is three device families wider than the one those
modules were written against.

What these functions draw is a **simplified representative** footprint for
each device -- correct layer stack, correct device-defining dimensions,
correct terminal/contact structure, drawn to the PDK's own DRC rule values --
not a re-implementation of each PCell's full geometry (its contact packing
loops, its dogbone/asymmetric-contact special cases, its thermal pseudo
layers, or, for ``cap_cmomi``, its 0.84 x 0.89 um unit-cell lattice). See
``layout/README.md`` "What this layout is, and is not" for the full list of
approximations and what each costs.

Conventions
-----------

* **Micron in, database-unit out.** ``dbu = 0.001`` (1 nm), matching
  ``sg13cmos5l.lyt``'s own ``<dbu>0.001</dbu>``. Every coordinate is snapped
  to the PDK's own 5 nm layout grid (``techParams['grid'] == 0.005``) on the
  way in, so the PDK deck's own off-grid check (``rule_decks/geometry/
  3_1_offgrid.drc``) has nothing to find.
* **Axis-aligned boxes only.** Every shape this module draws is a
  ``kdb.Box``. That is what lets ``generate.py`` assert Manhattan-ness
  directly (see its ``assert_manhattan``) rather than relying on the PDK
  deck's own 45-degree/angle table, which cannot run on this host -- see
  ``layout/README.md`` "DRC: what actually ran".
* **Net naming is by text on the ``.pin`` (datatype 2) layers**, which is
  what `klt`'s ``sg13cmos5l`` extraction deck reads
  (``EXTRACTION_DECK.metal_labels == ((8,2),(10,2),(30,2),(50,2),(126,2))``,
  ``well_label == (31,2)``, ``poly_label == (5,2)``). Texts, not boxes: the
  PDK's own ``Pin.*`` DRC rules check that every *polygon* on a ``.pin``
  layer is covered by its drawing layer, and a text carries no polygon. The
  one place this module draws a ``.pin`` **box** is
  :func:`draw_cap_cmomi`, where the MoM extractor requires exactly two
  ``Metal<n>.pin`` port polygons under the recognition marker -- and there
  they are drawn strictly inside a ``Metal1.drawing`` pad, so ``Pin.e`` is
  satisfied by construction.
"""

from __future__ import annotations

import klayout.db as kdb

# --------------------------------------------------------------------------- #
# Layer table.
#
# Every (layer, datatype) pair below was read from the resolved CMOS5L
# technology's own layer-properties file -- `ihp-sg13cmos5l/libs.tech/klayout/
# tech/sg13cmos5l.lyp`, the install `sim/pdk-cmos5l.json` pins -- by matching
# its `<name>` / `<source>` element pairs, not assumed from SG13G2's table and
# not copied from another repo. `layout/README.md` "SG13CMOS5L layer numbers"
# carries the same read-off as a table.
# --------------------------------------------------------------------------- #
L_ACTIV = (1, 0)  # Activ.drawing
L_GATPOLY = (5, 0)  # GatPoly.drawing
L_GATPOLY_PIN = (5, 2)  # GatPoly.pin   -- deck's `poly_label`
L_CONT = (6, 0)  # Cont.drawing
L_NSD = (7, 0)  # nSD.drawing   -- deck's `tap_nplus`
L_METAL1 = (8, 0)  # Metal1.drawing
L_METAL1_PIN = (8, 2)  # Metal1.pin    -- deck's `metal_labels[0]`
L_METAL2 = (10, 0)  # Metal2.drawing
L_METAL2_PIN = (10, 2)  # Metal2.pin    -- deck's `metal_labels[1]`
L_PSD = (14, 0)  # pSD.drawing   -- deck's `tap_pplus`
L_VIA1 = (19, 0)  # Via1.drawing  (Metal1 <-> Metal2)
L_SALBLOCK = (28, 0)  # SalBlock.drawing
L_VIA2 = (29, 0)  # Via2.drawing  (Metal2 <-> Metal3)
L_METAL3 = (30, 0)  # Metal3.drawing
L_METAL3_PIN = (30, 2)  # Metal3.pin    -- deck's `metal_labels[2]`
L_NWELL = (31, 0)  # NWell.drawing
L_NWELL_PIN = (31, 2)  # NWell.pin     -- deck's `well_label`
L_THICKGATEOX = (44, 0)  # ThickGateOx.drawing -- the HV flavour marker
L_TEXT = (63, 0)  # TEXT.drawing  -- human-readable annotation only
L_RECOG_MOM = (99, 39)  # Recog.mom     -- cap_cmomi recognition marker
L_EXTBLOCK = (111, 0)  # EXTBlock.drawing
L_POLYRES = (128, 0)  # PolyRes.drawing

LAYER_NAMES: dict[tuple[int, int], str] = {
    L_ACTIV: "Activ.drawing",
    L_GATPOLY: "GatPoly.drawing",
    L_GATPOLY_PIN: "GatPoly.pin",
    L_CONT: "Cont.drawing",
    L_NSD: "nSD.drawing",
    L_METAL1: "Metal1.drawing",
    L_METAL1_PIN: "Metal1.pin",
    L_METAL2: "Metal2.drawing",
    L_METAL2_PIN: "Metal2.pin",
    L_PSD: "pSD.drawing",
    L_VIA1: "Via1.drawing",
    L_SALBLOCK: "SalBlock.drawing",
    L_VIA2: "Via2.drawing",
    L_METAL3: "Metal3.drawing",
    L_METAL3_PIN: "Metal3.pin",
    L_NWELL: "NWell.drawing",
    L_NWELL_PIN: "NWell.pin",
    L_THICKGATEOX: "ThickGateOx.drawing",
    L_TEXT: "TEXT.drawing",
    L_RECOG_MOM: "Recog.mom",
    L_EXTBLOCK: "EXTBlock.drawing",
    L_POLYRES: "PolyRes.drawing",
}

#: Metal level -> (drawing layer, pin layer), for the routing helpers.
METAL_STACK: dict[int, tuple[tuple[int, int], tuple[int, int]]] = {
    1: (L_METAL1, L_METAL1_PIN),
    2: (L_METAL2, L_METAL2_PIN),
    3: (L_METAL3, L_METAL3_PIN),
}
#: Via layer that connects metal level n to n+1.
VIA_FOR_LEVEL: dict[int, tuple[int, int]] = {1: L_VIA1, 2: L_VIA2}

# --------------------------------------------------------------------------- #
# Process constants.
#
# Read from CMOS5L's own
# `libs.tech/klayout/python/sg13cmos5l_pycell_lib/sg13cmos5l_tech.json`
# `techParams` table (the same table every PCell in that library reads at
# generate time) and, for the rule *values* the drawn geometry has to clear,
# from the PDK DRC deck's own value table,
# `libs.tech/klayout/tech/drc/rule_decks/sg13cmos5l_tech_default.json`
# `drc_rules` (the file `ihp-sg13cmos5l.drc` itself loads). Cited per
# constant; none of these are inherited from SG13G2 by analogy.
# --------------------------------------------------------------------------- #
GRID_UM = 0.005  # techParams['grid'] -- the PDK's own layout grid

CNT_A = 0.16  # Cnt_a  -- Cont size (min AND max: rule Cnt.a)
CNT_B = 0.18  # Cnt_b  -- Cont space
CNT_C = 0.07  # Cnt_c  -- Activ enclosure of Cont
CNT_D = 0.07  # Cnt_d  -- GatPoly enclosure of Cont
CNT_E = 0.14  # Cnt_e  -- Cont-on-GatPoly space to Activ
CNT_G2 = 0.09  # Cnt_g2 -- pSD overlap of Cont on pSD-Activ
CONT_PITCH = CNT_A + CNT_B  # 0.34 -- the pitch `cont_array` packs on

ACT_A = 0.15  # Act_a  -- min Activ width
ACT_B = 0.21  # Act_b  -- min Activ space/notch
GAT_A = 0.13  # Gat_a  -- min GatPoly width
GAT_B = 0.18  # Gat_b  -- min GatPoly space/notch
GAT_C = 0.18  # Gat_c  -- GatPoly overlap of Activ (gate endcap)
GAT_D = 0.07  # Gat_d  -- GatPoly space to Activ
M1_A = 0.16  # M1_a   -- min Metal1 width
M1_B = 0.18  # M1_b   -- min Metal1 space/notch
M1_C1 = 0.05  # M1_c1  -- Metal1 endcap over a contact row
M1_E = 0.22  # M1_e   -- Metal1 space when one line is > 0.15 um wide
MN_A = 0.20  # Mn_a   -- min Metal2..4 width
MN_B = 0.21  # Mn_b   -- min Metal2..4 space
MN_E = 0.24  # Mn_e   -- Metal2..4 space when one line is > 0.195 um wide
V1_A = 0.19  # V1_a   -- Via1 size (min AND max)
V1_B = 0.22  # V1_b   -- Via1 space
V1_C = 0.01  # V1_c   -- Metal1 enclosure of Via1
#: ``Vn_a`` -- Via2/Via3 size (min AND max). A *separate* rule key from
#: ``V1_a`` in the PDK's own value table, checked by a separate deck table
#: (``rule_decks/beol/5_20_vian.drc``, which instantiates it per via level as
#: ``V2.a``/``V3.a`` -- there is no ``V2_a`` key to cite), that happens to
#: carry the same 0.19 um value. Named here rather than reusing ``V1_A`` so
#: :func:`via2` cites the rule that actually governs it: the two keys are not
#: required to track each other, and their enclosure siblings already do not
#: (``V1_c`` 0.01 vs ``Vn_c`` 0.005).
VN_A = 0.19  # Vn_a   -- Via2..Vian size (min AND max)
NW_C1 = 0.62  # NW_c1  -- NWell enclosure of p+ Activ
NW_B = 0.62  # NW_b   -- NWell space (same net)
NW_F1 = 0.62  # NW_f1  -- NWell space to a substrate tie inside ThickGateOx
PSD_C = 0.18  # pSD_c  -- pSD enclosure of p+ Activ
TGO_A = 0.27  # TGO_a  -- ThickGateOx overlay past Activ
TGO_C = 0.34  # TGO_c  -- ThickGateOx overlay past GatPoly
TGO_F = 0.86  # TGO_f  -- min ThickGateOx width (rule TGO.f)
LU_B = 20.0  # LU_b   -- max distance from N+Activ to a substrate tie

#: House spacing this module leaves between different-net conductors, chosen
#: once here rather than per call site: comfortably above every min-space rule
#: the two decks check (Metal1 ``M1.b`` 0.18 / ``M1.e`` 0.22, Metal2+ ``Mn.b``
#: 0.21 / ``Mn.e`` 0.24, ``Act.b`` 0.21, ``Gat.b`` 0.18), so a rounding error
#: in a floorplan coordinate cannot turn into a violation.
SPACE_UM = 0.30

#: Sheet resistance of ``rhigh``, ohm/square, as the curated `klt` deck
#: models it (``decks/sg13cmos5l.py``'s ``ResistorDevice(name="rhigh",
#: sheet_rho_ohm_sq=1360.0)``) and as the PDK's own ``cornerRES.lib``
#: ``res_typ`` section declares (``rsh_rhigh = 1360``). Used by
#: ``lvs_reference.py`` to state the reference device's ``R``.
RHIGH_SHEET_RHO = 1360.0


def snap(value_um: float) -> float:
    """Snap a micron coordinate to the PDK's own 5 nm layout grid."""
    return round(value_um / GRID_UM) * GRID_UM


class Builder:
    """A ``kdb.Layout`` + top cell + layer map, with box/text primitives.

    Micron in, database-unit out; every coordinate is grid-snapped by
    :func:`snap` before it reaches the database, so nothing this module draws
    can be off-grid.
    """

    def __init__(self, top_cell: str, dbu: float = 0.001) -> None:
        self.layout = kdb.Layout()
        self.layout.dbu = dbu
        self.cell = self.layout.create_cell(top_cell)
        self._layers: dict[tuple[int, int], int] = {}
        for (layer, datatype), name in LAYER_NAMES.items():
            info = kdb.LayerInfo(layer, datatype, name)
            self._layers[(layer, datatype)] = self.layout.layer(info)

    # -- primitives -------------------------------------------------------- #
    def _u(self, value_um: float) -> int:
        return int(round(snap(value_um) / self.layout.dbu))

    def box(
        self, layer: tuple[int, int], x0: float, y0: float, x1: float, y1: float
    ) -> tuple[float, float, float, float]:
        """Draw an axis-aligned box and return it as a micron 4-tuple."""
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        self.cell.shapes(self._layers[layer]).insert(
            kdb.Box(self._u(x0), self._u(y0), self._u(x1), self._u(y1))
        )
        return (snap(x0), snap(y0), snap(x1), snap(y1))

    def label(self, net: str, x: float, y: float, level: int = 1) -> None:
        """Name a net by placing a text on that metal level's ``.pin`` layer.

        Must land on a real drawing shape of the same level: the deck's own
        ``connect(metals[i], metal_labels[i])`` is what turns the text into a
        net name, and a text over empty field names nothing.
        """
        pin_layer = METAL_STACK[level][1]
        self.cell.shapes(self._layers[pin_layer]).insert(
            kdb.Text(net, self._u(x), self._u(y))
        )

    def well_label(self, net: str, x: float, y: float) -> None:
        """Name an ``NWell`` region (the deck's ``well_label``, 31/2), which is
        what gives a PMOS body terminal a real net instead of an anonymous,
        floating one."""
        self.cell.shapes(self._layers[L_NWELL_PIN]).insert(
            kdb.Text(net, self._u(x), self._u(y))
        )

    def annotate(self, text: str, x: float, y: float) -> None:
        """Human-readable annotation on ``TEXT.drawing`` -- read by nothing in
        the DRC/LVS flow, drawn so the GDS is legible in a viewer."""
        self.cell.shapes(self._layers[L_TEXT]).insert(
            kdb.Text(text, self._u(x), self._u(y))
        )

    def write(self, path: str) -> None:
        """Write the GDS **reproducibly**.

        GDSII's ``BGNLIB``/``BGNSTR`` records carry a modification and an
        access timestamp, and KLayout fills them from the wall clock by
        default -- so two runs of the same generator produce two different
        files, byte for byte, differing only in bytes 20 onward. That would
        make the committed ``.gds`` unverifiable as evidence: nobody could
        re-run ``generate.py`` and confirm the committed artifact is the one
        this code draws (``run_flow.sh --check`` does exactly that).
        ``gds2_write_timestamps = False`` zeroes them, which is what makes
        the committed stream a function of the source alone.
        """
        options = kdb.SaveLayoutOptions()
        options.format = "GDS2"
        options.gds2_write_timestamps = False
        self.layout.write(path, options)

    def bbox_um(self) -> tuple[float, float, float, float]:
        b = self.cell.bbox()
        d = self.layout.dbu
        return (b.left * d, b.bottom * d, b.right * d, b.top * d)


# --------------------------------------------------------------------------- #
# Contact / via arrays
# --------------------------------------------------------------------------- #
def cont_array(
    b: Builder, x0: float, y0: float, x1: float, y1: float
) -> int:
    """Fill ``(x0,y0)-(x1,y1)`` with ``Cnt_a``-sized contacts on a
    ``Cnt_a + Cnt_b`` pitch, centred in the box; returns how many were drawn.

    ``Cnt.a`` makes 0.16 um both the minimum *and* the maximum contact width,
    so this is an array of many small cuts rather than one big one -- the same
    reason CMOS5L's own ``contactArray()`` helper exists.
    """
    span_x, span_y = x1 - x0, y1 - y0
    nx = int((span_x + CNT_B + 1e-9) // CONT_PITCH)
    ny = int((span_y + CNT_B + 1e-9) // CONT_PITCH)
    if nx < 1 or ny < 1:
        return 0
    used_x = nx * CONT_PITCH - CNT_B
    used_y = ny * CONT_PITCH - CNT_B
    ox = x0 + (span_x - used_x) / 2
    oy = y0 + (span_y - used_y) / 2
    for i in range(nx):
        for j in range(ny):
            cx, cy = ox + i * CONT_PITCH, oy + j * CONT_PITCH
            b.box(L_CONT, cx, cy, cx + CNT_A, cy + CNT_A)
    return nx * ny


def via1(b: Builder, x: float, y: float) -> None:
    """One ``Via1`` cut centred at ``(x, y)``. ``V1.a`` fixes the size at
    0.19 um exactly (min and max), so this never sizes with its landing pad."""
    b.box(L_VIA1, x - V1_A / 2, y - V1_A / 2, x + V1_A / 2, y + V1_A / 2)


def via2(b: Builder, x: float, y: float) -> None:
    """One ``Via2`` cut centred at ``(x, y)``. Sized by ``Vn.a`` (``VN_A``),
    the Via2/Via3 rule -- which the PDK's own value table sets to the same
    0.19 um as ``V1.a``, but as its own key, so this cites its own rule."""
    b.box(L_VIA2, x - VN_A / 2, y - VN_A / 2, x + VN_A / 2, y + VN_A / 2)


def via_stack_12(b: Builder, x: float, y: float, pad: float = 0.4) -> None:
    """Metal1 pad + ``Via1`` + Metal2 pad at ``(x, y)``: the standard
    level-1-to-2 transition this floorplan uses wherever a net has to cross
    another on a different level."""
    b.box(L_METAL1, x - pad / 2, y - pad / 2, x + pad / 2, y + pad / 2)
    via1(b, x, y)
    b.box(L_METAL2, x - pad / 2, y - pad / 2, x + pad / 2, y + pad / 2)


def via_stack_23(b: Builder, x: float, y: float, pad: float = 0.4) -> None:
    """Metal2 pad + ``Via2`` + Metal3 pad at ``(x, y)``."""
    b.box(L_METAL2, x - pad / 2, y - pad / 2, x + pad / 2, y + pad / 2)
    via2(b, x, y)
    b.box(L_METAL3, x - pad / 2, y - pad / 2, x + pad / 2, y + pad / 2)


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def route_h(
    b: Builder, level: int, y: float, x0: float, x1: float, width: float = 0.4
) -> tuple[float, float, float, float]:
    """Horizontal wire centred on ``y`` from ``x0`` to ``x1`` on metal
    ``level``."""
    return b.box(METAL_STACK[level][0], x0, y - width / 2, x1, y + width / 2)


def route_v(
    b: Builder, level: int, x: float, y0: float, y1: float, width: float = 0.4
) -> tuple[float, float, float, float]:
    """Vertical wire centred on ``x`` from ``y0`` to ``y1`` on metal
    ``level``."""
    return b.box(METAL_STACK[level][0], x - width / 2, y0, x + width / 2, y1)


# --------------------------------------------------------------------------- #
# MOS devices
# --------------------------------------------------------------------------- #
#: Source/drain column width in a multi-finger row. 0.5 um comfortably holds
#: one contact column (``Cnt_a`` 0.16 + 2 x ``Cnt_c`` 0.07 = 0.30 um minimum)
#: and leaves 0.17 um from each contact edge to the neighbouring gate.
SD_W_UM = 0.5

#: Clearance from the Activ strip down to the gate contact row: ``Cnt.e``
#: (0.14) is the rule, drawn at 0.20 for 0.06 um of margin.
GATE_CONT_CLEAR_UM = 0.20

#: How far the poly runs on past that contact: ``Cnt.d`` (0.07) is the poly
#: enclosure of a contact, drawn at 0.10 for 0.03 um of margin.
GATE_CONT_ENCL_UM = 0.10

#: How far a gate's poly runs *below* the Activ strip, tail end to Activ
#: edge. Derived, not chosen: the gate endcap past the Activ is ``Gat_c``
#: (0.18), then the two clearances above. :func:`draw_mos_row` places the
#: contact row from the same two terms, so the tail length and the geometry
#: that produces it cannot drift apart.
GATE_TAIL_UM = GAT_C + GATE_CONT_CLEAR_UM + CNT_A + GATE_CONT_ENCL_UM


def draw_mos_row(
    b: Builder,
    name: str,
    flavour: str,
    fingers: int,
    w_finger: float,
    l_gate: float,
    x0: float,
    y0: float,
    gate_net: str,
    source_net: str,
    drain_net: str,
    *,
    draw_well: bool = True,
    draw_tgo: bool = True,
) -> dict:
    """Draw one interdigitated, shared-diffusion row of ``fingers`` HV MOS
    fingers of width ``w_finger`` and channel length ``l_gate``.

    Physical construction (the standard wide-device layout, and the reason
    this is a *row* generator rather than N independent devices): one ``Activ``
    strip carries ``fingers + 1`` source/drain columns with ``fingers`` gate
    stripes between them, so adjacent fingers share their source/drain
    diffusion. Column ``j`` is a *source* for even ``j`` and a *drain* for odd
    ``j``. Every gate is the same net.

    ``klt``'s extractor sees one device per gate stripe (that is what a
    finger is); ``klt lvs``'s ``options.combine_devices`` is what folds the
    row back into the single ``w = fingers * w_finger`` device the schematic
    declares. Both halves of that are load-bearing -- see
    ``layout/README.md`` "Why the LVS request sets ``combine_devices``".

    Layer stack per flavour, read from CMOS5L's own PyCell sources:

    * ``pmos`` (``pmosHV_code.py``): ``Activ`` + ``GatPoly`` + ``pSD``
      (p+ implant, enclosing the Activ by ``pSD_c``) + ``NWell`` (enclosing
      the Activ by ``NW_c1``) + ``ThickGateOx``.
    * ``nmos`` (``nmosHV_code.py``): ``Activ`` + ``GatPoly`` +
      ``ThickGateOx`` only -- **no implant and no well**. That is not an
      omission here: in SG13's layer scheme ``pSD`` is the only drawn implant
      mask and n+ is its complement, which is exactly how both decks derive
      the device (the PDK deck's ``nactiv = activ_drw.not(psd_drw...)``,
      the curated deck's "NMOS = active outside nwell").

    Escape routing, per row: the gates leave *downward* on a shared ``Metal1``
    bus under the strip; the sources leave *upward* on a ``Metal1`` bus; the
    drains leave upward too but transition to ``Metal2`` before they reach the
    source bus, so the two escape in the same direction without a short. (The
    curated deck models the full ``Metal1..TopMetal1`` stack with its vias as
    of klayout-tools #1417, so a second routing level is real here, not a
    drawing-only convenience.) The Metal2 transition is unconditional and has
    to be: the source bus spans the full row width at the same y the drain
    straps would have to cross, so a drain escaping on ``Metal1`` would short
    to the source net rather than merely violate a spacing rule.

    Returns the row's terminal geometry for the caller's floorplan: the bus
    boxes (``gate_bus``, ``source_bus``, ``drain_bus``), the device
    ``bbox``/``nwell``/``tgo`` extents, and the drawn ``total_width``.
    """
    if flavour not in ("pmos", "nmos"):
        raise ValueError(f"flavour must be 'pmos' or 'nmos', got {flavour!r}")
    if fingers < 1:
        raise ValueError("a row needs at least one finger")

    pitch = SD_W_UM + l_gate
    act_x0, act_y0 = x0, y0
    act_x1 = x0 + fingers * pitch + SD_W_UM
    act_y1 = y0 + w_finger
    b.box(L_ACTIV, act_x0, act_y0, act_x1, act_y1)

    # -- gates ------------------------------------------------------------- #
    gate_cont_top = act_y0 - GAT_C - GATE_CONT_CLEAR_UM
    gate_cont_bot = gate_cont_top - CNT_A
    poly_bot = act_y0 - GATE_TAIL_UM  # == gate_cont_bot - GATE_CONT_ENCL_UM
    for i in range(fingers):
        gx0 = x0 + SD_W_UM + i * pitch
        b.box(L_GATPOLY, gx0, poly_bot, gx0 + l_gate, act_y1 + GAT_C)
        # one contact per finger on the poly tail, inside the shared bus
        cx = gx0 + (l_gate - CNT_A) / 2
        b.box(L_CONT, cx, gate_cont_bot, cx + CNT_A, gate_cont_top)
    gate_bus = b.box(
        L_METAL1,
        act_x0,
        gate_cont_bot - M1_C1,
        act_x1,
        gate_cont_top + M1_C1,
    )
    b.label(gate_net, (act_x0 + act_x1) / 2, (gate_bus[1] + gate_bus[3]) / 2)

    # -- source/drain columns ---------------------------------------------- #
    source_bus_y0 = act_y1 + 0.85
    source_bus_y1 = source_bus_y0 + 0.40
    drain_strap_top = act_y1 + 0.55
    m2_pad_y = act_y1 + 0.35
    drain_bus_y0 = act_y1 + 1.70
    drain_bus_y1 = drain_bus_y0 + 0.40

    for j in range(fingers + 1):
        cx0 = x0 + j * pitch
        cx1 = cx0 + SD_W_UM
        cont_array(b, cx0 + CNT_C, act_y0 + CNT_C, cx1 - CNT_C, act_y1 - CNT_C)
        is_source = j % 2 == 0
        strap_top = source_bus_y1 if is_source else drain_strap_top
        b.box(L_METAL1, cx0 + M1_C1, act_y0, cx1 - M1_C1, strap_top)
        if not is_source:
            via1(b, (cx0 + cx1) / 2, m2_pad_y)
            b.box(
                L_METAL2,
                cx0 + M1_C1 + 0.03,
                m2_pad_y - 0.15,
                cx1 - M1_C1 - 0.03,
                drain_bus_y1,
            )

    source_bus = b.box(L_METAL1, act_x0, source_bus_y0, act_x1, source_bus_y1)
    b.label(source_net, (act_x0 + act_x1) / 2, (source_bus_y0 + source_bus_y1) / 2)
    drain_bus = b.box(L_METAL2, act_x0, drain_bus_y0, act_x1, drain_bus_y1)
    b.label(drain_net, (act_x0 + act_x1) / 2, (drain_bus_y0 + drain_bus_y1) / 2, level=2)

    # -- implant / well / thick oxide -------------------------------------- #
    nwell = None
    if flavour == "pmos":
        b.box(
            L_PSD,
            act_x0 - PSD_C,
            act_y0 - PSD_C,
            act_x1 + PSD_C,
            act_y1 + PSD_C,
        )
        nwell = (
            act_x0 - NW_C1,
            poly_bot - 0.20,
            act_x1 + NW_C1,
            act_y1 + NW_C1,
        )
        if draw_well:
            b.box(L_NWELL, *nwell)
            b.well_label(source_net, (act_x0 + act_x1) / 2, act_y1 + NW_C1 / 2)

    tgo = (
        act_x0 - TGO_A,
        poly_bot - TGO_C,
        act_x1 + TGO_A,
        act_y1 + TGO_C,
    )
    if draw_tgo:
        b.box(L_THICKGATEOX, *tgo)

    b.annotate(
        f"{name} sg13_hv_{flavour} {fingers}x w={w_finger}u l={l_gate}u",
        (act_x0 + act_x1) / 2,
        drain_bus_y1 + 0.5,
    )
    return {
        "name": name,
        "total_width": fingers * w_finger,
        "activ": (act_x0, act_y0, act_x1, act_y1),
        "gate_bus": gate_bus,
        "source_bus": source_bus,
        "drain_bus": drain_bus,
        "drain_level": 2,  # the drain bus is always Metal2 -- see "Escape routing"
        "nwell": nwell,
        "tgo": tgo,
        "bbox": (
            min(act_x0 - NW_C1, tgo[0]),
            min(tgo[1], poly_bot),
            max(act_x1 + NW_C1, tgo[2]),
            max(drain_bus_y1, tgo[3]),
        ),
    }


def draw_tap_bar(
    b: Builder,
    kind: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    net: str,
    *,
    label: bool = True,
) -> tuple[float, float, float, float]:
    """Draw a well tie (``kind="nwell"``) or substrate tie (``kind="psub"``)
    as a contacted ``Activ`` bar with its ``Metal1`` strap.

    Both decks derive these the same way and neither has a dedicated tap
    layer, so which tie this is comes entirely from its implant and its
    position:

    * ``psub``  -- ``Activ`` + ``pSD``, drawn **outside** every ``NWell``.
      The PDK deck's ``ptap = pactiv.and(pwell)``; the curated deck's
      ``tap_pplus = (14, 0)``. This is what ties an NMOS body to the
      substrate net, and what the PDK deck's ``LU.b`` latch-up rule looks for
      within 20 um of every NMOS.
    * ``nwell`` -- ``Activ`` + ``nSD``, drawn **inside** an ``NWell``. The PDK
      deck's ``ntap = nactiv.and(nwell_drw)``; the curated deck's
      ``tap_nplus = (7, 0)``. This is what biases the well a PMOS body sits
      in; without it the PMOS body extracts onto an unbiased, anonymous net.
    """
    b.box(L_ACTIV, x0, y0, x1, y1)
    implant = L_PSD if kind == "psub" else L_NSD
    b.box(implant, x0 - PSD_C, y0 - PSD_C, x1 + PSD_C, y1 + PSD_C)
    cont_array(b, x0 + CNT_C, y0 + CNT_C, x1 - CNT_C, y1 - CNT_C)
    strap = b.box(L_METAL1, x0 - M1_C1, y0 + M1_C1, x1 + M1_C1, y1 - M1_C1)
    if label:
        b.label(net, (x0 + x1) / 2, (y0 + y1) / 2)
    return strap


# --------------------------------------------------------------------------- #
# Drawn poly resistor: rhigh
# --------------------------------------------------------------------------- #
#: ``rhigh_defPS`` / ``rhigh_minPS`` -- the poly space between two stripes of
#: a meandered body. This is also the ``ps`` the PDK's own ngspice model
#: assumes when it computes the meander's effective length
#: (``leff = (b+1)*l + (2/kappa*weff + ps)*b`` in ``resistors_mod.lib``), so
#: drawing anything else would put the drawn device and the simulated one out
#: of step. 0.18 um is exactly ``Gat.b``'s min GatPoly space.
RHIGH_PS_UM = 0.18

#: Un-marked ``GatPoly`` head length at each free end -- long enough for a
#: contact (``Cnt_a`` 0.16) plus its ``Cnt_d`` (0.07) poly enclosure at both
#: ends, matching ``rhigh_code.py``'s own ``poly_cont_len = Cnt_a + Cnt_d``
#: with margin.
RHIGH_HEAD_UM = 0.50


def draw_rhigh(
    b: Builder,
    name: str,
    w_um: float,
    l_seg_um: float,
    bends: int,
    x0: float,
    y0: float,
    net_a: str,
    net_b: str,
) -> dict:
    """Draw a meandered ``rhigh`` poly resistor: ``bends + 1`` vertical
    stripes of length ``l_seg_um``, width ``w_um``, on a ``w + ps`` pitch,
    joined alternately at top and bottom.

    ``bends`` is the PDK PCell's own ``b`` parameter -- ``rhigh_code.py``'s
    ``stripes = b + 1`` -- and it is an *electrical* parameter, not just a
    drawing one: the PDK's ngspice model computes the body's effective length
    as ``(b+1)*l + (2/kappa*weff + ps)*b``, i.e. the bends carry resistance.
    That is why the schematic declares ``b`` too, and why the drawn stripe
    count here must equal the declared one rather than being a free layout
    choice. (0, 0) is the lower-left corner of stripe 0's marked body.

    Layer stack, read from CMOS5L's own ``rhigh_code.py`` and cross-checked
    against the curated deck's own recognition terms
    (``ResistorDevice(name="rhigh", body=(5,0), marker=(128,0),
    requires=(EXTBlock, pSD, nSD, SalBlock), excludes=(Activ, ThickGateOx))``):

    * ``GatPoly`` (5/0) is the conductor -- both the marked body and the two
      un-marked contact heads;
    * ``PolyRes`` (128/0) + ``SalBlock`` (28/0) mark the resistive body,
      **stopping short of the heads** so the heads stay ordinary conductor
      (that split is what gives the extractor its two terminals rather than
      one shorted-through wire);
    * ``pSD`` (14/0) **and** ``nSD`` (7/0) together are what make this
      ``rhigh`` rather than ``rppd`` (upstream's ``rhigh_res =
      polyres_mk.and(psd_drw).and(nsd_drw).and(salblock_drw)``; ``rppd``
      excludes ``nSD``), and ``EXTBlock`` (111/0) is the marker both share.

    Nothing here may be covered by ``ThickGateOx``: it is in *both* decks'
    exclusion term for a poly resistor, so a resistor drawn inside an HV
    device's thick-oxide window would silently stop being a resistor and
    start being a short. The floorplan keeps the two apart.
    """
    stripes = bends + 1
    pitch = w_um + RHIGH_PS_UM
    y_top = y0 + l_seg_um

    body: list[tuple[float, float, float, float]] = []
    for i in range(stripes):
        lx = x0 + i * pitch
        body.append((lx, y0, lx + w_um, y_top))
    for i in range(stripes - 1):
        lx = x0 + i * pitch
        if i % 2 == 0:  # link at the top
            body.append((lx + w_um, y_top - w_um, lx + pitch, y_top))
        else:  # link at the bottom
            body.append((lx + w_um, y0, lx + pitch, y0 + w_um))

    for layer in (L_GATPOLY, L_POLYRES, L_SALBLOCK, L_EXTBLOCK, L_PSD, L_NSD):
        for boxes in body:
            b.box(layer, *boxes)

    def _head(index: int, at_top: bool, net: str) -> tuple[float, float, float, float]:
        lx = x0 + index * pitch
        if at_top:
            hy0, hy1 = y_top, y_top + RHIGH_HEAD_UM
        else:
            hy0, hy1 = y0 - RHIGH_HEAD_UM, y0
        # Head conductor + the two implants that keep it the same flavour as
        # the body it feeds -- but deliberately no PolyRes/SalBlock, so the
        # extractor reads it as a terminal, not as more resistor.
        b.box(L_GATPOLY, lx, hy0, lx + w_um, hy1)
        b.box(L_PSD, lx - PSD_C, hy0 - PSD_C, lx + w_um + PSD_C, hy1 + PSD_C)
        b.box(L_NSD, lx - PSD_C, hy0 - PSD_C, lx + w_um + PSD_C, hy1 + PSD_C)
        b.box(L_EXTBLOCK, lx, hy0, lx + w_um, hy1)
        cy = (hy0 + hy1) / 2
        b.box(L_CONT, lx + (w_um - CNT_A) / 2, cy - CNT_A / 2, lx + (w_um + CNT_A) / 2, cy + CNT_A / 2)
        pad = b.box(L_METAL1, lx - 0.05, cy - 0.20, lx + w_um + 0.05, cy + 0.20)
        b.label(net, (pad[0] + pad[2]) / 2, cy)
        return pad

    # Stripe 0's free end is always at the bottom; the last stripe's free end
    # is at the bottom for an even stripe count and at the top for an odd one
    # (the links alternate, so the parity fixes it).
    pad_a = _head(0, at_top=False, net=net_a)
    pad_b = _head(stripes - 1, at_top=(stripes % 2 == 1), net=net_b)

    width_um = stripes * pitch - RHIGH_PS_UM
    b.annotate(
        f"{name} rhigh w={w_um}u l={l_seg_um}u b={bends}",
        x0 + width_um / 2,
        y_top + RHIGH_HEAD_UM + 0.4,
    )
    return {
        "name": name,
        "pad_a": pad_a,
        "pad_b": pad_b,
        "stripes": stripes,
        "width_um": width_um,
        "bbox": (
            min(pad_a[0], pad_b[0], x0) - PSD_C,
            min(pad_a[1], pad_b[1], y0) - PSD_C,
            max(pad_a[2], pad_b[2], x0 + width_um) + PSD_C,
            max(pad_a[3], pad_b[3], y_top) + PSD_C,
        ),
    }


# --------------------------------------------------------------------------- #
# MoM capacitor: cap_cmomi
# --------------------------------------------------------------------------- #
#: ``cap_cmomi_code.py``'s own lattice constants, kept here as *citations*:
#: the real PCell tiles a 0.840 x 0.890 um unit cell (``UC_X``/``UC_Y``) of
#: 0.21 um bars and teeth (``T_BAR``/``FINGER_W``) across the device. This
#: module draws a deliberately coarser comb -- see :func:`draw_cap_cmomi`.
CMOMI_UC_X, CMOMI_UC_Y = 0.840, 0.890
CMOMI_BAR_UM = 0.21


def draw_cap_cmomi(
    b: Builder,
    name: str,
    w_um: float,
    l_um: float,
    x0: float,
    y0: float,
    net_a: str,
    net_b: str,
    *,
    row_pitch: float = 2.0,
) -> dict:
    """Draw a ``cap_cmomi`` MoM capacitor footprint whose recognition marker
    is exactly the schematic's ``w`` x ``l``.

    **Axis convention, transcribed from the extractor rather than guessed**:
    `klt`'s ``_MomCapacitorExtractor`` sets ``L`` from the marker bounding
    box's *width* (X) and ``W`` from its *height* (Y) -- upstream's own
    ``custom_mom_extractor.lvs`` mapping. The PCell agrees ("length -> X
    (finger length), width -> Y (rows)"). So the marker drawn here spans
    ``l_um`` in X and ``w_um`` in Y, and the extracted device reports the
    schematic's own ``w``/``l`` back.

    **What is faithful and what is representative.** The marker
    (``Recog.mom`` 99/39) and the two ``Metal1.pin`` port polygons are the
    *entire* input to device recognition -- the extractor computes no
    capacitance at all (the real device's ``C`` comes from its Verilog-A
    model), so those three shapes are drawn exactly. The interior is a
    coarse interdigitated comb on ``Metal1``/``Metal2`` at ``row_pitch``
    (2 um by default) rather than the PCell's own 0.89 um row pitch of
    0.21 um bars: at the schematic's 30 x 100 um that lattice is ~63000
    rectangles, which is real geometry this phase has no way to verify and
    every reason not to commit. The consequence is stated plainly in
    ``layout/README.md``: this footprint occupies the right area and
    extracts as the right device, but its *drawn* fringe capacitance is not
    the PCell's ~3.2 pF, so it is a placeholder for a real ``cap_cmomi``
    PCell instance, not a substitute for one.
    """
    x1, y1 = x0 + l_um, y0 + w_um

    # Feed bars: plate A on the left, plate B on the right (the PCell's own
    # `feed='double'` configuration, which is what the schematic declares).
    feed_w = 0.6
    bar_a = b.box(L_METAL1, x0, y0, x0 + feed_w, y1)
    bar_b = b.box(L_METAL1, x1 - feed_w, y0, x1, y1)

    # Interdigitated rows: even rows belong to plate A (reaching in from the
    # left bar), odd rows to plate B (reaching in from the right).
    rows = max(2, int((w_um - CMOMI_BAR_UM) // row_pitch))
    finger_len = l_um - feed_w - 1.0
    for j in range(rows):
        yc = y0 + CMOMI_BAR_UM + j * row_pitch
        if yc + CMOMI_BAR_UM > y1:
            break
        if j % 2 == 0:
            fx0, fx1 = x0, x0 + feed_w + finger_len
        else:
            fx0, fx1 = x1 - feed_w - finger_len, x1
        b.box(L_METAL1, fx0, yc, fx1, yc + CMOMI_BAR_UM)
        b.box(L_METAL2, fx0, yc, fx1, yc + CMOMI_BAR_UM)
        via1(b, (fx0 + fx1) / 2, yc + CMOMI_BAR_UM / 2)
    b.box(L_METAL2, x0, y0, x0 + feed_w, y1)
    b.box(L_METAL2, x1 - feed_w, y0, x1, y1)
    via1(b, x0 + feed_w / 2, y0 + 0.5)
    via1(b, x1 - feed_w / 2, y0 + 0.5)

    # The recognition marker: exactly w x l, nothing else.
    b.box(L_RECOG_MOM, x0, y0, x1, y1)

    # Exactly two port polygons under the marker -- the extractor errors out
    # (and drops the device) on any other count. Drawn strictly inside their
    # own Metal1 feed bars so the PDK deck's `Pin.e` (Metal1 enclosure of
    # Metal1:pin) is satisfied by construction.
    port = 0.3
    b.box(L_METAL1_PIN, x0 + 0.1, y0 + 0.1, x0 + 0.1 + port, y0 + 0.1 + port)
    b.box(L_METAL1_PIN, x1 - 0.1 - port, y0 + 0.1, x1 - 0.1, y0 + 0.1 + port)
    b.label(net_a, x0 + feed_w / 2, y1 - 0.5)
    b.label(net_b, x1 - feed_w / 2, y1 - 0.5)

    b.annotate(f"{name} cap_cmomi w={w_um}u l={l_um}u", (x0 + x1) / 2, y1 + 0.5)
    return {
        "name": name,
        "bar_a": bar_a,
        "bar_b": bar_b,
        "bbox": (x0, y0, x1, y1),
    }
