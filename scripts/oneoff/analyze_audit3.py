#!/usr/bin/env python3
import json, re, sys
from collections import Counter

log_path = sys.argv[1] if len(sys.argv) > 1 else "logs/audit_v23_20260404T201529Z.json"

with open(log_path) as f:
    data = json.load(f)

results = data["results"]
fails = [r for r in results if r["is_code"] and not r["check_pass"] and not r["skipped"]]

# design_patterns unknown module
dp_fails = [r for r in fails if r["source"] == "aiken_design_patterns" and "unknown" in r.get("error","").lower()]
print(f"design_patterns unknown: {len(dp_fails)}")
for r in dp_fails[:6]:
    print("  INSTR:", r["instruction"][:70])
    for line in r.get("error","").splitlines():
        line = line.strip()
        if line and ("error" in line.lower() or "unknown" in line.lower() or "module" in line.lower()):
            print("  ERR  :", line[:120])
            break
    print()

print("---")
# Also show design_patterns parser errors
dp_parser = [r for r in fails if r["source"] == "aiken_design_patterns" and "aiken::parser" in r.get("error","")]
print(f"design_patterns parser: {len(dp_parser)}")
for r in dp_parser[:4]:
    print("  INSTR:", r["instruction"][:70])
    code = r.get("output","")
    print("  CODE :", code[:200].replace("\n"," | "))
    for line in r.get("error","").splitlines():
        if "unexpected" in line.lower():
            print("  ERR  :", line.strip()[:120])
            break
    print()
