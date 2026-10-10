"""Static guard for the row-2 bench versioning split (issue #88).

Run: python3 -m unittest sim/ldo-cmos5l-monte-carlo/test_deck_versioning.py

The committed record 20261009-003009-3ee8306 ran the five-port bench
tb_row2_accuracy.spice; every one of its raw reports pins that file by sha256
(environment.netlist_closure). Issue #67 made the core six-port (EN), so new
submissions use the successor tb_row2_accuracy_en.spice. `run_campaign.sh
check` re-derives records from their raw reports only and would NOT notice an
in-place edit of the historical deck, so these tests pin the split instead:

  * the historical deck keeps its exact bytes, and every bench file a committed
    raw report cites from this directory still hashes to the cited value;
  * every live request-row2-*.json selects the successor, never the
    historical deck;
  * the successor's core instance has exactly as many nodes as the current
    `.subckt ldo_core_cmos5l` has ports, with EN tied to VIN;
  * apart from that one instance (and comments) the successor is the
    historical deck card for card.

Stdlib only; no PDK, no simulator.
"""
import glob
import hashlib
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CORE = ROOT / "design" / "sg13cmos5l" / "netlist" / "ldo_core_cmos5l.spice"
HISTORICAL = "tb_row2_accuracy.spice"
HISTORICAL_SHA256 = "b994dbb053ec99fe38ae4bca7fbe9099e9fcd9f77ea2c38ddc0f4f367dadbd45"
SUCCESSOR = "tb_row2_accuracy_en.spice"
LIVE_REQUESTS = ("probe", "mc", "attribution", "negctl", "repro")
# Raw reports whose netlist_closure is checked: campaign records and the
# non-gating evidence (smoke) runs. Only files under this directory are
# re-hashed: the core netlist itself legitimately moves with the design
# (#67), which is exactly why a record pins it rather than relying on it.
RAW_GLOBS = ("records/*/raw/*.sim.json", "evidence/*/raw/*.sim.json")
BENCH_PREFIX = "sim/ldo-cmos5l-monte-carlo/"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cards(text):
    """Non-comment, non-blank SPICE lines (no continuation lines are used)."""
    return [ln.rstrip() for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("*")]


def core_instances(text):
    """Node lists of every X card instantiating ldo_core_cmos5l."""
    out = []
    for c in cards(text):
        tok = c.split()
        if tok[0].upper().startswith("X") and tok[-1] == "ldo_core_cmos5l":
            out.append(tok[1:-1])
    return out


def core_ports(text):
    for c in cards(text):
        tok = c.split()
        if tok[0].lower() == ".subckt" and tok[1] == "ldo_core_cmos5l":
            return tok[2:]
    raise AssertionError("no .subckt ldo_core_cmos5l in the core netlist")


def successor_problems(deck_text, ports):
    """Reasons the deck is NOT a valid EN-enabled bench for `ports` ([] = ok)."""
    inst = core_instances(deck_text)
    if len(inst) != 1:
        return [f"expected exactly one ldo_core_cmos5l instance, found {len(inst)}"]
    nodes = inst[0]
    probs = []
    if len(nodes) != len(ports):
        probs.append(f"instance has {len(nodes)} nodes, core has {len(ports)} ports {ports}")
        return probs
    m = dict(zip(ports, nodes))
    if "EN" not in m:
        probs.append("core has no EN port")
    elif m["EN"] != m.get("VIN"):
        probs.append(f"EN is wired to {m['EN']!r}, not to the VIN node {m.get('VIN')!r}")
    return probs


def drift_problems(hist_text, succ_text):
    """Reasons the successor differs from the historical deck other than in
    the core instance's appended port(s) ([] = ok)."""
    probs = []
    h = [c for c in cards(hist_text) if not core_instances(c)]
    s = [c for c in cards(succ_text) if not core_instances(c)]
    if s != h:
        probs.append("non-instance cards differ from the historical deck")
    hi, si = core_instances(hist_text), core_instances(succ_text)
    if not hi or not si or si[0][:len(hi[0])] != hi[0]:
        probs.append("core instance does not extend the historical node list")
    return probs


class DeckVersioningTests(unittest.TestCase):
    def setUp(self):
        self.hist = (HERE / HISTORICAL).read_text()
        self.succ = (HERE / SUCCESSOR).read_text()
        self.ports = core_ports(CORE.read_text())

    def test_historical_deck_bytes_unchanged(self):
        self.assertEqual(sha256(HERE / HISTORICAL), HISTORICAL_SHA256,
                         f"{HISTORICAL} is historical evidence (record "
                         "20261009-003009-3ee8306); add a new deck instead of editing it")

    def test_every_cited_bench_file_still_hashes(self):
        raws = sorted(p for g in RAW_GLOBS for p in glob.glob(str(HERE / g)))
        self.assertTrue(raws, "no committed raw reports found")
        cited_hist = 0
        for raw in raws:
            env = json.loads(Path(raw).read_text())["environment"]
            for ent in env["netlist_closure"]:
                if not ent["path"].startswith(BENCH_PREFIX):
                    continue
                f = ROOT / ent["path"]
                self.assertTrue(f.is_file(), f"{raw} cites missing {ent['path']}")
                self.assertEqual(sha256(f), ent["sha256"],
                                 f"{ent['path']} no longer matches the bytes {raw} ran")
                cited_hist += ent["path"].endswith("/" + HISTORICAL)
        self.assertGreater(cited_hist, 0, "no raw report cites the historical deck")

    def test_live_requests_select_successor(self):
        found = sorted(Path(p).name for p in glob.glob(str(HERE / "request-row2-*.json")))
        for name in LIVE_REQUESTS:
            self.assertIn(f"request-row2-{name}.json", found)
        for name in found:
            req = json.loads((HERE / name).read_text())
            self.assertEqual(req["netlist"], SUCCESSOR,
                             f"{name} must submit {SUCCESSOR}, not {req['netlist']}")

    def test_successor_instantiates_current_core_with_en_high(self):
        self.assertEqual(self.ports[-1], "EN")
        self.assertEqual(successor_problems(self.succ, self.ports), [])

    def test_successor_differs_only_in_core_instance(self):
        self.assertEqual(drift_problems(self.hist, self.succ), [])

    # Negative controls: the guard must reject the shapes it exists to catch.
    def test_rejects_historical_five_port_instance(self):
        self.assertTrue(successor_problems(self.hist, self.ports))

    def test_rejects_en_not_tied_to_vin(self):
        bad = self.succ.replace("IBIAS VIN ldo_core_cmos5l", "IBIAS 0 ldo_core_cmos5l")
        self.assertNotEqual(bad, self.succ)
        self.assertTrue(any("EN is wired" in p for p in successor_problems(bad, self.ports)))

    def test_rejects_duplicate_instance(self):
        bad = self.succ + "Xtwo VIN VOUT 0 VREF IBIAS VIN ldo_core_cmos5l\n"
        self.assertTrue(successor_problems(bad, self.ports))

    def test_rejects_extra_card_in_successor(self):
        bad = self.succ + "Rextra VOUT 0 1meg\n"
        self.assertEqual(successor_problems(bad, self.ports), [])  # instance still fine
        self.assertTrue(drift_problems(self.hist, bad))

    def test_rejects_reordered_core_nodes(self):
        inst = core_instances(self.succ)[0]
        swapped = " ".join([inst[1], inst[0]] + inst[2:])
        bad = self.succ.replace(" ".join(inst) + " ldo_core_cmos5l", swapped + " ldo_core_cmos5l")
        self.assertNotEqual(bad, self.succ)
        self.assertTrue(drift_problems(self.hist, bad))


if __name__ == "__main__":
    unittest.main()
