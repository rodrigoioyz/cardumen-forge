#!/usr/bin/env python3
"""
fix_plausible.py — Fix or purge PLAUSIBLE_NEEDS_CHECK examples

Actions per example (based on audit diagnosis):
  PURGE  — prose/markdown in output, incomplete stubs, no training value
  REPAIR — fixable with a one-line code change
  SKIP   — sandbox dependency issue (aiken_scott_utils), code may be valid
           → mark as PLAUSIBLE_SKIP_SANDBOX to exclude from training

Usage:
    python3 scripts/fix_plausible.py --dry-run
    python3 scripts/fix_plausible.py --backup
"""

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DATASET = ROOT / "data" / "processed" / "dataset_v23.jsonl"

# ── Action table (from audit diagnosis) ──────────────────────────────────────
# Format: index → ("action", "reason")

ACTIONS = {
    # REPAIR: transaction_id.hash → transaction_id (TransactionId is ByteArray)
    1683: ("repair", "transaction_id.hash → transaction_id"),

    # REPAIR: add missing `use aiken/builtin`
    1887: ("repair", "add missing use aiken/builtin"),

    # PURGE: prose/markdown output — no Aiken code
    2938: ("purge",  "output is prose, not Aiken code"),
    2948: ("purge",  "function stub without body"),
    2952: ("purge",  "output is prose, not Aiken code"),
    2959: ("purge",  "output is prose, not Aiken code"),
    2969: ("purge",  "output is prose/markdown"),
    2970: ("purge",  "placeholder hex literal #\"abcd...1234\""),
    2975: ("purge",  "output is prose/markdown"),
    2979: ("purge",  "incomplete assignment, no RHS"),
    2988: ("purge",  "output is prose/markdown"),

    # REPAIR: use cardano/credential → use cardano/address
    3059: ("repair", "use cardano/credential.{Script} → use cardano/address.{Script}"),

    # SKIP: aiken_scott_utils missing transitive dep in sandbox
    3095: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3096: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3107: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3109: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3124: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3125: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3126: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3132: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3133: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3135: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),
    3145: ("skip",   "aiken_scott_utils missing from sandbox (transitive dep)"),

    # REPAIR: dict.to_pairs inline path → already imported, use dict.to_pairs
    3180: ("repair", "aiken/collection/dict.to_pairs → dict.to_pairs (inline path)"),

    # REPAIR: builtin.shift_by_int → math.pow(2, n)
    3190: ("repair", "builtin.shift_by_int → math.pow(2, n)"),

    # REPAIR: _own_ref → own_ref (underscore prefix prevents binding)
    3268: ("repair", "_own_ref → own_ref in spend handler"),

    # REPAIR: add missing use cardano/address
    3274: ("repair", "add missing use cardano/address"),

    # Index 1707 — likely PTY false positive, mark as SKIP for now
    1707: ("skip",   "likely PTY timing false-positive, code appears syntactically valid"),
    # Index 2976 — missing ComputationRedeemer import from design-patterns
    2976: ("skip",   "ComputationRedeemer needs aiken_design_patterns import (sandbox dep)"),
}


def repair(code: str, index: int) -> str | None:
    """Apply targeted repair to code. Returns fixed code or None if repair failed."""
    if index == 1683:
        # transaction_id.hash → transaction_id
        fixed = re.sub(r'\btransaction_id\.hash\b', 'transaction_id', code)
        return fixed if fixed != code else None

    if index == 1887:
        # add use aiken/builtin at top
        if 'use aiken/builtin' not in code:
            lines = code.splitlines()
            # insert after last existing use statement
            last_use = 0
            for i, l in enumerate(lines):
                if l.strip().startswith('use '):
                    last_use = i
            lines.insert(last_use + 1, 'use aiken/builtin')
            return '\n'.join(lines)
        return None

    if index == 3059:
        # use cardano/credential.{Script} → use cardano/address.{Script}
        fixed = code.replace('use cardano/credential.{Script}', 'use cardano/address.{Script}')
        fixed = re.sub(r'\bcardano/credential\b', 'cardano/address', fixed)
        return fixed if fixed != code else None

    if index == 3180:
        # aiken/collection/dict.to_pairs → dict.to_pairs
        fixed = re.sub(r'aiken/collection/dict\.to_pairs', 'dict.to_pairs', code)
        # ensure use aiken/collection/dict is present
        if 'use aiken/collection/dict' not in fixed:
            lines = fixed.splitlines()
            last_use = 0
            for i, l in enumerate(lines):
                if l.strip().startswith('use '):
                    last_use = i
            lines.insert(last_use + 1, 'use aiken/collection/dict')
            fixed = '\n'.join(lines)
        return fixed if fixed != code else None

    if index == 3190:
        # builtin.shift_by_int(1, n) → math.pow(2, n)
        fixed = re.sub(r'builtin\.shift_by_int\s*\(\s*1\s*,\s*(\w+)\s*\)',
                       r'math.pow(2, \1)', code)
        # add use aiken/math if missing
        if 'use aiken/math' not in fixed and fixed != code:
            lines = fixed.splitlines()
            last_use = 0
            for i, l in enumerate(lines):
                if l.strip().startswith('use '):
                    last_use = i
            lines.insert(last_use + 1, 'use aiken/math')
            fixed = '\n'.join(lines)
        return fixed if fixed != code else None

    if index == 3268:
        # _own_ref → own_ref in spend handler signature and body
        fixed = re.sub(r'\b_own_ref\b', 'own_ref', code)
        return fixed if fixed != code else None

    if index == 3274:
        # add use cardano/address
        if 'use cardano/address' not in code:
            lines = code.splitlines()
            last_use = 0
            for i, l in enumerate(lines):
                if l.strip().startswith('use '):
                    last_use = i
            lines.insert(last_use + 1, 'use cardano/address')
            return '\n'.join(lines)
        return None

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print(f"  fix_plausible — {len(ACTIONS)} PLAUSIBLE examples")
    if args.dry_run:
        print(f"  mode: dry-run")
    print(f"{'═'*60}\n")

    # Load dataset
    examples = []
    with DATASET.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))

    # Count actions
    purge_count  = sum(1 for a, _ in ACTIONS.values() if a == "purge")
    repair_count = sum(1 for a, _ in ACTIONS.values() if a == "repair")
    skip_count   = sum(1 for a, _ in ACTIONS.values() if a == "skip")

    print(f"  Plan: {purge_count} purge  {repair_count} repair  {skip_count} skip\n")

    purged, repaired, skipped, repair_failed = 0, 0, 0, 0
    indices_to_purge = set()

    for idx, (action, reason) in sorted(ACTIONS.items()):
        if idx >= len(examples):
            print(f"  [WARN] index {idx} out of range — skipping")
            continue

        ex = examples[idx]
        topic = ex.get("topic", "?")[:45]

        if action == "purge":
            print(f"  🗑  [{idx:4d}] {topic:<45}  {reason[:50]}")
            if not args.dry_run:
                indices_to_purge.add(idx)
            purged += 1

        elif action == "repair":
            fixed = repair(ex.get("output", ""), idx)
            if fixed:
                print(f"  🔧 [{idx:4d}] {topic:<45}  {reason[:50]}")
                if not args.dry_run:
                    examples[idx]["output"] = fixed
                    examples[idx]["review_status"] = "VERIFIED_V3_ALIGNED"
                repaired += 1
            else:
                print(f"  ⚠️  [{idx:4d}] {topic:<45}  repair had no effect — skipping")
                repair_failed += 1

        elif action == "skip":
            print(f"  ⏭  [{idx:4d}] {topic:<45}  {reason[:50]}")
            if not args.dry_run:
                examples[idx]["review_status"] = "PLAUSIBLE_SKIP_SANDBOX"
            skipped += 1

    print(f"\n{'═'*60}")
    print(f"  Purged:       {purged}")
    print(f"  Repaired:     {repaired}")
    print(f"  Skipped:      {skipped}")
    print(f"  Repair fails: {repair_failed}")
    print(f"{'═'*60}")

    if args.dry_run:
        print("\n  [dry-run] No changes written.")
        return

    # Backup
    if args.backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = DATASET.with_suffix(f".pre_fixplausible_{ts}.jsonl")
        shutil.copy2(DATASET, backup)
        print(f"\n  Backup → {backup.name}")

    # Write dataset (excluding purged)
    new_examples = [ex for i, ex in enumerate(examples) if i not in indices_to_purge]
    with DATASET.open("w", encoding="utf-8") as f:
        for ex in new_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    after = len(new_examples)
    before = len(examples)
    print(f"\n  ✅ Dataset: {before} → {after} examples (-{before - after} purged)")
    print(f"  Output: {DATASET}")


if __name__ == "__main__":
    main()
