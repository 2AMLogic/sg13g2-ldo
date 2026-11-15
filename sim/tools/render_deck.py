#!/usr/bin/env python3
"""The single @@TOKEN@@ testbench-template renderer (issue #236).

Every ngspice testbench template under sim/ declares its parameters as
@@TOKEN@@ placeholders. Until #236 each driver carried its own copy of the
substitution chain -- eight of them across five files, two in
ldo-cmos5l-pvt-sweep/run_sweep.sh alone (the --check-env preflight and
gen_netlist rendered the same three templates through two different token
lists) -- and only startup_campaign.py checked for unsubstituted
placeholders, so the other seven could emit a deck containing a literal
@@TOKEN@@. This module is the one renderer every site calls, and it ALWAYS
fails loudly on any placeholder left in the rendered text (the
startup_campaign.py rule, made universal).

Substitution is a plain str.replace per @@KEY@@. The old shell sites used
`sed -e "s|@@KEY@@|value|g"` chains, which mangle values containing `|`,
`&` or backslashes; str.replace does not (a deliberate behavioural change,
asserted in test_render_deck.py). For every value the shipped scripts
substitute today the output is byte-identical to the old sed chains --
test_render_deck.py proves that against sed itself for every real
template, so a deck cannot move when a site converts.

Python API:
    import render_deck
    text = render_deck.render(template_text, {"MOS_SECTION": "mos_tt", ...})
    render_deck.render_file(template_path, out_path, mapping)

Shell API (the .sh call sites):
    python3 sim/tools/render_deck.py TEMPLATE OUT KEY=VALUE...
"""
import argparse
import re
import sys

# The placeholder shape every template uses. The leftover guard keys on the
# bare "@@" marker (any stray @@ fails, even one this regex would not
# classify); the regex only formats the diagnostics.
_PLACEHOLDER = re.compile(r"@@([A-Za-z0-9_]+)@@")


class RenderError(Exception):
    """A template could not be rendered: leftover @@...@@ or bad input."""


def render(text, mapping):
    """Substitute every @@KEY@@ in text from mapping (in mapping order).

    Raises RenderError if any @@ marker survives substitution, naming the
    leftover tokens: a deck with a literal placeholder must never reach a
    simulator (or a record) silently.
    """
    if not isinstance(text, str) or not isinstance(mapping, dict):
        raise RenderError("render() takes (str, dict)")
    for key, value in mapping.items():
        if not re.fullmatch(r"[A-Za-z0-9_]+", key):
            raise RenderError(f"placeholder key {key!r} is not [A-Za-z0-9_]+")
        text = text.replace(f"@@{key}@@", str(value))
    if "@@" in text:
        leftovers = sorted(set(_PLACEHOLDER.findall(text)))
        what = f"unsubstituted placeholder(s) {leftovers}" if leftovers else "a stray @@ marker"
        raise RenderError(f"{what} left in rendered text; supply every token the template declares")
    return text


def render_file(template, out, mapping):
    """Render the template file to out with mapping (both paths, not contents)."""
    with open(template, encoding="utf-8") as f:
        text = f.read()
    rendered = render(text, mapping)
    with open(out, "w", encoding="utf-8") as f:
        f.write(rendered)
    return rendered


def _parse_kv(pairs):
    mapping = {}
    for pair in pairs:
        if "=" not in pair:
            raise RenderError(f"argument {pair!r} is not KEY=VALUE")
        key, value = pair.split("=", 1)
        if not key:
            raise RenderError(f"argument {pair!r} has an empty key")
        mapping[key] = value
    return mapping


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Render a @@TOKEN@@ testbench template; fails on any placeholder left over.")
    ap.add_argument("template", help="template path")
    ap.add_argument("out", help="rendered output path")
    ap.add_argument("pairs", nargs="+", metavar="KEY=VALUE",
                    help="one per template token (unused tokens are harmless; missing ones are fatal)")
    a = ap.parse_args(argv)
    try:
        render_file(a.template, a.out, _parse_kv(a.pairs))
    except (RenderError, OSError) as exc:
        print(f"render_deck: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
