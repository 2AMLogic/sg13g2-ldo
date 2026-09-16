#!/usr/bin/env python3
"""Generate the ``klt lvs`` **reference** netlist for a SG13CMOS5L cell from
this repo's own schematic export -- never by hand, and never by copying the
extracted netlist.

    python3 layout/lvs_reference.py            # writes the reference next to
                                               # the cell's generate.py

The reference netlist is the *schematic* side of LVS. Deriving it mechanically
from ``design/sg13cmos5l/netlist/<cell>.spice`` (which ``design/netlist.py``
exports from the xschem source and CI re-checks byte-for-byte) is what keeps
"the layout matches the schematic" a real claim: there is no step in this
pipeline where a human writes down what they *believe* the schematic says.

Four transformations happen here, each of which is a real, documented
difference between the schematic's form and the form ``klt lvs`` compares --
not an approximation of the circuit:

1. **Hierarchy is flattened.** ``klt extract`` has no hierarchical mode: it
   always writes exactly one flat ``.SUBCKT`` (its own documented
   limitation). The schematic's ``Xamp`` instance of ``ldo_erramp_cmos5l`` is
   therefore inlined here, with its formal ports bound to the caller's nets
   and its internal nets (``TAIL``/``G1``/``N1``/``MZ``) carried through
   under their own names -- none of which collide with the core's.

2. **Subcircuit calls become plain elements.** The schematic export uses the
   *simulation* form (``XMpass ... sg13_hv_pmos w=2800u l=0.5u``) because
   that is what the PDK's ngspice models are. ``klt lvs`` reads its reference
   with a plain ``NetlistSpiceReader``, which turns any ``X`` card into a
   *subcircuit instance*, not a device -- so each MOS is re-emitted as an
   ``M`` card naming the curated deck's own device class (``pfet``/``nfet``),
   which is what ``klt extract`` writes on the layout side.

3. **``m`` (multiplicity) is folded into ``W``.** ``XMtail ... w=5u m=3`` is
   three parallel 5 um devices; the layout draws exactly that (three
   fingers), and ``klt lvs``'s ``options.combine_devices`` folds them back
   into one ``W=15U`` device before comparing. The reference therefore
   states the folded width. This is the one transformation that could hide a
   real error -- a layout that drew two fingers instead of three would still
   have to miss 5 um of width to be caught -- so the drawn finger count is
   asserted against the schematic's own ``m`` in the generator, and the
   per-device widths are printed by both scripts.

4. **Resistor values are stated in the deck's own first-order model, and the
   PDK model's value is carried alongside as a comment.** See
   :func:`rhigh_reference_ohms` -- this is the one place where the two sides
   genuinely disagree about physics, and the disagreement is written into
   the artifact rather than papered over with a tolerance.

The MoM capacitor is the one device with no plain-element form at all: KLayout
has no SPICE element letter for a custom ``GenericDeviceExtractor`` class, so
it is emitted as the same ``X ... cap_cmomi PARAMS: W= L=`` card ``klt
extract`` itself writes, and both sides compare it as a *subcircuit instance*
rather than as a device.

What that actually costs was measured, not assumed (``run_flow.sh`` stage 7
carries all three mutations as standing controls). KLayout's plain SPICE
reader mangles an undefined subcircuit's parameters into its circuit *name* --
``CAP_CMOMI(L=30,W=0.1K)`` -- so presence, connectivity **and** parameters all
do get compared, by string equality of that name. The price is that the device
never enters the report's device census (12 compared devices for this
13-device cell), ``options.parameter_tolerance`` never reaches it (a 0.001%
width difference hard-fails under a 10% tolerance), and any difference at all
degrades to the same unattributed ``topology: circuit could not be matched to
a counterpart``. That is an upstream tool gap, not a modelling choice here --
filed as ``2AMLogic/klayout-tools#1942``; see ``layout/README.md`` "LVS: what
is compared at device level, and what is not".
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import common_sg13cmos5l as c  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Curated-deck device class per PDK model name. ``klt extract`` writes these
#: class names on the layout side (``decks/sg13cmos5l.py``'s ``nfet``/``pfet``
#: roles); the HV flavour itself is drawn (``ThickGateOx``) and *is* modelled
#: by the deck's ``mos_flavours`` -- it shows up as the bound model name under
#: ``klt extract --pdk`` -- but the extracted device *class* both sides
#: compare on is the generic one.
MOS_CLASS = {"sg13_hv_pmos": "pfet", "sg13_hv_nmos": "nfet"}

#: PDK models this generator knows how to emit. Anything else in the netlist
#: is a hard error rather than a silent skip: a device the reference drops is
#: a device LVS stops checking.
KNOWN_MODELS = set(MOS_CLASS) | {"rhigh", "cap_cmomi"}


def _um(value: str) -> float:
    """Parse a netlist geometry literal (``2800u``, ``1e-6``, ``28.81e-6``)
    into micrometres. A bare literal is SI metres for this PDK -- SG13CMOS5L
    ships no ambient ``.option scale``, the same convention klayout-tools'
    own ``pdk_models.geometry_style_for_family`` records for this family."""
    text = value.strip().lower()
    if text.endswith("u"):
        return float(text[:-1])
    return float(text) * 1e6


def rhigh_reference_ohms(w_um: float, l_seg_um: float, bends: int) -> tuple[float, float]:
    """Return ``(deck_ohms, pdk_model_ohms)`` for one drawn ``rhigh``.

    ``deck_ohms`` is what the curated deck's extractor computes for the
    geometry :func:`common_sg13cmos5l.draw_rhigh` actually draws:
    ``R = L/W * sheet_rho`` with ``L`` taken from the body's own area at the
    drawn width, i.e. ``(b+1)*l + b*ps`` of conductor at ``w``. KLayout's
    resistor extractor derives ``L``/``W`` from the body region's area and
    perimeter, which for this serpentine reproduces that figure exactly (it
    was confirmed against a real ``klt extract`` run, not assumed -- the
    committed ``*.extracted.spice`` carries the same numbers).

    ``pdk_model_ohms`` is what the *PDK's own* ngspice model computes for the
    same declared device: ``R = rzspec/w + rspec * leff/weff`` with
    ``leff = (b+1)*l + (2/kappa*weff + ps)*b`` and ``weff = w - 0.04u``
    (``libs.tech/ngspice/models/resistors_mod.lib``, and the identical
    expression in ``rhigh.sym``'s own ``value`` attribute).

    **The two differ by about 7%**, and the difference is real physics the
    curated deck's single-coefficient model does not carry: the line-width
    delta (``weff``, +4.2%) and a measured corner-crowding term per bend
    (+2.9%), both of which the PDK models and ``R = L/W * rho`` cannot. The
    reference netlist states the *deck* figure, so the LVS compare is
    geometry-vs-geometry rather than one resistance model against a different
    one -- and prints the PDK figure next to it, so nothing about that choice
    is hidden. Neither number is "the" resistance: the device's identity in
    both netlists is its drawn ``w``/``l``/``b``, which is what a reader
    should compare.
    """
    stripes = bends + 1
    drawn_len = stripes * l_seg_um + bends * c.RHIGH_PS_UM
    deck_ohms = drawn_len / w_um * c.RHIGH_SHEET_RHO
    weff = w_um - 0.04
    leff = stripes * l_seg_um + (2.0 / 1.85 * weff + c.RHIGH_PS_UM) * bends
    pdk_ohms = 1.6e-4 / (w_um * 1e-6) + c.RHIGH_SHEET_RHO * leff / weff
    return deck_ohms, pdk_ohms


def parse_subckts(path: pathlib.Path) -> dict[str, dict]:
    """Parse every ``.subckt`` in a netlist export into
    ``{name: {"ports": [...], "instances": [(inst, nodes, model, params)]}}``.

    Deliberately narrow: this reads the exact shape ``design/netlist.py``
    emits (one instance per line, no continuations, no nested control cards),
    and raises on anything it does not recognise rather than skipping it.
    """
    subckts: dict[str, dict] = {}
    current: dict | None = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        low = line.lower()
        if low.startswith(".subckt"):
            fields = line.split()
            current = {"ports": fields[2:], "instances": []}
            subckts[fields[1]] = current
            continue
        if low.startswith(".ends"):
            current = None
            continue
        if current is None:
            continue
        fields = line.split()
        inst = fields[0]
        params = {}
        rest = fields[1:]
        while rest and "=" in rest[-1]:
            key, _, value = rest.pop().partition("=")
            params[key.lower()] = value
        model = rest[-1]
        nodes = rest[:-1]
        current["instances"].append((inst, nodes, model, params))
    if not subckts:
        raise SystemExit(f"no .subckt found in {path}")
    return subckts


def flatten(subckts: dict[str, dict], top: str) -> list[tuple[str, list[str], str, dict]]:
    """Inline every sub-subcircuit instance of ``top`` into one flat device
    list, binding each callee's formal ports to the caller's nets."""
    flat: list[tuple[str, list[str], str, dict]] = []
    for inst, nodes, model, params in subckts[top]["instances"]:
        if model in KNOWN_MODELS:
            flat.append((inst, nodes, model, params))
            continue
        if model not in subckts:
            raise SystemExit(
                f"{top}: instance {inst} references '{model}', which is neither a "
                f"known PDK device {sorted(KNOWN_MODELS)} nor a subcircuit in this "
                "netlist -- refusing to drop a device from the reference"
            )
        binding = dict(zip(subckts[model]["ports"], nodes, strict=True))
        for sub_inst, sub_nodes, sub_model, sub_params in subckts[model]["instances"]:
            if sub_model not in KNOWN_MODELS:
                raise SystemExit(f"{model}: nested hierarchy under {sub_inst} is not supported")
            flat.append(
                (
                    sub_inst,
                    [binding.get(n, n) for n in sub_nodes],
                    sub_model,
                    sub_params,
                )
            )
    return flat


def render(netlist: pathlib.Path, top_cell: str, source_top: str) -> str:
    subckts = parse_subckts(netlist)
    devices = flatten(subckts, source_top)
    ports = subckts[source_top]["ports"]

    lines = [
        f"* {top_cell} -- LVS reference netlist, generated by layout/lvs_reference.py",
        "* DO NOT EDIT BY HAND. Regenerate with:",
        "*   python3 layout/lvs_reference.py",
        f"* Source: {netlist.relative_to(REPO_ROOT)}"
        f" (.subckt {source_top}, flattened)",
        "* Plain-element form: `klt lvs` reads its reference with a bare",
        "* NetlistSpiceReader, which would read the schematic's own X cards as",
        "* subcircuit instances rather than devices. See this generator's module",
        "* docstring for all four transformations applied here.",
        f".SUBCKT {top_cell} {' '.join(ports)}",
    ]

    for inst, nodes, model, params in devices:
        # The schematic export's own instance names already carry the SPICE
        # `X` (subcircuit-call) prefix; strip it so the plain-element card's
        # own element letter is not doubled (`XMpass` -> `MMpass`).
        inst = inst[1:] if inst[:1].upper() == "X" and len(inst) > 1 else inst
        if model in MOS_CLASS:
            drain, gate, source, bulk = nodes
            w = _um(params["w"]) * int(params.get("m", "1"))
            length = _um(params["l"])
            mult = int(params.get("m", "1"))
            if mult > 1:
                lines.append(
                    f"* {inst}: schematic m={mult} x w={_um(params['w']):g}u folded "
                    f"into one W={w:g}u device (the layout draws {mult} fingers; "
                    "`klt lvs` combine_devices folds them)"
                )
            lines.append(
                f"M{inst} {drain} {gate} {source} {bulk} {MOS_CLASS[model]} "
                f"L={length:g}U W={w:g}U"
            )
        elif model == "rhigh":
            a, bnode, bulk = nodes
            w = _um(params["w"])
            l_seg = _um(params["l"])
            bends = int(params.get("b", "0"))
            deck_ohms, pdk_ohms = rhigh_reference_ohms(w, l_seg, bends)
            lines.append(
                f"* {inst}: rhigh w={w:g}u l={l_seg:g}u b={bends} "
                f"({bends + 1} stripes) -- deck model {deck_ohms:.1f} ohm, "
                f"PDK ngspice model {pdk_ohms:.1f} ohm"
            )
            lines.append(f"R{inst} {a} {bnode} {bulk} {deck_ohms:.1f} rhigh")
        elif model == "cap_cmomi":
            a, bnode = nodes
            w = _um(params["w"])
            length = _um(params["l"])
            lines.append(
                f"X{inst} {a} {bnode} cap_cmomi PARAMS: W={w:g} L={length:g}"
            )
        else:  # pragma: no cover -- KNOWN_MODELS guards this
            raise SystemExit(f"unhandled model {model}")

    lines += [f".ENDS {top_cell}", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", default="ldo_core_cmos5l")
    parser.add_argument("--top", default="sg13cmos5l_ldo_core_cmos5l")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    netlist = REPO_ROOT / "design" / "sg13cmos5l" / "netlist" / f"{args.cell}.spice"
    out = pathlib.Path(
        args.out
        or REPO_ROOT
        / "layout"
        / f"sg13cmos5l-{args.cell}"
        / f"sg13cmos5l-{args.cell}.lvs_reference.spice"
    )
    text = render(netlist, args.top, args.cell)
    out.write_text(text)
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    print(text)


if __name__ == "__main__":
    main()
