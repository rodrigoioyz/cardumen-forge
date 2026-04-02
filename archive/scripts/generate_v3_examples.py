#!/usr/bin/env python3
"""
generate_v3_examples.py
Genera ejemplos Aiken v3 curados para fine-tuning.

Uso:
    python3 generate_v3_examples.py --target 300
    python3 generate_v3_examples.py --target 100 --dataset data/processed/dataset_v6_clean.jsonl
    python3 generate_v3_examples.py --target 50 --model claude-haiku-4-5-20251001
    python3 generate_v3_examples.py --target 300 --output data/processed/dataset_v3_batch2.jsonl
    python3 generate_v3_examples.py --target 300 --dry-run
"""

import os
import sys
import json
import argparse
from collections import Counter
from anthropic import Anthropic

# ─────────────────────────────────────────────
# Configuración de modelos
# ─────────────────────────────────────────────
DEFAULT_MODEL  = "claude-sonnet-4-6"           # mejor calidad
FAST_MODEL     = "claude-haiku-4-5-20251001"   # más barato
MAX_TOKENS     = 8000
BATCH_SIZE     = 25                            # ejemplos por llamada API


# ─────────────────────────────────────────────
# 10 ejemplos semilla (v3 curados manualmente)
# ─────────────────────────────────────────────
SEED_EXAMPLES = [
    {"lang":"en","instruction":"Write an Aiken v3 spending validator that checks the script's own input contains a specific NFT.","input":"Use the spend handler with the script's own OutputReference. PolicyId = #\"00112233445566778899aabbccddeeff00112233445566778899aabb\". AssetName = \"Member\". Use documented stdlib helpers only.","output":"use cardano/transaction\nuse cardano/assets\n\nvalidator nft_gate {\n  spend(_datum, _redeemer, own_ref, self) {\n    let own_output = transaction.resolve_input(self.inputs, own_ref)\n    assets.has_nft(\n      own_output.value,\n      #\"00112233445566778899aabbccddeeff00112233445566778899aabb\",\n      \"Member\",\n    )\n  }\n}","source":"aiken_v3_curated","topic":"aiken_v3_spend_nft_gate","review_status":"VERIFIED_V3_ALIGNED"},
    {"lang":"en","instruction":"Explain why checking any transaction input for an NFT is weaker than checking the script's own input in a spend validator.","input":"Contrast insecure scanning of self.inputs with resolving the validator's own output reference.","output":"In a spending validator, checking whether any input carries an NFT is weaker because a transaction may include unrelated inputs. That lets an attacker satisfy the condition with some other input while spending the script UTxO that does not have the required asset. In Aiken v3, the safer pattern is to use the spend handler's own OutputReference and resolve that exact input with transaction.find_input or transaction.resolve_input. This binds the check to the UTxO currently governed by the validator instead of to the transaction globally.","source":"aiken_v3_curated","topic":"aiken_v3_security_own_input","review_status":"VERIFIED_V3_ALIGNED"},
    {"lang":"en","instruction":"Write an Aiken v3 validator that requires every transaction output to carry at least 1 ADA.","input":"Use Transaction.outputs and the documented cardano/assets helper for Ada. Avoid invented fields like output.value.lovelace.","output":"use aiken/collection/list\nuse cardano/assets\n\nvalidator min_ada_outputs {\n  spend(_datum, _redeemer, _own_ref, self) {\n    list.all(self.outputs, fn(output) {\n      assets.lovelace_of(output.value) >= 1_000_000\n    })\n  }\n}","source":"aiken_v3_curated","topic":"aiken_v3_min_ada_outputs","review_status":"VERIFIED_V3_ALIGNED"},
    {"lang":"en","instruction":"Explain the difference between has_nft and has_nft_strict in Aiken v3.","input":"Use the semantics from cardano/assets. Keep it short and technical.","output":"assets.has_nft(value, policy, asset_name) checks whether the Value contains exactly one unit of the requested NFT, but it tolerates other assets being present as well. assets.has_nft_strict(value, policy, asset_name) is stronger: it succeeds only when the Value contains the requested NFT and no other non-Ada assets. In practice, use has_nft when you only care that the NFT is present somewhere in the bundle, and has_nft_strict when the UTxO must be clean except for Ada plus that NFT.","source":"aiken_v3_curated","topic":"aiken_v3_has_nft_vs_strict","review_status":"PLAUSIBLE_NEEDS_CHECK"},
    {"lang":"en","instruction":"Write an Aiken v3 spending validator that requires the owner's signature.","input":"Use a datum containing a VerificationKeyHash. Validate against Transaction.extra_signatories. Keep the code minimal.","output":"use aiken/collection/list\nuse aiken/crypto.{VerificationKeyHash}\n\npub type Datum {\n  owner: VerificationKeyHash,\n}\n\nvalidator signed_by_owner {\n  spend(datum: Option<Datum>, _redeemer, _own_ref, self) {\n    expect Some(Datum { owner }) = datum\n    list.has(self.extra_signatories, owner)\n  }\n}","source":"aiken_v3_curated","topic":"aiken_v3_extra_signatories","review_status":"VERIFIED_V3_ALIGNED"},
    {"lang":"en","instruction":"Write an Aiken v3 mint policy that allows minting exactly one token of a given asset name and rejects any other quantity.","input":"Use Transaction.mint and cardano/assets.quantity_of. AssetName = \"Badge\". The mint handler receives the policy id as argument.","output":"use cardano/assets\n\nvalidator badge_policy {\n  mint(_redeemer, policy_id, self) {\n    assets.quantity_of(self.mint, policy_id, \"Badge\") == 1\n  }\n}","source":"aiken_v3_curated","topic":"aiken_v3_mint_exact_quantity","review_status":"VERIFIED_V3_ALIGNED"},
    {"lang":"en","instruction":"Write an Aiken v3 spending validator that enforces spending only after a deadline stored in the datum.","input":"Datum contains deadline: Int representing POSIX time in milliseconds. Use Transaction.validity_range. Keep the explanation out; return only code.","output":"use aiken/interval\n\npub type Datum {\n  deadline: Int,\n}\n\nvalidator after_deadline {\n  spend(datum: Option<Datum>, _redeemer, _own_ref, self) {\n    expect Some(Datum { deadline }) = datum\n    interval.is_entirely_after(self.validity_range, deadline)\n  }\n}","source":"aiken_v3_curated","topic":"aiken_v3_deadline_spend","review_status":"PLAUSIBLE_NEEDS_CHECK"},
    {"lang":"es","instruction":"Explica qué son `reference_inputs` en Aiken v3 y en qué se diferencian de `inputs`.","input":"Respuesta corta, técnica y orientada a eUTxO.","output":"En Aiken v3, `inputs` representa las entradas que la transacción realmente gasta. Esas UTxO desaparecen del conjunto UTxO si la transacción valida. En cambio, `reference_inputs` son UTxO que la transacción puede leer como contexto sin consumirlas. Sirven para consultar datos o scripts de referencia sin gastar esas salidas. La diferencia clave es semántica: `inputs` cambia estado on-chain; `reference_inputs` solo aporta lectura.","source":"aiken_v3_curated","topic":"aiken_v3_reference_inputs_explanation","review_status":"VERIFIED_V3_ALIGNED"},
    {"lang":"en","instruction":"Write an Aiken v3 validator that checks there is at least one continuing output to the same script.","input":"Use the documented transaction helper for script outputs rather than manually scanning outputs.","output":"use aiken/collection/list\nuse cardano/transaction\n\nvalidator must_continue {\n  spend(_datum, _redeemer, own_ref, self) {\n    let continuing = transaction.find_script_outputs(self.outputs, own_ref)\n    not(list.is_empty(continuing))\n  }\n}","source":"aiken_v3_curated","topic":"aiken_v3_continuing_outputs","review_status":"PLAUSIBLE_NEEDS_CHECK"},
    {"lang":"es","instruction":"Corrige este error conceptual: `output.value.lovelace` es la forma correcta de leer ADA en Aiken v3.","input":"Explica la forma correcta y da un ejemplo corto.","output":"Eso es incorrecto como regla general. En Aiken v3, la forma documentada de consultar Ada en un `Value` es usando helpers del módulo `cardano/assets`, especialmente `assets.lovelace_of(value)`. Un ejemplo corto sería: `assets.lovelace_of(output.value) >= 1_000_000`. Esto evita inventar campos estructurales sobre `Value` y mantiene el código alineado con la stdlib oficial.","source":"aiken_v3_curated","topic":"aiken_v3_lovelace_of_correction","review_status":"VERIFIED_V3_ALIGNED"},
]


# ─────────────────────────────────────────────
# Tool schema para output estructurado
# ─────────────────────────────────────────────
TOOL_SCHEMA = {
    "name": "save_v3_examples",
    "description": "Save a batch of curated Aiken v3 dataset examples",
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
                        "review_status": {"type": "string", "enum": ["VERIFIED_V3_ALIGNED", "PLAUSIBLE_NEEDS_CHECK"]},
                    },
                    "required": ["lang", "instruction", "input", "output", "source", "topic", "review_status"],
                },
            }
        },
        "required": ["examples"],
    },
}


# ─────────────────────────────────────────────
# Prompt del sistema
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a strict dataset builder and technical curator for Aiken stdlib v3.
Your task is to generate high-quality fine-tuning examples for Aiken smart contracts on Cardano.

## GROUND TRUTH — Aiken v3 documented surfaces

Transaction fields (via `self` in handlers):
  inputs, reference_inputs, outputs, mint, validity_range,
  extra_signatories, redeemers, datums, id

Transaction helpers (cardano/transaction):
  find_input(inputs, output_reference) -> Option<Input>
  resolve_input(inputs, output_reference) -> Input   [fails if not found]
  find_datum(datums, datum_hash) -> Option<Data>
  find_script_outputs(outputs, ...) -> List<Output>  [exact signature uncertain]

Assets helpers (cardano/assets):
  lovelace_of(value) -> Int
  quantity_of(value, policy_id, asset_name) -> Int
  has_nft(value, policy_id, asset_name) -> Bool
  has_nft_strict(value, policy_id, asset_name) -> Bool  [uncertain — mark PLAUSIBLE]

Interval helpers (aiken/interval):
  is_entirely_after(range, point) -> Bool   [plausible]
  is_entirely_before(range, point) -> Bool  [plausible]
  contains(range, point) -> Bool

Validator handler signatures (v3):
  spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
  withdraw(redeemer: T, account: StakeCredential, self: Transaction) -> Bool
  publish(redeemer: T, certificate: Certificate, self: Transaction) -> Bool

## HARD RULES

NEVER generate:
  - output.value.lovelace  (wrong — use assets.lovelace_of)
  - value.get_ada()        (invented)
  - output.assets.contains(...) (invented)
  - "current time" outside validity_range
  - checking any input when own input is the correct scope
  - Haskell syntax mixed with Aiken

## REVIEW STATUS RULES

Mark VERIFIED_V3_ALIGNED only when:
  - all imports are from documented modules
  - all helpers are confirmed in the ground truth above

Mark PLAUSIBLE_NEEDS_CHECK when:
  - using has_nft_strict
  - using find_script_outputs
  - using interval helpers beyond contains()
  - any helper not listed in ground truth

## OUTPUT RULES

- source must always be "aiken_v3_curated"
- topic must be snake_case and descriptive
- instruction must be a single actionable sentence
- input provides constraints/context
- output is either clean Aiken code OR a short technical explanation
- be minimal — avoid overengineering
- avoid near-duplicate examples

## CODE QUALITY RULES (strictly enforced)

NEVER include in output:
  - meta-comments like `// Correct approach`, `// Better version`, `// Fixed:`
  - inline reasoning like `// This is wrong because...` before showing the fix
  - dead expressions or discarded drafts before the final solution
  - placeholder comments like `// TODO`, `// ...`, `// rest of logic here`

Code outputs must be:
  - the final solution only — no build-up, no before/after within the same output
  - silent on correctness — the code speaks for itself
  - commented only when the logic is non-obvious (eUTxO semantics, edge cases)
"""


# ─────────────────────────────────────────────
# Prompt de usuario
# ─────────────────────────────────────────────
def build_user_prompt(seed_examples: list, existing_topics: set, batch_size: int, batch_num: int, target_total: int) -> str:
    seed_json = "\n".join(json.dumps(e, ensure_ascii=False) for e in seed_examples)

    existing_topics_str = "\n".join(f"  - {t}" for t in sorted(existing_topics)) if existing_topics else "  (none yet)"

    # Scale distribution to target_total
    scale = target_total / 50
    distribution = f"""
REQUIRED DISTRIBUTION across all {target_total} examples (scale factor {scale:.1f}x from base 50):
  - {round(10*scale):>3} examples: value / assets (lovelace_of, quantity_of, has_nft)
  - {round(10*scale):>3} examples: spend validators (own input correctness, datum patterns)
  - {round(10*scale):>3} examples: mint policies
  - {round(5*scale):>3} examples: signatures (extra_signatories)
  - {round(5*scale):>3} examples: validity_range / deadlines
  - {round(5*scale):>3} examples: reference_inputs usage
  - {round(5*scale):>3} examples: anti-hallucination / API correction examples
"""

    return f"""\
## TASK

Generate exactly {batch_size} new Aiken v3 examples (batch {batch_num} of a {target_total}-example run).

{distribution}

## SEED EXAMPLES (already in dataset — do NOT duplicate topics)

{seed_json}

## TOPICS ALREADY COVERED (avoid near-duplicates)

{existing_topics_str}

## INSTRUCTIONS

1. Do NOT reproduce any topic already covered.
2. Vary between code generation, explanation, refactoring, and security tasks.
3. Mix EN and ES (aim for ~60% EN, ~40% ES).
4. Each example must be minimal and correct.
5. Mark review_status strictly per the system rules.
6. Use source = "aiken_v3_curated" for all examples.

Call save_v3_examples with exactly {batch_size} examples.
"""


# ─────────────────────────────────────────────
# Llamada a Claude con tool_use
# ─────────────────────────────────────────────
def call_claude(prompt: str, model: str, client: Anthropic, dry_run: bool = False) -> list:
    if dry_run:
        print(f"\n[DRY RUN] Prompt ({len(prompt)} chars):\n{prompt[:600]}...\n")
        return []

    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "save_v3_examples"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "save_v3_examples":
            return block.input.get("examples", [])

    return []


# ─────────────────────────────────────────────
# Deduplicación por topic
# ─────────────────────────────────────────────
def dedup_by_topic(examples: list) -> list:
    seen = set()
    result = []
    for ex in examples:
        t = ex.get("topic", "")
        if t not in seen:
            seen.add(t)
            result.append(ex)
    return result


# ─────────────────────────────────────────────
# Resumen final
# ─────────────────────────────────────────────
def print_summary(examples: list, output_path: str):
    total = len(examples)
    by_lang   = Counter(e.get("lang", "?")           for e in examples)
    by_status = Counter(e.get("review_status", "?")  for e in examples)
    by_topic  = Counter(e.get("topic", "?")           for e in examples)

    print("\n" + "="*50)
    print(f" RESUMEN — {output_path}")
    print("="*50)
    print(f"  Total ejemplos : {total}")
    print(f"  Por idioma     : {dict(by_lang)}")
    print(f"  Por status     :")
    for status, count in by_status.most_common():
        print(f"    {status}: {count}")
    print(f"  Por topic ({len(by_topic)} únicos):")
    for topic, count in by_topic.most_common():
        print(f"    {topic}: {count}")
    print("="*50)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Genera ejemplos Aiken v3 curados para fine-tuning")
    parser.add_argument("--target",    type=int, required=True,
                        help="Número de ejemplos nuevos a generar (ej: 300)")
    parser.add_argument("--dataset",   default="data/processed/dataset_v6_clean.jsonl",
                        help="Dataset existente para extraer topics ya cubiertos (no se modifica)")
    parser.add_argument("--output",    default=None,
                        help="Archivo de salida base (default: dataset_v3_gen_{target}.jsonl)")
    parser.add_argument("--model",     default=DEFAULT_MODEL,
                        help=f"Modelo Claude a usar (default: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Muestra prompts sin llamar a la API")
    parser.add_argument("--overwrite", action="store_true",
                        help="Sobrescribe el archivo de salida si ya existe")
    args = parser.parse_args()

    # Output paths
    base_output = args.output or f"data/processed/dataset_v3_gen_{args.target}.jsonl"
    verified_output  = base_output.replace(".jsonl", "_verified.jsonl")
    plausible_output = base_output.replace(".jsonl", "_plausible.jsonl")
    summary_path     = base_output.replace(".jsonl", "_summary.json")

    # Protección contra sobreescritura
    if not args.overwrite and not args.dry_run:
        for p in [base_output, verified_output, plausible_output]:
            if os.path.exists(p):
                print(f"ERROR: {p} ya existe. Usa --overwrite para sobreescribir.")
                sys.exit(1)

    # API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY no encontrada.")
        sys.exit(1)

    client = Anthropic(api_key=api_key) if not args.dry_run else None

    # Cargar topics existentes (para evitar duplicados)
    existing_topics = set()
    if os.path.exists(args.dataset):
        with open(args.dataset, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        if rec.get("topic"):
                            existing_topics.add(rec["topic"])
                    except json.JSONDecodeError:
                        pass
        print(f"Dataset existente: {len(existing_topics)} topics cargados (no se repetirán)")
    else:
        print(f"AVISO: Dataset no encontrado en {args.dataset} — se generará sin exclusión de topics")

    # Agregar topics de los seeds
    existing_topics.update(e["topic"] for e in SEED_EXAMPLES)

    # Calcular batches necesarios
    num_batches = (args.target + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\nTarget: {args.target} ejemplos en {num_batches} batches de ~{BATCH_SIZE}")
    print(f"Modelo: {args.model}")
    print(f"Output: {base_output}")

    collected = []

    for batch_num in range(1, num_batches + 1):
        need = args.target - len(collected)
        if need <= 0:
            break

        current_batch = min(BATCH_SIZE, need)
        covered = existing_topics | {e["topic"] for e in collected}

        print(f"\n[Batch {batch_num}/{num_batches}] Generando {current_batch} ejemplos "
              f"({len(collected)}/{args.target} acumulados)...")

        prompt = build_user_prompt(SEED_EXAMPLES, covered, current_batch, batch_num, args.target)
        examples = call_claude(prompt, args.model, client, args.dry_run)
        print(f"  Recibidos: {len(examples)}")
        collected.extend(examples)

    # Deduplicar por topic
    before_dedup = len(collected)
    collected = dedup_by_topic(collected)
    print(f"\nDedup: {before_dedup} → {len(collected)} únicos")

    if args.dry_run:
        print("\n[DRY RUN] No se escribió ningún archivo.")
        return

    # Forzar campos obligatorios
    for ex in collected:
        ex.setdefault("source", "aiken_v3_curated")
        ex.setdefault("review_status", "PLAUSIBLE_NEEDS_CHECK")

    # Split por review_status
    verified  = [e for e in collected if e.get("review_status") == "VERIFIED_V3_ALIGNED"]
    plausible = [e for e in collected if e.get("review_status") == "PLAUSIBLE_NEEDS_CHECK"]

    # Escribir archivos
    os.makedirs(os.path.dirname(base_output) if os.path.dirname(base_output) else ".", exist_ok=True)

    with open(base_output, "w", encoding="utf-8") as f:
        for ex in collected:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with open(verified_output, "w", encoding="utf-8") as f:
        for ex in verified:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with open(plausible_output, "w", encoding="utf-8") as f:
        for ex in plausible:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\n{'='*52}")
    print(f"  Archivos generados:")
    print(f"  ALL      → {base_output} ({len(collected)} ejemplos)")
    print(f"  VERIFIED → {verified_output} ({len(verified)} ejemplos)")
    print(f"  PLAUSIBLE→ {plausible_output} ({len(plausible)} ejemplos)")
    print(f"{'='*52}")

    # Resumen en consola
    print_summary(collected, base_output)

    # Resumen JSON
    summary = {
        "target":         args.target,
        "generated":      len(collected),
        "model":          args.model,
        "dataset_ref":    args.dataset,
        "output_all":     base_output,
        "output_verified":  verified_output,
        "output_plausible": plausible_output,
        "by_lang":    dict(Counter(e.get("lang") for e in collected)),
        "by_status":  dict(Counter(e.get("review_status") for e in collected)),
        "by_topic":   dict(Counter(e.get("topic") for e in collected)),
        "verified_count":  len(verified),
        "plausible_count": len(plausible),
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  SUMMARY  → {summary_path}")


if __name__ == "__main__":
    main()
