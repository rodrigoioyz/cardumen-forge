#!/usr/bin/env python3
"""
purge_dot_imports.py
Elimina los 201 ejemplos aiken_stdlib con dot-notation imports del dataset_v13.
Solo afecta outputs en ejemplos que NO son correction_set.

Uso:
    python3 purge_dot_imports.py --dry-run
    python3 purge_dot_imports.py
"""
import json, re, argparse
from collections import Counter

INPUT  = "data/processed/dataset_v13_train.jsonl"
OUTPUT = "data/processed/dataset_v13_purged.jsonl"

# Patron: lineas de import con dot-notation en el output
DOT_IMPORT = re.compile(r'^use\s+\w+\.\w+', re.MULTILINE)

def is_correction(r):
    return (r.get("source") == "correction_set" or
            "correction" in r.get("topic", "") or
            "anti" in r.get("topic", ""))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = []
    with open(INPUT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    kept    = []
    removed = []

    for r in records:
        if is_correction(r):
            kept.append(r)
            continue
        if DOT_IMPORT.search(r.get("output", "")):
            removed.append(r)
        else:
            kept.append(r)

    print(f"Input   : {len(records)}")
    print(f"Removed : {len(removed)}")
    print(f"Kept    : {len(kept)}")

    # Breakdown de removidos
    src_counts = Counter(r.get("source","?") for r in removed)
    status_counts = Counter(r.get("review_status","?") for r in removed)
    print(f"\nRemoved by source: {dict(src_counts)}")
    print(f"Removed by status: {dict(status_counts)}")

    if args.dry_run:
        print("\n[DRY RUN] No se escribió nada.")
        return

    with open(OUTPUT, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Verificación
    final = []
    with open(OUTPUT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                final.append(json.loads(line))

    residual = [r for r in final if DOT_IMPORT.search(r.get("output","")) and not is_correction(r)]
    print(f"\nVerificación: {len(final)} líneas escritas")
    print(f"  dot-imports residuales (non-correction): {len(residual)}", "✅" if not residual else "❌")
    print(f"\nEscrito: {OUTPUT}")

if __name__ == "__main__":
    main()
