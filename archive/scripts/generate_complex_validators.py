#!/usr/bin/env python3
"""
generate_complex_validators.py
Genera validators complejos usando aiken_stdlib.json, aiken_docs.json y
aiken_design_patterns.json como fuente de verdad — no inventar APIs.

Uso:
    python3 generate_complex_validators.py --dry-run
    python3 generate_complex_validators.py --output data/processed/complex_validators.jsonl
    python3 generate_complex_validators.py --overwrite
"""

import os, sys, json, argparse
from collections import Counter
from anthropic import Anthropic

DEFAULT_MODEL  = "claude-sonnet-4-6"
MAX_TOKENS     = 16000
STDLIB_PATH    = "data/raw/aiken_stdlib.json"
DOCS_PATH      = "data/raw/aiken_docs.json"
PATTERNS_PATH  = "data/raw/aiken_design_patterns.json"

TOOL_SCHEMA = {
    "name": "save_examples",
    "description": "Save Aiken v3 complex validator examples",
    "input_schema": {
        "type": "object",
        "properties": {
            "examples": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "lang":          {"type": "string", "enum": ["en", "es"]},
                        "instruction":   {"type": "string"},
                        "input":         {"type": "string"},
                        "output":        {"type": "string"},
                        "source":        {"type": "string"},
                        "topic":         {"type": "string"},
                        "review_status": {"type": "string",
                            "enum": ["VERIFIED_V3_ALIGNED", "PLAUSIBLE_NEEDS_CHECK"]},
                    },
                    "required": ["lang","instruction","input","output","source","topic","review_status"],
                },
            }
        },
        "required": ["examples"],
    },
}

# ─────────────────────────────────────────────
# Cargar contexto real desde raw files
# ─────────────────────────────────────────────
def load_stdlib_context(path: str) -> str:
    records = json.load(open(path))
    relevant_modules = {
        "cardano.assets", "cardano.transaction",
        "aiken.collection.list", "aiken.interval",
        "cardano.address", "aiken.crypto",
    }
    lines = ["## REAL AIKEN STDLIB SIGNATURES (source: aiken_stdlib.json)\n"]
    lines.append("Use ONLY these APIs. Do not invent functions.\n")
    by_module = {}
    for r in records:
        m = r.get("module", "")
        if m in relevant_modules:
            by_module.setdefault(m, []).append(r)
    for mod in sorted(by_module):
        lines.append(f"\n### {mod}")
        for r in by_module[mod]:
            sig = r.get("signature", "").strip()
            desc = r.get("description", "").strip()
            if sig:
                lines.append(f"  {sig}")
                if desc and len(desc) < 120:
                    lines.append(f"    // {desc[:120]}")
    return "\n".join(lines)


def load_pattern_examples(path: str) -> str:
    """Extrae código real de los design patterns como ejemplos de referencia."""
    files = json.load(open(path))
    lines = ["## REAL PRODUCTION PATTERNS (source: aiken_design_patterns.json)\n"]
    lines.append("Use these as structural reference for complete validators.\n")
    for f in files[:8]:  # top 8 patterns
        content = f.get("content", "").strip()
        if len(content) < 100:
            continue
        # Extraer solo bloques de código Aiken (entre ``` markers)
        code_blocks = []
        in_block = False
        block = []
        for line in content.split("\n"):
            if line.strip().startswith("```aiken") or line.strip().startswith("```"):
                if in_block:
                    code_blocks.append("\n".join(block))
                    block = []
                in_block = not in_block
            elif in_block:
                block.append(line)
        if code_blocks:
            lines.append(f"\n### Pattern: {f['name'][:50]}")
            lines.append(code_blocks[0][:800])  # primer bloque de código
    return "\n".join(lines)


def load_docs_examples(path: str) -> str:
    """Extrae ejemplos de código de la documentación oficial."""
    pages = json.load(open(path))
    lines = ["## REAL CODE EXAMPLES (source: aiken_docs.json)\n"]
    count = 0
    for page in pages:
        if count >= 6:
            break
        for section in page.get("sections", []):
            examples = section.get("code_examples", [])
            for ex in examples[:1]:
                if len(ex) > 50 and ("validator" in ex or "fn " in ex):
                    lines.append(f"\n### From docs: {page.get('title','')[:40]}")
                    lines.append(ex[:600])
                    count += 1
                    break
    return "\n".join(lines)


# ─────────────────────────────────────────────
# System prompt — construido con fuentes reales
# ─────────────────────────────────────────────
def build_system_prompt(stdlib_context: str, pattern_examples: str, docs_examples: str) -> str:
    return f"""\
You are a senior Aiken v3 engineer generating complex validator examples for LLM fine-tuning.
Your examples must be grounded in the real APIs and patterns shown below — do not invent anything.

{stdlib_context}

{pattern_examples}

{docs_examples}

## VERIFIED TRANSACTION FIELDS (self: Transaction)
  self.inputs              : List<Input>
  self.reference_inputs    : List<Input>
  self.outputs             : List<Output>
  self.fee                 : Lovelace
  self.mint                : Value
  self.validity_range      : ValidityRange
  self.extra_signatories   : List<VerificationKeyHash>
  self.redeemers           : Pairs<ScriptPurpose, Redeemer>
  self.datums              : Dict<DataHash, Data>
  self.id                  : TransactionId

## VERIFIED HANDLER SIGNATURES (Aiken v3) — MANDATORY STRUCTURE

  validator my_contract {{
    fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool {{
      ...
    }}
    fn mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool {{
      ...
    }}
    fn withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool {{
      ...
    }}
  }}

  CRITICAL RULES:
  - ALWAYS use the fn keyword before the handler name
  - ALWAYS wrap handlers inside validator {{ }} block
  - NEVER write bare fn spend() outside a validator block
  - NEVER invent extra parameters (policy_id, _own_vout, _self_vout, etc.)
  - spend has exactly 4 params: datum, redeemer, own_ref, self
  - mint has exactly 3 params: redeemer, policy_id, self
  - withdraw has exactly 3 params: redeemer, account, self

## VERIFIED IMPORTS (slash-style only)
  use cardano/assets
  use cardano/transaction
  use aiken/interval
  use aiken/collection/list
  use aiken/crypto.{{VerificationKeyHash}}

## KNOWN CORRECT PATTERNS
  -- ADA amount (ONLY correct way):
  assets.lovelace_of(output.value) >= amount

  -- Signature check:
  list.has(self.extra_signatories, key)

  -- N-of-M multisig:
  list.count(admins, fn(k) {{ list.has(self.extra_signatories, k) }}) >= n

  -- NFT check (3 args required):
  assets.has_nft(output.value, policy_id, asset_name)

  -- Token quantity:
  assets.quantity_of(output.value, policy_id, asset_name) >= n

  -- Time check:
  interval.is_entirely_after(self.validity_range, deadline)
  interval.is_entirely_before(self.validity_range, expiry)
  interval.contains(self.validity_range, point)

  -- List operations over outputs:
  list.any(self.outputs, fn(o) {{ ... }})
  list.all(self.outputs, fn(o) {{ ... }})
  list.filter(self.outputs, fn(o) {{ ... }})

  -- Find script outputs:
  transaction.find_script_outputs(self.outputs, script_hash)

## HARD RULES
  NEVER use: transaction.signatories(tx)
  NEVER use: list.has_any(...)
  NEVER use: output.value.lovelace
  NEVER use: self.time or self.signatures
  NEVER use: tx.validity_range or ctx.transaction.validity_range
  NEVER use: cardano.transaction.{{...}} (dot-style import)
  NEVER use: self.outputs.all() or self.outputs.any() — use list.all/any instead
  NEVER use: output.assets.ada — use assets.lovelace_of(output.value)
  NEVER use: Signature.from_bytes() — does not exist

## CODE QUALITY
  - Final solution only — no // Correct, no // Fixed comments
  - Complete validators with all imports
  - Minimal but compilable

## REVIEW STATUS
  VERIFIED_V3_ALIGNED: only uses APIs listed above
  PLAUSIBLE_NEEDS_CHECK: uses output.address comparison or datum access patterns
"""


# ─────────────────────────────────────────────
# Batch configs — 20 ejemplos por batch, grounded en patrones reales
# ─────────────────────────────────────────────
BATCH_CONFIGS = [
    ("spend_lovelace_signatories_a", 20, """\
Generate 20 Aiken v3 SPEND validators combining ADA checks with signatures.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Use assets.lovelace_of(output.value) for ADA — NEVER output.assets.ada
  - Use list.has(self.extra_signatories, key) for signatures — NEVER self.signatures

Vary: owner withdrawal, escrow release, refund with signature, treasury payout.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("spend_lovelace_signatories_b", 20, """\
Generate 20 MORE Aiken v3 SPEND validators combining ADA checks with N-of-M multisig.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Use list.count(admins, fn(k) {{ list.has(self.extra_signatories, k) }}) >= n for multisig
  - Use assets.lovelace_of(output.value) for ADA

Vary: 2-of-3, 3-of-5, 4-of-7 multisig with different contexts (DAO, treasury, escrow).
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("spend_nft_time_a", 20, """\
Generate 20 Aiken v3 SPEND validators combining NFT checks with time constraints.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Use assets.has_nft(output.value, policy_id, asset_name) with 3 args
  - Use interval.is_entirely_after(self.validity_range, deadline) OR is_entirely_before OR contains

Vary: NFT-gated spend after deadline, time-bounded claim, collection access control.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("spend_nft_time_b", 20, """\
Generate 20 MORE Aiken v3 SPEND validators with NFT + ADA + time combinations.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Combine at least 2 of: NFT check, ADA check, time check
  - Use list.any(self.outputs, fn(o) {{ ... }}) for output iteration

Vary: NFT swap with ADA, time-locked NFT vault, royalty with deadline.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("spend_payment_a", 20, """\
Generate 20 Aiken v3 SPEND validators for payment enforcement.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Use list.any(self.outputs, fn(o) {{ ... }}) to check outputs
  - Use assets.lovelace_of(o.value) for ADA — NEVER output.assets.ada

Cover: seller payment, royalty split, marketplace fee, minimum price enforcement.
Mark as PLAUSIBLE_NEEDS_CHECK (output.address comparison).
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("spend_payment_b", 20, """\
Generate 20 MORE Aiken v3 SPEND validators for complex payment scenarios.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Use list.all(self.outputs, fn(o) {{ ... }}) OR list.any for output checks

Cover: multi-recipient payment, NFT + ADA swap, auction settlement, escrow with fees.
Mark as PLAUSIBLE_NEEDS_CHECK.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("mint_complex_a", 20, """\
Generate 20 Aiken v3 MINT validators combining 2+ constraints.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Use self.mint field (NOT output checking for supply)

Combine from:
  - assets.quantity_of(self.mint, policy_id, asset_name) for amount control
  - list.has(self.extra_signatories, admin) for authorization
  - self.validity_range for time-bounded minting

Vary: admin-authorized mint, time-bounded ICO, burn policy, capped supply.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("mint_complex_b", 20, """\
Generate 20 MORE Aiken v3 MINT validators with advanced patterns.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
  - Be inside a validator {{ }} block

Cover: one-shot minting policy, NFT collection mint with admin, time-expiry mint,
multisig-authorized mint (2-of-3), burn-only policy.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("withdraw_complex", 20, """\
Generate 20 Aiken v3 WITHDRAW validators.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Use self.extra_signatories for signature checks

Cover: staking reward withdrawal, DAO treasury withdrawal with multisig,
time-locked withdrawal, credential-gated withdrawal.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("spend_reference_inputs", 20, """\
Generate 20 Aiken v3 SPEND validators using self.reference_inputs.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Use transaction.find_input(self.reference_inputs, config_ref) pattern

Cover: oracle price check, allowlist validation, config-based spend, price feed validator.
Mark as PLAUSIBLE_NEEDS_CHECK if datum access from reference input is uncertain.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("spend_list_operations", 20, """\
Generate 20 Aiken v3 SPEND validators showcasing list operations over outputs.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Use list.all, list.any, list.filter, or list.count on self.outputs

CRITICAL — use list module functions, NOT method chaining:
  CORRECT: list.all(self.outputs, fn(o) {{ ... }})
  WRONG:   self.outputs.all(fn(o) {{ ... }})

Cover: all outputs have min ADA, count outputs to script, filter by address, find specific output.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("spend_datum_typed", 20, """\
Generate 20 Aiken v3 SPEND validators with typed custom datums.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<MyDatum>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Define a custom type for the datum
  - Use expect Some(d) = datum to unwrap

Cover: vesting with beneficiary key, auction with bid amount, escrow with buyer/seller,
NFT sale datum, time-locked vault with owner.
Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),

    ("spend_combined_three_way", 20, """\
Generate 20 Aiken v3 SPEND validators combining THREE constraints simultaneously.
Base your examples on the real patterns and stdlib shown above.

Every example MUST:
  - Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  - Be inside a validator {{ }} block
  - Combine ALL THREE: signature check + ADA/NFT check + time check

Examples:
  - Owner signed + min ADA sent + after deadline
  - 2-of-3 multisig + NFT present + within time window
  - Admin signed + token quantity check + before expiry

Mix EN/ES (~60/40). Call save_examples with 20 examples.
"""),
]


# ─────────────────────────────────────────────
# Claude call
# ─────────────────────────────────────────────
def call_claude(prompt, system_prompt, model, client, dry_run=False):
    if dry_run:
        print(f"  [DRY RUN] prompt {len(prompt)} chars / system {len(system_prompt)} chars")
        return []
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "save_examples"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "save_examples":
            return block.input.get("examples", [])
    return []


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",    default="data/processed/complex_validators.jsonl")
    parser.add_argument("--model",     default=DEFAULT_MODEL)
    parser.add_argument("--stdlib",    default=STDLIB_PATH)
    parser.add_argument("--docs",      default=DOCS_PATH)
    parser.add_argument("--patterns",  default=PATTERNS_PATH)
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not args.overwrite and not args.dry_run and os.path.exists(args.output):
        print(f"ERROR: {args.output} ya existe. Usa --overwrite.")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY no encontrada.")
        sys.exit(1)

    # Cargar fuentes reales
    print(f"Cargando stdlib desde {args.stdlib}...")
    stdlib_context = load_stdlib_context(args.stdlib)

    print(f"Cargando design patterns desde {args.patterns}...")
    pattern_examples = load_pattern_examples(args.patterns)

    print(f"Cargando docs desde {args.docs}...")
    docs_examples = load_docs_examples(args.docs)

    system_prompt = build_system_prompt(stdlib_context, pattern_examples, docs_examples)
    print(f"System prompt: {len(system_prompt)} chars con fuentes reales")

    total_expected = sum(n for _, n, _ in BATCH_CONFIGS)
    print(f"Batches: {len(BATCH_CONFIGS)} | Esperados: ~{total_expected} ejemplos")

    if args.dry_run:
        for label, n, prompt in BATCH_CONFIGS:
            call_claude(prompt, system_prompt, args.model, None, dry_run=True)
            print(f"  [{label}] ~{n} ejemplos")
        print(f"\n[DRY RUN] Total esperado: ~{total_expected}")
        return

    client = Anthropic(api_key=api_key)
    all_examples = []
    batch_counts = {}

    for label, expected, prompt in BATCH_CONFIGS:
        print(f"\n[{label}] Generando ~{expected} ejemplos...")
        examples = call_claude(prompt, system_prompt, args.model, client)
        # Filtrar no-dicts
        examples = [e for e in examples if isinstance(e, dict)]
        print(f"  Recibidos: {len(examples)}")
        for ex in examples:
            ex.setdefault("source", "aiken_v3_curated")
            ex.setdefault("review_status", "PLAUSIBLE_NEEDS_CHECK")
        all_examples.extend(examples)
        batch_counts[label] = len(examples)

    # Verificación de calidad
    fn_spend  = sum(1 for e in all_examples if "fn spend(" in e.get("output",""))
    fn_mint   = sum(1 for e in all_examples if "fn mint(" in e.get("output",""))
    fn_with   = sum(1 for e in all_examples if "fn withdraw(" in e.get("output",""))
    own_ref   = sum(1 for e in all_examples if "own_ref: OutputReference" in e.get("output",""))
    bad_sig   = sum(1 for e in all_examples if "self.signatures" in e.get("output",""))
    bad_time  = sum(1 for e in all_examples if "self.time" in e.get("output",""))
    bad_chain = sum(1 for e in all_examples if "self.outputs.all(" in e.get("output","") or "self.outputs.any(" in e.get("output",""))

    print(f"\n{'='*52}")
    print(f"  Total: {len(all_examples)}")
    for label, cnt in batch_counts.items():
        print(f"  {label}: {cnt}")
    print(f"\n  QUALITY CHECK:")
    print(f"  fn spend(     : {fn_spend}")
    print(f"  fn mint(      : {fn_mint}")
    print(f"  fn withdraw(  : {fn_with}")
    print(f"  own_ref       : {own_ref}")
    print(f"  self.signatures (BAD): {bad_sig}")
    print(f"  self.time (BAD)      : {bad_time}")
    print(f"  method chaining (BAD): {bad_chain}")
    print(f"{'='*52}")

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    summary_path = args.output.replace(".jsonl", "_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(all_examples),
            "by_batch": batch_counts,
            "by_lang": dict(Counter(e.get("lang","?") for e in all_examples)),
            "by_status": dict(Counter(e.get("review_status","?") for e in all_examples)),
            "quality": {
                "fn_spend": fn_spend, "fn_mint": fn_mint, "fn_withdraw": fn_with,
                "own_ref": own_ref, "bad_signatures": bad_sig,
                "bad_self_time": bad_time, "bad_method_chain": bad_chain,
            },
            "stdlib_source": args.stdlib,
            "patterns_source": args.patterns,
            "docs_source": args.docs,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Output : {args.output}")
    print(f"  Summary: {summary_path}")
    print(f"\nPara agregar al dataset:")
    print(f"  cat {args.output} >> data/processed/dataset_v12_train.jsonl")
    print(f"  wc -l data/processed/dataset_v12_train.jsonl")


if __name__ == "__main__":
    main()
