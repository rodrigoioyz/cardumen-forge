#!/usr/bin/env python3
"""
generate_corrections_v2.py
Genera ~50 nuevos ejemplos CORRECTION cubriendo anti-patrones de Conway-era,
dict/pairs, rational, tx.inputs vs self.inputs, y errores en multi-handler.

Uso:
    python3 generate_corrections_v2.py --dry-run
    python3 generate_corrections_v2.py
    python3 generate_corrections_v2.py --model claude-haiku-4-5-20251001
"""

import os, sys, json, argparse
from collections import Counter
from anthropic import Anthropic

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS    = 8000
OUTPUT_PATH   = "data/processed/corrections_v2.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# Tool schema
# ─────────────────────────────────────────────────────────────────────────────
TOOL_SCHEMA = {
    "name": "save_correction_examples",
    "description": "Save a batch of Aiken v3 correction examples",
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

# ─────────────────────────────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a senior Aiken v3 engineer creating a CORRECTION dataset for fine-tuning an LLM.

## Correct Aiken v3 reference

Handler signatures (all inside validator { } block):
  spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
  withdraw(redeemer: T, account: StakeCredential, self: Transaction) -> Bool
  publish(redeemer: T, cert: Certificate, self: Transaction) -> Bool
  vote(redeemer: T, voter: Voter, self: Transaction) -> Bool

Transaction fields accessed via `self`:
  self.inputs, self.outputs, self.mint, self.reference_inputs,
  self.validity_range, self.extra_signatories, self.redeemers, self.datums, self.id

Correct imports (slash, NEVER dot):
  use cardano/assets
  use cardano/transaction
  use cardano/certificate.{Certificate}
  use cardano/governance.{Voter, ProposalProcedure}
  use aiken/interval
  use aiken/collection/list
  use aiken/collection/dict
  use aiken/collection/pairs
  use aiken/math/rational
  use aiken/crypto.{VerificationKeyHash}

Conway-era:
  publish handler: publish(redeemer: T, cert: Certificate, self: Transaction)
  vote handler:    vote(redeemer: T, voter: Voter, self: Transaction)
  Certificate type from: use cardano/certificate.{Certificate}
  Voter type from:        use cardano/governance.{Voter}

dict API (aiken/collection/dict):
  dict.get(d, key) -> Option<value>
  dict.insert(d, key, value, compare) -> Dict<k,v>
  dict.delete(d, key) -> Dict<k,v>
  dict.to_pairs(d) -> Pairs<k,v>
  dict.size(d) -> Int
  WRONG: dict.to_list, dict.get_or_default, dict.lookup

rational API (aiken/math/rational):
  rational.new(numerator, denominator) -> Option<Rational>
  rational.add(a, b) -> Rational
  rational.mul(a, b) -> Rational
  rational.compare(a, b) -> Ordering
  rational.to_int(r) -> Int
  WRONG: rational.from_int, rational.divide, rational.gte, rational.value

## HARD RULES for output
- Correct code only in `output` field — no broken code in outputs
- instruction: "Fix this Aiken v3 error: [describe error]"
- input: the WRONG snippet
- output: brief explanation of what's wrong + CORRECT replacement code
- No meta-comments inside code (// Fixed, // Correct, etc.)
- No TODO placeholders
"""

# ─────────────────────────────────────────────────────────────────────────────
# Batch configs
# ─────────────────────────────────────────────────────────────────────────────
BATCH_CONFIGS = [
    ("conway_era_errors", 20, """\
Generate 20 Aiken v3 CORRECTION examples for Conway-era handler errors.

Cover these mistakes (at least 5 each):
1. Wrong publish signature: `fn publish(redeemer: T, self: Transaction)` — missing `cert: Certificate`
   Correct: `publish(redeemer: T, cert: Certificate, self: Transaction) -> Bool`

2. Wrong vote signature: `fn vote(redeemer: T, self: Transaction)` — missing `voter: Voter`
   Correct: `vote(redeemer: T, voter: Voter, self: Transaction) -> Bool`

3. Wrong import for Certificate: `use cardano/transaction.{Certificate}` or `use aiken/certificate`
   Correct: `use cardano/certificate.{Certificate}`

4. Wrong import for Voter: `use cardano/transaction.{Voter}` or `use aiken/governance.{Voter}`
   Correct: `use cardano/governance.{Voter}`

Each example:
- instruction: "Fix this Aiken v3 error: [specific error]"
- input: wrong snippet
- output: explanation + correct validator code

Call save_correction_examples with 20 examples.
"""),

    ("tx_fields_errors", 15, """\
Generate 15 Aiken v3 CORRECTION examples for Transaction field access errors.

Cover these mistakes (at least 3 each):
1. `tx.inputs` or `ctx.inputs` → correct: `self.inputs`
2. `tx.extra_signatories` → correct: `self.extra_signatories`
3. `tx.validity_range` or `ctx.validity_range` → correct: `self.validity_range`
4. `ctx.transaction.inputs` → correct: `self.inputs` (v3 passes Transaction directly as `self`)
5. `context.signers` or `tx.signers` → correct: `self.extra_signatories`

Each example must show a full validator context with the error in a realistic handler.

Call save_correction_examples with 15 examples.
"""),

    ("dict_rational_errors", 15, """\
Generate 15 Aiken v3 CORRECTION examples for dict and rational API errors.

Cover dict errors (at least 4 examples):
1. `dict.to_list(d)` → correct: `dict.to_pairs(d)`
2. `dict.lookup(d, key)` → correct: `dict.get(d, key)`
3. `dict.get_or_default(d, key, default)` → correct: `when dict.get(d, key) is { Some(v) -> v  None -> default }`
4. Wrong dict import: `use aiken/dict` → correct: `use aiken/collection/dict`

Cover rational errors (at least 4 examples):
1. `rational.from_int(n)` → correct: `rational.new(n, 1) |> option.or_else(rational.zero())`
   Actually correct: `rational.new(n, 1)` returns Option<Rational>
2. `rational.divide(a, b)` → correct: `rational.new(numerator, denominator)`
3. `rational.gte(a, b)` → correct: `rational.compare(a, b) != Less` or use `when`
4. Wrong rational import: `use aiken/rational` → correct: `use aiken/math/rational`

Each example shows realistic validator context where the error would appear.

Call save_correction_examples with 15 examples.
"""),
]

# ─────────────────────────────────────────────────────────────────────────────
# Claude call
# ─────────────────────────────────────────────────────────────────────────────
def call_claude(prompt: str, model: str, client, dry_run: bool = False) -> list:
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


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--model",     default=DEFAULT_MODEL)
    parser.add_argument("--output",    default=OUTPUT_PATH)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.overwrite and os.path.exists(args.output):
        print(f"ERROR: {args.output} ya existe. Usa --overwrite para sobreescribir.")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY no encontrada.")
        sys.exit(1)

    client = Anthropic(api_key=api_key) if not args.dry_run else None

    all_examples = []
    type_counts  = {}

    total_expected = sum(n for _, n, _ in BATCH_CONFIGS)
    print(f"Batches: {len(BATCH_CONFIGS)} | Esperados: ~{total_expected} ejemplos\n")

    for label, expected, prompt in BATCH_CONFIGS:
        print(f"[{label}] Generando ~{expected} ejemplos...")
        examples = call_claude(prompt, args.model, client, args.dry_run)
        print(f"  Recibidos: {len(examples)}")

        for ex in examples:
            ex["source"]        = "correction_set_v2"
            ex["topic"]         = f"correction/{label}"
            ex["review_status"] = "CORRECTION"
            ex.setdefault("lang", "en")

        all_examples.extend(examples)
        type_counts[label] = len(examples)

    print(f"\n{'='*52}")
    print(f"  Total generados: {len(all_examples)}")
    for label, cnt in type_counts.items():
        print(f"  {label}: {cnt}")
    print(f"{'='*52}")

    if args.dry_run:
        print("\n[DRY RUN] No se escribió nada.")
        return

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    written = sum(1 for _ in open(args.output, encoding="utf-8"))
    print(f"\n  Output: {args.output} ({written} líneas)")
    print(f"\nAgregar a v14:")
    print(f"  Actualizar build_dataset_v14.py para incluir {args.output}")


if __name__ == "__main__":
    main()
