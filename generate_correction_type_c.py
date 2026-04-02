#!/usr/bin/env python3
"""
generate_correction_type_c.py
Genera SOLO el bloque TYPE_C (negative corrections) del correction set.

Uso:
    python3 generate_correction_type_c.py
    python3 generate_correction_type_c.py --dry-run
    python3 generate_correction_type_c.py --model claude-haiku-4-5-20251001
"""

import os
import sys
import json
import argparse
from collections import Counter
from anthropic import Anthropic

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS    = 8000

OUTPUT_PATH   = "data/processed/correction_set_type_c.jsonl"
SUMMARY_PATH  = "data/processed/correction_set_type_c_summary.json"

TOOL_SCHEMA = {
    "name": "save_correction_examples",
    "description": "Save a batch of negative correction examples for Aiken v3",
    "input_schema": {
        "type": "object",
        "properties": {
            "examples": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "instruction": {"type": "string"},
                        "input":       {"type": "string"},
                        "output":      {"type": "string"},
                    },
                    "required": ["instruction", "input", "output"],
                },
            }
        },
        "required": ["examples"],
    },
}

SYSTEM_PROMPT = """\
You are a senior Aiken v3 engineer generating NEGATIVE CORRECTION examples for a fine-tuned LLM.

The model produces these hallucinations. Your examples must directly contradict them.

## CORRECT Aiken v3 APIs

Signatures:
  list.has(self.extra_signatories, key)         ← CORRECT
  NOT: transaction.signatories(tx)               ← does not exist

List operations:
  list.any(items, fn(x) { ... })                ← CORRECT
  NOT: list.has_any(a, b)                        ← does not exist

Assets (ALL require 3 args: value, policy_id, asset_name):
  assets.has_nft(value, policy_id, "TokenName") ← CORRECT
  NOT: assets.has_nft(value, policy_id)          ← missing asset_name

  assets.lovelace_of(output.value)              ← CORRECT
  NOT: output.value.lovelace                     ← field does not exist

Interval:
  interval.is_entirely_after(self.validity_range, deadline)  ← CORRECT
  NOT: interval.is_after(deadline, tx.validity_range)         ← wrong fn + wrong arg order

Transaction access:
  self.validity_range   ← CORRECT (self is the Transaction)
  NOT: tx.validity_range, NOT: ctx.transaction.validity_range

Imports (slash-style only):
  use cardano/assets           ← CORRECT
  use cardano/transaction      ← CORRECT
  NOT: use cardano.transaction.{Transaction, TransactionSigner}
  NOT: use cardano/governance/transaction   ← module does not exist

Validator structure (REQUIRED):
  validator name {
    fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool {
      ...
    }
  }
  NOT: bare fn definitions outside a validator block

## FORMAT RULES

Each example:
- instruction: "Fix this Aiken v3 error: [short description]"
- input: the broken code snippet
- output: one sentence explaining what's wrong + corrected code

Code in output must be final solution only. No // Correct, no // Fixed comments.
"""

# Two batches of 25 — TYPE_C fails at 50 because output is too long
BATCH_PROMPTS = [
    ("TYPE_C_batch1", 25, """\
Generate 25 Aiken v3 negative correction examples (batch 1 of 2).

REQUIRED coverage in this batch — at least 4 examples each:
1. transaction.signatories(tx)  → list.has(self.extra_signatories, key)
2. list.has_any(a, b)           → list.any(b, fn(x) { list.has(a, x) })
3. assets.has_nft(v, p) [2 args] → assets.has_nft(v, p, asset_name) [3 args required]
4. output.value.lovelace        → assets.lovelace_of(output.value)
5. missing validator {} wrapper  → correct validator block structure

Each example:
- instruction: "Fix this Aiken v3 error: [short description]"
- input: broken code snippet (5-15 lines max)
- output: one sentence of diagnosis + corrected code

Call save_correction_examples with exactly 25 examples.
"""),

    ("TYPE_C_batch2", 25, """\
Generate 25 Aiken v3 negative correction examples (batch 2 of 2).

REQUIRED coverage in this batch — at least 4 examples each:
1. interval.is_after(deadline, range) → interval.is_entirely_after(self.validity_range, deadline)
2. use cardano.transaction.{Transaction} → use cardano/transaction  (dot vs slash)
3. use cardano/governance/transaction   → does not exist; use cardano/transaction
4. tx.validity_range                    → self.validity_range
5. assets.quantity_of called with wrong arg count or order

Each example:
- instruction: "Fix this Aiken v3 error: [short description]"
- input: broken code snippet (5-15 lines max)
- output: one sentence of diagnosis + corrected code

Call save_correction_examples with exactly 25 examples.
"""),
]


def call_claude(prompt, model, client, dry_run=False):
    if dry_run:
        print(f"  [DRY RUN] prompt {len(prompt)} chars")
        return []

    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "save_correction_examples"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "save_correction_examples":
            return block.input.get("examples", [])
    return []


def main():
    parser = argparse.ArgumentParser(description="Genera TYPE_C correction examples")
    parser.add_argument("--model",     default=DEFAULT_MODEL)
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not args.overwrite and not args.dry_run and os.path.exists(OUTPUT_PATH):
        print(f"ERROR: {OUTPUT_PATH} ya existe. Usa --overwrite para sobreescribir.")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY no encontrada.")
        sys.exit(1)

    client = Anthropic(api_key=api_key) if not args.dry_run else None

    collected = []
    batch_counts = {}

    for label, expected, prompt in BATCH_PROMPTS:
        print(f"\n[{label}] Generando ~{expected} ejemplos...")
        examples = call_claude(prompt, args.model, client, args.dry_run)
        print(f"  Recibidos: {len(examples)}")

        for ex in examples:
            ex["source"]        = "correction_set"
            ex["topic"]         = "correction/type_c_negative"
            ex["review_status"] = "CORRECTION"
            ex.setdefault("lang", "en")

        collected.extend(examples)
        batch_counts[label] = len(examples)

    print(f"\n{'='*50}")
    print(f"  TYPE_C total: {len(collected)}")
    for label, cnt in batch_counts.items():
        print(f"  {label}: {cnt}")
    print(f"{'='*50}")

    if args.dry_run:
        print("\n[DRY RUN] No se escribió ningún archivo.")
        return

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for ex in collected:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    summary = {
        "total": len(collected),
        "by_batch": batch_counts,
        "by_lang": dict(Counter(e.get("lang","?") for e in collected)),
        "output": OUTPUT_PATH,
        "model": args.model,
    }
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n  Output  : {OUTPUT_PATH}")
    print(f"  Summary : {SUMMARY_PATH}")
    print(f"\nPara agregar al correction set completo:")
    print(f"  cat {OUTPUT_PATH} >> data/processed/correction_set.jsonl")
    print(f"\nPara agregar al dataset principal:")
    print(f"  cat data/processed/correction_set.jsonl >> data/processed/dataset_v8_train.jsonl")


if __name__ == "__main__":
    main()
