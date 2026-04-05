#!/usr/bin/env python3
import json, re, sys
from collections import Counter

log_path = sys.argv[1] if len(sys.argv) > 1 else "logs/audit_v23_20260404T201529Z.json"

with open(log_path) as f:
    data = json.load(f)

results = data["results"]
fails = [r for r in results if r["is_code"] and not r["check_pass"] and not r["skipped"]]

# Unknown modules
mod_fails = [r for r in fails if "unknown::module" in r.get("error","")]
mod_ctr = Counter()
for r in mod_fails:
    for m in re.finditer(r"Unknown module `([^`]+)`", r.get("error","")):
        mod_ctr[m.group(1)] += 1
print("All unknown modules:")
for mod, n in mod_ctr.most_common():
    print(f"  {n:3d}x  {mod}")

print()

# Cycle errors
cycle_fails = [r for r in fails if "check::cycle" in r.get("error","")]
print(f"Cycle errors: {len(cycle_fails)}")
for r in cycle_fails[:3]:
    code = r.get("output","")
    print("  CODE:", code[:250].replace("\n"," | "))
    for line in r.get("error","").splitlines():
        if "cycle" in line.lower() or "alias" in line.lower() or "type" in line.lower():
            print("  ERR:", line.strip()[:120])
            break
    print()

# Let-at-toplevel
print("Let-at-toplevel samples:")
let_fails = [r for r in fails if "aiken::parser" in r.get("error","")
             and "unexpected token 'let'" in r.get("error","")]
for r in let_fails[:3]:
    print("  SRC:", r["source"])
    print("  CODE:", r.get("output","")[:150].replace("\n"," | "))
    print()
