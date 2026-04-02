#!/usr/bin/env python3
"""
Cuantifica dot-import contamination en dataset_v13.
Separa correction_set (intencional) de contaminación real.
"""
import json, re
from collections import Counter

DATASET = "data/processed/dataset_v13_train.jsonl"

# Patron: imports con dot-notation en código (no en prosa)
DOT_IMPORT = re.compile(r'^use\s+\w+\.\w+', re.MULTILINE)

# Correction set (dot-imports SON intencionales aquí — muestran código malo)
def is_correction(r):
    return (r.get("source") == "correction_set" or
            "correction" in r.get("topic", "") or
            "anti" in r.get("topic", ""))

records = []
with open(DATASET, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

contaminated = []
correction_with_dot = []
clean = []

for r in records:
    output = r.get("output", "")
    if DOT_IMPORT.search(output):
        if is_correction(r):
            correction_with_dot.append(r)
        else:
            contaminated.append(r)
    else:
        clean.append(r)

print(f"Total: {len(records)}")
print(f"  Con dot-imports (NO correction): {len(contaminated)}  ← contaminación real")
print(f"  Con dot-imports (correction_set): {len(correction_with_dot)}  ← intencional, OK")
print(f"  Sin dot-imports: {len(clean)}")

print(f"\nContaminados por review_status:")
status_counts = Counter(r.get("review_status","?") for r in contaminated)
for s, n in status_counts.most_common():
    print(f"  {s}: {n}")

print(f"\nContaminados por source:")
src_counts = Counter(r.get("source","?") for r in contaminated)
for s, n in src_counts.most_common():
    print(f"  {s}: {n}")

print(f"\nMuestra de imports dot-style en contaminados:")
for r in contaminated[:5]:
    matches = DOT_IMPORT.findall(r.get("output",""))
    print(f"  [{r.get('source')}] [{r.get('review_status')}]")
    print(f"    instr: {r.get('instruction','')[:70]}")
    for m in matches[:2]:
        print(f"    import: {m}")

print(f"\nSi purgas los {len(contaminated)} contaminados:")
print(f"  Dataset resultante: {len(records) - len(contaminated)} ejemplos")
print(f"  ({len(records)} - {len(contaminated)} = {len(records) - len(contaminated)})")
