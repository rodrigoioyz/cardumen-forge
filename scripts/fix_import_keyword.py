#!/usr/bin/env python3
"""
fix_import_keyword.py — Cardumen Forge

Fixes two problems in dataset outputs:
  1. `import x.y.z{Items}` → `use x/y/z.{Items}`  (wrong keyword + dot-style)
  2. Deletes specific bad examples by index (e.g. the PyCardano/Python example)

Usage:
    python3 scripts/fix_import_keyword.py --dry-run
    python3 scripts/fix_import_keyword.py --apply
"""

import re
import json
import argparse
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DATASET = ROOT / "data" / "processed" / "dataset_v22.jsonl"

# Examples to delete outright (index in dataset, 0-based)
DELETE_INDICES = {2512}


def fix_import_line(line: str) -> tuple[str, bool]:
    """
    Transforms a single line containing `import x.y.z` or `import x.y.z.{A, B}`.
    Returns (fixed_line, was_changed).
    """
    m = re.match(r'^(\s*)import\s+([\w.]+?)(\.\{[^}]*\})?(\s*)$', line)
    if not m:
        return line, False
    indent       = m.group(1)
    module_path  = m.group(2).replace('.', '/')
    items        = m.group(3) or ''   # e.g. ".{Scalar, State}"
    trailing     = m.group(4)
    fixed = f"{indent}use {module_path}{items}{trailing}"
    return fixed, True


def fix_output(output: str) -> tuple[str, int]:
    """Fix all import lines in an output. Returns (fixed_output, change_count)."""
    lines = output.split('\n')
    fixed_lines = []
    changes = 0
    for line in lines:
        fixed, changed = fix_import_line(line)
        fixed_lines.append(fixed)
        if changed:
            changes += 1
    return '\n'.join(fixed_lines), changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply",   action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    examples = []
    with DATASET.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    print(f"Loaded {len(examples)} examples")

    fixed_count   = 0
    line_changes  = 0
    deleted       = []
    report        = []

    for i, ex in enumerate(examples):
        if i in DELETE_INDICES:
            deleted.append((i, ex['instruction'][:80]))
            continue

        output = ex.get("output", "")
        fixed_output, changes = fix_output(output)
        if changes:
            fixed_count += 1
            line_changes += changes
            report.append({
                "idx":         i,
                "source":      ex.get("source", "?"),
                "instruction": ex["instruction"][:70],
                "changes":     changes,
                "before":      [l for l in output.split('\n') if re.match(r'\s*import\s+', l)][:3],
                "after":       [l for l in fixed_output.split('\n')
                                if re.match(r'\s*use\s+', l) and '/' in l][:3],
            })
            examples[i] = {**ex, "output": fixed_output}

    print(f"\nTo delete : {len(deleted)} examples")
    for i, instr in deleted:
        print(f"  [{i}] {instr}")

    print(f"\nTo fix    : {fixed_count} examples ({line_changes} import lines)")

    if args.dry_run:
        print("\nSample fixes:")
        for r in report[:5]:
            print(f"\n  [{r['idx']}] {r['source']} — {r['instruction']}")
            for b, a in zip(r['before'], r['after']):
                print(f"    - {b.strip()}")
                print(f"    + {a.strip()}")
        return

    # Apply: rebuild list without deleted indices
    new_examples = [ex for i, ex in enumerate(examples) if i not in DELETE_INDICES]

    with DATASET.open("w", encoding="utf-8") as f:
        for ex in new_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nWritten   : {len(new_examples)} examples → {DATASET}")
    print(f"Deleted   : {len(deleted)}")
    print(f"Fixed     : {fixed_count} examples ({line_changes} lines changed)")


if __name__ == "__main__":
    main()
