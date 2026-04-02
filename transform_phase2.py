"""
Fase 2 - Transformación a pares Q&A
Lee los archivos raw de data/raw/ y genera ejemplos de entrenamiento
en formato ShareGPT con la Claude API (EN + ES).

Salida: data/processed/dataset.jsonl
Checkpoint: data/processed/checkpoint.json (permite resumir si se interrumpe)

Uso:
  python3 transform_phase2.py                    # procesa todo
  python3 transform_phase2.py --source stdlib    # solo un source
  python3 transform_phase2.py --dry-run          # muestra prompts sin llamar API
"""

import json
import os
import re
import sys
import time
import argparse
import hashlib
from pathlib import Path
from typing import Optional
import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY:
    raise SystemExit("ERROR: Setea ANTHROPIC_API_KEY antes de correr este script.")

# Usar haiku para bulk (rápido y barato); sonnet para patrones complejos
MODEL_BULK = "claude-haiku-4-5-20251001"
MODEL_COMPLEX = "claude-sonnet-4-6"

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/processed")
DATASET_FILE = OUT_DIR / "dataset.jsonl"
CHECKPOINT_FILE = OUT_DIR / "checkpoint.json"

client = anthropic.Anthropic(api_key=API_KEY)

# ---------------------------------------------------------------------------
# Checkpoint (para resumir si se interrumpe)
# ---------------------------------------------------------------------------

def load_checkpoint() -> set:
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text())
        return set(data.get("done", []))
    return set()

def save_checkpoint(done: set):
    CHECKPOINT_FILE.write_text(json.dumps({"done": list(done)}, indent=2))

def item_id(source: str, key: str) -> str:
    return hashlib.md5(f"{source}:{key}".encode()).hexdigest()[:12]

# ---------------------------------------------------------------------------
# Escritura de ejemplos
# ---------------------------------------------------------------------------

def append_examples(examples: list[dict]):
    with open(DATASET_FILE, "a", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------------------
# Llamada a Claude
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert in Cardano blockchain development with deep knowledge of:
- Aiken smart contract language (syntax, stdlib, validators, patterns)
- Hydra Head protocol (layer-2 scaling, state channels, on-chain/off-chain)
- Cardano Improvement Proposals (CIPs) and standards
- Plutus and eUTxO model

Your task: given a piece of documentation or source code, generate high-quality training examples
for a language model. Each example must be realistic, accurate, and useful for a developer.

Output ONLY a JSON array of objects. Each object has:
{
  "lang": "en" or "es",
  "instruction": "a clear developer question or task",
  "input": "optional context (code snippet, error, etc.) — empty string if none",
  "output": "accurate, helpful answer. Include code when relevant."
}

Rules:
- Generate exactly the number of examples requested
- Mix question types: concept explanation, code usage, code→explanation, debug, comparison
- For ES examples: write the instruction and output fully in Spanish, but keep code/identifiers in English
- Keep outputs concise but complete (100-400 words)
- Never invent APIs or functions that don't exist in the source material"""


TOOL_SCHEMA = {
    "name": "save_examples",
    "description": "Save the generated training examples",
    "input_schema": {
        "type": "object",
        "properties": {
            "examples": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "lang":        {"type": "string", "enum": ["en", "es"]},
                        "instruction": {"type": "string"},
                        "input":       {"type": "string"},
                        "output":      {"type": "string"},
                    },
                    "required": ["lang", "instruction", "input", "output"],
                }
            }
        },
        "required": ["examples"],
    }
}


def call_claude(prompt: str, n_examples: int, use_complex: bool = False, dry_run: bool = False) -> list[dict]:
    model = MODEL_COMPLEX if use_complex else MODEL_BULK

    if dry_run:
        print(f"\n--- DRY RUN ({model}) ---")
        print(prompt[:300] + "...")
        return []

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=[TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "save_examples"},
                messages=[{"role": "user", "content": prompt}],
            )
            # tool_use garantiza JSON válido — el input ya viene parseado
            for block in response.content:
                if block.type == "tool_use" and block.name == "save_examples":
                    examples = block.input.get("examples", [])
                    return examples
            return []

        except anthropic.RateLimitError:
            print(f"  Rate limit, esperando 60s...")
            time.sleep(60)
        except Exception as e:
            print(f"  Error API (intento {attempt+1}): {e}")
            time.sleep(5)

    return []

# ---------------------------------------------------------------------------
# Templates de prompts por tipo de fuente
# ---------------------------------------------------------------------------

def prompt_stdlib(record: dict) -> tuple[str, int, bool]:
    ctx = f"""Module: {record['module']}
Name: {record['name']}
Type: {record['type']}
Signature: {record['signature']}
Description: {record['description'][:800]}
"""
    if record.get('source_code'):
        ctx += f"\nSource code:\n{record['source_code'][:600]}"

    prompt = f"""Source: Aiken standard library
{ctx}

Generate 3 training examples about this stdlib item:
- 1 in English: how to use it with a practical example
- 1 in English: explain what it does and when to use it
- 1 in Spanish: pregunta práctica sobre su uso

Return a JSON array with exactly 3 objects."""
    return prompt, 3, False


def prompt_aiken_docs(page: dict) -> tuple[str, int, bool]:
    # Tomar las secciones más sustanciales
    content_parts = []
    for section in page.get("sections", [])[:6]:
        heading = section.get("heading", "")
        content = section.get("content", "")[:400]
        codes = section.get("code_examples", [])
        code_str = ""
        if codes:
            first_code = codes[0] if isinstance(codes[0], str) else codes[0].get("code", "")
            code_str = f"\n```\n{first_code[:300]}\n```"
        if content or code_str:
            content_parts.append(f"### {heading}\n{content}{code_str}")

    full_content = "\n\n".join(content_parts)[:2000]

    prompt = f"""Source: Aiken language documentation
Page: {page['title']}
URL: {page['url']}

Content:
{full_content}

Generate 4 training examples:
- 2 in English: one conceptual, one practical/code-focused
- 2 in Spanish: una conceptual, una práctica

Return a JSON array with exactly 4 objects."""
    return prompt, 4, False


def prompt_hydra_docs(page: dict) -> tuple[str, int, bool]:
    content_parts = []
    for section in page.get("sections", [])[:5]:
        heading = section.get("heading", "")
        content = section.get("content", "")[:500]
        codes = section.get("code_examples", [])
        code_str = ""
        if codes:
            first = codes[0]
            code_text = first.get("code", "") if isinstance(first, dict) else first
            code_str = f"\n```\n{code_text[:300]}\n```"
        if content:
            content_parts.append(f"### {heading}\n{content}{code_str}")

    full_content = "\n\n".join(content_parts)[:2000]
    breadcrumb = " > ".join(page.get("breadcrumb", []))

    prompt = f"""Source: Hydra Head Protocol documentation
Section: {breadcrumb or page['title']}
Page: {page['title']}

Content:
{full_content}

Generate 4 training examples about Hydra/Cardano layer-2:
- 2 in English: one about concepts, one operational/practical
- 2 in Spanish

Return a JSON array with exactly 4 objects."""
    return prompt, 4, False


def prompt_cip(cip: dict) -> tuple[str, int, bool]:
    content = cip.get("content", "")[:2500]
    is_hv = cip.get("is_high_value", False)
    n = 5 if is_hv else 3

    prompt = f"""Source: Cardano Improvement Proposal
CIP ID: {cip['id']}
Title: {cip['title']}
Status: {cip['status']}
Category: {cip.get('category', 'N/A')}

Content (excerpt):
{content}

Generate {n} training examples about this CIP:
- {"3" if is_hv else "2"} in English: summary, technical details, and {"developer implications" if is_hv else "usage"}
- {"2" if is_hv else "1"} in Spanish

Return a JSON array with exactly {n} objects."""
    return prompt, n, is_hv


def prompt_design_pattern(record: dict) -> tuple[str, int, bool]:
    content = record.get("content", "")[:2500]
    name = record.get("name", "")
    rtype = record.get("type", "")

    if rtype == "aiken_source":
        prompt = f"""Source: Aiken Design Patterns (Anastasia Labs)
File: {name}

Source code:
```aiken
{content[:2000]}
```

Generate 4 training examples:
- 2 in English: explain what this code does, and how/when to use this pattern
- 2 in Spanish: explica el patrón y su aplicación práctica

Return a JSON array with exactly 4 objects."""
    else:
        prompt = f"""Source: Aiken Design Patterns documentation
File: {name}

Content:
{content[:2000]}

Generate 4 training examples:
- 2 in English: conceptual and practical
- 2 in Spanish

Return a JSON array with exactly 4 objects."""
    return prompt, 4, True  # use complex model for code


def prompt_hydra_code(record: dict) -> tuple[str, int, bool]:
    content = record.get("content", "")
    path = record.get("path", "")
    ext = record.get("extension", "")

    if ext == ".md":
        prompt = f"""Source: Hydra repository documentation
File: {path}

Content:
{content[:2000]}

Generate 3 training examples:
- 2 in English
- 1 in Spanish

Return a JSON array with exactly 3 objects."""
        return prompt, 3, False
    else:
        # Código Haskell — solo si tiene comentarios significativos
        if len(content) < 200:
            return "", 0, False
        prompt = f"""Source: Hydra Plutus implementation (Haskell)
File: {path}

Code excerpt:
```haskell
{content[:2000]}
```

Generate 2 training examples for Cardano developers who want to understand Hydra internals:
- 1 in English: what this code implements and its role in Hydra
- 1 in Spanish

Return a JSON array with exactly 2 objects."""
        return prompt, 2, True

# ---------------------------------------------------------------------------
# Procesadores por fuente
# ---------------------------------------------------------------------------

def process_stdlib(done: set, dry_run: bool) -> int:
    print("\n=== [1/6] Aiken stdlib ===")
    data = json.loads((RAW_DIR / "aiken_stdlib.json").read_text())
    count = 0

    # Solo items con descripción útil
    items = [r for r in data if r.get("description") and len(r["description"]) > 30]
    print(f"  {len(items)} items con descripción")

    for record in items:
        uid = item_id("stdlib", record["module"] + record["name"])
        if uid in done:
            continue

        prompt, n, complex_ = prompt_stdlib(record)
        examples = call_claude(prompt, n, complex_, dry_run)

        for ex in examples:
            ex["source"] = "aiken_stdlib"
            ex["topic"] = f"aiken/{record['module']}"

        if examples:
            append_examples(examples)
            count += len(examples)

        done.add(uid)
        save_checkpoint(done)
        time.sleep(0.5)

    print(f"  Generados {count} ejemplos")
    return count


def process_aiken_docs(done: set, dry_run: bool) -> int:
    print("\n=== [2/6] Aiken docs ===")
    data = json.loads((RAW_DIR / "aiken_docs.json").read_text())
    count = 0

    for page in data:
        uid = item_id("aiken_docs", page["url"])
        if uid in done:
            continue
        if not page.get("sections"):
            done.add(uid)
            continue

        prompt, n, complex_ = prompt_aiken_docs(page)
        examples = call_claude(prompt, n, complex_, dry_run)

        for ex in examples:
            ex["source"] = "aiken_docs"
            ex["topic"] = "aiken/language"

        if examples:
            append_examples(examples)
            count += len(examples)

        done.add(uid)
        save_checkpoint(done)
        time.sleep(0.5)

    print(f"  Generados {count} ejemplos")
    return count


def process_hydra_docs(done: set, dry_run: bool) -> int:
    print("\n=== [3/6] Hydra docs ===")
    data = json.loads((RAW_DIR / "hydra_docs.json").read_text())
    count = 0

    for page in data:
        uid = item_id("hydra_docs", page["url"])
        if uid in done:
            continue
        if not page.get("sections"):
            done.add(uid)
            continue

        prompt, n, complex_ = prompt_hydra_docs(page)
        examples = call_claude(prompt, n, complex_, dry_run)

        for ex in examples:
            ex["source"] = "hydra_docs"
            ex["topic"] = "hydra/protocol"

        if examples:
            append_examples(examples)
            count += len(examples)

        done.add(uid)
        save_checkpoint(done)
        time.sleep(0.5)

    print(f"  Generados {count} ejemplos")
    return count


def process_cips(done: set, dry_run: bool) -> int:
    print("\n=== [4/6] CIPs ===")
    data = json.loads((RAW_DIR / "cips.json").read_text())
    count = 0

    for cip in data:
        uid = item_id("cips", cip["id"])
        if uid in done:
            continue

        prompt, n, complex_ = prompt_cip(cip)
        examples = call_claude(prompt, n, complex_, dry_run)

        for ex in examples:
            ex["source"] = "cips"
            ex["topic"] = f"cardano/cip/{cip['id'].lower()}"

        if examples:
            append_examples(examples)
            count += len(examples)

        done.add(uid)
        save_checkpoint(done)
        time.sleep(0.5)

    print(f"  Generados {count} ejemplos")
    return count


def process_design_patterns(done: set, dry_run: bool) -> int:
    print("\n=== [5/6] Aiken Design Patterns ===")
    data = json.loads((RAW_DIR / "aiken_design_patterns.json").read_text())
    count = 0

    for record in data:
        uid = item_id("patterns", record["name"])
        if uid in done:
            continue

        prompt, n, complex_ = prompt_design_pattern(record)
        if not prompt:
            done.add(uid)
            continue

        examples = call_claude(prompt, n, complex_, dry_run)

        for ex in examples:
            ex["source"] = "aiken_design_patterns"
            ex["topic"] = "aiken/patterns"

        if examples:
            append_examples(examples)
            count += len(examples)

        done.add(uid)
        save_checkpoint(done)
        time.sleep(0.8)  # un poco más de delay para el modelo complex

    print(f"  Generados {count} ejemplos")
    return count


def process_hydra_code(done: set, dry_run: bool) -> int:
    print("\n=== [6/6] Hydra Plutus code ===")
    data = json.loads((RAW_DIR / "hydra_plutus.json").read_text())
    count = 0

    # Priorizar .md, luego .hs con contenido sustancial
    items = sorted(data, key=lambda x: (0 if x.get("extension") == ".md" else 1, x.get("path", "")))

    for record in items:
        uid = item_id("hydra_code", record["path"])
        if uid in done:
            continue

        prompt, n, complex_ = prompt_hydra_code(record)
        if not prompt:
            done.add(uid)
            continue

        examples = call_claude(prompt, n, complex_, dry_run)

        for ex in examples:
            ex["source"] = "hydra_plutus"
            ex["topic"] = "hydra/implementation"

        if examples:
            append_examples(examples)
            count += len(examples)

        done.add(uid)
        save_checkpoint(done)
        time.sleep(0.6)

    print(f"  Generados {count} ejemplos")
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SOURCES = {
    "stdlib": process_stdlib,
    "aiken_docs": process_aiken_docs,
    "hydra_docs": process_hydra_docs,
    "cips": process_cips,
    "patterns": process_design_patterns,
    "hydra_code": process_hydra_code,
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=list(SOURCES.keys()), help="Procesar solo una fuente")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar prompts sin llamar la API")
    parser.add_argument("--reset", action="store_true", help="Ignorar checkpoint y empezar de cero")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    done = set() if args.reset else load_checkpoint()
    if done:
        print(f"Retomando desde checkpoint ({len(done)} items ya procesados)")

    total = 0
    targets = {args.source: SOURCES[args.source]} if args.source else SOURCES

    print("=" * 50)
    print(" Fase 2: Transformación Q&A")
    print(f" Modelo bulk: {MODEL_BULK}")
    print(f" Modelo complex: {MODEL_COMPLEX}")
    print("=" * 50)

    for name, processor in targets.items():
        count = processor(done, args.dry_run)
        total += count

    print(f"\n{'=' * 50}")
    print(f" Total ejemplos generados: {total}")
    print(f" Archivo: {DATASET_FILE}")

    if DATASET_FILE.exists():
        lines = DATASET_FILE.read_text().strip().split("\n")
        print(f" Líneas en dataset: {len(lines)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
