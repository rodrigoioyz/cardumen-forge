#!/usr/bin/env python3
"""
fix_types.py — Cardumen Forge
Fix #2 and #3 from the dataset audit, verified against data/raw/aiken_stdlib.json.

Fix #2 — Wrong Credential constructor names (Plutus v2 relics):
    ScriptCredential(...)  →  Script(...)
    PubKeyCredential(...)  →  VerificationKey(...)
    Verified: cardano.address.Credential has constructors Script and VerificationKey.
    ScriptCredential / PubKeyCredential do NOT exist in Aiken v3 stdlib.

Fix #3 — PolicyId imported from wrong module:
    use cardano/transaction.{..., PolicyId, ...}  →  move PolicyId to use cardano/assets
    Verified: PolicyId = pub type PolicyId = Hash<Blake2b_224, Script> lives in cardano.assets.

Safety rules:
  - Only modify OUTPUT fields (inputs may show intentionally buggy code)
  - Skip examples where topic contains 'correction/' (correction examples show errors on purpose)
  - Only replace inside code fences (``` blocks) for Fix #2
  - Dry-run by default — use --write to apply

Usage:
    python3 scripts/fix_types.py               # dry-run, full report
    python3 scripts/fix_types.py --write        # apply fixes, save v17
"""

import re
import json
import argparse
from pathlib import Path

INPUT_PATH  = Path("data/processed/dataset_v16_train_split.jsonl")
OUTPUT_PATH = Path("data/processed/dataset_v17_train_split.jsonl")
REPORT_PATH = Path("logs/fix_types_report.md")

# ─────────────────────────────────────────────────────────────────────────────
# Ground truth from data/raw/aiken_stdlib.json
# ─────────────────────────────────────────────────────────────────────────────
# cardano.address.Credential constructors: Script, VerificationKey
# cardano.assets.PolicyId  (NOT cardano.transaction)

CONSTRUCTOR_FIXES = [
    # (wrong, correct, description)
    ("ScriptCredential", "Script",          "Plutus v2 name → Aiken v3 constructor"),
    ("PubKeyCredential", "VerificationKey", "Plutus v2 name → Aiken v3 constructor"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Fix #2 — Constructor name fixes (inside code fences only)
# ─────────────────────────────────────────────────────────────────────────────

def fix_constructors_in_code(text: str) -> tuple[str, list[str]]:
    """Replace wrong constructor names only inside ``` code blocks."""
    changes = []

    def replace_in_block(match):
        fence_open = match.group(1)   # ```aiken or ``` etc
        code       = match.group(2)
        fence_close = match.group(3)  # ```
        modified = code
        for wrong, correct, desc in CONSTRUCTOR_FIXES:
            pattern = r'\b' + re.escape(wrong) + r'\b'
            n = len(re.findall(pattern, modified))
            if n > 0:
                modified = re.sub(pattern, correct, modified)
                changes.append(f"{wrong} → {correct} ({n}x): {desc}")
        return fence_open + modified + fence_close

    result = re.sub(
        r'(```(?:\w+)?\n)(.*?)(```)',
        replace_in_block,
        text,
        flags=re.DOTALL
    )
    return result, changes


# ─────────────────────────────────────────────────────────────────────────────
# Fix #3 — PolicyId import module fix
# ─────────────────────────────────────────────────────────────────────────────

# Matches: use cardano/transaction.{..., PolicyId, ...} or use cardano/transaction.{PolicyId}
TRANSACTION_POLICYID_RE = re.compile(
    r'(use\s+cardano/transaction\s*\.\s*\{)([^}]*\bPolicyId\b[^}]*)(\})',
)

def fix_policyid_import(text: str) -> tuple[str, list[str]]:
    """
    Move PolicyId out of cardano/transaction import into cardano/assets import.
    If cardano/assets import already exists, append PolicyId to it.
    If not, add a new use cardano/assets.{PolicyId} line.
    """
    changes = []

    def remove_from_transaction(match):
        prefix  = match.group(1)  # use cardano/transaction.{
        items   = match.group(2)  # comma-separated items including PolicyId
        suffix  = match.group(3)  # }

        # Remove PolicyId from the list
        parts = [p.strip() for p in items.split(',')]
        parts = [p for p in parts if p and p != 'PolicyId']

        changes.append("Removed PolicyId from cardano/transaction import")

        if parts:
            return prefix + ', '.join(parts) + suffix
        else:
            # Nothing left in the import — remove the whole line
            return '__REMOVE_LINE__'

    lines = text.split('\n')
    new_lines = []
    policyid_needs_adding = False

    for line in lines:
        if TRANSACTION_POLICYID_RE.search(line):
            fixed = TRANSACTION_POLICYID_RE.sub(remove_from_transaction, line)
            if fixed == '__REMOVE_LINE__':
                policyid_needs_adding = True
                continue  # drop the line
            else:
                new_lines.append(fixed)
                policyid_needs_adding = True
        else:
            new_lines.append(line)

    if policyid_needs_adding:
        # Try to add PolicyId to existing cardano/assets import
        assets_import_re = re.compile(r'(use\s+cardano/assets\s*\.\s*\{)([^}]*)(\})')
        merged = False
        for i, line in enumerate(new_lines):
            if assets_import_re.search(line):
                def add_policyid(m):
                    items = m.group(2).strip()
                    if 'PolicyId' not in items:
                        items = items + ', PolicyId' if items else 'PolicyId'
                    return m.group(1) + items + m.group(3)
                new_lines[i] = assets_import_re.sub(add_policyid, line)
                changes.append("Added PolicyId to existing cardano/assets import")
                merged = True
                break

        if not merged:
            # Insert new use cardano/assets.{PolicyId} after last `use` line
            last_use = max((i for i, l in enumerate(new_lines) if l.strip().startswith('use ')), default=0)
            new_lines.insert(last_use + 1, 'use cardano/assets.{PolicyId}')
            changes.append("Inserted new use cardano/assets.{PolicyId} line")

    return '\n'.join(new_lines), changes


# ─────────────────────────────────────────────────────────────────────────────
# Is this a correction example? (intentionally shows errors)
# ─────────────────────────────────────────────────────────────────────────────

def is_correction_example(ex: dict) -> bool:
    topic  = ex.get('topic', '')
    source = ex.get('source', '')
    return 'correction' in topic.lower() or 'correction' in source.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   default=str(INPUT_PATH))
    parser.add_argument("--output",  default=str(OUTPUT_PATH))
    parser.add_argument("--report",  default=str(REPORT_PATH))
    parser.add_argument("--write",   action="store_true", help="Apply fixes and save output")
    args = parser.parse_args()

    mode = "WRITE" if args.write else "DRY RUN"
    print(f"\nCardumen Forge — Fix Types (#{2} + #{3})")
    print(f"Input  : {args.input}")
    print(f"Output : {args.output}")
    print(f"Mode   : {mode}\n")

    with open(args.input, encoding="utf-8") as f:
        examples = [json.loads(l) for l in f if l.strip()]
    print(f"Loaded : {len(examples):,} examples")

    stats = {
        "fix2_constructor_examples": 0,
        "fix2_constructor_total":    0,
        "fix3_policyid_examples":    0,
        "skipped_correction":        0,
    }
    fix2_log = []
    fix3_log = []
    results  = []

    for ex in examples:
        output  = ex.get("output", "")
        changed = False

        # Skip correction examples for both fixes
        if is_correction_example(ex):
            stats["skipped_correction"] += 1
            results.append(ex)
            continue

        # ── Fix #2: constructor names ────────────────────────────────────────
        fixed_output, c2_changes = fix_constructors_in_code(output)
        if c2_changes:
            stats["fix2_constructor_examples"] += 1
            stats["fix2_constructor_total"]    += len(c2_changes)
            fix2_log.append({
                "source":      ex.get("source"),
                "topic":       ex.get("topic"),
                "instruction": ex.get("instruction", "")[:100],
                "changes":     c2_changes,
            })
            output  = fixed_output
            changed = True

        # ── Fix #3: PolicyId import ──────────────────────────────────────────
        fixed_output, c3_changes = fix_policyid_import(output)
        if c3_changes:
            stats["fix3_policyid_examples"] += 1
            fix3_log.append({
                "source":      ex.get("source"),
                "topic":       ex.get("topic"),
                "instruction": ex.get("instruction", "")[:100],
                "changes":     c3_changes,
            })
            output  = fixed_output
            changed = True

        if changed:
            ex = {**ex, "output": output}
        results.append(ex)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  GOAL: Fix wrong type names and wrong import modules")
    print(f"{'='*60}")
    print(f"  Fix #2 — Constructor names")
    print(f"    Examples touched : {stats['fix2_constructor_examples']}")
    print(f"    Total replacements: {stats['fix2_constructor_total']}")
    print(f"  Fix #3 — PolicyId import")
    print(f"    Examples touched : {stats['fix3_policyid_examples']}")
    print(f"  Skipped (correction examples): {stats['skipped_correction']}")
    print(f"  Dataset size (unchanged)     : {len(results):,}")
    print(f"{'='*60}")

    if fix2_log:
        print(f"\n  Fix #2 detail (first 5):")
        for item in fix2_log[:5]:
            print(f"    [{item['source']}] {item['instruction'][:70]}")
            for c in item['changes']:
                print(f"      → {c}")

    if fix3_log:
        print(f"\n  Fix #3 detail (first 5):")
        for item in fix3_log[:5]:
            print(f"    [{item['source']}] {item['instruction'][:70]}")
            for c in item['changes']:
                print(f"      → {c}")

    # ── Save ─────────────────────────────────────────────────────────────────
    if args.write:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            for ex in results:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"\n  ✅ Saved → {args.output}")
    else:
        print(f"\n  (dry run — use --write to apply)")

    # ── Report ────────────────────────────────────────────────────────────────
    report = [
        "# Fix Types Report (Fix #2 + Fix #3)",
        "",
        f"**Input:** `{args.input}`",
        f"**Mode:** {mode}",
        "",
        "## Ground Truth (from data/raw/aiken_stdlib.json)",
        "",
        "| Type | Module | Note |",
        "|------|--------|------|",
        "| `PolicyId` | `cardano/assets` | NOT in cardano/transaction |",
        "| `Credential` | `cardano/address` | Constructors: `Script`, `VerificationKey` |",
        "| `ScriptCredential` | — | Does NOT exist in Aiken v3 |",
        "| `PubKeyCredential` | — | Does NOT exist in Aiken v3 |",
        "",
        "## Fix #2 — Constructor Names",
        "",
        f"Examples touched: **{stats['fix2_constructor_examples']}**  |  Total replacements: **{stats['fix2_constructor_total']}**",
        "",
    ]
    for item in fix2_log:
        report.append(f"- `{item['source']}` / `{item['topic']}`")
        report.append(f"  - {item['instruction']}")
        for c in item['changes']:
            report.append(f"  - `{c}`")
        report.append("")

    report += [
        "## Fix #3 — PolicyId Import",
        "",
        f"Examples touched: **{stats['fix3_policyid_examples']}**",
        "",
    ]
    for item in fix3_log:
        report.append(f"- `{item['source']}` / `{item['topic']}`")
        report.append(f"  - {item['instruction']}")
        for c in item['changes']:
            report.append(f"  - `{c}`")
        report.append("")

    report += [
        "## Pending",
        "",
        "- [ ] Fix `import` → `use` (needs manual review)",
        "- [ ] Regenerate ~62 truncated outputs",
        "- [ ] Generate new examples: propose(0→15), vote(20→40), publish(16→36)",
        "- [ ] Reduce 800+ duplicate signature-check examples",
        "- [ ] Verify 1,500 PLAUSIBLE_NEEDS_CHECK examples",
        "",
        "_Generated by `scripts/fix_types.py`_",
    ]

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(report), encoding="utf-8")
    print(f"  Report → {args.report}")


if __name__ == "__main__":
    main()
