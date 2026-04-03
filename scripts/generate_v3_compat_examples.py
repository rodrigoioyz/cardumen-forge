#!/usr/bin/env python3
"""
generate_v3_compat_examples.py — Cardumen Forge
Generates dataset examples targeting stdlib v3.0.0 breaking changes.

Breaking changes addressed:
  - Record fields require commas (affects any custom type with 2+ fields)
  - DeregisterCredential → UnregisterCredential
  - InlineDatum must be explicitly imported from cardano/transaction
  - interval.* requires explicit use aiken/interval import
  - Interval is NOT generic (use Interval, not Interval<Int>)
  - VerificationKeyCredential → VerificationKey
  - ScriptCredential → Script
  - aiken/time / PosixTime → removed (use self.validity_range)

Usage:
    python3 scripts/generate_v3_compat_examples.py --dry-run
    python3 scripts/generate_v3_compat_examples.py --write
    python3 scripts/generate_v3_compat_examples.py --write --append-to-v21
    python3 scripts/generate_v3_compat_examples.py --write --batches 1 3 5
"""

import os
import re
import json
import argparse
import time
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("pip install anthropic")
    raise

ROOT        = Path(__file__).parent.parent
STDLIB_FILE = ROOT / "data" / "raw" / "aiken_stdlib.json"
OUTPUT_FILE = ROOT / "data" / "processed" / "components" / "v3_compat_examples.jsonl"
DATASET_V21 = ROOT / "data" / "processed" / "dataset_v20_reviewed.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# Generation system prompt — strict v3 rules
# ─────────────────────────────────────────────────────────────────────────────

GEN_SYSTEM_PROMPT = """\
You are generating Aiken v3 smart contract training examples for a fine-tuning dataset.
Every example MUST strictly follow stdlib v3.0.0 rules listed below.

═══ STDLIB V3 RULES — NON-NEGOTIABLE ═══

1. CUSTOM TYPES — commas after EVERY field (including last):
   pub type MyDatum {
     owner: VerificationKeyHash,
     deadline: Int,
     amount: Int,
   }

2. VALIDATOR syntax — NO fn keyword before handlers:
   validator my_contract {
     spend(datum: Option<MyDatum>, redeemer: MyRedeemer, own_ref: OutputReference, self: Transaction) -> Bool {
       ...
     }
   }

3. IMPORTS — slash style, must come FIRST in file:
   use cardano/assets
   use cardano/transaction.{Transaction, OutputReference}
   — If using InlineDatum: add InlineDatum to the import list
   — If using interval.*: add use aiken/interval
   — If using Certificate: use cardano/certificate.{Certificate}

4. CERTIFICATE constructors (exact names):
   RegisterCredential, UnregisterCredential, DelegateCredential
   RegisterAndDelegateCredential
   (UnregisterCredential replaced DeregisterCredential — NEVER use DeregisterCredential)

5. INLINE DATUM — must be imported explicitly:
   use cardano/transaction.{Transaction, OutputReference, InlineDatum}
   expect InlineDatum(raw) = output.datum

6. INTERVAL — not generic, always import:
   use aiken/interval          ← required import
   self.validity_range         ← type is Interval (NOT Interval<Int>)

7. VERIFIED API:
   assets.lovelace_of(output.value)
   list.has(self.extra_signatories, key)
   assets.quantity_of(value, policy_id, asset_name)
   transaction.find_input(self.inputs, ref)
   transaction.find_input(self.reference_inputs, ref)
   dict.to_pairs(d)

8. NEVER generate:
   DeregisterCredential | VerificationKeyCredential | ScriptCredential
   PosixTime | MintedValue | use aiken/time | Interval<Int>
   fn spend( | fn mint( | fn withdraw(    (no fn prefix on handlers)
   use cardano.  | use aiken.              (no dot imports)

═══ OUTPUT FORMAT ═══
Return a JSON array. Each item: {"instruction": "...", "input": "", "output": "..."}
"output" must be complete, compilable Aiken v3 code.
"instruction" in English or Spanish (mix both across examples).
"input" is usually empty string.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Batches
# ─────────────────────────────────────────────────────────────────────────────

BATCHES = [
    # ── Batch 1: Record types with commas — spend validators ──────────────────
    {
        "id": 1,
        "theme": "record_syntax_spend",
        "n": 10,
        "prompt": """\
Generate 10 Aiken v3 spend validator examples. Each must define a custom datum type
with 2-4 fields using COMMAS after every field. Vary the use case:
escrow, vesting, auction, subscription, lending, game, NFT sale, DAO treasury,
multisig escrow, time-locked payment.

CRITICAL: Every custom type field must end with a comma.
pub type Datum {
  field1: Type1,
  field2: Type2,
}

Each output must include the full validator with imports and type definitions."""
    },

    # ── Batch 2: Record types with commas — mint/withdraw ─────────────────────
    {
        "id": 2,
        "theme": "record_syntax_mint_withdraw",
        "n": 8,
        "prompt": """\
Generate 8 Aiken v3 examples mixing mint and withdraw validators.
Each must define at least one custom type (redeemer or datum) with 2+ fields
using COMMAS after every field.

Vary: token launch policy, staking reward claim, DAO token mint,
capped supply with admin list, liquidity pool token, NFT collection mint,
staking withdraw with time lock, governance token.

CRITICAL: pub type MyRedeemer { field1: Type1, field2: Type2, }"""
    },

    # ── Batch 3: Certificate handlers — v3 constructor names ──────────────────
    {
        "id": 3,
        "theme": "certificate_v3",
        "n": 10,
        "prompt": """\
Generate 10 Aiken v3 publish validator examples using CORRECT stdlib v3 certificate
constructor names. Use a variety of certificate types:
- UnregisterCredential (NOT DeregisterCredential — this was renamed in v3)
- RegisterCredential
- DelegateCredential
- RegisterAndDelegateCredential

Vary use cases: DAO stake management, pool operator registry, DeFi protocol staking,
multi-sig stake control, protocol governance stake, staking rewards controller,
validator node registration, community pool delegation, treasury stake,
cross-protocol credential management.

Always import: use cardano/certificate.{Certificate}
If datum has multiple fields, add commas after each."""
    },

    # ── Batch 4: InlineDatum with explicit import ─────────────────────────────
    {
        "id": 4,
        "theme": "inline_datum_import",
        "n": 10,
        "prompt": """\
Generate 10 Aiken v3 spend validator examples that read data from reference inputs
using InlineDatum. CRITICAL: InlineDatum MUST be explicitly imported:
    use cardano/transaction.{Transaction, OutputReference, InlineDatum}

Then use it as:
    expect InlineDatum(raw) = ref_input.output.datum
    expect my_data: MyType = raw

Vary use cases: price oracle, protocol config, allowlist, NFT metadata reader,
exchange rate feed, risk parameters, governance config, reward schedule,
collateral ratio, DEX price feed.

All custom types must use commas between fields."""
    },

    # ── Batch 5: Interval with explicit import ────────────────────────────────
    {
        "id": 5,
        "theme": "interval_import",
        "n": 10,
        "prompt": """\
Generate 10 Aiken v3 spend validator examples using time/interval checks.
CRITICAL:
- Always include: use aiken/interval
- Use type Interval (NOT Interval<Int> — the type is no longer generic in stdlib v3)
- Use self.validity_range (NOT self.time — aiken/time module was removed)

Available interval functions:
  interval.is_entirely_before(range, deadline)
  interval.is_entirely_after(range, start)
  interval.contains(range, point)

Vary: vesting cliff, auction deadline, subscription renewal, flash loan window,
time-locked escrow, bond maturity, option expiry, staking lock period,
governance voting window, delayed withdrawal.

All custom datum types must use commas between fields."""
    },

    # ── Batch 6: Typed mint redeemers ─────────────────────────────────────────
    {
        "id": 6,
        "theme": "typed_mint_redeemer",
        "n": 8,
        "prompt": """\
Generate 8 Aiken v3 mint validator examples where the redeemer is a custom type
(not just Data or OutputReference raw). Define explicit redeemer types with commas.

Example pattern:
pub type MintRedeemer {
  utxo_ref: OutputReference,
  amount: Int,
}
validator my_policy {
  mint(redeemer: MintRedeemer, policy_id: PolicyId, self: Transaction) -> Bool { ... }
}

Vary: NFT with proof of ownership, capped supply with admin signature,
fair launch with UTXO consumption, bonding curve mint, DAO membership token,
protocol fee token, loyalty reward token, bridge token.

All custom types must use commas between fields."""
    },

    # ── Batch 7: Type-safe datum fields ───────────────────────────────────────
    {
        "id": 7,
        "theme": "type_safe_datum",
        "n": 8,
        "prompt": """\
Generate 8 Aiken v3 spend validator examples with explicitly typed datum fields.
Focus on patterns where signatories are checked. The key: datum fields that hold
key hashes must be typed as VerificationKeyHash (not ByteArray).

Example pattern:
pub type MultiSigDatum {
  admin1: VerificationKeyHash,
  admin2: VerificationKeyHash,
  admin3: VerificationKeyHash,
  threshold: Int,
}

Then use: list.has(self.extra_signatories, d.admin1)

Vary: 2-of-3 multisig, weighted voting, emergency admin override,
council approval, board vote, DAO proposal execution, treasury multisig,
protocol upgrade approval.

All datum fields must use commas."""
    },

    # ── Batch 8: Mixed v3 best practices ─────────────────────────────────────
    {
        "id": 8,
        "theme": "mixed_v3_patterns",
        "n": 10,
        "prompt": """\
Generate 10 Aiken v3 examples combining multiple v3 patterns correctly.
Each example should combine at least 2 of: custom types with commas,
interval checks with explicit import, InlineDatum with explicit import,
certificate handlers with v3 names, typed signatories.

Vary: DeFi liquidation (interval + oracle datum), DAO proposal (vote + cert),
NFT marketplace (spend + mint), staking dashboard (withdraw + cert + time),
yield farm (spend + reference input + interval), DEX swap (spend + oracle),
bond protocol (spend + interval + multisig), governance (vote + cert + time),
bridge escrow (spend + oracle + multisig), lending (spend + oracle + interval).

All custom types MUST use commas. Imports MUST be complete and correct."""
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def strip_markdown(text: str) -> str:
    m = re.search(r'```(?:\w+)?\n(.*?)```', text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def validate_example(ex: dict) -> list[str]:
    errors = []
    out = ex.get("output", "")
    code = strip_markdown(out)

    if not code:
        return ["empty output"]

    # Standard structure
    if "validator" not in code:
        errors.append("missing: validator block")
    if re.search(r'\bfn\s+(spend|mint|withdraw|publish|vote|propose)\s*\(', code):
        errors.append("bad: fn prefix on handler")
    if re.search(r'\buse\s+\w+\.(?!ak\b)', code):
        errors.append("bad: dot-style import")

    # v3 — record field commas
    type_blocks = re.findall(r'pub\s+type\s+\w+\s*\{([^}]+)\}', code)
    for block in type_blocks:
        fields = [l.strip() for l in block.splitlines() if re.search(r'\w+\s*:', l)]
        if len(fields) >= 2:
            for field in fields[:-1]:  # all but last must have comma
                if field and not field.rstrip().endswith(','):
                    errors.append(f"bad: record field missing comma: {field[:50]}")

    # v3 — removed/renamed
    if "DeregisterCredential" in code:
        errors.append("bad: DeregisterCredential (use UnregisterCredential)")
    if "VerificationKeyCredential" in code:
        errors.append("bad: VerificationKeyCredential (use VerificationKey)")
    if "ScriptCredential" in code:
        errors.append("bad: ScriptCredential (use Script)")
    if "PosixTime" in code:
        errors.append("bad: PosixTime (removed in stdlib v3)")
    if "MintedValue" in code:
        errors.append("bad: MintedValue (removed in stdlib v3)")
    if re.search(r'\buse\s+aiken/time\b', code):
        errors.append("bad: use aiken/time (removed in stdlib v3)")
    if re.search(r'Interval\s*<', code):
        errors.append("bad: Interval<T> (Interval is not generic in stdlib v3)")

    # v3 — InlineDatum must be imported when used
    if "InlineDatum" in code:
        tx_imports = re.findall(r'use\s+cardano/transaction\.\{([^}]+)\}', code)
        imported = ','.join(tx_imports)
        if "InlineDatum" not in imported:
            errors.append("bad: InlineDatum used but not imported from cardano/transaction")

    # v3 — interval must be imported when used
    if re.search(r'\binterval\.', code):
        if "use aiken/interval" not in code:
            errors.append("bad: interval.* used without 'use aiken/interval'")

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Generation
# ─────────────────────────────────────────────────────────────────────────────

def load_stdlib_context() -> str:
    if not STDLIB_FILE.exists():
        return ""
    data = json.loads(STDLIB_FILE.read_text(encoding="utf-8"))
    # Extract key function signatures
    entries = []
    for item in data if isinstance(data, list) else []:
        sig = item.get("signature") or item.get("name", "")
        if sig:
            entries.append(sig)
    return "\n".join(entries[:200])  # keep context lean


def generate_batch(client: Anthropic, batch: dict, stdlib_ctx: str) -> list[dict]:
    n       = batch["n"]
    theme   = batch["theme"]
    prompt  = batch["prompt"]

    context = f"Stdlib API reference (key signatures):\n{stdlib_ctx}\n\n" if stdlib_ctx else ""
    user_msg = f"{context}Generate exactly {n} examples.\n\n{prompt}\n\nReturn ONLY a JSON array."

    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=GEN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text.strip()

    # Extract JSON array
    m = re.search(r'\[.*\]', raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON array in response for batch {batch['id']}")

    examples = json.loads(m.group(0))
    for ex in examples:
        ex.setdefault("input", "")
        ex["source"] = "v3_compat_examples"
        ex["topic"]  = f"v3/{theme}"
        ex["review_status"] = "VERIFIED_V3"

    return examples


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",       action="store_true", help="Print batch prompts without calling API")
    parser.add_argument("--write",         action="store_true", help="Write output file")
    parser.add_argument("--append-output", action="store_true", help="Append to existing output file (don't overwrite)")
    parser.add_argument("--append-to-v21", action="store_true", help="Merge into dataset_v20_reviewed.jsonl (v21→v22)")
    parser.add_argument("--batches",       nargs="*", type=int, help="Run only these batch IDs")
    args = parser.parse_args()

    batches_to_run = BATCHES
    if args.batches:
        batches_to_run = [b for b in BATCHES if b["id"] in args.batches]

    total_requested = sum(b["n"] for b in batches_to_run)
    print(f"Batches  : {[b['id'] for b in batches_to_run]}")
    print(f"Requested: {total_requested} examples")

    if args.dry_run:
        for b in batches_to_run:
            print(f"\n── Batch {b['id']} ({b['theme']}, n={b['n']}) ──")
            print(b["prompt"][:300])
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client     = Anthropic(api_key=api_key)
    stdlib_ctx = load_stdlib_context()
    all_examples: list[dict] = []

    for b in batches_to_run:
        print(f"\n── Batch {b['id']} ({b['theme']}, n={b['n']}) ──", flush=True)
        try:
            examples = generate_batch(client, b, stdlib_ctx)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        valid, invalid = [], []
        for ex in examples:
            errs = validate_example(ex)
            if errs:
                invalid.append((ex, errs))
            else:
                valid.append(ex)

        print(f"  Valid: {len(valid)}/{len(examples)}", flush=True)
        for ex, errs in invalid:
            instr = ex.get("instruction", "")[:60]
            print(f"  ✗ {instr!r}: {errs}")

        all_examples.extend(valid)
        time.sleep(1)

    print(f"\nTotal valid: {len(all_examples)}/{total_requested}")

    # Validation summary by category
    issues = {}
    for ex in all_examples:
        for err in validate_example(ex):
            issues[err] = issues.get(err, 0) + 1
    if issues:
        print("Remaining issues:")
        for k, v in sorted(issues.items(), key=lambda x: -x[1]):
            print(f"  {v:3d}x  {k}")

    if not args.write:
        print("\nDry output (first example):")
        if all_examples:
            print(json.dumps(all_examples[0], indent=2, ensure_ascii=False)[:600])
        print("\nRe-run with --write to save.")
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append_output else "w"
    with OUTPUT_FILE.open(mode, encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"\nWritten {len(all_examples)} examples → {OUTPUT_FILE}")

    if args.append_to_v21:
        before = sum(1 for _ in DATASET_V21.open(encoding="utf-8"))
        with DATASET_V21.open("a", encoding="utf-8") as f:
            for ex in all_examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        after = sum(1 for _ in DATASET_V21.open(encoding="utf-8"))
        print(f"Merged into {DATASET_V21.name}: {before} → {after} examples (+{after - before})")

        # Coverage report
        full_text = DATASET_V21.read_text(encoding="utf-8")
        checks = {
            "commas in types": len(re.findall(r'\w+:\s*\w+,', full_text)),
            "UnregisterCredential": full_text.count("UnregisterCredential"),
            "InlineDatum": full_text.count("InlineDatum"),
            "use aiken/interval": full_text.count("use aiken/interval"),
            "validator block": full_text.count('"validator'),
        }
        print("\nCoverage after merge:")
        for k, v in checks.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
