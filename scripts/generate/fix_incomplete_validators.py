#!/usr/bin/env python3
"""
fix_incomplete_validators.py
Identifica ejemplos en dataset_v13 donde la instrucción pide código
pero el output no tiene handler completo, y regenera los outputs.

Criterio de "incompleto":
  - instruction contiene frase imperativa de código (write a validator, etc.)
  - output NO contiene fn spend( ni fn mint( ni fn withdraw(
  - source NO es correction_set, cips, ni hydra_docs (son explicativos por naturaleza)

Estrategia:
  - Agrupa los incompletos en batches de BATCH_SIZE instrucciones
  - Por cada batch: envía todas las instrucciones a Claude y pide
    el output completo para cada una
  - Preserva lang, source, topic, input del original — solo regenera output
  - Guarda exitosos en validators_fixed.jsonl
  - Guarda descartados en validators_fixed_skipped.jsonl (para purge posterior)

Uso:
    python3 fix_incomplete_validators.py --dry-run
    python3 fix_incomplete_validators.py
    python3 fix_incomplete_validators.py --limit 30   # probar con 30 primeros
    python3 fix_incomplete_validators.py --overwrite
"""

import os, sys, json, re, argparse
from collections import Counter
from anthropic import Anthropic

DEFAULT_MODEL  = "claude-sonnet-4-6"
MAX_TOKENS     = 16000
BATCH_SIZE     = 4    # conservador — cada validator puede ser largo
DATASET_PATH   = "data/processed/dataset_v13_train.jsonl"
STDLIB_PATH    = "data/raw/aiken_stdlib.json"
PATTERNS_PATH  = "data/raw/aiken_design_patterns.json"
OUTPUT_PATH    = "data/processed/validators_fixed.jsonl"

# Sources que son inherentemente explicativos — no regenerar como validators
EXPLANATION_SOURCES = {"correction_set", "cips", "hydra_docs"}

# Regex estricto: solo cuando la instruccion menciona validator/contract/handler/spend/mint/withdraw
# Evita falsos positivos como "show a practical example of bls12_381_add" o "write a function for option.map"
CODE_PHRASE = re.compile(
    r'\b(write|implement|create|build|generate|make|develop|construct|design)\b'
    r'(?:\s+\w+){0,5}\s+'
    r'\b(validator|contract|spend|mint|withdraw|handler)\b'
    r'|'
    r'\b(spend|mint|withdraw)\s+(validator|handler|function|contract)\b'
    r'|'
    r'\b(escribe|implementa|crea|construye|genera|diseña|desarrolla)\b'
    r'(?:\s+\w+){0,5}\s+'
    r'\b(validador|validator|contrato|script)\b',
    re.IGNORECASE,
)

# Instrucciones conceptuales/explicativas — aunque mencionen "validator", su output ideal es prosa
EXPLAIN_PHRASE = re.compile(
    r'^\s*(explain|how\s+does|how\s+do(?:es)?\s+(?!i\b|you\b|we\b)|what\s+is|what\s+are|'
    r'why\s+does|why\s+is|describe|when\s+should|what\s+does|how\s+are|'
    r'¿?(cómo\s+funciona|qué\s+es|explica|cuándo\s+debo|describe|por\s+qué))',
    re.IGNORECASE,
)

TOOL_SCHEMA = {
    "name": "save_fixed_validators",
    "description": "Save regenerated complete Aiken v3 validators. Return items IN THE SAME ORDER as the numbered instructions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fixed": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "output":        {"type": "string"},
                        "review_status": {
                            "type": "string",
                            "enum": ["VERIFIED_V3_ALIGNED", "PLAUSIBLE_NEEDS_CHECK"],
                        },
                    },
                    "required": ["output", "review_status"],
                },
            }
        },
        "required": ["fixed"],
    },
}


# ─────────────────────────────────────────────────────
# Filtrado de incompletos
# ─────────────────────────────────────────────────────

def has_complete_handler(output: str) -> bool:
    """Requiere que spend/mint/withdraw (con o sin fn keyword) aparezca DENTRO de un bloque validator."""
    m = re.search(r'\bvalidator\b[^{]*\{', output)
    if not m:
        return False
    body = output[m.start():]
    # Accept both 'fn spend(' and bare 'spend(' inside validator block
    return bool(re.search(r'\b(?:fn\s+)?(spend|mint|withdraw)\s*\(', body))


def wants_code(instruction: str) -> bool:
    return bool(CODE_PHRASE.search(instruction))


def find_incomplete(records):
    incomplete = []
    for r in records:
        if (wants_code(r.get("instruction", "")) and
                not EXPLAIN_PHRASE.search(r.get("instruction", "")) and
                not has_complete_handler(r.get("output", "")) and
                r.get("source") not in EXPLANATION_SOURCES):
            incomplete.append(r)
    return incomplete


# ─────────────────────────────────────────────────────
# Carga de contexto real
# ─────────────────────────────────────────────────────

def load_stdlib(path):
    if not os.path.exists(path):
        print(f"ERROR: no existe {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    relevant = {
        "cardano.assets", "cardano.transaction",
        "aiken.collection.list", "aiken.interval",
        "cardano.address", "aiken.crypto",
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
    if not os.path.exists(path):
        print(f"ERROR: no existe {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        files = json.load(f)
    lines = ["## REAL PRODUCTION CODE EXAMPLES\n"]
    extracted = 0
    for pf in files:
        if extracted >= 3:
            break
        content = pf.get("content", "")
        in_block = False
        block = []
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
                    extracted += 1
                    break
            elif in_block:
                block.append(line)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────

SYSTEM_TEMPLATE = """\
You are a senior Aiken v3 engineer. For each instruction given, produce
a COMPLETE, COMPILABLE Aiken v3 validator that fully answers the question.

STDLIB_PLACEHOLDER

PATTERNS_PLACEHOLDER

## MANDATORY STRUCTURE for every output:

use cardano/assets
use cardano/transaction.{OutputReference, Transaction}
use aiken/collection/list

validator contract_name {
  fn spend(datum: Option<MyDatum>, redeemer: MyRedeemer, own_ref: OutputReference, self: Transaction) -> Bool {
    // real logic
  }
}

## VERIFIED HANDLER SIGNATURES (use fn keyword, handlers go INSIDE validator block):
  spend   : fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  mint    : fn mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
  withdraw: fn withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool

NOTE: Always use the fn keyword before spend/mint/withdraw inside the validator block.

## CORRECT API PATTERNS:
  ADA check : assets.lovelace_of(output.value) >= amount
  Signature : list.has(self.extra_signatories, key)
  N-of-M    : list.count(admins, fn(k) { list.has(self.extra_signatories, k) }) >= n
  NFT       : assets.has_nft(output.value, policy_id, asset_name)
  Time after: interval.is_entirely_after(self.validity_range, deadline)
  List all  : list.all(self.outputs, fn(o) { ... })

## ABSOLUTE PROHIBITIONS:
  NEVER: pub fn outside validator block
  NEVER: self.signatures — use self.extra_signatories
  NEVER: self.time — use self.validity_range
  NEVER: self.outputs.all() — use list.all(self.outputs, fn)
  NEVER: output.assets.ada — use assets.lovelace_of(output.value)
  NEVER: output.value >= N — use assets.lovelace_of(output.value) >= N
  NEVER: MultiSignature, RedeemData, option.or_try
  NEVER: fn body with only True
  NEVER: markdown fences in output field (no ```)
  NEVER: placeholder comments like // implement here, // TODO, // completar

## OUTPUT FORMAT:
  - output field = ONLY raw Aiken code, no prose, no fences
  - Copy the instruction text EXACTLY into the instruction field
  - Use VERIFIED_V3_ALIGNED if all APIs are in stdlib above, else PLAUSIBLE_NEEDS_CHECK
"""


# ─────────────────────────────────────────────────────
# Quality check — cubre los 12 patrones prohibidos
# ─────────────────────────────────────────────────────

def has_bare_pub_fn(output: str) -> bool:
    first_validator = output.find("validator ")
    first_pub_fn    = output.find("pub fn ")
    if first_pub_fn == -1:
        return False
    return first_validator == -1 or first_pub_fn < first_validator


def quality_check(examples):
    fn_spend         = sum(1 for e in examples if "fn spend(" in e.get("output",""))
    fn_mint          = sum(1 for e in examples if "fn mint(" in e.get("output",""))
    fn_with          = sum(1 for e in examples if "fn withdraw(" in e.get("output",""))
    validator_block  = sum(1 for e in examples if "validator " in e.get("output",""))
    own_ref          = sum(1 for e in examples if "own_ref: OutputReference" in e.get("output",""))
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
                           if re.search(
                               r'//\s*(TODO|FIXME|implement here|implementar|completar|placeholder|add logic|agregar)',
                               e.get("output",""), re.IGNORECASE))
    bad_fence        = sum(1 for e in examples if e.get("output","").strip().startswith("```"))
    bad_trivial_true = sum(1 for e in examples
                           if re.search(r'fn \w+\([^)]*\)\s*(->\s*Bool\s*)?\{?\s*True\s*\}?',
                                        e.get("output",""))
                           and len(e.get("output","").split("\n")) < 8)
    total_bad = (bad_sigs + bad_time + bad_chain + bad_ada + bad_pub_fn +
                 bad_multisig + bad_redeemdata + bad_or_try + bad_value_cmp +
                 bad_placeholder + bad_fence + bad_trivial_true)
    return {
        "fn_spend": fn_spend, "fn_mint": fn_mint, "fn_withdraw": fn_with,
        "validator_block": validator_block, "own_ref": own_ref,
        "bad_signatures": bad_sigs, "bad_self_time": bad_time,
        "bad_method_chain": bad_chain, "bad_ada": bad_ada, "bad_pub_fn": bad_pub_fn,
        "bad_multisig": bad_multisig, "bad_redeemdata": bad_redeemdata,
        "bad_or_try": bad_or_try, "bad_value_compare": bad_value_cmp,
        "bad_placeholder": bad_placeholder, "bad_fence": bad_fence,
        "bad_trivial_true": bad_trivial_true, "total_bad": total_bad,
    }


def strip_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


# ─────────────────────────────────────────────────────
# Claude call
# ─────────────────────────────────────────────────────

def call_claude(batch, system, model, client):
    numbered = "\n\n".join(
        f"[{i+1}] ({r.get('lang','en')}) {r['instruction']}"
        + (f"\n  Context: {r['input'][:200]}" if r.get("input","").strip() else "")
        for i, r in enumerate(batch)
    )
    prompt = (
        f"For each of the {len(batch)} instructions below, produce a complete "
        f"compilable Aiken v3 validator.\n"
        f"Return exactly {len(batch)} items in 'fixed', in the SAME ORDER.\n"
        f"Copy each instruction text EXACTLY into the instruction field.\n\n"
        f"INSTRUCTIONS:\n{numbered}\n\n"
        f"Call save_fixed_validators with {len(batch)} items."
    )
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "save_fixed_validators"},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "max_tokens":
        print("  WARNING: respuesta truncada por max_tokens — reducir BATCH_SIZE")
    for block in response.content:
        if block.type == "tool_use" and block.name == "save_fixed_validators":
            return [e for e in block.input.get("fixed", []) if isinstance(e, dict)]
    return []


# ─────────────────────────────────────────────────────
# Match results back to originals — positional (by order)
# Claude returns items in same order as numbered instructions.
# If counts differ, drop the whole batch (safer than mismatching).
# ─────────────────────────────────────────────────────

def match_fixed_to_originals(originals, fixed_list):
    """
    Empareja por posición: originals[i] ↔ fixed_list[i].
    Si los conteos no coinciden, descarta todo el batch.
    Returns: (matched_records, unmatched_originals)
    """
    if len(fixed_list) != len(originals):
        print(f"  WARNING: conteo no coincide ({len(fixed_list)} recibidos, {len(originals)} esperados) — batch descartado")
        return [], originals

    matched = []
    for orig, fix in zip(originals, fixed_list):
        merged = dict(orig)
        merged["output"]        = strip_fences(fix.get("output", ""))
        merged["review_status"] = fix.get("review_status", "PLAUSIBLE_NEEDS_CHECK")
        matched.append(merged)
    return matched, []


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset",    default=DATASET_PATH)
    parser.add_argument("--output",     default=OUTPUT_PATH)
    parser.add_argument("--model",      default=DEFAULT_MODEL)
    parser.add_argument("--stdlib",     default=STDLIB_PATH)
    parser.add_argument("--patterns",   default=PATTERNS_PATH)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--limit",      type=int, default=0,
                        help="Limitar a N incompletos (0 = todos)")
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--overwrite",  action="store_true")
    args = parser.parse_args()

    if not args.overwrite and not args.dry_run and os.path.exists(args.output):
        print(f"ERROR: {args.output} ya existe. Usa --overwrite.")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY no encontrada.")
        sys.exit(1)

    # Cargar dataset
    if not os.path.exists(args.dataset):
        print(f"ERROR: dataset no encontrado: {args.dataset}")
        sys.exit(1)
    print(f"Cargando {args.dataset}...")
    records = []
    with open(args.dataset, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if isinstance(r, dict):
                    records.append(r)
            except json.JSONDecodeError as e:
                print(f"  [WARN] línea {i}: {e}")
    print(f"  Cargados: {len(records)} ejemplos")

    # Identificar incompletos
    all_incomplete = find_incomplete(records)
    total_incomplete = len(all_incomplete)

    src_counts = Counter(r.get("source","?") for r in all_incomplete)
    print(f"\nIncompletos encontrados: {total_incomplete} / {len(records)} ({100*total_incomplete/max(1,len(records)):.1f}%)")
    print("  Por source (solo sources regenerables):")
    for src, cnt in src_counts.most_common():
        print(f"    {src:35s}: {cnt}")

    incomplete = all_incomplete[:args.limit] if args.limit > 0 else all_incomplete
    if args.limit > 0:
        print(f"  Procesando: {len(incomplete)} (--limit {args.limit})")

    if args.dry_run:
        batches_count = (len(incomplete) + args.batch_size - 1) // args.batch_size
        print(f"\n[DRY RUN] {len(incomplete)} ejemplos → {batches_count} batches de {args.batch_size}")
        print("\nMuestra de instrucciones incompletas:")
        for r in incomplete[:5]:
            print(f"  [{r.get('source')}] {r['instruction'][:80]}")
            print(f"    output preview: {r.get('output','')[:60]}...")
        return

    # Cargar contexto
    print("\nCargando fuentes reales...")
    stdlib_text   = load_stdlib(args.stdlib)
    patterns_text = load_pattern_code(args.patterns)
    system = (SYSTEM_TEMPLATE
              .replace("STDLIB_PLACEHOLDER", stdlib_text)
              .replace("PATTERNS_PLACEHOLDER", patterns_text))
    print(f"System prompt: {len(system)} chars")

    client = Anthropic(api_key=api_key)
    all_fixed = []
    all_skipped = []  # originales que no pasaron QC — para purge posterior
    batches = [incomplete[i:i+args.batch_size]
               for i in range(0, len(incomplete), args.batch_size)]

    skipped_path = os.path.splitext(args.output)[0] + "_skipped.jsonl"
    parent = os.path.dirname(args.output)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as out_f, \
         open(skipped_path, "w", encoding="utf-8") as skip_f:

        for bi, batch in enumerate(batches):
            print(f"\n[batch {bi+1}/{len(batches)}] {len(batch)} instrucciones...")
            fixed_list = call_claude(batch, system, args.model, client)
            print(f"  Recibidos: {len(fixed_list)}")

            if len(fixed_list) == 0:
                print(f"  ERROR: batch {bi+1} devolvió 0 resultados.")
                print(f"  Guardando progreso hasta aquí y abortando.")
                break  # flush files via context manager, then exit below

            if len(fixed_list) < len(batch) * 0.5:
                print(f"  WARNING: esperados {len(batch)}, recibidos {len(fixed_list)} (<50%)")

            # Match con originales — sin fallback posicional
            merged, unmatched_orig = match_fixed_to_originals(batch, fixed_list)

            # Originales sin match → sidecar
            for orig in unmatched_orig:
                orig["fix_status"] = "unmatched"
                skip_f.write(json.dumps(orig, ensure_ascii=False) + "\n")
                all_skipped.append(orig)

            # Quality check por ejemplo — filtrar malos
            good = []
            for ex in merged:
                out = ex.get("output", "")
                if not has_complete_handler(out):
                    ex["fix_status"] = "no_handler"
                    # Debug: show why — does it have 'validator' at all?
                    has_v = "validator" in out
                    has_fn = bool(re.search(r'\bfn\s+(spend|mint|withdraw)', out))
                    print(f"  DBG no_handler: has_validator={has_v} has_fn={has_fn} preview={out[:80].replace(chr(10),' ')!r}")
                    skip_f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                    all_skipped.append(ex)
                    continue
                qc = quality_check([ex])
                if qc["total_bad"] > 0:
                    bad_keys = [k for k in ("bad_signatures","bad_self_time","bad_method_chain",
                                            "bad_ada","bad_pub_fn","bad_multisig","bad_redeemdata",
                                            "bad_or_try","bad_value_compare","bad_placeholder",
                                            "bad_fence","bad_trivial_true") if qc[k] > 0]
                    ex["fix_status"] = "hallucination"
                    print(f"  DBG hallucination: {bad_keys} preview={out[:60].replace(chr(10),' ')!r}")
                    skip_f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                    all_skipped.append(ex)
                    continue
                good.append(ex)

            dropped_batch = len(merged) - len(good) + len(unmatched_orig)
            if dropped_batch > 0:
                print(f"  DROPPED {dropped_batch} (sin handler, hallucination, o sin match)")

            for ex in good:
                out_f.write(json.dumps(ex, ensure_ascii=False) + "\n")

            all_fixed.extend(good)
            print(f"  Escritos: {len(good)}")

    # Si abortamos por batch vacío, salir con error después de flush
    if len(batches) > 0 and len(all_fixed) == 0 and len(all_skipped) == 0:
        sys.exit(1)

    # Quality check global (solo conteos, ya filtrado individualmente)
    qc = quality_check(all_fixed)
    n = len(all_fixed)

    print(f"\n{'='*55}")
    print(f"  Procesados          : {len(incomplete)}")
    print(f"  Escritos (buenos)   : {n}")
    print(f"  Descartados         : {len(all_skipped)}")
    print(f"\n  HANDLER COVERAGE:")
    print(f"  fn spend(   : {qc['fn_spend']} ({100*qc['fn_spend']/max(1,n):.1f}%)")
    print(f"  fn mint(    : {qc['fn_mint']} ({100*qc['fn_mint']/max(1,n):.1f}%)")
    print(f"  fn withdraw(: {qc['fn_withdraw']} ({100*qc['fn_withdraw']/max(1,n):.1f}%)")
    print(f"  validator {{}}  : {qc['validator_block']}")
    print(f"  own_ref     : {qc['own_ref']}")
    print(f"\n  HALLUCINATIONS (debe ser 0 — ya filtrado):")
    for key in ("bad_signatures","bad_self_time","bad_method_chain","bad_ada",
                "bad_pub_fn","bad_multisig","bad_redeemdata","bad_or_try",
                "bad_value_compare","bad_placeholder","bad_fence","bad_trivial_true"):
        v = qc[key]
        flag = "✅" if v == 0 else "❌"
        print(f"    {flag} {key:30s}: {v}")
    print(f"  TOTAL BAD: {qc['total_bad']}")
    print(f"{'='*55}")

    langs = Counter(e.get("lang","?") for e in all_fixed)
    summary = {
        "total_incomplete_found": total_incomplete,
        "total_incomplete_processed": len(incomplete),
        "total_fixed": n,
        "total_skipped": len(all_skipped),
        "by_lang": dict(langs),
        "quality": qc,
    }
    summary_path = os.path.splitext(args.output)[0] + "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n  Output   : {args.output}")
    print(f"  Skipped  : {skipped_path}  ({len(all_skipped)} records — usar para purge)")
    print(f"  Summary  : {summary_path}")
    print(f"\nPara construir dataset v14:")
    print(f"  Paso 1 — purgar originales incompletos de v13 usando skipped list:")
    print(f"    python3 purge_v9.py --blacklist {skipped_path} \\")
    print(f"      --input {args.dataset} --output data/processed/dataset_v13_purged.jsonl")
    print(f"  Paso 2 — agregar fixed + validators_v2:")
    print(f"    cat data/processed/dataset_v13_purged.jsonl \\")
    print(f"        {args.output} \\")
    print(f"        data/processed/validators_v2.jsonl \\")
    print(f"        > data/processed/dataset_v14_train.jsonl")


if __name__ == "__main__":
    main()
