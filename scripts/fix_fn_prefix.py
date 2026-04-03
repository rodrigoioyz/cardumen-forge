#!/usr/bin/env python3
"""
fix_fn_prefix.py — Cardumen Forge
Removes the invalid `fn` keyword from validator handler definitions in dataset outputs.

The Aiken v3 compiler rejects `fn spend(...)` inside validator blocks.
Correct syntax is `spend(...)` — no `fn` prefix.

Usage:
    python3 scripts/fix_fn_prefix.py
    python3 scripts/fix_fn_prefix.py --dry-run       # preview without writing
    python3 scripts/fix_fn_prefix.py --input data/processed/dataset_v14_train_split.jsonl
"""

import re
import json
import argparse
from pathlib import Path
from collections import Counter

HANDLERS = ["spend", "mint", "withdraw", "publish", "vote"]

# Matches `fn spend(`, `fn  mint(`, etc. — the invalid pattern
FN_HANDLER_RE = re.compile(
    r'\bfn\s+(' + '|'.join(HANDLERS) + r')\s*\(',
)


def fix_output(text: str) -> tuple[str, int]:
    """Remove `fn ` prefix from handler clauses. Returns (fixed_text, count_fixes)."""
    fixed, n = FN_HANDLER_RE.subn(r'\1(', text)
    return fixed, n


def process_dataset(input_path: Path, output_path: Path, dry_run: bool = False):
    with open(input_path, encoding="utf-8") as f:
        examples = [json.loads(l) for l in f if l.strip()]

    fixed_count = 0
    touched_examples = 0
    fixes_per_handler = Counter()

    patched = []
    for ex in examples:
        original_output = ex.get("output", "")
        fixed_output, n = fix_output(original_output)

        if n > 0:
            touched_examples += 1
            fixed_count += n
            # Track which handlers were fixed
            for h in HANDLERS:
                occurrences = len(re.findall(rf'\bfn\s+{h}\s*\(', original_output))
                if occurrences:
                    fixes_per_handler[h] += occurrences

            ex = {**ex, "output": fixed_output}

            if dry_run:
                # Show a diff preview
                print(f"\n--- Example (source={ex.get('source')}, topic={ex.get('topic', '')[:50]})")
                print(f"    Instruction: {ex.get('instruction', '')[:100]}")
                # Show first affected line
                for orig_line, fixed_line in zip(original_output.splitlines(), fixed_output.splitlines()):
                    if orig_line != fixed_line:
                        print(f"    BEFORE: {orig_line.strip()}")
                        print(f"    AFTER : {fixed_line.strip()}")
                        break

        patched.append(ex)

    print(f"\n{'='*60}")
    print(f"  Input  : {input_path} ({len(examples):,} examples)")
    print(f"  Output : {output_path}")
    print(f"  Mode   : {'DRY RUN (no files written)' if dry_run else 'WRITE'}")
    print(f"{'='*60}")
    print(f"  Examples touched : {touched_examples:,} / {len(examples):,} ({100*touched_examples/len(examples):.1f}%)")
    print(f"  Total fixes      : {fixed_count:,}")
    print(f"  By handler:")
    for h, cnt in fixes_per_handler.most_common():
        print(f"    fn {h}(  →  {h}(  : {cnt} fixes")
    print(f"{'='*60}")

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for ex in patched:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"\n  ✅ Saved → {output_path}")
    else:
        print(f"\n  (dry run — nothing written)")

    return touched_examples, fixed_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   default="data/processed/dataset_v14_train_split.jsonl")
    parser.add_argument("--output",  default="data/processed/dataset_v15_train_split.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    process_dataset(Path(args.input), Path(args.output), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
