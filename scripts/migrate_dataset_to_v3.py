#!/usr/bin/env python3
"""
migrate_dataset_to_v3.py — Cardumen Forge
Migrates dataset_v20_reviewed.jsonl (v21 content) to stdlib v3.0.0 patterns.

Changes applied:
  1. Record field commas   — adds comma after every field in pub type blocks
  2. Constructor renames   — DeregisterCredential, VerificationKeyCredential, etc.
  3. Interval<T>           — removes generic parameter
  4. aiken/time / PosixTime — removes or replaces
  5. MintedValue           — replaces with Value

Usage:
    python3 scripts/migrate_dataset_to_v3.py --dry-run         # report only
    python3 scripts/migrate_dataset_to_v3.py --apply           # write in-place
    python3 scripts/migrate_dataset_to_v3.py --apply --out data/processed/dataset_v22.jsonl
"""

import re
import json
import argparse
import shutil
from pathlib import Path
from collections import defaultdict

ROOT       = Path(__file__).parent.parent
INPUT_FILE = ROOT / "data" / "processed" / "dataset_v20_reviewed.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# Fix 1 — Record field commas
# ─────────────────────────────────────────────────────────────────────────────

def fix_record_commas(code: str) -> tuple[str, int]:
    """
    Add commas after record fields that are missing them.
    Targets: pub type Foo { field: Type\n  field2: Type2 }
    Returns (fixed_code, number_of_commas_added).
    """
    added = 0

    def fix_type_block(m: re.Match) -> str:
        nonlocal added
        block_start = m.group(0)  # "pub type Name {"
        rest_start  = m.end()
        return block_start  # we process inside separately

    # Find all pub type blocks and fix fields inside them
    def process_type_block(match: re.Match) -> str:
        nonlocal added
        header = match.group(1)   # "pub type Name "
        body   = match.group(2)   # content between { }

        lines = body.split('\n')
        new_lines = []

        for i, line in enumerate(lines):
            stripped = line.rstrip()

            # Is this a field line? Pattern: optional spaces + name: Type
            # Ends without comma, not a comment, not empty, not closing brace
            if (re.match(r'^\s+\w+\s*:', stripped)
                    and not stripped.rstrip().endswith(',')
                    and not stripped.rstrip().endswith('{')
                    and '//' not in stripped):
                stripped += ','
                added += 1

            new_lines.append(stripped)

        return f"{header}{{{'\n'.join(new_lines)}}}"

    # Match: pub type Name { ... } (single-level, non-nested)
    pattern = re.compile(
        r'(pub\s+type\s+\w+(?:\s*\([^)]*\))?\s*)\{([^{}]*)\}',
        re.DOTALL
    )
    fixed = pattern.sub(process_type_block, code)
    return fixed, added


# ─────────────────────────────────────────────────────────────────────────────
# Fix 2 — Constructor / module renames
# ─────────────────────────────────────────────────────────────────────────────

RENAMES = [
    # (pattern, replacement, description)
    (r'\bDeregisterCredential\b',      'UnregisterCredential',   'DeregisterCredential→UnregisterCredential'),
    (r'\bVerificationKeyCredential\b', 'VerificationKey',        'VerificationKeyCredential→VerificationKey'),
    (r'\bScriptCredential\b',          'Script',                 'ScriptCredential→Script'),
    (r'\bMintedValue\b',               'Value',                  'MintedValue→Value'),
    # Interval<X> → Interval (remove generic parameter)
    (r'\bInterval\s*<[^>]+>',          'Interval',               'Interval<T>→Interval'),
]


def fix_renames(code: str) -> tuple[str, dict]:
    counts = defaultdict(int)
    for pattern, replacement, desc in RENAMES:
        new_code, n = re.subn(pattern, replacement, code)
        if n:
            counts[desc] += n
        code = new_code
    return code, dict(counts)


# ─────────────────────────────────────────────────────────────────────────────
# Fix 3 — aiken/time and PosixTime
# ─────────────────────────────────────────────────────────────────────────────

def fix_time_module(code: str) -> tuple[str, int]:
    """
    Remove 'use aiken/time' import lines.
    Replace PosixTime type annotations with Int.
    """
    removed = 0

    # Remove import line
    new_code, n = re.subn(r'^\s*use\s+aiken/time[^\n]*\n?', '', code, flags=re.MULTILINE)
    removed += n
    code = new_code

    # Replace PosixTime with Int in type annotations
    new_code, n = re.subn(r'\bPosixTime\b', 'Int', code)
    removed += n
    code = new_code

    return code, removed


# ─────────────────────────────────────────────────────────────────────────────
# Apply all fixes to one example
# ─────────────────────────────────────────────────────────────────────────────

def migrate_example(ex: dict) -> tuple[dict, dict]:
    """Returns (migrated_example, change_report)."""
    output = ex.get("output", "")
    if not output:
        return ex, {}

    report = {}

    output, n_commas    = fix_record_commas(output)
    output, rename_map  = fix_renames(output)
    output, n_time      = fix_time_module(output)

    if n_commas:
        report["commas_added"] = n_commas
    if rename_map:
        report.update(rename_map)
    if n_time:
        report["time_module_removed"] = n_time

    new_ex = {**ex, "output": output}
    return new_ex, report


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    parser.add_argument("--apply",   action="store_true", help="Apply changes")
    parser.add_argument("--out",     default=None,        help="Output path (default: overwrite input)")
    parser.add_argument("--input",   default=str(INPUT_FILE), help="Input JSONL file")
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

    # Migrate all
    migrated      = []
    total_changes = defaultdict(int)
    changed_count = 0

    for ex in examples:
        new_ex, report = migrate_example(ex)
        migrated.append(new_ex)
        if report:
            changed_count += 1
            for k, v in report.items():
                total_changes[k] += v

    # Report
    print(f"\nExamples changed : {changed_count}/{len(examples)}")
    print("\nChanges by type:")
    for k, v in sorted(total_changes.items(), key=lambda x: -x[1]):
        print(f"  {v:5d}  {k}")

    if args.dry_run:
        # Show a few examples of what changed
        print("\n── Sample diffs (first 5 changed examples) ──")
        shown = 0
        for orig, new_ex in zip(examples, migrated):
            if orig["output"] != new_ex["output"]:
                orig_lines = set(orig["output"].splitlines())
                new_lines  = set(new_ex["output"].splitlines())
                added   = [l for l in new_ex["output"].splitlines() if l not in orig_lines][:3]
                removed = [l for l in orig["output"].splitlines() if l not in new_lines][:3]
                print(f"\n  instruction: {orig.get('instruction','')[:70]}")
                for l in removed:
                    print(f"  - {l.rstrip()}")
                for l in added:
                    print(f"  + {l.rstrip()}")
                shown += 1
                if shown >= 5:
                    break
        print("\nRe-run with --apply to write changes.")
        return

    # Write
    if output_path == input_path:
        backup = input_path.with_suffix(".jsonl.v21_backup")
        if not backup.exists():
            shutil.copy2(input_path, backup)
            print(f"\nBackup  : {backup}")
        else:
            print(f"\nBackup already exists: {backup} (not overwriting)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for ex in migrated:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    written = sum(1 for _ in output_path.open(encoding="utf-8"))
    print(f"\nWritten : {written} examples → {output_path}")
    print("\nDataset is now v22-ready. Next step:")
    print("  python3 scripts/generate_v3_compat_examples.py --write --append-to-v21")


if __name__ == "__main__":
    main()
