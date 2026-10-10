#!/usr/bin/env python3
"""Flatten klt sim JSON reports into `request,unit,measurement,value,status` CSV rows.
usage: summarize.py report.sim.json [...]"""
import json, os, sys
print("request,unit,measurement,value,status")
for p in sys.argv[1:]:
    r = json.load(open(p))
    req = os.path.basename(p).replace(".sim.json", "")
    for c in r["corners"]:
        for m in c["measurements"]:
            print(f"{req},{c['corner_id']},{m['name']},{m['value']},{m['status']}")
