#!/usr/bin/env python3
"""
build_dataset_v13.py
Construye dataset_v13_train.jsonl desde dataset_v12 + complex_validators con:
  1. Normalización de review_status faltante → PLAUSIBLE_NEEDS_CHECK
  2. Merge de complex_validators.jsonl verificados
  3. Verificación de integridad estructural post-merge
  4. Audit de calidad: handler coverage, API coverage, hallucinations

Uso:
    python3 build_dataset_v13.py --dry-run
    python3 build_dataset_v13.py
    python3 build_dataset_v13.py --overwrite
"""

import json, sys, argparse
from collections import Counter
from pathlib import Path

INPUT_V12      = "data/processed/dataset_v12_train.jsonl"
INPUT_COMPLEX  = "data/processed/complex_validators.jsonl"
OUTPUT_V13     = "data/processed/dataset_v13_train.jsonl"

REQUIRED_FIELDS = {"lang", "instruction", "input", "output", "source", "topic", "review_status"}
VALID_STATUSES  = {"VERIFIED_V3_ALIGNED", "PLAUSIBLE_NEEDS_CHECK", "CORRECTION"}
VALID_LANGS     = {"en", "es"}

# APIs que deben aparecer en el dataset con buena cobertura
GOOD_APIS = [
    ("fn spend(",              "spend handler"),
    ("fn mint(",               "mint handler"),
    ("fn withdraw(",           "withdraw handler"),
    ("own_ref: OutputReference","own_ref param"),
    ("assets.lovelace_of(",    "ADA check"),
    ("assets.has_nft(",        "NFT check"),
    ("assets.quantity_of(",    "token quantity"),
    ("list.has(",              "list.has"),
    ("list.all(",              "list.all"),
    ("list.any(",              "list.any"),
    ("list.count(",            "list.count"),
    ("self.extra_signatories", "signatories"),
    ("self.validity_range",    "validity range"),
    ("interval.is_entirely_after(", "interval after"),
    ("interval.is_entirely_before(","interval before"),
    ("interval.contains(",     "interval contains"),
]

# Patrones que NO deben aparecer fuera del correction_set
BAD_APIS = [
    "self.signatures",
    "self.time",
    "output.assets.ada",
    "self.outputs.all(",
    "self.outputs.any(",
    "self.outputs.find(",
    "self.outputs.fold(",
    "transaction.signatories(",
    "list.has_any(",
    "output.value.lovelace",
    "Signature.from_bytes(",
    "aiken.time.",
    "aiken.crypto.{Hash, Signature}",
]

def is_correction(r):
    return (
        r.get("source") == "correction_set" or
        "correction" in r.get("topic", "") or
        "anti" in r.get("topic", "")
    )

def normalize_record(r, idx):
    """Normaliza y valida un registro. Retorna (record, [warnings])."""
    warnings = []

    # 1. review_status faltante → PLAUSIBLE_NEEDS_CHECK
    if not r.get("review_status") or r["review_status"] not in VALID_STATUSES:
        old = r.get("review_status", "missing")
        r["review_status"] = "PLAUSIBLE_NEEDS_CHECK"
        warnings.append(f"  [line {idx}] review_status '{old}' → PLAUSIBLE_NEEDS_CHECK")

    # 2. lang faltante o inválido → "en"
    if not r.get("lang") or r["lang"] not in VALID_LANGS:
        old = r.get("lang", "missing")
        r["lang"] = "en"
        warnings.append(f"  [line {idx}] lang '{old}' → 'en'")

    # 3. Campos requeridos vacíos
    for field in ("instruction", "output", "source", "topic"):
        if not r.get(field, "").strip():
            warnings.append(f"  [line {idx}] EMPTY field: {field} (source={r.get('source')})")

    # 4. input faltante → string vacío (es opcional)
    if "input" not in r:
        r["input"] = ""

    return r, warnings

def audit(records, label):
    n = len(records)
    print(f"\n{'='*60}")
    print(f"  {label} — {n} ejemplos")
    print(f"{'='*60}")

    # Sources
    sources = Counter(r.get("source", "?") for r in records)
    print(f"\n  SOURCES:")
    for src, cnt in sources.most_common():
        print(f"    {src:35s}: {cnt:5d}  ({100*cnt/n:.1f}%)")

    # Lang
    langs = Counter(r.get("lang", "?") for r in records)
    print(f"\n  LANGUAGES: {dict(langs)}")

    # Review status
    statuses = Counter(r.get("review_status", "?") for r in records)
    print(f"\n  REVIEW STATUS: {dict(statuses)}")

    # Handler / API coverage
    print(f"\n  API COVERAGE (examples with pattern in output):")
    for pat, label_api in GOOD_APIS:
        hits = sum(1 for r in records if pat in r.get("output", ""))
        pct = 100 * hits / n
        bar = "█" * (hits // 20)
        flag = "⚠️ " if pct < 3 else "✅" if pct >= 5 else "  "
        print(f"    {flag} {label_api:30s}: {hits:4d}  ({pct:.1f}%)")

    # Hallucinations
    print(f"\n  HALLUCINATION CHECK (real uses, excl. corrections):")
    found_bad = False
    for pat in BAD_APIS:
        real = [r for r in records if pat in r.get("output", "") and not is_correction(r)]
        if real:
            print(f"    ❌ '{pat}': {len(real)} real uses")
            for ex in real[:1]:
                idx = ex["output"].find(pat)
                print(f"       src={ex.get('source')} topic={ex.get('topic')}")
                print(f"       ...{ex['output'][max(0,idx-30):idx+60]}...")
            found_bad = True
    if not found_bad:
        print(f"    ✅ 0 hallucinations found")

    # Structural integrity
    print(f"\n  STRUCTURAL INTEGRITY:")
    missing_fields = sum(1 for r in records if not REQUIRED_FIELDS.issubset(r.keys()))
    empty_output   = sum(1 for r in records if not r.get("output", "").strip())
    empty_instr    = sum(1 for r in records if not r.get("instruction", "").strip())
    print(f"    Missing required fields : {missing_fields}")
    print(f"    Empty output            : {empty_output}")
    print(f"    Empty instruction       : {empty_instr}")

    return {
        "total": n,
        "sources": dict(sources),
        "langs": dict(langs),
        "statuses": dict(statuses),
        "hallucinations": found_bad,
        "missing_fields": missing_fields,
    }


def load_jsonl(path, label):
    """Carga un JSONL con conteo explícito de líneas procesadas, skipped y dropped."""
    records = []
    dropped = 0
    skipped = 0
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                skipped += 1
                continue
            try:
                r = json.loads(line)
                if not isinstance(r, dict):
                    print(f"  [WARN] {label} línea {i}: no es dict ({type(r).__name__}), ignorada")
                    dropped += 1
                    continue
                records.append(r)
            except json.JSONDecodeError as e:
                print(f"  [WARN] {label} línea {i}: JSON error — {e}")
                dropped += 1
    if dropped > 0:
        print(f"  ⚠️  {label}: {dropped} líneas descartadas, {skipped} vacías, {len(records)} cargadas")
    else:
        print(f"  ✅ {label}: {len(records)} cargadas, {skipped} vacías, 0 descartadas")
    return records


def deduplicate(v12, complex_recs):
    """Detecta y reporta duplicados entre v12 y complex por (instruction, output)."""
    seen = {}
    for r in v12:
        key = (r.get("instruction",""), r.get("output",""))
        seen[key] = seen.get(key, 0) + 1

    duplicates = 0
    unique_complex = []
    for r in complex_recs:
        key = (r.get("instruction",""), r.get("output",""))
        if key in seen:
            duplicates += 1
        else:
            seen[key] = 1
            unique_complex.append(r)

    # Duplicados internos en v12
    v12_internal_dups = sum(1 for c in seen.values() if c > 1)

    if duplicates > 0:
        print(f"  ⚠️  {duplicates} duplicados entre v12 y complex — eliminados del complex")
    if v12_internal_dups > 0:
        print(f"  ⚠️  {v12_internal_dups} claves duplicadas internamente en v12")
    if duplicates == 0 and v12_internal_dups == 0:
        print(f"  ✅ 0 duplicados detectados")

    return unique_complex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not args.overwrite and not args.dry_run and Path(OUTPUT_V13).exists():
        print(f"ERROR: {OUTPUT_V13} ya existe. Usa --overwrite.")
        sys.exit(1)

    # ── Cargar v12 ──────────────────────────────────────────
    print(f"Cargando {INPUT_V12}...")
    v12_records = load_jsonl(INPUT_V12, "v12")

    # ── Cargar complex_validators ────────────────────────────
    print(f"\nCargando {INPUT_COMPLEX}...")
    complex_records = load_jsonl(INPUT_COMPLEX, "complex")

    # ── Verificar que complex tiene fn spend/mint/withdraw ───
    fn_spend_complex = sum(1 for r in complex_records if "fn spend(" in r.get("output",""))
    fn_mint_complex  = sum(1 for r in complex_records if "fn mint(" in r.get("output",""))
    fn_with_complex  = sum(1 for r in complex_records if "fn withdraw(" in r.get("output",""))
    bad_complex      = sum(1 for r in complex_records
                          if any(p in r.get("output","") for p in BAD_APIS)
                          and not is_correction(r))
    print(f"\n  Complex validators quality check:")
    print(f"    fn spend(    : {fn_spend_complex}")
    print(f"    fn mint(     : {fn_mint_complex}")
    print(f"    fn withdraw( : {fn_with_complex}")
    print(f"    hallucinations: {bad_complex}")

    if bad_complex > 0:
        print(f"\n  ⚠️  ADVERTENCIA: complex_validators tiene {bad_complex} hallucinations.")
        print(f"  Considera purgarlos antes de continuar.")

    # ── Normalizar v12 ───────────────────────────────────────
    print(f"\nNormalizando {len(v12_records)} registros v12...")
    normalized_v12 = []
    all_warnings = []
    status_fixes = 0
    lang_fixes = 0

    for i, r in enumerate(v12_records, 1):
        r, warnings = normalize_record(r, i)
        if warnings:
            all_warnings.extend(warnings)
            for w in warnings:
                if "review_status" in w:
                    status_fixes += 1
                if "lang" in w:
                    lang_fixes += 1
        normalized_v12.append(r)

    print(f"  review_status normalizados: {status_fixes}")
    print(f"  lang normalizados         : {lang_fixes}")
    if all_warnings[:5]:
        print(f"  Primeras advertencias:")
        for w in all_warnings[:5]:
            print(w)

    # ── Normalizar complex ───────────────────────────────────
    print(f"\nNormalizando {len(complex_records)} complex validators...")
    normalized_complex = []
    for i, r in enumerate(complex_records, 1):
        r, _ = normalize_record(r, i)
        normalized_complex.append(r)

    # ── Deduplicación ────────────────────────────────────────
    print(f"\nVerificando duplicados...")
    normalized_complex = deduplicate(normalized_v12, normalized_complex)

    # ── Merge ────────────────────────────────────────────────
    all_records = normalized_v12 + normalized_complex
    print(f"\nMerge: {len(normalized_v12)} + {len(normalized_complex)} = {len(all_records)} ejemplos")

    # ── Audit pre-write ──────────────────────────────────────
    stats = audit(all_records, f"dataset_v13 (pre-write)")

    if args.dry_run:
        print(f"\n[DRY RUN] No se escribió ningún archivo.")
        return

    # ── Escribir ─────────────────────────────────────────────
    print(f"\nEscribiendo {OUTPUT_V13}...")
    with open(OUTPUT_V13, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Verificar líneas escritas + validar JSON de muestra
    written = 0
    json_errors = 0
    with open(OUTPUT_V13, encoding="utf-8") as f:
        for line in f:
            written += 1
            try:
                json.loads(line)
            except json.JSONDecodeError:
                json_errors += 1

    print(f"  Verificación: {written} líneas, {json_errors} errores JSON")
    assert written == len(all_records), f"MISMATCH líneas: {written} != {len(all_records)}"
    assert json_errors == 0, f"MISMATCH: {json_errors} líneas con JSON inválido en el output"

    print(f"\n✅ {OUTPUT_V13} listo.")
    print(f"   {len(normalized_v12)} (v12) + {len(normalized_complex)} (complex) = {written} total")


if __name__ == "__main__":
    main()
