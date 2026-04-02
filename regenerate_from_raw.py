#!/usr/bin/env python3
"""
regenerate_from_raw.py
Genera ejemplos de alta calidad desde los raw files, usando el contenido
real como contexto para Claude — sin alucinaciones de API.

Fuentes:
  - aiken_stdlib.json     → 458 funciones con firmas reales
  - aiken_docs.json       → 28 páginas de documentación oficial
  - aiken_design_patterns → 22 archivos de patrones de producción
  - cips.json             → CIPs técnicos filtrados (Ledger, Plutus, Tokens)

Uso:
    python3 regenerate_from_raw.py --dry-run
    python3 regenerate_from_raw.py --source stdlib
    python3 regenerate_from_raw.py --source all
    python3 regenerate_from_raw.py --source stdlib --n-per-chunk 6
    python3 regenerate_from_raw.py --source cips --n-per-chunk 5
"""

import os, sys, json, argparse, time
from collections import Counter
from anthropic import Anthropic

DEFAULT_MODEL  = "claude-sonnet-4-6"
MAX_TOKENS     = 8000
RAW_DIR        = "data/raw"
OUT_DIR        = "data/processed"

# ─────────────────────────────────────────────
# Tool schema
# ─────────────────────────────────────────────
TOOL_SCHEMA = {
    "name": "save_examples",
    "input_schema": {
        "type": "object",
        "properties": {
            "examples": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "lang":          {"type": "string", "enum": ["en","es"]},
                        "instruction":   {"type": "string"},
                        "input":         {"type": "string"},
                        "output":        {"type": "string"},
                        "source":        {"type": "string"},
                        "topic":         {"type": "string"},
                        "review_status": {"type": "string",
                            "enum": ["VERIFIED_V3_ALIGNED","PLAUSIBLE_NEEDS_CHECK"]},
                    },
                    "required": ["lang","instruction","input","output","source","topic","review_status"],
                }
            }
        },
        "required": ["examples"],
    }
}

# ─────────────────────────────────────────────
# Stdlib context (firmas reales)
# ─────────────────────────────────────────────
def load_stdlib_signatures() -> str:
    records = json.load(open(f"{RAW_DIR}/aiken_stdlib.json"))
    relevant = {
        "cardano.assets", "cardano.transaction",
        "aiken.collection.list", "aiken.interval",
        "aiken.option", "aiken.math",
    }
    lines = ["## VERIFIED AIKEN STDLIB SIGNATURES\n"]
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

# ─────────────────────────────────────────────
# System prompt base
# ─────────────────────────────────────────────
BASE_SYSTEM = """\
You are a senior Aiken v3 engineer generating fine-tuning examples from real documentation.

## VERIFIED TRANSACTION FIELDS (self: Transaction)
  self.inputs, self.reference_inputs, self.outputs, self.fee, self.mint,
  self.validity_range, self.extra_signatories, self.redeemers, self.datums, self.id

## VERIFIED HANDLER SIGNATURES
  spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
  mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool
  withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool

## VERIFIED IMPORTS (slash only)
  use cardano/assets
  use cardano/transaction
  use aiken/interval
  use aiken/collection/list
  use aiken/crypto.{VerificationKeyHash}

## NEVER USE
  transaction.signatories(tx)     — does not exist
  list.has_any(...)               — does not exist
  output.value.lovelace           — does not compile
  tx.validity_range               — use self.validity_range
  cardano.transaction.{...}       — dot imports are wrong

## CODE QUALITY
  - Final solution only — no // Correct, no // Fixed, no // TODO
  - Complete validator with all imports
  - Mark PLAUSIBLE_NEEDS_CHECK if using output.address or uncertain datum access
"""

# ─────────────────────────────────────────────
# Chunk builders por fuente
# ─────────────────────────────────────────────

def stdlib_chunks():
    """Una entrada por función stdlib con firma + descripción completa."""
    records = json.load(open(f"{RAW_DIR}/aiken_stdlib.json"))
    relevant_modules = {
        "cardano.assets", "cardano.transaction",
        "aiken.collection.list", "aiken.interval",
        "aiken.option", "aiken.math",
        "aiken.primitive.bytearray", "cardano.address",
    }
    chunks = []
    for r in records:
        if r.get("module") not in relevant_modules:
            continue
        if not r.get("signature") or not r.get("description"):
            continue
        # Saltar type aliases, opaque types, test files
        sig = r["signature"]
        if sig.startswith("pub opaque") or sig.startswith("//") or "test" in r.get("module",""):
            continue
        chunks.append({
            "source":   "aiken_stdlib",
            "topic":    f"aiken/{r['module']}.{r['name']}",
            "context":  f"Module: {r['module']}\nFunction: {sig}\n\nDocumentation:\n{r['description'][:1500]}",
            "prompt_hint": "stdlib function usage",
        })
    return chunks


def docs_chunks():
    """Una entrada por sección de aiken_docs con contenido real."""
    pages = json.load(open(f"{RAW_DIR}/aiken_docs.json"))
    # Saltar páginas de instalación/tooling
    skip_titles = {"installation", "getting started with aiken", "aikup"}
    chunks = []
    for page in pages:
        title = page.get("title","")
        if any(s in title.lower() for s in skip_titles):
            continue
        for section in page.get("sections", []):
            content = section.get("content","").strip()
            if len(content) < 100:
                continue
            # Incluir ejemplos de código si existen
            code = "\n".join(section.get("code_examples", []))
            full = content + (f"\n\nCode examples:\n{code}" if code else "")
            chunks.append({
                "source":   "aiken_docs",
                "topic":    f"aiken/{title[:40].lower().replace(' ','_')}",
                "context":  f"Page: {title}\nSection: {section.get('heading','')}\n\n{full[:2000]}",
                "prompt_hint": "language concept or pattern",
            })
    return chunks


def patterns_chunks():
    """Una entrada por archivo de design patterns."""
    files = json.load(open(f"{RAW_DIR}/aiken_design_patterns.json"))
    chunks = []
    for f in files:
        content = f.get("content","").strip()
        if len(content) < 100:
            continue
        chunks.append({
            "source":   "aiken_design_patterns",
            "topic":    f"aiken/patterns/{f['name'][:40].lower().replace(' ','_')}",
            "context":  f"File: {f['name']}\nURL: {f.get('source_url','')}\n\n{content[:2500]}",
            "prompt_hint": "production design pattern",
        })
    return chunks


def cips_chunks():
    """CIPs técnicamente relevantes (Ledger, Plutus, Tokens) con is_high_value."""
    cips = json.load(open(f"{RAW_DIR}/cips.json"))
    relevant_cats = {"Ledger", "Plutus", "Tokens", "Metadata"}
    chunks = []
    for c in cips:
        # Solo CIPs técnicos o high_value
        if c.get("category") not in relevant_cats and not c.get("is_high_value"):
            continue
        # Saltar CIPs ya eliminados (CIP-0001 a 0015)
        cip_id = c.get("id","")
        try:
            num = int(cip_id.replace("CIP-","").lstrip("0") or "0")
            if num <= 15:
                continue
        except:
            pass
        content = c.get("content","").strip()
        if len(content) < 200:
            continue
        chunks.append({
            "source":   "cips",
            "topic":    f"cardano/cip/{cip_id.lower()}",
            "context":  f"CIP: {cip_id}\nTitle: {c.get('title','')}\nCategory: {c.get('category','')}\nStatus: {c.get('status','')}\n\n{content[:2500]}",
            "prompt_hint": "CIP standard or technical specification",
        })
    return chunks


# ─────────────────────────────────────────────
# Prompt por chunk
# ─────────────────────────────────────────────
def build_prompt(chunk: dict, n: int, stdlib_sigs: str) -> str:
    return f"""\
## SOURCE CONTENT (use this as ground truth — do not invent APIs)

{chunk['context']}

---

{stdlib_sigs}

---

## TASK

Generate exactly {n} fine-tuning examples based ONLY on the source content above.

Guidelines:
- instruction: a realistic question a Cardano developer would ask
- input: optional constraints or context (can be empty string "")
- output: correct answer using ONLY APIs shown in source or stdlib signatures
- Mix EN and ES (~60/40)
- Vary task types: code generation, explanation, refactoring, security
- source = "{chunk['source']}"
- topic = "{chunk['topic']}"
- Use VERIFIED_V3_ALIGNED if all APIs are in the stdlib signatures above
- Use PLAUSIBLE_NEEDS_CHECK if any API or pattern is not explicitly listed

Call save_examples with exactly {n} examples.
"""


# ─────────────────────────────────────────────
# Claude call
# ─────────────────────────────────────────────
def call_claude(prompt, system, model, client, dry_run=False):
    if dry_run:
        return []
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
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
    parser.add_argument("--source", default="all",
        choices=["all","stdlib","docs","patterns","cips"],
        help="Qué fuente procesar")
    parser.add_argument("--n-per-chunk", type=int, default=5,
        help="Ejemplos a generar por chunk (default: 5)")
    parser.add_argument("--model",   default=DEFAULT_MODEL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit",   type=int, default=0,
        help="Limitar a N chunks (0 = todos, útil para pruebas)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    # Output path por fuente
    suffix = args.source if args.source != "all" else "all_sources"
    output_path = f"{OUT_DIR}/regen_{suffix}_n{args.n_per_chunk}.jsonl"

    if not args.overwrite and not args.dry_run and os.path.exists(output_path):
        print(f"ERROR: {output_path} ya existe. Usa --overwrite.")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY no encontrada.")
        sys.exit(1)

    client = Anthropic(api_key=api_key) if not args.dry_run else None

    # Cargar firmas stdlib (contexto de verdad para todos los prompts)
    print("Cargando firmas stdlib...")
    stdlib_sigs = load_stdlib_signatures()
    system_prompt = BASE_SYSTEM + "\n\n" + stdlib_sigs

    # Seleccionar chunks según --source
    source_map = {
        "stdlib":   stdlib_chunks,
        "docs":     docs_chunks,
        "patterns": patterns_chunks,
        "cips":     cips_chunks,
    }

    if args.source == "all":
        chunks = []
        for fn in source_map.values():
            chunks.extend(fn())
    else:
        chunks = source_map[args.source]()

    if args.limit > 0:
        chunks = chunks[:args.limit]

    total_expected = len(chunks) * args.n_per_chunk
    print(f"Chunks: {len(chunks)} | N/chunk: {args.n_per_chunk} | Expected: ~{total_expected} ejemplos")
    print(f"Modelo: {args.model} | Output: {output_path}")

    if args.dry_run:
        print("\n[DRY RUN] Muestra de chunks:")
        for c in chunks[:3]:
            print(f"  source={c['source']} topic={c['topic']}")
            print(f"  context preview: {c['context'][:100]}...")
        print(f"\n[DRY RUN] Estimado: ~{total_expected} ejemplos, {len(chunks)} llamadas API.")
        return

    # Procesar
    all_examples = []
    source_counts = Counter()
    failed = 0

    os.makedirs(OUT_DIR, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as out_f:
        for i, chunk in enumerate(chunks):
            prompt = build_prompt(chunk, args.n_per_chunk, stdlib_sigs)
            examples = call_claude(prompt, system_prompt, args.model, client)

            if not examples:
                failed += 1
                print(f"  [{i+1}/{len(chunks)}] {chunk['topic'][:50]} — 0 recibidos ⚠️")
                continue

            # Forzar source y topic desde el chunk (no confiar en Claude)
            for ex in examples:
                if not isinstance(ex, dict):
                    continue
                ex["source"] = chunk["source"]
                ex["topic"]  = chunk["topic"]
                ex.setdefault("review_status", "PLAUSIBLE_NEEDS_CHECK")
                out_f.write(json.dumps(ex, ensure_ascii=False) + "\n")

            all_examples.extend(examples)
            source_counts[chunk["source"]] += len(examples)

            print(f"  [{i+1}/{len(chunks)}] {chunk['topic'][:55]} → {len(examples)} ejemplos")

            # Rate limit: pequeña pausa cada 10 chunks
            if (i + 1) % 10 == 0:
                time.sleep(1)

    # Resumen
    print(f"\n{'='*55}")
    print(f"  Total generados : {len(all_examples)}")
    print(f"  Chunks fallidos : {failed}")
    for src, cnt in source_counts.most_common():
        print(f"  {src}: {cnt}")
    langs = Counter(e.get("lang","?") for e in all_examples)
    print(f"  Idiomas: {dict(langs)}")
    print(f"{'='*55}")

    summary = {
        "total": len(all_examples),
        "failed_chunks": failed,
        "n_per_chunk": args.n_per_chunk,
        "source": args.source,
        "by_source": dict(source_counts),
        "by_lang": dict(Counter(e.get("lang","?") for e in all_examples)),
        "output": output_path,
    }
    summary_path = output_path.replace(".jsonl", "_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n  Output  : {output_path}")
    print(f"  Summary : {summary_path}")
    print(f"\nPara agregar al dataset:")
    print(f"  cat {output_path} >> data/processed/dataset_v10_train.jsonl")
    print(f"  wc -l data/processed/dataset_v10_train.jsonl")


if __name__ == "__main__":
    main()
