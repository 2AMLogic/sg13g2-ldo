# erc-supply-spec.json -- rationale

This used to be the spec's own `_comment` array. A klt that rejects
unrecognised spec keys (klayout-tools#2243, in the build this repo's signoff
pin now uses) refuses `_comment`, so the rationale lives here. The spec is
strict JSON with no free-form keys.

```text
klt erc supply spec for the SG13CMOS5L LDO core layout -- the T1 item 11
(power delivery, structural) evidence for klayout-tools' design-evidence
tiers checklist (item approved 2026-09-17, klayout-tools#2025). This is
the first ERC supply spec written for an IHP SG13-family PDK in the
fleet.

What this spec asserts, and why each piece is shaped this way:

- `stackup[0]` MUST carry `role: "gate"` (klt erc's own contract), so the
  stack starts at GatPoly rather than at Metal1. `active_layer` (Activ)
  makes the gate identification `poly n diff` instead of raw poly area:
  this layout's three rhigh resistors end in un-gated GatPoly contact
  heads (real poly, no gate oxide), and `poly n diff` keeps them out of
  `gates[]` entirely instead of reporting non-physical antenna ratios
  (klayout-tools docs/cli/erc.md, 'Gate area').
- GDS layer numbers are SG13CMOS5L's own, read from the PDK's own
  `libs.tech/klayout/tech/sg13cmos5l.lyp` (the same read-off documented
  in layout/common_sg13cmos5l.py's layer table) AND cross-checked against
  klayout-tools' curated `sg13cmos5l` deck's `EXTRACTION_DECK`
  (`poly=(5,0)`, `active=(1,0)`, `contact=(6,0)`,
  `metals=((8,0),(10,0),(30,0),(50,0),(126,0))`,
  `vias=((19,0),(29,0),(49,0),(125,0))`,
  `metal_labels=((8,2),(10,2),(30,2),(50,2),(126,2))`) -- not copied from
  another PDK's spec.
- Metal1 carries `label_layer` 8/2 because that is where every device's
  source escape, every well/substrate tie bar's strap, and every rhigh
  contact head carries its net text: VIN labels the Mpass source buses,
  the pass-array NWell tie strap, the error-amp's VIN well tie and the
  enable-device (XMen/XMbdis) VIN well tie; VSS
  labels the NMOS source buses and the substrate tie; VOUT labels Rtop's
  upper (divider) head.
- Metal2 carries `label_layer` 10/2 because that is where every drain
  bus carries its net text; VOUT's labels live here too (each Mpass row's
  drain bus, merged by the vertical Metal2 VOUT bus).
- Metal3 carries `label_layer` 30/2 because the global distribution
  level is one horizontal trunk per net in the routing channel
  (-70 < y < -50), and every net's trunk -- VIN, VOUT and VSS included --
  is labeled on it.
- GatPoly declares no `label_layer`: this layout puts no text on
  GatPoly.pin (5/2) at all (the only .pin text layers present in the
  stream are 8/2, 10/2, 30/2 and NWell.pin 31/2), so declaring one would
  add nothing.
- Metal4 (50/0) and TopMetal1 (126/0) exist in the PDK's stack but are
  deliberately NOT declared: this block routes no supply geometry above
  Metal3, and a stackup entry for a layer this layout never touches
  would only add zero-area noise to every net's levels[].
- `vias`: Cont (6/0) bridges GatPoly to Metal1 -- in this PDK Cont lands
  directly on Metal1, there is no li1-like local-interconnect level
  (curated deck: `contact=(6,0)`). Via1 (19/0) and Via2 (29/0) bridge the
  metal levels (M1<->M2, M2<->M3). Cont also lands on Activ, but Activ is
  intentionally not a stackup role: it is a device layer, not a level the
  supplies route on, so diffusion-level connectivity does not enter this
  graph -- the supply-island check runs on the true routing stack.
- `nets[]`: VIN, VOUT and VSS are this LDO block's three power rails, all
  declared `kind: "supply"`, which is what makes a short between any
  two of them report as the severe `erc.supply_short` rather than the
  general `erc.multiply_driven_net` -- VIN is dead shorted against VSS if
  the input rail touches ground, and VIN against VOUT if the pass device
  no longer separates them (a regulator-sized defect, not a nit). Each
  must resolve to exactly ONE electrical island: `erc.unconnected_net`
  fires on zero matches (nothing in the layout carries that label at all)
  AND on more than one (the rail is split into pieces that never touch) --
  so ZERO findings of that rule is exactly the 'one island per supply'
  verdict, not merely an absence. VREF (external reference input) and
  IBIAS (bias-mirror node at Mb0's gate/drain) and EN (enable input,
  gates of XMen/XMbdis) are control signals by the ratified topology
  decision (DR-0002), not power rails, so they are not declared.

- `devices[]`: the three rhigh resistor bodies are drawn on GatPoly
  (5/0), so the wire-connectivity model reads each meander as a wire
  and Rtop (VOUT-FB) + Rbot (FB-VSS) chain the two declared rails
  through the divider string into one island -- a FALSE
  erc.supply_short on an LVS-matched layout (the exact gap klayout-tools
  #2183 filed for supply-sensing analog blocks, fixed by the `devices[]`
  carve-out this spec uses). body_layer 128/0 (PolyRes) is this deck's
  OWN rhigh recognition marker -- the curated sg13cmos5l EXTRACTION_DECK
  declares `ResistorDevice(name="rhigh", body=(5,0), marker=(128,0))` --
  and this layout's draw_rhigh draws PolyRes exactly over each meander
  body and its two contact heads, so the subtraction removes precisely
  the device body and nothing else: the report's
  `provenance.devices[].body_area_um2 > 0` is the cross-check that the
  carve-out actually bit. The divider terminal nets (FB, MZ, G1) and
  both rails then match the full LVS extraction's own view of the
  connectivity. Cc (cap_cmomi) needs no declaration: its two plates
  are interdigitated Metal1/Metal2 rows on alternating row centres,
  each via1 row tying only that row's own same-plate metal -- plate A
  (EAOUT) and plate B (MZ) never touch, and neither is a declared
  supply, so no declared pair is bridged.

- `ties[]`: the well/substrate taps, declared and CHECKED (#59). Three ties,
  none hand-typed: the boxes are the layout generator's own `draw_tap_bar`
  calls (`common_sg13cmos5l.py`), written by `generate.py` to
  `erc-tap-boxes.json`, turned into `ties[]` by `layout/erc_ties.py`, and
  `layout/run_flow.sh` fails if the committed spec's `ties[]` differ from
  that derivation (so a moved tap bar cannot leave a stale assertion).
  * `nwell_tie_VIN`: `well_layer` NWell (31/0), `tap_layer` Activ (1/0)
    narrowed by `tap_requires` nSD (7/0) -- layer-derived, because this
    stream draws implants (inside an NWell, nSD-covered Activ is a tap and
    PMOS source/drain Activ, pSD-covered, is not) -- and by `tap_boxes` (the
    pass-array tie strap, the error-amp's VIN well tie and the enable
    devices' VIN well tie, added for #68; XMen/XMbdis bodies are VIN-tied). The earlier
    rationale for omitting `ties[]` (klayout-tools#2169, a declared tie
    collapsing a routed layout into one island) no longer applies: the fix is
    upstream, and `erc_status` stays `clean` with ties declared.
  * `nwell_tie_TAIL`: the diff pair's own well, separate net, separate entry.
    `well_requires_boxes` (the same tap boxes) selects which NWell each n-tie
    is about, so the TAIL well is not graded against VIN and vice versa
    (klayout-tools#2540).
  * `substrate_tie_VSS`: the NMOS group sits in native substrate -- no drawn
    well layer -- so `well_layer` is `null` and `well_boxes` asserts the
    region (klayout-tools#2255): the tap bar grown by 20 um, the PDK deck's
    LU.b reach (every N+ implant within 20 um of a substrate tie). Tap layer
    Activ narrowed by pSD (14/0) and the tap box.
  Every tie therefore rests on a caller assertion and is reported under
  `erc_coverage.checked_by_assertion` and `checked_by_well_assertion`, not
  as an unconditional geometric pass. `well_assertion_coverage` for the
  substrate tie reports `uncovered_tap_fraction` ~0.977: the drawn Activ
  outside the asserted region (every device's source/drain contact) was not
  examined by that tie. Falsifiability: `run_flow.sh` stage 8b moves one tap
  box off its tap and requires `erc.missing_tie` to fire. The wire-level
  evidence that still stands beside it: the contacted tie bars are extracted
  and compared by `klt lvs` (status `match`), and the PDK deck's LU.b ran
  clean over this GDS.
- No `--pdk` is passed: klt erc has a real antenna-ratio table only for
  sky130, so every antenna verdict in the report is `unchecked`. Antenna
  is not item 11's subject (klayout-tools#1994); any antenna-class
  finding in the report would be real but does not grade this item.

- Report provenance: this report must be produced by a klt that carries the
  `provenance`/`status` envelope (#1968), the `devices[]` carve-out (#2183),
  `well_layer: null` + `well_boxes` (#2255) and `well_requires_boxes`
  (#2540) -- all in upstream main, ahead of the 0.5.0 release pip/uv installs.
  The committed report's `provenance.klt_version` records the exact source
  build (0.7.0+gb82427b30c96, also the CI signoff pin). All layer numbers above are
  independent of the klt version -- they come from the PDK and the
  curated deck, not from the tool.

Run it from the repo root against the committed GDS (one top cell, so no
--top is needed; `layout/run_flow.sh` stage 8 does this and asserts the result):

    klt erc layout/sg13cmos5l-ldo_core_cmos5l/sg13cmos5l-ldo_core_cmos5l.gds \
      layout/sg13cmos5l-ldo_core_cmos5l/erc-supply-spec.json --format json

```
