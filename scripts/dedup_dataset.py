#!/usr/bin/env python3
"""
dedup_dataset.py — Cardumen Forge
Removes duplicate and near-duplicate examples from the dataset.

Two passes:
  Pass 1 — Exact dedup: hash of normalized output (catches identical outputs)
  Pass 2 — Near-dedup: normalized instruction similarity > threshold
            Uses character n-gram overlap (no embeddings, no API cost)

Safety rules:
  - Correction examples are never removed (always keep anti-pattern teaching)
  - When deduplicating, keep the example with VERIFIED_V3_ALIGNED status over PLAUSIBLE
  - Dry-run by default — shows what would be removed without writing

Usage:
    python3 scripts/dedup_dataset.py                    # dry-run, full report
    python3 scripts/dedup_dataset.py --write            # apply and save
    python3 scripts/dedup_dataset.py --threshold 0.85   # similarity threshold (default 0.9)
    python3 scripts/dedup_dataset.py --output-only      # only hash outputs (skip near-dedup)
"""

import re
import json
import hashlib
import argparse
from pathlib import Path
from collections import defaultdict

INPUT_PATH  = Path("data/processed/dataset_v17_train_split.jsonl")
OUTPUT_PATH = Path("data/processed/dataset_v17_dedup.jsonl")
REPORT_PATH = Path("logs/dedup_report.md")

DEFAULT_THRESHOLD = 0.90  # instruction similarity above this = near-duplicate

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, remove punctuation noise."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def hash_output(output: str) -> str:
    """MD5 of normalized output — catches exact duplicate code."""
    return hashlib.md5(normalize(output).encode()).hexdigest()


def ngram_similarity(a: str, b: str, n: int = 3) -> float:
    """Character n-gram Jaccard similarity. Fast, no dependencies."""
    def ngrams(s):
        return set(s[i:i+n] for i in range(len(s) - n + 1))
    na, nb = ngrams(normalize(a)), ngrams(normalize(b))
    if not na or not nb:
        return 0.0
    return len(na & nb) / len(na | nb)


STATUS_PRIORITY = {
    "VERIFIED_V3_ALIGNED": 0,
    "CORRECTION":          1,
    "PLAUSIBLE_NEEDS_CHECK": 2,
}

def better_example(a: dict, b: dict) -> dict:
    """Return the higher-quality example between two duplicates."""
    pa = STATUS_PRIORITY.get(a.get("review_status", ""), 99)
    pb = STATUS_PRIORITY.get(b.get("review_status", ""), 99)
    if pa != pb:
        return a if pa < pb else b
    # Same status — prefer longer output (more complete)
    return a if len(a.get("output", "")) >= len(b.get("output", "")) else b


def is_correction(ex: dict) -> bool:
    return ("correction" in ex.get("topic",  "").lower() or
            "correction" in ex.get("source", "").lower())


# ─────────────────────────────────────────────────────────────────────────────
# Pass 1 — Exact output dedup
# ─────────────────────────────────────────────────────────────────────────────

def pass1_exact(examples: list) -> tuple[list, list]:
    """Remove examples with identical outputs. Returns (kept, removed)."""
    seen   = {}   # hash → index of kept example
    kept   = []
    removed = []

    for ex in examples:
        if is_correction(ex):
            kept.append(ex)
            continue

        h = hash_output(ex.get("output", ""))
        if h not in seen:
            seen[h] = len(kept)
            kept.append(ex)
        else:
            # Compare quality and potentially swap
            existing_idx = seen[h]
            winner = better_example(kept[existing_idx], ex)
            if winner is ex:
                removed.append(kept[existing_idx])
                kept[existing_idx] = ex
                seen[h] = existing_idx
            else:
                removed.append(ex)

    return kept, removed


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2 — Near-duplicate instruction dedup
# ─────────────────────────────────────────────────────────────────────────────

def pass2_near(examples: list, threshold: float) -> tuple[list, list]:
    """
    Remove near-duplicate instructions within the same topic/category.
    Groups by first 2 words of normalized instruction to limit comparisons.
    """
    kept    = []
    removed = []

    # Group by topic prefix + first 2 words for efficient comparison
    groups  = defaultdict(list)
    for i, ex in enumerate(examples):
        if is_correction(ex):
            kept.append(ex)
            continue
        topic  = ex.get("topic", "")[:30]
        words  = normalize(ex.get("instruction", "")).split()[:2]
        key    = topic + " " + " ".join(words)
        groups[key].append(i)

    kept_indices = set()

    for key, indices in groups.items():
        if len(indices) == 1:
            kept_indices.add(indices[0])
            continue

        # Pairwise similarity within group
        cluster_kept = [indices[0]]
        for i in indices[1:]:
            ex_i   = examples[i]
            instr_i = ex_i.get("instruction", "")
            is_dup  = False
            for j in cluster_kept:
                ex_j    = examples[j]
                instr_j = ex_j.get("instruction", "")
                sim     = ngram_similarity(instr_i, instr_j)
                if sim >= threshold:
                    # Keep better quality
                    winner = better_example(ex_i, ex_j)
                    if winner is ex_i:
                        cluster_kept.remove(j)
                        cluster_kept.append(i)
                    is_dup = True
                    break
            if not is_dup:
                cluster_kept.append(i)

        kept_indices.update(cluster_kept)

    for i, ex in enumerate(examples):
        if is_correction(ex):
            continue  # already added above
        if i in kept_indices:
            kept.append(ex)
        else:
            removed.append(ex)

    return kept, removed


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",       default=str(INPUT_PATH))
    parser.add_argument("--output",      default=str(OUTPUT_PATH))
    parser.add_argument("--report",      default=str(REPORT_PATH))
    parser.add_argument("--threshold",   type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--write",       action="store_true")
    parser.add_argument("--output-only", action="store_true", help="Skip near-dedup pass")
    args = parser.parse_args()

    print(f"\nCardumen Forge — Dedup Dataset")
    print(f"Input     : {args.input}")
    print(f"Output    : {args.output}")
    print(f"Threshold : {args.threshold} (near-dup similarity)")
    print(f"Mode      : {'WRITE' if args.write else 'DRY RUN'}\n")

    with open(args.input, encoding="utf-8") as f:
        examples = [json.loads(l) for l in f if l.strip()]
    print(f"Loaded : {len(examples):,} examples")
    corrections = sum(1 for ex in examples if is_correction(ex))
    print(f"  Corrections (protected) : {corrections}")
    print(f"  Dedup candidates        : {len(examples) - corrections}")

    # ── Pass 1: exact output hash ─────────────────────────────────────────────
    print(f"\nPass 1 — Exact output dedup...")
    after_p1, removed_p1 = pass1_exact(examples)
    print(f"  Removed : {len(removed_p1):,}  ({len(after_p1):,} remain)")

    # ── Pass 2: near-duplicate instructions ──────────────────────────────────
    removed_p2 = []
    after_p2   = after_p1

    if not args.output_only:
        print(f"\nPass 2 — Near-duplicate instruction dedup (threshold={args.threshold})...")
        after_p2, removed_p2 = pass2_near(after_p1, args.threshold)
        print(f"  Removed : {len(removed_p2):,}  ({len(after_p2):,} remain)")

    total_removed = len(removed_p1) + len(removed_p2)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Original         : {len(examples):,}")
    print(f"  Pass 1 removed   : {len(removed_p1):,}  (exact output duplicates)")
    print(f"  Pass 2 removed   : {len(removed_p2):,}  (near-dup instructions)")
    print(f"  Final            : {len(after_p2):,}")
    print(f"  Reduction        : {100*total_removed/max(1,len(examples)):.1f}%")
    print(f"{'='*60}")

    # Sample of what would be removed
    if removed_p1:
        print(f"\n  Pass 1 sample (first 5 exact dups):")
        for ex in removed_p1[:5]:
            print(f"    [{ex.get('source')}] {ex.get('instruction','')[:80]}")

    if removed_p2:
        print(f"\n  Pass 2 sample (first 5 near-dups):")
        for ex in removed_p2[:5]:
            print(f"    [{ex.get('source')}] {ex.get('instruction','')[:80]}")

    # ── Save ─────────────────────────────────────────────────────────────────
    if args.write:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            for ex in after_p2:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"\n  ✅ Saved → {args.output}")
    else:
        print(f"\n  (dry run — use --write to apply)")

    # ── Report ────────────────────────────────────────────────────────────────
    report = [
        "# Dedup Report",
        "",
        f"**Input:** `{args.input}` ({len(examples):,} examples)",
        f"**Threshold:** {args.threshold}",
        f"**Mode:** {'WRITE' if args.write else 'DRY RUN'}",
        "",
        "## Summary",
        "",
        f"| Step | Before | Removed | After |",
        f"|------|--------|---------|-------|",
        f"| Pass 1 — exact output hash | {len(examples):,} | {len(removed_p1):,} | {len(after_p1):,} |",
        f"| Pass 2 — near-dup instructions | {len(after_p1):,} | {len(removed_p2):,} | {len(after_p2):,} |",
        "",
        "## Pass 1 — Exact duplicates removed",
        "",
        "| Source | Topic | Instruction |",
        "|--------|-------|-------------|",
    ]
    for ex in removed_p1[:50]:
        src   = (ex.get("source") or "")[:20]
        topic = (ex.get("topic")  or "")[:30]
        instr = (ex.get("instruction") or "")[:80]
        report.append(f"| `{src}` | `{topic}` | {instr} |")

    report += [
        "",
        "## Pass 2 — Near-duplicates removed",
        "",
        "| Source | Topic | Instruction |",
        "|--------|-------|-------------|",
    ]
    for ex in removed_p2[:50]:
        src   = (ex.get("source") or "")[:20]
        topic = (ex.get("topic")  or "")[:30]
        instr = (ex.get("instruction") or "")[:80]
        report.append(f"| `{src}` | `{topic}` | {instr} |")

    report += ["", "_Generated by `scripts/dedup_dataset.py`_"]

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(report), encoding="utf-8")
    print(f"  Report → {args.report}")


if __name__ == "__main__":
    main()
