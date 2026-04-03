#!/usr/bin/env python3
"""
build_v16.py — Cardumen Forge
Applies safe, unambiguous fixes to dataset_v15 to produce dataset_v16:

  Fix 1 — Remove `fn` prefix from `else` handlers  (fn else( → else()
  Fix 2 — Remove confirmed broken examples (by content fingerprint)
  Fix 3 — Detect truncated outputs (report only, no modification)

Usage:
    python3 scripts/build_v16.py
    python3 scripts/build_v16.py --dry-run
"""

import re
import json
import argparse
from pathlib import Path
from collections import Counter

INPUT_PATH  = Path("data/processed/dataset_v15_train_split.jsonl")
OUTPUT_PATH = Path("data/processed/dataset_v16_train_split.jsonl")
REPORT_PATH = Path("logs/v16_build_report.md")

# ─────────────────────────────────────────────────────────────────────────────
# Fix 1 — fn else( → else(
# ─────────────────────────────────────────────────────────────────────────────

FN_ELSE_RE = re.compile(r'\bfn\s+else\s*\(')

def fix_fn_else(text: str) -> tuple[str, int]:
    fixed, n = FN_ELSE_RE.subn('else(', text)
    return fixed, n

# ─────────────────────────────────────────────────────────────────────────────
# Fix 2 — Remove confirmed broken examples
# Identified by unique broken code fragments confirmed in the 1882-sample audit
# ─────────────────────────────────────────────────────────────────────────────

BROKEN_FINGERPRINTS = [
    # Verified against data/raw/aiken_stdlib.json:
    # assets.flatten(assets.from_asset_list([])) — garbled combo, from_asset_list takes Pairs not []
    "assets.flatten(assets.from_asset_list([]))",
    # value.to_dict( — wrong module, correct is assets.to_dict( (cardano/assets, not cardano/value)
    "value.to_dict(",
    # NOTE: assets.reduce( IS valid — signature: (Value, result, fn(PolicyId, AssetName, Int, result))
    # NOTE: assets.restricted_to( IS valid — exists in cardano.assets
    # NOTE: assets.flatten( IS valid — exists in cardano.assets
]

def is_broken(output: str) -> tuple[bool, str]:
    for fp in BROKEN_FINGERPRINTS:
        if fp in output:
            return True, fp
    return False, ""

# ─────────────────────────────────────────────────────────────────────────────
# Fix 3 — Detect truncated outputs (report only)
# ─────────────────────────────────────────────────────────────────────────────

def count_braces(text: str) -> int:
    """Returns open - close brace count. 0 = balanced."""
    return text.count('{') - text.count('}')

def extract_code_blocks(text: str) -> list[str]:
    return re.findall(r'```(?:\w+)?\n(.*?)```', text, re.DOTALL)

def is_truncated(output: str) -> tuple[bool, str]:
    # Check 1: output ends mid-word (no sentence-ending punctuation or closing brace/backtick)
    stripped = output.strip()
    if stripped and stripped[-1] not in '.`})\n':
        return True, f"ends_abruptly: ...{stripped[-30:]!r}"

    # Check 2: unbalanced braces inside code blocks
    for block in extract_code_blocks(output):
        imbalance = count_braces(block)
        if imbalance > 0:
            return True, f"unclosed_braces: {imbalance} open without close"

    # Check 3: code block opened but never closed
    opens  = output.count('```')
    if opens % 2 != 0:
        return True, "unclosed_code_fence"

    return False, ""

# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",    default=str(INPUT_PATH))
    parser.add_argument("--output",   default=str(OUTPUT_PATH))
    parser.add_argument("--report",   default=str(REPORT_PATH))
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    print(f"\nCardumen Forge — Build v16")
    print(f"Input  : {args.input}")
    print(f"Output : {args.output}\n")

    with open(args.input, encoding="utf-8") as f:
        examples = [json.loads(l) for l in f if l.strip()]
    print(f"Loaded : {len(examples):,} examples")

    # ── Apply fixes ──────────────────────────────────────────────────────────
    results = []
    stats = {
        "fn_else_fixed":   0,
        "broken_removed":  0,
        "truncated_found": 0,
    }
    broken_log   = []
    truncated_log = []

    for ex in examples:
        output = ex.get("output", "")

        # Fix 2: check broken before modifying
        broken, fp = is_broken(output)
        if broken:
            stats["broken_removed"] += 1
            broken_log.append({
                "source":      ex.get("source"),
                "topic":       ex.get("topic"),
                "instruction": ex.get("instruction", "")[:120],
                "fingerprint": fp,
            })
            continue  # drop example

        # Fix 1: fn else( → else(
        fixed_output, n = fix_fn_else(output)
        if n > 0:
            stats["fn_else_fixed"] += n
            ex = {**ex, "output": fixed_output}

        # Fix 3: detect truncated (report only, keep example)
        truncated, reason = is_truncated(ex.get("output", ""))
        if truncated:
            stats["truncated_found"] += 1
            truncated_log.append({
                "source":      ex.get("source"),
                "topic":       ex.get("topic"),
                "instruction": ex.get("instruction", "")[:100],
                "reason":      reason,
                "output_tail": ex.get("output", "")[-80:].replace("\n", "↵"),
            })

        results.append(ex)

    # ── Print summary ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Fix 1 — fn else( fixed      : {stats['fn_else_fixed']}")
    print(f"  Fix 2 — broken examples removed : {stats['broken_removed']}")
    print(f"  Fix 3 — truncated detected   : {stats['truncated_found']} (kept, not modified)")
    print(f"  Final dataset size           : {len(results):,}")
    print(f"{'='*60}")

    # ── Broken examples detail ───────────────────────────────────────────────
    if broken_log:
        print(f"\n  Removed examples:")
        for b in broken_log:
            print(f"    [{b['fingerprint'][:40]}]")
            print(f"    source={b['source']} topic={b['topic']}")
            print(f"    {b['instruction'][:80]}")

    # ── Save dataset ─────────────────────────────────────────────────────────
    if not args.dry_run:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            for ex in results:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"\n  ✅ Saved → {args.output}")
    else:
        print(f"\n  (dry run — nothing written)")

    # ── Save report ──────────────────────────────────────────────────────────
    report_lines = [
        "# Dataset v16 Build Report",
        "",
        f"**Input:** `{args.input}` ({len(examples):,} examples)",
        f"**Output:** `{args.output}` ({len(results):,} examples)",
        "",
        "## Fixes Applied",
        "",
        f"| Fix | Result |",
        f"|-----|--------|",
        f"| `fn else(` → `else(` | {stats['fn_else_fixed']} occurrences fixed |",
        f"| Broken examples removed | {stats['broken_removed']} examples dropped |",
        f"| Truncated outputs detected | {stats['truncated_found']} flagged (not modified) |",
        "",
        "## Removed Examples",
        "",
    ]
    for b in broken_log:
        report_lines += [
            f"- **{b['fingerprint']}**",
            f"  - source: `{b['source']}`  topic: `{b['topic']}`",
            f"  - instruction: {b['instruction']}",
            "",
        ]

    report_lines += [
        "## Truncated Outputs (top 30)",
        "",
        "These examples were kept but flagged for future regeneration.",
        "",
        "| Source | Topic | Reason | Tail |",
        "|--------|-------|--------|------|",
    ]
    for t in truncated_log[:30]:
        src   = (t['source'] or '')[:20]
        topic = (t['topic']  or '')[:30]
        reason = t['reason'][:40]
        tail   = t['output_tail'][:40]
        report_lines.append(f"| `{src}` | `{topic}` | {reason} | `{tail}` |")

    if len(truncated_log) > 30:
        report_lines.append(f"\n_...and {len(truncated_log)-30} more. Full list in memory._")

    report_lines += [
        "",
        "## Pending (not done in this build)",
        "",
        "- [ ] Fix `import` → `use` (needs manual review)",
        "- [ ] Fix `ScriptCredential` → `Script` (needs correction-example check)",
        "- [ ] Fix `cardano/value` → `cardano/assets` (needs context check)",
        "- [ ] Fix `PolicyId` wrong imports (~50-100 examples)",
        "- [ ] Reduce 800+ duplicate signature-check examples",
        "- [ ] Regenerate ~300-400 truncated outputs",
        "- [ ] Verify 1,500 PLAUSIBLE_NEEDS_CHECK examples",
        "- [ ] Generate new: propose(15), vote(20), publish(20), state machine(20), CIP-68(15)",
        "",
        "_Generated by `scripts/build_v16.py`_",
    ]

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(report_lines), encoding="utf-8")
    print(f"  Report → {args.report}")


if __name__ == "__main__":
    main()
