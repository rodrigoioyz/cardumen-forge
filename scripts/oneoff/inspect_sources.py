#!/usr/bin/env python3
import json, sys

INPUT = "data/processed/dataset_v22.jsonl"
TARGET_SOURCES = ["aiken_design_patterns", "correction_set_v2"]

examples = []
with open(INPUT) as f:
    for line in f:
        ex = json.loads(line.strip())
        examples.append(ex)

for source in TARGET_SOURCES:
    subset = [e for e in examples if e.get("source") == source]
    print(f"\n{'='*60}")
    print(f"SOURCE: {source}  ({len(subset)} examples)")
    print(f"{'='*60}")

    fence = sum(1 for e in subset if "```" in e["output"])
    starts_code = sum(1 for e in subset if e["output"].strip().startswith("use ") or
                      e["output"].strip().startswith("validator "))
    print(f"  has markdown fence:    {fence}")
    print(f"  starts with code:      {starts_code}")
    print(f"  prose (neither):       {len(subset) - fence - starts_code}")

    print(f"\n  --- First 3 examples ---")
    for i, ex in enumerate(subset[:3]):
        print(f"\n  [{i+1}] {ex['instruction'][:90]}")
        print(f"       {ex['output'][:300]}")
        print()
