#!/usr/bin/env python3
"""
strip_markdown_outputs.py — Cardumen Forge
Strips markdown wrapping (prose + code fences) from dataset examples whose
output field contains ```aiken ... ``` blocks instead of raw code.

Usage:
    python3 scripts/strip_markdown_outputs.py --dry-run           # report only
    python3 scripts/strip_markdown_outputs.py --apply             # write in-place
    python3 scripts/strip_markdown_outputs.py --source generated_governance_v1 --apply
    python3 scripts/strip_markdown_outputs.py --apply --out data/processed/dataset_v23.jsonl
"""

import re
import json
import argparse
import shutil
from pathlib import Path
from collections import defaultdict

ROOT       = Path(__file__).parent.parent
INPUT_FILE = ROOT / "data" / "processed" / "dataset_v22.jsonl"


def strip_markdown(output: str) -> str:
    """Extract code from a markdown fence if present, otherwise return as-is.
    Prefers ```aiken fence; falls back to first fence of any type.
    """
    # Try aiken-specific fence first
    m = re.search(r'```aiken\n(.*?)```', output, re.DOTALL)
    if not m:
        m = re.search(r'```(?:\w*)?\n(.*?)```', output, re.DOTALL)
    return m.group(1).strip() if m else output


def needs_stripping(output: str) -> bool:
    """Return True only if output STARTS with a markdown code fence.
    Outputs that start with prose + have an embedded fence are explanations
    and should not be stripped — the prose is part of the value.
    """
    return bool(re.match(r'\s*```', output))


def is_standalone_code_block(output: str) -> bool:
    """Return True if the embedded aiken fence contains a standalone compilable snippet
    (has 'validator' keyword or starts with 'use ') — not just a type def or fragment.
    Used for smart-stripping sources like aiken_design_patterns where prose+code
    examples exist but only full validators/modules should be extracted.
    """
    m = re.search(r'```aiken\n(.*?)```', output, re.DOTALL)
    if not m:
        return False
    code = m.group(1).strip()
    return 'validator' in code or code.startswith('use ')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",    action="store_true", help="Report changes without writing")
    parser.add_argument("--apply",     action="store_true", help="Apply changes")
    parser.add_argument("--source",    default=None,        help="Only process this source (e.g. generated_governance_v1)")
    parser.add_argument("--out",       default=None,        help="Output path (default: overwrite input)")
    parser.add_argument("--input",     default=str(INPUT_FILE), help="Input JSONL file")
    parser.add_argument("--force-strip", action="store_true",
                        help="Strip fence even if prose precedes it (use for sources like generated_governance_v1)")
    parser.add_argument("--smart-strip", action="store_true",
                        help="Strip prose+fence only when the embedded code block is a standalone validator/module (use for aiken_design_patterns)")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    input_path  = Path(args.input)
    output_path = Path(args.out) if args.out else input_path

    examples = []
    with input_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    print(f"Loaded  : {len(examples)} examples from {input_path.name}")
    if args.source:
        print(f"Filter  : source={args.source}")

    # Process
    migrated      = []
    changed_count = 0
    skipped_count = 0
    by_source     = defaultdict(int)

    for ex in examples:
        source = ex.get("source", "")
        output = ex.get("output", "")

        # Skip if source filter active and doesn't match
        if args.source and source != args.source:
            migrated.append(ex)
            skipped_count += 1
            continue

        should_strip = (
            (args.force_strip and bool(re.search(r'```', output))) or
            (args.smart_strip and is_standalone_code_block(output))
        )
        if should_strip or needs_stripping(output):
            stripped = strip_markdown(output)
            if stripped != output:
                migrated.append({**ex, "output": stripped})
                changed_count += 1
                by_source[source] += 1
            else:
                migrated.append(ex)
        else:
            migrated.append(ex)

    # Report
    print(f"\nExamples changed : {changed_count}/{len(examples) - skipped_count} checked")
    if by_source:
        print("\nChanged by source:")
        for src, n in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"  {n:4d}  {src}")

    if args.dry_run:
        print("\n── Sample (first 5 changed) ──")
        shown = 0
        for orig, new_ex in zip(examples, migrated):
            if orig["output"] != new_ex["output"]:
                print(f"\n  [{orig.get('source','')}] {orig.get('instruction','')[:70]}")
                print(f"  BEFORE (first 100): {orig['output'][:100].strip()!r}")
                print(f"  AFTER  (first 100): {new_ex['output'][:100].strip()!r}")
                shown += 1
                if shown >= 5:
                    break
        print("\nRe-run with --apply to write changes.")
        return

    # Backup
    if output_path == input_path:
        backup = input_path.with_suffix(".jsonl.pre_strip_backup")
        if not backup.exists():
            shutil.copy2(input_path, backup)
            print(f"\nBackup  : {backup}")
        else:
            print(f"\nBackup already exists: {backup} (not overwriting)")

    # Write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for ex in migrated:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    written = sum(1 for _ in output_path.open(encoding="utf-8"))
    print(f"\nWritten : {written} examples → {output_path}")


if __name__ == "__main__":
    main()
