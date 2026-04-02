#!/usr/bin/env python3
"""
generate_correction_set.py
Genera el correction dataset para fijar API hallucinations del modelo fine-tuneado.

Uso:
    python3 generate_correction_set.py
    python3 generate_correction_set.py --dry-run
    python3 generate_correction_set.py --model claude-haiku-4-5-20251001
    python3 generate_correction_set.py --output data/processed/correction_set.jsonl
"""

import os
import sys
import json
import argparse
from collections import Counter
from anthropic import Anthropic

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS    = 8000
BATCH_SIZE    = 30   # más pequeño que el generador general — ejemplos más densos

# ─────────────────────────────────────────────
# Tool schema
# ─────────────────────────────────────────────
TOOL_SCHEMA = {
    "name": "save_correction_examples",
    "description": "Save a batch of correction examples for Aiken v3 API grounding",
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

# ─────────────────────────────────────────────
# System prompt — base rules
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a senior Aiken v3 engineer generating a correction dataset for a fine-tuned LLM.

The model has these specific hallucinations that must be corrected:
  - transaction.signatories(tx)        → WRONG, does not exist
  - list.has_any(list, other_list)     → WRONG, does not exist
  - assets.has_nft(value, policy)      → WRONG (missing asset_name arg)
  - interval.is_after(point, range)    → WRONG (function/arg order)
  - use cardano.transaction.{...}      → WRONG (dot not slash)
  - use cardano/governance/transaction → WRONG (module does not exist)

## CORRECT Aiken v3 APIs

Transaction fields (via `self` in handlers):
  self.inputs, self.outputs, self.mint, self.reference_inputs,
  self.validity_range, self.extra_signatories, self.redeemers, self.datums, self.id

Signature check:
  list.has(self.extra_signatories, key)          ← CORRECT
  list.count(admins, fn(k) { list.has(self.extra_signatories, k) }) >= N  ← CORRECT

Assets:
  assets.lovelace_of(value) -> Int
  assets.quantity_of(value, policy_id, asset_name) -> Int   ← asset_name REQUIRED
  assets.has_nft(value, policy_id, asset_name) -> Bool      ← asset_name REQUIRED

Interval:
  interval.contains(range, point) -> Bool
  interval.is_entirely_before(range, point) -> Bool
  interval.is_entirely_after(range, point) -> Bool

Transaction helpers:
  transaction.find_input(inputs, output_reference) -> Option<Input>
  transaction.resolve_input(inputs, output_reference) -> Input

Correct imports (slash, never dot):
  use cardano/assets
  use cardano/transaction
  use aiken/interval
  use aiken/collection/list
  use aiken/crypto.{VerificationKeyHash}

Validator handler signatures (v3):
  spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
  withdraw(redeemer: T, account: StakeCredential, self: Transaction) -> Bool

## HARD RULES

NEVER generate:
  - transaction.signatories(tx)
  - list.has_any(...)
  - assets.has_nft(value, policy)  [without asset_name]
  - dot-style imports
  - invented modules

Code outputs must be the final solution only.
No meta-comments like // Correct approach or // Fixed.
No reasoning inside code blocks.
No TODO placeholders.
"""

# ─────────────────────────────────────────────
# Batch prompts — uno por tipo
# ─────────────────────────────────────────────

BATCH_CONFIGS = [
    # (type_label, n_examples, prompt_body)

    ("TYPE_A_signatories", 25, """\
Generate 25 Aiken v3 examples focused EXCLUSIVELY on correct signature checking.

REQUIRED: every example uses self.extra_signatories correctly.
Vary contexts: single signer, 2-of-N multisig, admin check, owner-only spend, mint gated by key.

Each example must:
- use full validator structure: validator name { fn spend/mint(..., self) { ... } }
- use list.has(self.extra_signatories, key) OR list.count(admins, fn(k) { list.has(...) }) >= N
- NEVER use transaction.signatories(tx)
- include correct imports

Call save_correction_examples with 25 examples.
"""),

    ("TYPE_A_assets", 25, """\
Generate 25 Aiken v3 examples focused EXCLUSIVELY on correct assets usage.

REQUIRED APIs to cover:
- assets.lovelace_of(value) — min ADA checks, output value checks
- assets.quantity_of(value, policy_id, asset_name) — token counts, mint caps, burn checks
- assets.has_nft(value, policy_id, asset_name) — NFT gating (ALL 3 args required)

Vary contexts: spend validators, mint policies, min-ada enforcement, NFT gates, multi-token checks.

Each example must:
- use full validator structure
- NEVER call assets.has_nft with only 2 args
- NEVER use output.value.lovelace
- include correct imports: use cardano/assets

Call save_correction_examples with 25 examples.
"""),

    ("TYPE_A_interval", 25, """\
Generate 25 Aiken v3 examples focused EXCLUSIVELY on correct interval and time usage.

REQUIRED APIs:
- interval.contains(self.validity_range, point) -> Bool
- interval.is_entirely_before(self.validity_range, deadline) -> Bool
- interval.is_entirely_after(self.validity_range, deadline) -> Bool

Vary contexts: spend-after-deadline, spend-before-expiry, time-bounded mint, claim windows.

Each example must:
- use full validator structure
- use self.validity_range (NOT tx.validity_range, NOT ctx.transaction.validity_range)
- NEVER use interval.is_after(deadline, range) — wrong function and wrong arg order
- include: use aiken/interval

Call save_correction_examples with 25 examples.
"""),

    ("TYPE_A_list_and_reference", 25, """\
Generate 25 Aiken v3 examples covering:
- correct list operations: list.has, list.all, list.any, list.count, list.filter, list.map
- reference_inputs usage: self.reference_inputs to read oracle/config UTxOs

REQUIRED:
- NEVER use list.has_any — use list.any(list, fn(x) { ... }) instead
- NEVER use list.has_all — use list.all(list, fn(x) { ... }) instead
- reference_inputs examples must show reading datum from a reference UTxO

Each example must use full validator structure with correct imports.

Call save_correction_examples with 25 examples.
"""),

    ("TYPE_B_imports", 30, """\
Generate 30 Aiken v3 examples focused EXCLUSIVELY on correct import syntax.

Each example should:
- show a correct import and briefly explain why it's correct
- OR contrast a wrong import with the correct one

Cover ALL these modules:
  use cardano/assets          (NOT cardano.assets, NOT cardano/assets/{Assets})
  use cardano/transaction     (NOT cardano.transaction.{Transaction})
  use aiken/interval          (NOT aiken.interval)
  use aiken/collection/list   (NOT aiken/list, NOT aiken.list)
  use aiken/crypto.{VerificationKeyHash}  (correct destructure)

Mix:
- 10 examples: "What is the correct import for X?"
- 10 examples: "Fix this incorrect import: [wrong]"
- 10 examples: short validators showing correct imports in context

Call save_correction_examples with 30 examples.
"""),

    ("TYPE_C_corrections", 50, """\
Generate 50 Aiken v3 NEGATIVE CORRECTION examples.

Each example must:
- show a piece of WRONG code in `input`
- explain briefly what's wrong
- show the CORRECT replacement in `output`

REQUIRED: you MUST cover each of these hallucinations at least 6 times each:

1. transaction.signatories(tx) → correct: list.has(self.extra_signatories, key)
2. list.has_any(a, b) → correct: list.any(b, fn(x) { list.has(a, x) })
3. assets.has_nft(value, policy) [2 args] → correct: assets.has_nft(value, policy, asset_name)
4. interval.is_after(deadline, range) → correct: interval.is_entirely_after(range, deadline)
5. use cardano.transaction.{Transaction} → correct: use cardano/transaction
6. use cardano/governance/transaction → correct: module does not exist; use cardano/transaction

Also include:
- 4 examples: missing validator {} wrapper (bare functions)
- 4 examples: tx.validity_range → correct: self.validity_range
- 4 examples: output.value.lovelace → correct: assets.lovelace_of(output.value)

Format for each:
- instruction: "Fix this Aiken v3 error: [describe the error]"
- input: the broken code snippet
- output: explanation of what's wrong + corrected code

Call save_correction_examples with 50 examples.
"""),
]

# ─────────────────────────────────────────────
# Claude call
# ─────────────────────────────────────────────
def call_claude(prompt: str, model: str, client: Anthropic, dry_run: bool = False) -> list:
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


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Genera correction dataset para Aiken v3 API grounding")
    parser.add_argument("--output",    default="data/processed/correction_set.jsonl")
    parser.add_argument("--model",     default=DEFAULT_MODEL)
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not args.overwrite and not args.dry_run and os.path.exists(args.output):
        print(f"ERROR: {args.output} ya existe. Usa --overwrite para sobreescribir.")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY no encontrada.")
        sys.exit(1)

    client = Anthropic(api_key=api_key) if not args.dry_run else None

    all_examples = []
    type_counts = {}

    for type_label, expected, prompt_body in BATCH_CONFIGS:
        print(f"\n[{type_label}] Generando ~{expected} ejemplos...")
        examples = call_claude(prompt_body, args.model, client, args.dry_run)
        print(f"  Recibidos: {len(examples)}")

        # Agregar metadata de tipo para tracking
        for ex in examples:
            ex["source"]       = "correction_set"
            ex["topic"]        = f"correction/{type_label.lower()}"
            ex["review_status"] = "VERIFIED_V3_ALIGNED" if "TYPE_A" in type_label or "TYPE_B" in type_label else "CORRECTION"
            ex["lang"]         = ex.get("lang", "en")

        all_examples.extend(examples)
        type_counts[type_label] = len(examples)

    print(f"\n{'='*52}")
    print(f"  Total generados: {len(all_examples)}")
    for label, cnt in type_counts.items():
        print(f"  {label}: {cnt}")
    print(f"{'='*52}")

    if args.dry_run:
        print("\n[DRY RUN] No se escribió ningún archivo.")
        return

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Summary
    summary_path = args.output.replace(".jsonl", "_summary.json")
    summary = {
        "total": len(all_examples),
        "by_type": type_counts,
        "by_lang": dict(Counter(e.get("lang","?") for e in all_examples)),
        "output": args.output,
        "model": args.model,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n  Output  : {args.output}")
    print(f"  Summary : {summary_path}")
    print(f"\nPara agregar al dataset principal:")
    print(f"  cat {args.output} >> data/processed/dataset_v8_train.jsonl")
    print(f"  wc -l data/processed/dataset_v8_train.jsonl")


if __name__ == "__main__":
    main()
