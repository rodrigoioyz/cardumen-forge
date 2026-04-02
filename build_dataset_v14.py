#!/usr/bin/env python3
"""
build_dataset_v14.py
Construye dataset_v14_train.jsonl con orden curriculum:
  1. CORRECTION (v13 + corrections_v2)
  2. VERIFIED_V3_ALIGNED (v13 purged)
  3. validators_v3 (19 batches, ~479 ejemplos nuevos)
  4. PLAUSIBLE_NEEDS_CHECK (v13 purged)

Uso:
    python3 build_dataset_v14.py --dry-run
    python3 build_dataset_v14.py
"""
import json, sys, argparse
from collections import Counter
from pathlib import Path

V13_PURGED      = "data/processed/dataset_v13_purged.jsonl"
VALIDATORS_V3   = "data/processed/validators_v3.jsonl"
FIXED           = "data/processed/validators_fixed.jsonl"
CORRECTIONS_V2  = "data/processed/corrections_v2.jsonl"
OUTPUT          = "data/processed/dataset_v14_train.jsonl"

def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"  {path}: {len(records)} registros")
    return records

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and Path(OUTPUT).exists():
        print(f"ERROR: {OUTPUT} ya existe. Bórralo primero.")
        sys.exit(1)

    print("Cargando fuentes...")
    v13 = load_jsonl(V13_PURGED)
    v3  = load_jsonl(VALIDATORS_V3)
    fx  = load_jsonl(FIXED)
    cx2 = load_jsonl(CORRECTIONS_V2) if Path(CORRECTIONS_V2).exists() else []
    if not cx2:
        print(f"  AVISO: {CORRECTIONS_V2} no encontrado — generalo con generate_corrections_v2.py")

    # Separar v13 por status
    correction = [r for r in v13 if r.get("review_status") == "CORRECTION"]
    verified   = [r for r in v13 if r.get("review_status") == "VERIFIED_V3_ALIGNED"]
    plausible  = [r for r in v13 if r.get("review_status") == "PLAUSIBLE_NEEDS_CHECK"]

    # fixed: reemplaza los 7 incompletos originales que ya están en v13_purged
    fixed_instructions = {r["instruction"] for r in fx}
    verified_deduped  = [r for r in verified if r["instruction"] not in fixed_instructions]
    plausible_deduped = [r for r in plausible if r["instruction"] not in fixed_instructions]

    # Orden curriculum: CORRECTION (v13 + v2) → VERIFIED → fixed → validators_v3 → PLAUSIBLE
    ordered = correction + cx2 + verified_deduped + fx + v3 + plausible_deduped
    total = len(ordered)

    print(f"\nComposición v14:")
    print(f"  CORRECTION (v13) : {len(correction)}")
    print(f"  CORRECTION (v2)  : {len(cx2)}")
    print(f"  VERIFIED (v13)   : {len(verified_deduped)}")
    print(f"  fixed (7)        : {len(fx)}")
    print(f"  validators_v3    : {len(v3)}")
    print(f"  PLAUSIBLE (v13)  : {len(plausible_deduped)}")
    print(f"  ─────────────────")
    print(f"  TOTAL            : {total}")

    # Deduplicación por (instruction, output)
    seen = set()
    deduped = []
    for r in ordered:
        key = (r.get("instruction",""), r.get("output",""))
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    if len(deduped) < total:
        print(f"  Duplicados eliminados: {total - len(deduped)}")
        total = len(deduped)

    # Distribución final
    sources = Counter(r.get("source","?") for r in deduped)
    statuses = Counter(r.get("review_status","?") for r in deduped)
    langs = Counter(r.get("lang","?") for r in deduped)
    print(f"\nDistribución final:")
    print(f"  Por status: {dict(statuses)}")
    print(f"  Por lang  : {dict(langs)}")
    print(f"  Top sources:")
    for s, n in sources.most_common(5):
        print(f"    {s:35s}: {n}")

    if args.dry_run:
        print(f"\n[DRY RUN] No se escribió nada.")
        return

    with open(OUTPUT, "w", encoding="utf-8") as f:
        for r in deduped:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Verificar
    written = sum(1 for _ in open(OUTPUT, encoding="utf-8"))
    print(f"\n✅ {OUTPUT} — {written} líneas")

if __name__ == "__main__":
    main()
