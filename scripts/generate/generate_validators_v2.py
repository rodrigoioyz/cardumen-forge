#!/usr/bin/env python3
"""
generate_validators_v2.py
Genera EXCLUSIVAMENTE validators completos y compilables.

El problema diagnosticado: el 73% de las instrucciones "write a validator"
en el dataset responden con fragmentos o explicaciones — no con código completo.
Este script genera SOLO outputs con estructura:

    validator name {
      fn spend/mint/withdraw(...) -> Bool {
        <lógica real usando APIs verificadas>
      }
    }

Sin prosa. Sin placeholders. Sin True como única línea.

Uso:
    python3 generate_validators_v2.py --dry-run
    python3 generate_validators_v2.py
    python3 generate_validators_v2.py --overwrite
"""

import os, sys, json, re, argparse
from collections import Counter
from anthropic import Anthropic

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS    = 16000
STDLIB_PATH   = "data/raw/aiken_stdlib.json"
PATTERNS_PATH = "data/raw/aiken_design_patterns.json"
OUTPUT_PATH   = "data/processed/validators_v3.jsonl"

TOOL_SCHEMA = {
    "name": "save_validators",
    "description": "Save complete compilable Aiken v3 validators",
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
                        "topic":         {"type": "string", "minLength": 3},
                        "review_status": {"type": "string",
                            "enum": ["VERIFIED_V3_ALIGNED", "PLAUSIBLE_NEEDS_CHECK"]},
                    },
                    # source removed — set by script, not Claude
                    "required": ["lang", "instruction", "input", "output", "topic", "review_status"],
                },
            }
        },
        "required": ["examples"],
    },
}


def load_stdlib(path):
    if not os.path.exists(path):
        print(f"ERROR: stdlib file not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    relevant = {
        "cardano.assets", "cardano.transaction",
        "aiken.collection.list", "aiken.interval",
        "cardano.address", "aiken.crypto",
        "cardano.certificate", "cardano.governance",
        "aiken.collection.dict", "aiken.collection.pairs",
        "aiken.math.rational",
    }
    lines = ["## VERIFIED STDLIB SIGNATURES\n"]
    by_mod = {}
    for r in records:
        if r.get("module") in relevant and r.get("signature"):
            by_mod.setdefault(r["module"], []).append(r["signature"].strip())
    for mod in sorted(by_mod):
        lines.append(f"### {mod}")
        for sig in by_mod[mod]:
            lines.append(f"  {sig}")
        lines.append("")
    return "\n".join(lines)


def load_pattern_code(path):
    """Extrae solo bloques de código Aiken de los design patterns."""
    if not os.path.exists(path):
        print(f"ERROR: patterns file not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        files = json.load(f)
    lines = ["## REAL PRODUCTION CODE (from design patterns)\n"]
    for pf in files[:6]:
        content = pf.get("content", "")
        in_block = False
        block = []
        code_found = False
        for line in content.split("\n"):
            if "```aiken" in line:
                in_block = True
                block = []
            elif "```" in line and in_block:
                in_block = False
                code = "\n".join(block).strip()
                if len(code) > 100 and ("validator" in code or "fn " in code):
                    lines.append(f"\n// From: {pf['name'][:40]}")
                    lines.append(code[:600])
                    code_found = True
                    break
            elif in_block:
                block.append(line)
        if code_found:
            # one good block is enough — stop reading more files once we have 3
            if len([l for l in lines if l.startswith("// From:")]) >= 3:
                break
    return "\n".join(lines)


def strip_markdown_fences(text: str) -> str:
    """Remove ```aiken ... ``` wrappers if Claude added them."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def has_bare_pub_fn(output: str) -> bool:
    """Detect pub fn at module level (outside any validator block)."""
    first_validator = output.find("validator ")
    first_pub_fn    = output.find("pub fn ")
    if first_pub_fn == -1:
        return False
    if first_validator == -1 or first_pub_fn < first_validator:
        return True
    return False


def quality_check(examples):
    """Checks all ABSOLUTE PROHIBITIONS and structural requirements."""
    fn_spend   = sum(1 for e in examples if re.search(r'\b(?:fn\s+)?spend\s*\(', e.get("output","")))
    fn_mint    = sum(1 for e in examples if re.search(r'\b(?:fn\s+)?mint\s*\(', e.get("output","")))
    fn_with    = sum(1 for e in examples if re.search(r'\b(?:fn\s+)?withdraw\s*\(', e.get("output","")))
    fn_pub     = sum(1 for e in examples if re.search(r'\b(?:fn\s+)?publish\s*\(', e.get("output","")))
    fn_vote    = sum(1 for e in examples if re.search(r'\b(?:fn\s+)?vote\s*\(', e.get("output","")))
    validator  = sum(1 for e in examples if "validator " in e.get("output",""))
    own_ref    = sum(1 for e in examples if "own_ref: OutputReference" in e.get("output",""))

    bad_sigs         = sum(1 for e in examples if "self.signatures" in e.get("output",""))
    bad_time         = sum(1 for e in examples if "self.time" in e.get("output",""))
    bad_chain        = sum(1 for e in examples
                           if re.search(r'self\.\w+\.(all|any|filter|map|find)\(', e.get("output","")))
    bad_ada          = sum(1 for e in examples if "output.assets.ada" in e.get("output",""))
    bad_pub_fn       = sum(1 for e in examples if has_bare_pub_fn(e.get("output","")))
    bad_multisig     = sum(1 for e in examples if "MultiSignature" in e.get("output",""))
    bad_redeemdata   = sum(1 for e in examples if "RedeemData" in e.get("output",""))
    bad_or_try       = sum(1 for e in examples if "option.or_try" in e.get("output",""))
    bad_value_cmp    = sum(1 for e in examples
                           if re.search(r'output\.value\s*(>=|<=|>|<|==)', e.get("output","")))
    bad_placeholder  = sum(1 for e in examples
                           if "// implement here" in e.get("output","") or "// TODO" in e.get("output",""))
    bad_fence        = sum(1 for e in examples if e.get("output","").strip().startswith("```"))
    # Trivial True body — fn with only True inside (real hallucination)
    bad_trivial_true = sum(1 for e in examples
                           if re.search(r'fn \w+\([^)]*\)\s*(->\s*Bool\s*)?\{?\s*True\s*\}?', e.get("output",""))
                           and len(e.get("output","").split("\n")) < 8)

    total_bad = (bad_sigs + bad_time + bad_chain + bad_ada + bad_pub_fn +
                 bad_multisig + bad_redeemdata + bad_or_try + bad_value_cmp +
                 bad_placeholder + bad_fence + bad_trivial_true)

    return {
        "fn_spend": fn_spend, "fn_mint": fn_mint, "fn_withdraw": fn_with,
        "fn_publish": fn_pub, "fn_vote": fn_vote,
        "validator_block": validator, "own_ref": own_ref,
        "bad_signatures": bad_sigs, "bad_self_time": bad_time,
        "bad_method_chain": bad_chain, "bad_ada": bad_ada,
        "bad_pub_fn": bad_pub_fn, "bad_multisig": bad_multisig,
        "bad_redeemdata": bad_redeemdata, "bad_or_try": bad_or_try,
        "bad_value_compare": bad_value_cmp, "bad_placeholder": bad_placeholder,
        "bad_fence": bad_fence, "bad_trivial_true": bad_trivial_true,
        "total_bad": total_bad,
    }


# ─────────────────────────────────────────────
# System prompt — uses string replace, NOT .format(), to avoid brace collisions
# with Aiken code blocks in stdlib/patterns
# ─────────────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """\
You are a senior Aiken v3 engineer. Your task is to generate fine-tuning examples
where EVERY output is a complete, compilable Aiken v3 validator.

STDLIB_PLACEHOLDER

PATTERNS_PLACEHOLDER

## MANDATORY OUTPUT STRUCTURE — every single output MUST follow this exactly:

use cardano/assets
use cardano/transaction.{OutputReference, Transaction}
use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}

validator contract_name {
  fn spend(datum: Option<DatumType>, redeemer: RedeemType, own_ref: OutputReference, self: Transaction) -> Bool {
    // real logic here — never just True
  }
}

## VERIFIED HANDLER SIGNATURES — memorize these exactly:

spend   : fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
mint    : fn mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
withdraw: fn withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool
publish : fn publish(redeemer: T, cert: Certificate, self: Transaction) -> Bool
vote    : fn vote(redeemer: T, voter: Voter, self: Transaction) -> Bool

Imports for governance/certificate handlers:
  use cardano/certificate.{Certificate}
  use cardano/governance.{Voter, ProposalProcedure}

Imports for dict/rational:
  use aiken/collection/dict
  use aiken/math/rational

## CORRECT API USAGE:

ADA check    : assets.lovelace_of(output.value) >= amount
Signature    : list.has(self.extra_signatories, key)
N-of-M       : list.count(admins, fn(k) { list.has(self.extra_signatories, k) }) >= n
NFT check    : assets.has_nft(output.value, policy_id, asset_name)
Token qty    : assets.quantity_of(output.value, policy_id, asset_name) >= n
After time   : interval.is_entirely_after(self.validity_range, deadline)
Before time  : interval.is_entirely_before(self.validity_range, expiry)
In window    : interval.contains(self.validity_range, point)
List outputs : list.any(self.outputs, fn(o) { ... })
List all     : list.all(self.outputs, fn(o) { ... })
Mint field   : assets.quantity_of(self.mint, policy_id, asset_name)

## ABSOLUTE PROHIBITIONS — if any output contains these, the example is WRONG:

NEVER: pub fn outside validator block (bare module-level functions)
NEVER: self.signatures (use self.extra_signatories)
NEVER: self.time (use self.validity_range)
NEVER: self.outputs.all() (use list.all(self.outputs, fn))
NEVER: self.outputs.any() (use list.any(self.outputs, fn))
NEVER: output.assets.ada (use assets.lovelace_of(output.value))
NEVER: output.value >= N (use assets.lovelace_of(output.value) >= N)
NEVER: MultiSignature (does not exist)
NEVER: RedeemData (does not exist)
NEVER: option.or_try (does not exist)
NEVER: return True as the only logic inside fn body
NEVER: placeholder comments like "// implement here" or "// TODO"
NEVER: wrap the output in markdown code fences (no ```)

## OUTPUT FORMAT RULES:

- output field = ONLY the raw Aiken code, no markdown fences, no prose explanation
- instruction = realistic question a developer would ask
- input = optional broken code OR empty string
- Every example must have real logic (not just True)
- Mix EN/ES 60/40
"""


# ─────────────────────────────────────────────
# Batch configs — 25 ejemplos por batch, solo código
# ─────────────────────────────────────────────
BATCH_CONFIGS = [
    ("spend_owner_signature", 25, """\
Generate 25 SPEND validators where the output is ONLY compilable Aiken v3 code.

Each validator must:
- Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Be inside validator { } block
- Use list.has(self.extra_signatories, key) for signature check
- Have real logic — not just True

Vary: owner withdrawal, beneficiary unlock, admin-only spend, joint account 2-of-2.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("spend_ada_payment", 25, """\
Generate 25 SPEND validators checking ADA payments where output is ONLY compilable code.

Each validator must:
- Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Be inside validator { } block
- Use assets.lovelace_of(output.value) >= amount — NEVER output.value >= or output.assets.ada
- Use list.any(self.outputs, fn(o) { ... }) to iterate outputs

Vary: min ADA to seller, royalty split, marketplace fee, escrow release.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("spend_time_locked", 25, """\
Generate 25 SPEND validators with time constraints where output is ONLY compilable code.

Each validator must:
- Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Be inside validator { } block
- Use interval.is_entirely_after(self.validity_range, deadline) OR is_entirely_before OR contains
- NEVER use self.time or block_num

Vary: vesting after deadline, time-window claim, expiry lock, cliff unlock.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("spend_nft_gated", 25, """\
Generate 25 SPEND validators requiring NFT presence where output is ONLY compilable code.

Each validator must:
- Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Be inside validator { } block
- Use assets.has_nft(output.value, policy_id, asset_name) with exactly 3 args
- Use list.any(self.outputs, fn(o) { ... }) to check outputs

Vary: NFT-gated access, collection membership, token-gated unlock, NFT swap.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("spend_multisig", 25, """\
Generate 25 SPEND validators with N-of-M multisig where output is ONLY compilable code.

Each validator must:
- Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Be inside validator { } block
- Use list.count(admins, fn(k) { list.has(self.extra_signatories, k) }) >= n for multisig
- NEVER use self.signatures or MultiSignature

Vary: 2-of-3, 3-of-5, 4-of-7, DAO treasury, committee approval.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("spend_combined", 25, """\
Generate 25 SPEND validators combining 2-3 constraints where output is ONLY compilable code.

Each validator must:
- Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Be inside validator { } block
- Combine at least 2: signature + ADA, NFT + time, multisig + deadline, ADA + NFT

Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("spend_typed_datum", 25, """\
Generate 25 SPEND validators with custom typed datums where output is ONLY compilable code.

Each validator must:
- Define a custom type for the datum (e.g. type VestingDatum { beneficiary: VerificationKeyHash, deadline: Int })
- Use fn spend(datum: Option<MyDatum>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Use expect Some(d) = datum to unwrap
- Be inside validator { } block

Vary: vesting datum, escrow datum, auction datum, NFT sale datum.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("mint_admin_supply", 25, """\
Generate 25 MINT validators where output is ONLY compilable code.

Each validator must:
- Use fn mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
- Be inside validator { } block
- Use self.mint field for supply checks: assets.quantity_of(self.mint, policy_id, name)
- Use list.has(self.extra_signatories, admin) for authorization
- NEVER use inputs/outputs/tx_metadata as parameters

Vary: admin-authorized mint, capped supply, burn-only, one-shot policy.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("mint_time_bounded", 25, """\
Generate 25 MINT validators with time constraints where output is ONLY compilable code.

Each validator must:
- Use fn mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
- Be inside validator { } block
- Use self.validity_range with interval.is_entirely_before OR is_entirely_after
- NEVER use self.time or block_num

Vary: time-bounded ICO, expiry mint, launch window, seasonal mint.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("withdraw_staking", 25, """\
Generate 25 WITHDRAW validators where output is ONLY compilable code.

Each validator must:
- Use fn withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool
- Be inside validator { } block
- Use list.has(self.extra_signatories, key) for authorization
- NEVER use MultiSignature, RedeemData, or redeem_data as parameter name

Vary: staking reward withdrawal, DAO treasury withdrawal, multisig withdrawal,
time-locked withdrawal, credential-gated withdrawal.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("spend_reference_inputs", 25, """\
Generate 25 SPEND validators using reference inputs where output is ONLY compilable code.

Each validator must:
- Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Be inside validator { } block
- Use self.reference_inputs with transaction.find_input(self.reference_inputs, ref)

Vary: oracle price check, config-based spend, allowlist validation, price feed.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("spend_list_all_any", 25, """\
Generate 25 SPEND validators using list operations on outputs where output is ONLY compilable code.

Each validator must:
- Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Be inside validator { } block
- Use list.all(self.outputs, fn(o) { ... }) OR list.any(self.outputs, fn(o) { ... })
- NEVER use self.outputs.all() or self.outputs.any() — always prefix with list.

Vary: all outputs have min ADA, any output to specific script, count outputs, filter outputs.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("publish_cert", 25, """\
Generate 25 PUBLISH validators (certificate handlers) where output is ONLY compilable code.

Each validator must:
- Use fn publish(redeemer: T, cert: Certificate, self: Transaction) -> Bool
- Be inside validator { } block
- Import: use cardano/certificate.{Certificate}
- Use pattern matching on cert variants: RegisterCredential, UnregisterCredential,
  DelegateCredential, RegisterAndDelegateCredential, RetireStakePool
- Use list.has(self.extra_signatories, key) for authorization

Vary: owner-only registration, admin-controlled delegation, multisig deregistration,
stake pool retirement, authorized credential registration.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("vote_governance", 25, """\
Generate 25 VOTE validators (governance handlers) where output is ONLY compilable code.

Each validator must:
- Use fn vote(redeemer: T, voter: Voter, self: Transaction) -> Bool
- Be inside validator { } block
- Import: use cardano/governance.{Voter}
- Use list.has(self.extra_signatories, key) for authorization
- Logic must check who is allowed to vote (owner, committee, multisig)

Vary: single authorized voter, N-of-M committee vote, time-constrained vote,
admin-only governance, DAO membership vote.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("mint_complex_redeemer", 25, """\
Generate 25 MINT validators with complex redeemers where output is ONLY compilable code.

Each validator must:
- Use fn mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
- Be inside validator { } block
- Use a custom redeemer type with multiple fields or variants
- Use assets.quantity_of(self.mint, policy_id, name) for supply control

Vary: burn-to-mint (check negative quantity in self.mint for burned token),
parametric mint (redeemer specifies token name and max quantity),
batch mint (multiple asset names in one tx), NFT one-shot with UTXO ref check.
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("interval_advanced", 25, """\
Generate 25 SPEND or MINT validators using advanced interval logic where output is ONLY compilable code.

Each validator must:
- Use fn spend(...) or fn mint(...) inside validator { } block
- Use at least ONE of: interval.hull, interval.includes, interval.intersection,
  interval.between, interval.entirely_between, interval.contains
- Use self.validity_range — NEVER self.time

Vary: claim within window (between two deadlines), vesting cliff + expiry (intersection),
phase-based unlock (includes point), multi-phase auction window (hull of two ranges).
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("dict_patterns", 25, """\
Generate 25 SPEND validators using dict operations where output is ONLY compilable code.

Each validator must:
- Use fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Be inside validator { } block
- Import: use aiken/collection/dict
- Use at least one: dict.get, dict.has_key, dict.foldl, dict.filter, dict.insert
- Dict comes from datum (stored on-chain) or is built from transaction data

Vary: whitelist check (dict.has_key), fee lookup (dict.get), vote tally (dict.foldl),
permission map (dict.filter), state transition (dict.insert into new datum).
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("rational_fee", 25, """\
Generate 25 SPEND or MINT validators using rational arithmetic where output is ONLY compilable code.

Each validator must:
- Use fn spend(...) or fn mint(...) inside validator { } block
- Import: use aiken/math/rational
- Use at least one: rational.new, rational.compare_with, rational.mul, rational.floor, rational.ceil
- Apply rational math to fee checks, collateral ratios, swap rates, or percentage thresholds

Vary: minimum fee as percentage of ADA (2.5%), collateral ratio >= 150%,
DEX swap rate within 1% slippage, royalty calculation (5% of sale),
protocol fee enforcement (0.3% of token quantity).
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),

    ("multi_handler", 25, """\
Generate 25 validators with MULTIPLE HANDLERS in a single validator block where output is ONLY compilable code.

Each validator must:
- Contain 2 or more handlers inside ONE validator { } block
- Use any combination: spend + mint, spend + withdraw, mint + withdraw, spend + mint + withdraw
- Each handler has real independent logic
- All handlers follow verified signatures

Vary: NFT marketplace (spend + mint), staking contract (spend + withdraw),
DAO (spend + mint + withdraw), escrow with receipt (spend + mint),
parametric token sale (spend + mint + withdraw).
Output = code only, no prose. Mix EN/ES. Call save_validators with 25 examples.
"""),
]


def call_claude(prompt, system, model, client):
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "save_validators"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "save_validators":
            return [e for e in block.input.get("examples", []) if isinstance(e, dict)]
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",    default=OUTPUT_PATH)
    parser.add_argument("--model",     default=DEFAULT_MODEL)
    parser.add_argument("--stdlib",    default=STDLIB_PATH)
    parser.add_argument("--patterns",  default=PATTERNS_PATH)
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--overwrite",    action="store_true")
    parser.add_argument("--resume-from",  default="",
                        help="Reanudar desde este batch label (append al archivo existente)")
    args = parser.parse_args()

    resuming = bool(args.resume_from)

    if not args.overwrite and not args.dry_run and not resuming and os.path.exists(args.output):
        print(f"ERROR: {args.output} ya existe. Usa --overwrite o --resume-from LABEL.")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY no encontrada.")
        sys.exit(1)

    print("Cargando fuentes reales...")
    stdlib_text   = load_stdlib(args.stdlib)
    patterns_text = load_pattern_code(args.patterns)

    # Use string replace — NOT .format() — to avoid brace collisions with Aiken code
    system = (SYSTEM_PROMPT_TEMPLATE
              .replace("STDLIB_PLACEHOLDER", stdlib_text)
              .replace("PATTERNS_PLACEHOLDER", patterns_text))
    print(f"System prompt: {len(system)} chars")

    total_expected = sum(n for _, n, _ in BATCH_CONFIGS)
    print(f"Batches: {len(BATCH_CONFIGS)} | Esperados: ~{total_expected} ejemplos")

    if args.dry_run:
        for label, n, _ in BATCH_CONFIGS:
            print(f"  [{label}] ~{n} ejemplos")
        print(f"\n[DRY RUN] Total: ~{total_expected}")
        return

    client = Anthropic(api_key=api_key)
    all_examples = []
    batch_counts = {}
    seen_instructions = set()

    parent = os.path.dirname(args.output)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # Filtrar batches si se está reanudando
    batches_to_run = BATCH_CONFIGS
    if resuming:
        labels = [l for l, _, _ in BATCH_CONFIGS]
        if args.resume_from not in labels:
            print(f"ERROR: batch '{args.resume_from}' no encontrado. Opciones: {labels}")
            sys.exit(1)
        start = labels.index(args.resume_from)
        batches_to_run = BATCH_CONFIGS[start:]
        print(f"Reanudando desde '{args.resume_from}' ({len(batches_to_run)} batches restantes)")

    file_mode = "a" if resuming else "w"

    with open(args.output, file_mode, encoding="utf-8") as out_f:
        for label, expected, prompt in batches_to_run:
            print(f"\n[{label}] Generando ~{expected} ejemplos...")
            examples = call_claude(prompt, system, args.model, client)
            print(f"  Recibidos: {len(examples)}")

            if len(examples) == 0:
                print(f"  ERROR: batch {label} returned 0 examples. Abortando.")
                sys.exit(1)
            if len(examples) < expected * 0.5:
                print(f"  WARNING: esperados ~{expected}, recibidos {len(examples)} (<50%)")

            # Strip markdown fences, set defaults, deduplicate
            clean = []
            for ex in examples:
                ex["output"] = strip_markdown_fences(ex.get("output", ""))
                ex["source"] = "aiken_v3_curated_v2"
                ex.setdefault("review_status", "PLAUSIBLE_NEEDS_CHECK")
                ex.setdefault("input", "")
                ex.setdefault("topic", f"aiken/validators/{label}")
                # Deduplicate by instruction prefix
                key = ex.get("instruction", "")[:100]
                if key and key in seen_instructions:
                    continue
                seen_instructions.add(key)
                clean.append(ex)

            # Quality check — filter bad examples before writing
            qc_all = quality_check(clean)
            good = []
            bad_dropped = 0
            for ex in clean:
                ex_qc = quality_check([ex])
                if ex_qc["total_bad"] > 0:
                    bad_dropped += 1
                else:
                    good.append(ex)

            if bad_dropped > 0:
                print(f"  DROPPED {bad_dropped} hallucinated examples")
            if qc_all["total_bad"] > 0:
                print(f"  ⚠️  Hallucinations detectadas en batch:")
                print(f"      bad_signatures={qc_all['bad_signatures']} bad_time={qc_all['bad_self_time']} "
                      f"bad_chain={qc_all['bad_method_chain']} bad_ada={qc_all['bad_ada']} "
                      f"bad_pub_fn={qc_all['bad_pub_fn']} bad_multisig={qc_all['bad_multisig']} "
                      f"bad_fence={qc_all['bad_fence']} bad_trivial_true={qc_all['bad_trivial_true']}")

            for ex in good:
                out_f.write(json.dumps(ex, ensure_ascii=False) + "\n")

            all_examples.extend(good)
            batch_counts[label] = len(good)
            print(f"  Escritos: {len(good)}")

    # Quality check global
    qc = quality_check(all_examples)

    print(f"\n{'='*55}")
    print(f"  Total generados: {len(all_examples)}")
    for label, cnt in batch_counts.items():
        print(f"  {label}: {cnt}")
    print(f"\n  QUALITY CHECK:")
    n = len(all_examples)
    print(f"  spend handler          : {qc['fn_spend']} ({100*qc['fn_spend']/max(1,n):.1f}%)")
    print(f"  mint handler           : {qc['fn_mint']} ({100*qc['fn_mint']/max(1,n):.1f}%)")
    print(f"  withdraw handler       : {qc['fn_withdraw']} ({100*qc['fn_withdraw']/max(1,n):.1f}%)")
    print(f"  publish handler        : {qc['fn_publish']} ({100*qc['fn_publish']/max(1,n):.1f}%)")
    print(f"  vote handler           : {qc['fn_vote']} ({100*qc['fn_vote']/max(1,n):.1f}%)")
    print(f"  validator block        : {qc['validator_block']}")
    print(f"  own_ref: OutputReference: {qc['own_ref']}")
    print(f"  --- HALLUCINATIONS ---")
    print(f"  self.signatures (BAD)  : {qc['bad_signatures']}")
    print(f"  self.time (BAD)        : {qc['bad_self_time']}")
    print(f"  method chain (BAD)     : {qc['bad_method_chain']}")
    print(f"  output.assets.ada (BAD): {qc['bad_ada']}")
    print(f"  bare pub fn (BAD)      : {qc['bad_pub_fn']}")
    print(f"  MultiSignature (BAD)   : {qc['bad_multisig']}")
    print(f"  RedeemData (BAD)       : {qc['bad_redeemdata']}")
    print(f"  option.or_try (BAD)    : {qc['bad_or_try']}")
    print(f"  output.value cmp (BAD) : {qc['bad_value_compare']}")
    print(f"  placeholder (BAD)      : {qc['bad_placeholder']}")
    print(f"  markdown fence (BAD)   : {qc['bad_fence']}")
    print(f"  trivial True (BAD)     : {qc['bad_trivial_true']}")
    print(f"  TOTAL BAD              : {qc['total_bad']}")
    print(f"{'='*55}")

    summary = {
        "total": len(all_examples),
        "by_batch": batch_counts,
        "by_lang": dict(Counter(e.get("lang","?") for e in all_examples)),
        "quality": qc,
    }
    summary_path = args.output.replace(".jsonl", "_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n  Output : {args.output}")
    print(f"  Summary: {summary_path}")
    print(f"\nPara agregar al dataset v14:")
    print(f"  cat {args.output} >> data/processed/dataset_v14_train.jsonl")


if __name__ == "__main__":
    main()
