#!/usr/bin/env python3
"""Derive the headline numbers of the issue-#67 enable smoke record from the raw
`klt sim` reports (stdlib only).  usage: derive.py <record-dir>/raw

Loop gain: the bench breaks the loop with Vbreak (ac 1) between FB and FBAMP, so
v(fbamp) = v(fb) - 1 and L = -v(fb)/v(fbamp) = fb/(1-fb); |L| = 1 exactly when
Re(fb) = 0.5, which is what the .meas WHEN searches for."""
import cmath, json, math, os, sys

raw = sys.argv[1]
def load(n):
    r = json.load(open(os.path.join(raw, f"{n}.sim.json")))
    return {c["corner_id"]: {m["name"]: m["value"] for m in c["measurements"]} for c in r["corners"]}
def one(n):
    return next(iter(load(n).values()))

def loop(n):
    m = one(n)
    L0 = complex(m["fb_re_1hz"], m["fb_im_1hz"]); L0 = L0 / (1 - L0)
    fu = complex(0.5, m["fb_im_at_ugf"]); Lu = fu / (1 - fu)
    ph = math.degrees(cmath.phase(Lu))
    return {"lg0_db": 20 * math.log10(abs(L0)), "ugf_hz": m["ugf_hz"], "|L|_at_ugf": abs(Lu), "phase_at_ugf_deg": ph, "phase_margin_deg": 180 + ph}
def psrr(n):
    m = one(n)
    return {k.replace("vdb_vout", "psrr_db"): -v for k, v in m.items()}

print("== loop gain (tt/27C, Vin 3.30 V, 1 mA, Cc = 5.47 pF linear stand-in, Cout 1 uF) ==")
a, b = loop("baseline-loopgain"), loop("enable-loopgain")
for k in a: print(f"{k:18s} baseline {a[k]:.6g}  enable {b[k]:.6g}  delta {b[k]-a[k]:+.3g}")
print("== PSRR ==")
a, b = psrr("baseline-psrr"), psrr("enable-psrr")
for k in a: print(f"{k:18s} baseline {a[k]:.6f}  enable {b[k]:.6f}  delta {b[k]-a[k]:+.2e}")
print("== DC regulating state, EN tied to VIN vs pre-#67 design (|max abs delta| per quantity) ==")
ea, ba = load("enable-reg"), load("baseline-reg")
worst = {}
for cid in ea:
    for k, v in ea[cid].items():
        base = k.rsplit("_", 1)[0]
        d = abs(v - ba[cid][k]); worst[base] = max(worst.get(base, 0), d)
for k, d in worst.items(): print(f"{k:10s} max|delta| {d:.3g}")
print("== disabled: pass-device leakage, VOUT clamped to 0 V ==")
for k, v in one("enable-leak").items(): print(k, v)
