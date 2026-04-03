#!/usr/bin/env python3
"""
generate_reference_input_examples.py — Cardumen Forge

Generates grounded training examples for CIP-31 reference input patterns.
Uses local documentation only: data/raw/cips.json (CIP-0031) and
data/raw/aiken_stdlib.json (find_input, find_datum, Input, OutputReference).

Target: 80+ examples, all VERIFIED_V3_ALIGNED, all using:
    transaction.find_input(self.reference_inputs, <ref>)

Usage:
    python3 scripts/generate_reference_input_examples.py --dry-run     # print first batch, no API
    python3 scripts/generate_reference_input_examples.py               # generate all, dry run
    python3 scripts/generate_reference_input_examples.py --write       # save to output file
    python3 scripts/generate_reference_input_examples.py --write --append-to-v20  # merge into v20
"""

import re
import json
import time
import argparse
from pathlib import Path

import anthropic

# ── Paths ─────────────────────────────────────────────────────────────────────
STDLIB_PATH  = Path("data/raw/aiken_stdlib.json")
CIPS_PATH    = Path("data/raw/cips.json")
OUTPUT_PATH  = Path("data/processed/components/reference_input_examples.jsonl")
V22_PATH     = Path("data/processed/dataset_v22.jsonl")

# ── Load local documentation ──────────────────────────────────────────────────

def load_stdlib_context() -> str:
    with open(STDLIB_PATH) as f:
        entries = json.load(f)

    relevant_names = {
        "find_input", "find_datum", "find_script_outputs",
        "Input", "Output", "OutputReference", "Transaction",
        "InlineDatum", "lovelace_of", "quantity_of", "has_nft",
    }
    relevant_modules = {"cardano.transaction", "cardano.assets"}

    lines = []
    for e in entries:
        if e.get("name") in relevant_names or e.get("module") in relevant_modules:
            lines.append(
                f"MODULE: {e['module']}\n"
                f"NAME:   {e['name']}\n"
                f"SIG:    {e.get('signature','')}\n"
                f"DESC:   {e.get('description','')[:300]}\n"
            )
    return "\n".join(lines)


def load_cip31_context() -> str:
    with open(CIPS_PATH) as f:
        cips = json.load(f)
    cip31 = next((c for c in cips if c.get("id") == "CIP-0031"), None)
    if not cip31:
        return ""
    return f"CIP-0031 — {cip31['title']}\nStatus: {cip31['status']}\n\n{cip31['content'][:3000]}"


# ── Scenario batches ─────────────────────────────────────────────────────────
# Each batch has a theme and 8-10 instruction/lang pairs.
# The script sends all instructions in a single API call per batch.

BATCHES = [
    {
        "theme": "Oracle price feeds",
        "items": [
            ("en", "Write an Aiken v3 spend validator that reads an ADA/USD price from a reference input oracle and checks the payment covers the USD cost."),
            ("es", "Escribe un validador spend que lea el precio ADA/USD de una entrada de referencia oracle y verifique que el pago cubre el costo en USD."),
            ("en", "Write an Aiken v3 spend validator for a swap contract that reads an exchange rate from a reference input and validates the swap is fair within 1% slippage."),
            ("es", "Escribe un validador spend para un contrato de swap que lea la tasa de cambio de una referencia y valide que el swap es justo con menos del 1% de deslizamiento."),
            ("en", "Write an Aiken v3 spend validator that reads a minimum price from a reference input and rejects any payment below that threshold."),
            ("es", "Escribe un validador spend que lea un precio mínimo de una entrada de referencia y rechace pagos por debajo de ese umbral."),
            ("en", "Write an Aiken v3 spend validator for a lending protocol that reads the collateral ratio from a reference input oracle to check if a position is undercollateralized."),
            ("es", "Escribe un validador spend para un protocolo de préstamos que lea el ratio de colateral de una referencia oracle para verificar si una posición está sub-colateralizada."),
        ],
    },
    {
        "theme": "Config and protocol parameters",
        "items": [
            ("en", "Write an Aiken v3 spend validator that reads a fee rate from a reference input config datum and deducts the correct fee before allowing withdrawal."),
            ("es", "Escribe un validador spend que lea una tasa de comisión de un datum de configuración en una referencia y descuente la comisión correcta antes de permitir el retiro."),
            ("en", "Write an Aiken v3 spend validator that reads minimum ADA requirements from a reference input and validates the output meets the minimum."),
            ("es", "Escribe un validador spend que lea los requisitos mínimos de ADA de una referencia y valide que la salida cumple con el mínimo."),
            ("en", "Write an Aiken v3 spend validator that reads a deadline from a reference input config and only allows spending before that deadline."),
            ("es", "Escribe un validador spend que lea una fecha límite de una configuración de referencia y solo permita gastar antes de esa fecha."),
            ("en", "Write an Aiken v3 spend validator for a protocol that reads its own parameters (max supply, fee rate, admin key) from a reference input config UTXO."),
            ("es", "Escribe un validador spend para un protocolo que lea sus parámetros (suministro máximo, tasa de comisión, clave admin) de una UTXO de configuración de referencia."),
            ("en", "Write an Aiken v3 spend validator that reads a treasury address from a reference input and ensures fees are sent to that address."),
        ],
    },
    {
        "theme": "Allowlists and access control",
        "items": [
            ("en", "Write an Aiken v3 spend validator that reads an allowlist of permitted public key hashes from a reference input and checks the signer is in the list."),
            ("es", "Escribe un validador spend que lea una lista blanca de claves públicas permitidas desde una referencia y verifique que el firmante está en la lista."),
            ("en", "Write an Aiken v3 spend validator that reads a blocklist from a reference input and rejects transactions signed by any key on the blocklist."),
            ("es", "Escribe un validador spend que lea una lista negra de una referencia y rechace transacciones firmadas por cualquier clave en esa lista."),
            ("en", "Write an Aiken v3 spend validator for a DAO treasury that reads the list of approved multisig signers from a reference input and requires 2 of them to sign."),
            ("es", "Escribe un validador spend para una tesorería DAO que lea la lista de firmantes multisig aprobados de una referencia y requiera que 2 de ellos firmen."),
            ("en", "Write an Aiken v3 spend validator that reads a list of approved script hashes from a reference input and validates the output goes to an approved script."),
            ("es", "Escribe un validador spend que lea una lista de hashes de scripts aprobados de una referencia y valide que la salida vaya a un script aprobado."),
        ],
    },
    {
        "theme": "DEX and DeFi patterns",
        "items": [
            ("en", "Write an Aiken v3 spend validator for a DEX order that reads the current pool state from a reference input and validates the order can be filled at the current price."),
            ("es", "Escribe un validador spend para una orden de DEX que lea el estado actual del pool de una referencia y valide que la orden puede ejecutarse al precio actual."),
            ("en", "Write an Aiken v3 spend validator that reads liquidity pool reserves from a reference input and validates the constant product invariant k = x * y is maintained."),
            ("es", "Escribe un validador spend que lea las reservas de un pool de liquidez de una referencia y valide que el invariante k = x * y se mantiene."),
            ("en", "Write an Aiken v3 spend validator for a stablecoin that reads the peg price from a reference oracle and only allows redemption when the price depegs by more than 2%."),
            ("es", "Escribe un validador spend para una stablecoin que lea el precio de anclaje de una referencia oracle y solo permita redención cuando el precio se desancle más del 2%."),
            ("en", "Write an Aiken v3 spend validator for a yield farm that reads the current reward rate from a reference input and computes the correct reward to distribute."),
            ("en", "Write an Aiken v3 spend validator for a lending market that reads the current interest rate from a reference input oracle to compute accrued interest."),
        ],
    },
    {
        "theme": "NFT and token metadata",
        "items": [
            ("en", "Write an Aiken v3 spend validator that reads NFT metadata from a reference input (CIP-68 reference NFT) and validates the token meets metadata requirements."),
            ("es", "Escribe un validador spend que lea metadatos de NFT de una referencia (NFT de referencia CIP-68) y valide que el token cumple los requisitos de metadatos."),
            ("en", "Write an Aiken v3 spend validator that reads a collection policy from a reference input and validates the minted token belongs to that collection."),
            ("es", "Escribe un validador spend que lea la política de una colección desde una referencia y valide que el token acuñado pertenece a esa colección."),
            ("en", "Write an Aiken v3 spend validator for a marketplace that reads a royalty rate and recipient from a reference input NFT and ensures the royalty is paid."),
            ("es", "Escribe un validador spend para un marketplace que lea la tasa de regalías y el destinatario de una referencia NFT y verifique que se pagan las regalías."),
            ("en", "Write an Aiken v3 spend validator that reads token traits from a reference input datum and validates the token has the required trait to access the gated content."),
            ("es", "Escribe un validador spend que lea los atributos de un token de un datum de referencia y valide que el token tiene el atributo requerido para acceder al contenido."),
        ],
    },
    {
        "theme": "State machines and on-chain state",
        "items": [
            ("en", "Write an Aiken v3 spend validator that reads the current state of an on-chain state machine from a reference input and validates the transition is valid."),
            ("es", "Escribe un validador spend que lea el estado actual de una máquina de estados on-chain desde una referencia y valide que la transición es válida."),
            ("en", "Write an Aiken v3 spend validator for a vending machine contract that reads the current inventory count from a reference input and checks items are available."),
            ("es", "Escribe un validador spend para un contrato de máquina expendedora que lea el inventario actual de una referencia y verifique que hay artículos disponibles."),
            ("en", "Write an Aiken v3 spend validator that reads a game state from a reference input (player position, score, level) and validates the move is legal."),
            ("es", "Escribe un validador spend que lea el estado de un juego desde una referencia (posición del jugador, puntuación, nivel) y valide que el movimiento es legal."),
            ("en", "Write an Aiken v3 spend validator for an auction that reads the current highest bid from a reference input and rejects bids below it."),
            ("es", "Escribe un validador spend para una subasta que lea la oferta más alta actual de una referencia y rechace ofertas por debajo de ella."),
        ],
    },
    {
        "theme": "Governance and DAO patterns",
        "items": [
            ("en", "Write an Aiken v3 spend validator for a DAO that reads the current governance proposal from a reference input and validates a vote is within the voting window."),
            ("es", "Escribe un validador spend para una DAO que lea la propuesta de gobernanza actual desde una referencia y valide que un voto está dentro del período de votación."),
            ("en", "Write an Aiken v3 spend validator for a community fund that reads approved recipients from a reference input governance datum and validates the disbursement."),
            ("es", "Escribe un validador spend para un fondo comunitario que lea los beneficiarios aprobados de un datum de gobernanza de referencia y valide el desembolso."),
            ("en", "Write an Aiken v3 spend validator that reads a governance parameter (quorum threshold) from a reference input and validates enough votes have been cast."),
            ("es", "Escribe un validador spend que lea un parámetro de gobernanza (umbral de quórum) de una referencia y valide que se han emitido suficientes votos."),
            ("en", "Write an Aiken v3 spend validator for a timelock treasury that reads the release schedule from a reference input and only allows withdrawal when the unlock date passes."),
        ],
    },
    {
        "theme": "Multi-validator and cross-contract patterns",
        "items": [
            ("en", "Write an Aiken v3 spend validator that reads the address of a companion validator from a reference input and ensures funds are forwarded to it."),
            ("es", "Escribe un validador spend que lea la dirección de un validador compañero desde una referencia y asegure que los fondos se reenvíen hacia él."),
            ("en", "Write an Aiken v3 spend validator that reads version information from a reference input and rejects interactions with deprecated script versions."),
            ("es", "Escribe un validador spend que lea información de versión de una referencia y rechace interacciones con versiones de script obsoletas."),
            ("en", "Write an Aiken v3 spend validator that reads a whitelist of trusted oracle addresses from a reference input and validates the used oracle is in the list."),
            ("es", "Escribe un validador spend que lea una lista de direcciones oracle confiables de una referencia y valide que el oracle utilizado está en esa lista."),
            ("en", "Write an Aiken v3 spend validator for a bridge that reads the target chain address mapping from a reference input and validates the destination."),
            ("en", "Write an Aiken v3 spend validator that reads two reference inputs simultaneously — a price oracle and a config datum — to validate a complex DeFi operation."),
            ("es", "Escribe un validador spend que lea dos referencias simultáneamente — un oracle de precios y un datum de configuración — para validar una operación DeFi compleja."),
        ],
    },
    {
        "theme": "Rate limiting and time-based patterns",
        "items": [
            ("en", "Write an Aiken v3 spend validator that reads a rate limit (max withdrawals per epoch) from a reference input and enforces it using the transaction validity range."),
            ("es", "Escribe un validador spend que lea un límite de tasa (máximo de retiros por época) de una referencia y lo haga cumplir usando el rango de validez de la transacción."),
            ("en", "Write an Aiken v3 spend validator for a drip faucet that reads the drip rate and last-claim time from reference inputs and prevents claiming too frequently."),
            ("es", "Escribe un validador spend para un faucet de goteo que lea la tasa y el tiempo del último reclamo de referencias y evite reclamos demasiado frecuentes."),
            ("en", "Write an Aiken v3 spend validator that reads a time-based multiplier from a reference input oracle and applies it to compute the final payout amount."),
            ("es", "Escribe un validador spend que lea un multiplicador temporal de una referencia oracle y lo aplique para calcular el monto de pago final."),
            ("en", "Write an Aiken v3 spend validator for a vesting contract that reads the vesting schedule from a reference input and calculates how many tokens are unlocked."),
            ("es", "Escribe un validador spend para un contrato de vesting que lea el calendario de liberación desde una referencia y calcule cuántos tokens están desbloqueados."),
        ],
    },
    {
        "theme": "Advanced CIP-31 patterns",
        "items": [
            ("en", "Write an Aiken v3 spend validator that reads a datum from a reference input using find_input and accesses nested fields from the resolved InlineDatum."),
            ("es", "Escribe un validador spend que lea un datum de una referencia con find_input y acceda a campos anidados del InlineDatum resuelto."),
            ("en", "Write an Aiken v3 spend validator that checks the value locked in a reference input (not just its datum) to validate a collateral requirement is met."),
            ("es", "Escribe un validador spend que verifique el valor bloqueado en una entrada de referencia (no solo su datum) para validar que se cumple un requisito de colateral."),
            ("en", "Write an Aiken v3 spend validator that reads a list of valid UTxO references from a reference input and checks the current transaction includes one of them as input."),
            ("es", "Escribe un validador spend que lea una lista de referencias UTxO válidas desde una referencia y verifique que la transacción actual incluye una de ellas como entrada."),
            ("en", "Write an Aiken v3 spend validator that reads a script hash from a reference input datum and validates all outputs go to a script with that hash."),
            ("en", "Write an Aiken v3 spend validator that verifies a reference input is from a known trusted issuer by checking its address, then uses its datum for validation."),
            ("es", "Escribe un validador spend que verifique que una entrada de referencia proviene de un emisor confiable conocido comprobando su dirección, y luego use su datum para la validación."),
        ],
    },
]


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """You are an expert Aiken v3 smart contract engineer for the Cardano blockchain.
You generate correct, compilable Aiken v3 training examples using ONLY the APIs documented below.

━━━ CIP-31 — REFERENCE INPUTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{cip31}

━━━ VERIFIED STDLIB APIs ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{stdlib}

━━━ CRITICAL RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HANDLER SYNTAX — NO fn keyword inside validator blocks:
  validator my_contract {{
    spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool {{
      ...
    }}
  }}

IMPORTS — slash style only, never dot:
  use cardano/transaction.{{Transaction, OutputReference, Input, find_input}}
  use cardano/assets
  use aiken/collection/list

REFERENCE INPUT PATTERN — always use this exact pattern:
  expect Some(ref_in) = transaction.find_input(self.reference_inputs, oracle_ref)
  // then access: ref_in.output.value, ref_in.output.datum, ref_in.output.address

DATUM ACCESS:
  when ref_in.output.datum is {{
    InlineDatum(raw) -> {{
      expect data: MyType = raw
      ...
    }}
    _ -> fail
  }}

DO NOT USE:
  - self.signatures (use self.extra_signatories)
  - self.time (use self.validity_range)
  - fn spend( (use spend( directly)
  - use cardano.transaction (dot-style import)
  - list.find (use transaction.find_input)

━━━ OUTPUT FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return a JSON array. Each object:
{{
  "instruction": "...",
  "input": "",
  "output": "...complete Aiken v3 code...",
  "lang": "en" or "es"
}}

Rules for output field:
- Complete compilable validator code (not pseudocode)
- MUST contain: reference_inputs, find_input
- Imports at top using slash style
- Custom types defined before the validator
- No markdown fences, no explanation text — just the code
"""


# ── Generation ────────────────────────────────────────────────────────────────

def build_user_message(batch: dict) -> str:
    lines = [f"Generate Aiken v3 training examples for the theme: {batch['theme']}\n"]
    lines.append("Generate one example per instruction below. Return a JSON array.\n")
    for i, (lang, instruction) in enumerate(batch["items"], 1):
        lines.append(f"[{i}] ({lang}) {instruction}")
    return "\n".join(lines)


def validate_example(ex: dict) -> list[str]:
    """Returns list of error strings, empty = valid."""
    errors = []
    out = ex.get("output", "")
    if not out:
        errors.append("empty output")
        return errors
    if "reference_inputs" not in out:
        errors.append("missing: reference_inputs")
    if "find_input" not in out:
        errors.append("missing: find_input")
    if "validator" not in out:
        errors.append("missing: validator block")
    if "spend(" not in out:
        errors.append("missing: spend( handler")
    if re.search(r'\bfn\s+(spend|mint|withdraw|publish|vote)\s*\(', out):
        errors.append("bad: fn prefix on handler")
    if re.search(r'\buse\s+\w+\.', out):
        errors.append("bad: dot-style import")
    if "self.signatures" in out:
        errors.append("bad: self.signatures")
    if "self.time" in out:
        errors.append("bad: self.time")
    return errors


def generate_batch(client: anthropic.Anthropic, batch: dict,
                   system_prompt: str, dry_run: bool = False) -> list[dict]:
    if dry_run:
        print(f"\n  [DRY RUN] Would generate batch: {batch['theme']}")
        print(f"  {len(batch['items'])} instructions")
        return []

    user_msg = build_user_message(batch)
    print(f"\n  Generating: {batch['theme']} ({len(batch['items'])} examples)...")

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()

    # Extract JSON array
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        print(f"  ERROR: no JSON array in response")
        return []

    try:
        examples = json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"  ERROR: JSON parse failed: {e}")
        return []

    # Validate and annotate
    good, bad = [], []
    for ex in examples:
        errors = validate_example(ex)
        if errors:
            bad.append((ex.get("instruction", "?")[:60], errors))
        else:
            ex["source"] = "reference_input_examples"
            ex["topic"] = f"cip31/{batch['theme'].lower().replace(' ', '_')}"
            ex["review_status"] = "VERIFIED_V3_ALIGNED"
            good.append(ex)

    print(f"  ✅ {len(good)} valid  |  ❌ {len(bad)} rejected")
    for instr, errs in bad:
        print(f"     REJECTED [{', '.join(errs)}]: {instr}")

    return good


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",       action="store_true", help="Print plan, no API calls")
    parser.add_argument("--write",         action="store_true", help="Save output file")
    parser.add_argument("--append-output", action="store_true", help="Append to component file instead of overwrite")
    parser.add_argument("--append-to-v22", action="store_true", help="Append to dataset_v22.jsonl")
    parser.add_argument("--batches",       type=str, default="all",
                        help="Comma-separated batch indices (0-based) or 'all'")
    args = parser.parse_args()

    print("\nCardumen Forge — Reference Input Examples Generator")
    print(f"CIP-31 context  : {CIPS_PATH}")
    print(f"Stdlib context  : {STDLIB_PATH}")
    print(f"Output          : {OUTPUT_PATH}")
    print(f"Mode            : {'DRY RUN' if args.dry_run else 'GENERATE'}")

    # Load context
    cip31_ctx  = load_cip31_context()
    stdlib_ctx = load_stdlib_context()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(cip31=cip31_ctx, stdlib=stdlib_ctx)

    print(f"\nContext loaded  : CIP-31 ({len(cip31_ctx)} chars) + stdlib ({len(stdlib_ctx)} chars)")

    # Select batches
    if args.batches == "all":
        selected = BATCHES
        indices  = list(range(len(BATCHES)))
    else:
        indices  = [int(x) for x in args.batches.split(",")]
        selected = [BATCHES[i] for i in indices]

    total_instructions = sum(len(b["items"]) for b in selected)
    print(f"Batches         : {len(selected)} / {len(BATCHES)}  ({total_instructions} instructions)")

    if args.dry_run:
        for i, b in zip(indices, selected):
            print(f"\n  Batch [{i}] — {b['theme']} ({len(b['items'])} items)")
            for lang, instr in b["items"]:
                print(f"    ({lang}) {instr[:80]}")
        print(f"\n  Total: {total_instructions} examples planned")
        return

    # Generate
    client    = anthropic.Anthropic()
    all_good  = []

    for batch in selected:
        examples = generate_batch(client, batch, system_prompt, dry_run=False)
        all_good.extend(examples)
        time.sleep(1)  # rate limit courtesy

    print(f"\n{'='*60}")
    print(f"  Total generated : {total_instructions} attempted")
    print(f"  Total valid     : {len(all_good)}")
    print(f"  Pass rate       : {100*len(all_good)/max(1,total_instructions):.1f}%")

    # Verify critical patterns
    with_both = sum(1 for e in all_good
                    if "reference_inputs" in e["output"] and "find_input" in e["output"])
    print(f"  Both patterns   : {with_both}/{len(all_good)} (reference_inputs + find_input)")
    print(f"{'='*60}")

    if not args.write:
        print("\n  (dry run — use --write to save)")
        if all_good:
            print(f"\n  Sample output (first example):")
            print(f"  Instruction: {all_good[0]['instruction'][:80]}")
            print(f"  Lang: {all_good[0]['lang']}")
            print(f"  Output (first 400 chars):\n{all_good[0]['output'][:400]}")
        return

    # Save component file
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_mode = "a" if args.append_output else "w"
    with open(OUTPUT_PATH, write_mode, encoding="utf-8") as f:
        for ex in all_good:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    action = "Appended" if args.append_output else "Saved"
    total_in_file = sum(1 for _ in open(OUTPUT_PATH))
    print(f"\n  ✅ {action} {len(all_good)} examples → {OUTPUT_PATH}  (file total: {total_in_file})")

    # Optionally append to v22
    if args.append_to_v22:
        with open(V22_PATH, "a", encoding="utf-8") as f:
            for ex in all_good:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        # Count new total
        with open(V22_PATH) as f:
            new_total = sum(1 for l in f if l.strip())
        print(f"  ✅ Appended to {V22_PATH}  (new total: {new_total:,})")


if __name__ == "__main__":
    main()
