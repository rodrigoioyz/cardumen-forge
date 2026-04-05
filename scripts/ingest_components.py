#!/usr/bin/env python3
"""
ingest_components.py — Merge verified component files into dataset_v23.jsonl

Converts:
  {prompt, output, category}
to dataset format:
  {instruction, input, output, source, topic, review_status, lang}

Deduplicates by SHA256 of output before appending.

Usage:
    python3 scripts/ingest_components.py --dry-run
    python3 scripts/ingest_components.py
    python3 scripts/ingest_components.py --backup
"""

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT       = Path(__file__).parent.parent
DATASET    = ROOT / "data" / "processed" / "dataset_v23.jsonl"
COMPONENTS = ROOT / "data" / "processed" / "components"

COMPONENT_FILES = [
    ("datum_inline_verified.jsonl",  "spend/datum_inline"),
    ("multisig_verified.jsonl",      "spend/multisig_threshold"),
]


def load_existing_hashes(dataset: Path) -> set:
    hashes = set()
    if not dataset.exists():
        return hashes
    with dataset.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                h = hashlib.sha256(obj.get("output", "").encode()).hexdigest()
                hashes.add(h)
    return hashes


def component_to_dataset(obj: dict) -> dict:
    """Convert component record to dataset format."""
    prompt   = obj.get("prompt", "")
    output   = obj.get("output", "")
    category = obj.get("category", "unknown")
    return {
        "instruction":   prompt,
        "input":         "",
        "output":        output,
        "source":        "generated_verified",
        "topic":         category,
        "review_status": "VERIFIED_V3_ALIGNED",
        "lang":          "en",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without writing")
    parser.add_argument("--backup", action="store_true",
                        help="Create timestamped backup of dataset before writing")
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print(f"  ingest_components → {DATASET.name}")
    print(f"{'═'*60}\n")

    # Load existing hashes for dedup
    print("  Loading existing dataset hashes...", end=" ", flush=True)
    seen = load_existing_hashes(DATASET)
    before_count = sum(1 for l in DATASET.open(encoding="utf-8") if l.strip()) if DATASET.exists() else 0
    print(f"{before_count} examples, {len(seen)} unique hashes")

    # Collect new records
    new_records = []
    for filename, category in COMPONENT_FILES:
        path = COMPONENTS / filename
        if not path.exists():
            print(f"  [WARN] {filename} not found — skipping")
            continue

        file_new = 0
        file_dup = 0
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                h = hashlib.sha256(obj.get("output", "").encode()).hexdigest()
                if h in seen:
                    file_dup += 1
                else:
                    seen.add(h)
                    new_records.append(component_to_dataset(obj))
                    file_new += 1

        print(f"  {filename:<45} +{file_new:>4} new   {file_dup:>4} dupes skipped")

    print(f"\n  Total new examples to add: {len(new_records)}")

    if not new_records:
        print("  Nothing to add — dataset unchanged.")
        return

    if args.dry_run:
        print("\n  [dry-run] No changes written.")
        print(f"  Would grow dataset: {before_count} → {before_count + len(new_records)}")
        # Show a sample
        print("\n  Sample record (first new):")
        sample = new_records[0]
        print(f"    instruction: {sample['instruction'][:80]}...")
        print(f"    topic:       {sample['topic']}")
        print(f"    review_status: {sample['review_status']}")
        return

    # Optional backup
    if args.backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = DATASET.with_suffix(f".pre_ingest_{ts}.jsonl")
        shutil.copy2(DATASET, backup)
        print(f"\n  Backup → {backup.name}")

    # Append to dataset
    with DATASET.open("a", encoding="utf-8") as f:
        for rec in new_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    after_count = before_count + len(new_records)
    print(f"\n  ✅ Done. Dataset: {before_count} → {after_count} examples (+{len(new_records)})")
    print(f"  Output: {DATASET}")

    # Show category breakdown of what was added
    from collections import Counter
    cats = Counter(r["topic"] for r in new_records)
    print(f"\n  Added by category:")
    for cat, n in cats.most_common():
        print(f"    {cat:<35} +{n}")

    print(f"\n{'═'*60}")


if __name__ == "__main__":
    main()
