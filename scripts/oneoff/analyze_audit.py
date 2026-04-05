#!/usr/bin/env python3
"""Analyze audit log failures."""
import json, re, sys
from collections import Counter, defaultdict

log_path = sys.argv[1] if len(sys.argv) > 1 else "logs/audit_v23_20260404T201529Z.json"

with open(log_path) as f:
    data = json.load(f)

results = data["results"]
fails = [r for r in results if r["is_code"] and not r["check_pass"] and not r["skipped"]]

print(f"Total failures: {len(fails)}")
print()

# Parser token breakdown
parser_fails = [r for r in fails if "aiken::parser" in r.get("error","")]
token_ctr = Counter()
for r in parser_fails:
    m = re.search(r"unexpected token '([^']+)'", r.get("error",""))
    tok = m.group(1) if m else "(other)"
    token_ctr[tok] += 1

print(f"Parser errors: {len(parser_fails)}")
for tok, n in token_ctr.most_common(12):
    print(f"  {n:3d}x  unexpected '{tok}'")
print()

# Backtick failures — classify
backtick_fails = [r for r in parser_fails if chr(96) in r.get("error","")]
has_fence = sum(1 for r in backtick_fails if "```" in r.get("output",""))
has_bold  = sum(1 for r in backtick_fails if "**" in r.get("output",""))
bt_in_comment = sum(1 for r in backtick_fails
    if re.search(r'//[^\n]*`', r.get("output","")))

print(f"Backtick errors: {len(backtick_fails)}")
print(f"  has triple-fence (markdown body)  : {has_fence}")
print(f"  has ** (markdown text)            : {has_bold}")
print(f"  backtick in // comment            : {bt_in_comment}")
pure = [r for r in backtick_fails if "```" not in r.get("output","") and "**" not in r.get("output","")]
print(f"  no obvious markdown markers       : {len(pure)}")
print()
if pure:
    print("  Sample pure-code backtick failures:")
    for r in pure[:3]:
        code = r.get("output","")
        for line in code.splitlines():
            if "`" in line:
                print(f"    LINE: {line[:100]}")
                break
    print()

# Unknown module errors
mod_fails = [r for r in fails if "unknown::module" in r.get("error","")]
print(f"Unknown module errors: {len(mod_fails)}")
mod_ctr = Counter()
for r in mod_fails:
    m = re.search(r"Unknown module `([^`]+)`", r.get("error",""))
    if m:
        mod_ctr[m.group(1)] += 1
for mod, n in mod_ctr.most_common(10):
    print(f"  {n:3d}x  {mod}")
print()

# Cycle errors
cycle_fails = [r for r in fails if "check::cycle" in r.get("error","")]
print(f"Cycle errors: {len(cycle_fails)}")
for r in cycle_fails[:2]:
    print(f"  SRC: {r['source']}")
    for line in r.get("error","").splitlines():
        if "cycle" in line.lower() or "×" in line:
            print(f"  ERR: {line.strip()[:100]}")
            break
print()

# Type mismatch
type_fails = [r for r in fails if "type_mismatch" in r.get("error","")]
print(f"Type mismatch errors: {len(type_fails)}")
for r in type_fails[:3]:
    err = r.get("error","")
    print(f"  SRC: {r['source'][:30]}  INSTR: {r['instruction'][:60]}")
    for line in err.splitlines():
        if "expected" in line.lower() or "found" in line.lower() or "×" in line:
            print(f"  ERR: {line.strip()[:100]}")
            break
print()

# design_patterns unknown module
dp_mod_fails = [r for r in fails if r["source"] == "aiken_design_patterns" and "unknown::module" in r.get("error","")]
print(f"aiken_design_patterns unknown module: {len(dp_mod_fails)}")
dp_mod_ctr = Counter()
for r in dp_mod_fails:
    m = re.search(r"Unknown module `([^`]+)`", r.get("error",""))
    if m:
        dp_mod_ctr[m.group(1)] += 1
for mod, n in dp_mod_ctr.most_common(10):
    print(f"  {n:3d}x  {mod}")
