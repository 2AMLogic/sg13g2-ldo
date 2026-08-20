# sg13g2-ldo

A low-dropout linear regulator (LDO) on
[IHP SG13G2](https://github.com/IHP-GmbH/IHP-Open-PDK), a 130 nm SiGe BiCMOS
open PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: just opened.** Nothing is designed yet. The tooling path is open —
`klt` resolves this PDK and a curated SG13G2 DRC/LVS starter deck ships with
klayout-tools — but the deck is new and starter-grade, so expect it to have
gaps this design will be the first to find.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result under PVT corners. Where the agents hit friction with the
open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction is
filed as a public issue against the tool itself, so the fix benefits everyone
using SG13G2, not just this repo.

## Why this block, on this PDK

This is a **port, not a new design**. The fleet has already carried this
block through two PDKs — the ratified, corner-verified
[gf180-ldo](https://github.com/2AMLogic/gf180-ldo) and its mirror
[sky130-ldo](https://github.com/2AMLogic/sky130-ldo) — so the circuit, the
spec structure, and the verification harness are known quantities. That is
the whole experimental design: **the PDK is the variable, not the design.**
Anything that breaks here should be assumed to be the PDK, the deck, or the
tools before it is assumed to be the circuit. Work starts from the sibling
repos' schematics, specs, and decision records, not from a blank page.

SG13G2 being a **BiCMOS** process is a genuine difference, not just a rule
deck swap: it offers real bipolar devices alongside CMOS, which reopens the
two choices that define an LDO — the pass device and the error amplifier —
and hands extraction and LVS a device class the CMOS ports never exercised.
Where SG13G2's device set makes the sibling design's choice wrong rather
than merely different, the departure is argued in a decision record.

The SG13G2 DRC/LVS deck in klayout-tools is a recently shipped starter deck.
Part of this canary's job is to find what it cannot check yet and file those
gaps upstream — never to route around them.

## Target specification (DRAFT — to be ratified via spec/)

Port parity: the targets below mirror the ratified gf180-ldo spec — same
block, third PDK. Ratification must confirm each row against SG13G2's device
flavors (supply rails, pass-device options); where the PDK makes a target
inappropriate rather than merely harder, change it through a decision record
and record why.

| Parameter | Target | Stretch |
|---|---|---|
| Input | 3.3 V ±10% — confirm against SG13G2 device flavors | — |
| Output | 1.8 V ±2% (fixed) | programmable variants deferred |
| Load | 0–50 mA (no external preload assumed) | 100 mA |
| Dropout @ 50 mA | < 300 mV worst corner | < 200 mV |
| Line / load regulation | < 5 mV/V; < 1% over full load, inside the accuracy window | — |
| PSRR | > 50 dB @ 1 kHz, > 20 dB @ 100 kHz | > 60 dB @ 1 kHz |
| Iq (excluding load) | < 30 µA at no load and at full load | < 10 µA |
| Current limit | 65–80 mA brickwall over PVT; short-survivable | — |
| Startup | monotonic, controlled ramp, inside ±2% within 3 ms of enable | — |
| Stability | 0–50 mA, C_out 0.33–4.7 µF effective, ESR 0–500 mΩ; PM ≥ 45°, GM ≥ 10 dB worst corner | capless variant (separate fork) |

Maturity ladder: spec ratified → schematic simulated across PVT → layout
DRC/LVS-clean → post-layout re-verification → shuttle seat → measured
silicon. **Current position: pre-spec.**

## Repo layout

```
spec/          ratified spec + decision records
design/        schematics / netlists (xschem)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
