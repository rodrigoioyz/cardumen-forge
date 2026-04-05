#!/usr/bin/env python3
"""
regenerate_stdlib_json.py — Regenera data/raw/aiken_stdlib.json desde los
archivos fuente .ak reales del sandbox (build/packages/aiken-lang-stdlib).

Fuente de verdad: eval/aiken_sandbox/build/packages/aiken-lang-stdlib/
Versión embebida: leída de aiken-lang-stdlib/aiken.toml

Uso:
    python3 scripts/regenerate_stdlib_json.py
    python3 scripts/regenerate_stdlib_json.py --dry-run   # imprime, no escribe
"""

import re
import json
import argparse
from pathlib import Path

BASE_DIR    = Path(__file__).parent.parent
STDLIB_DIR  = BASE_DIR / "eval/aiken_sandbox/build/packages/aiken-lang-stdlib"
STDLIB_LIB  = STDLIB_DIR / "lib"
STDLIB_TOML = STDLIB_DIR / "aiken.toml"
OUT_PATH    = BASE_DIR / "data/raw/aiken_stdlib.json"


def read_version() -> str:
    """Lee la versión del stdlib desde aiken.toml."""
    for line in STDLIB_TOML.read_text().splitlines():
        m = re.match(r'^version\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    return "unknown"


def path_to_module(path: Path) -> str:
    """Convierte path relativo a lib/ en nombre de módulo con puntos."""
    rel = path.relative_to(STDLIB_LIB)
    parts = list(rel.parts)
    parts[-1] = parts[-1].replace(".ak", "")
    return ".".join(parts)


def extract_doc_comment(lines: list, idx: int) -> str:
    """Extrae el bloque de comentario /// justo antes de la línea idx."""
    doc_lines = []
    i = idx - 1
    while i >= 0 and lines[i].strip().startswith("///"):
        doc_lines.insert(0, lines[i].strip().lstrip("/").strip())
        i -= 1
    return " ".join(doc_lines).strip()


def parse_ak_file(path: Path) -> list:
    """
    Extrae pub fn, pub type y pub const de un archivo .ak.
    Maneja declaraciones multi-línea (alias con valor en línea siguiente,
    funciones con argumentos en múltiples líneas).
    Retorna lista de dicts con: module, name, kind, signature, doc.
    """
    module = path_to_module(path)
    text   = path.read_text(encoding="utf-8")
    lines  = text.splitlines()
    entries = []
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        # ── pub fn (puede ser multi-línea) ────────────────────────────────────
        m = re.match(r'^pub fn (\w+)\s*\(', stripped)
        if m:
            name = m.group(1)
            doc  = extract_doc_comment(lines, i)
            # Recoge hasta cerrar paréntesis + flecha de retorno opcional
            sig_lines = [stripped]
            depth = stripped.count('(') - stripped.count(')')
            j = i + 1
            while depth > 0 and j < len(lines):
                sig_lines.append(lines[j].strip())
                depth += lines[j].count('(') - lines[j].count(')')
                j += 1
            # Agrega la flecha de retorno si está en la siguiente línea
            if j < len(lines):
                next_stripped = lines[j].strip()
                if next_stripped.startswith('->'):
                    # Toma hasta la llave de apertura o fin de línea
                    ret = re.match(r'^(->.*?)(?:\s*\{.*)?$', next_stripped)
                    if ret:
                        sig_lines.append(ret.group(1).strip())
            sig = " ".join(sig_lines)
            entries.append({
                "module":    module,
                "name":      name,
                "kind":      "function",
                "signature": sig,
                "doc":       doc,
            })
            i += 1
            continue

        # ── pub type Name = Alias (misma línea) ───────────────────────────────
        m = re.match(r'^pub type (\w+(?:<[^>]+>)?)\s*=\s*(.+)', stripped)
        if m:
            name = m.group(1).split('<')[0]  # nombre sin parámetros genéricos
            sig  = f"pub type {m.group(1)} = {m.group(2).rstrip()}"
            doc  = extract_doc_comment(lines, i)
            entries.append({
                "module":    module,
                "name":      name,
                "kind":      "type_alias",
                "signature": sig,
                "doc":       doc,
            })
            i += 1
            continue

        # ── pub type Name = (valor en línea siguiente) ────────────────────────
        m = re.match(r'^pub type (\w+(?:<[^>]+>)?)\s*=$', stripped)
        if m:
            name = m.group(1).split('<')[0]
            value = lines[i + 1].strip() if i + 1 < len(lines) else ""
            sig  = f"pub type {m.group(1)} = {value}"
            doc  = extract_doc_comment(lines, i)
            entries.append({
                "module":    module,
                "name":      name,
                "kind":      "type_alias",
                "signature": sig,
                "doc":       doc,
            })
            i += 2
            continue

        # ── pub type Name { (custom type / enum) ─────────────────────────────
        m = re.match(r'^pub type (\w+(?:<[^>]+>)?)\s*\{', stripped)
        if m:
            name = m.group(1).split('<')[0]
            body_lines = [stripped]
            depth = stripped.count('{') - stripped.count('}')
            j = i + 1
            while depth > 0 and j < len(lines):
                body_lines.append(lines[j].rstrip())
                depth += lines[j].count('{') - lines[j].count('}')
                j += 1
            sig = "\n".join(body_lines)
            doc = extract_doc_comment(lines, i)
            entries.append({
                "module":    module,
                "name":      name,
                "kind":      "type",
                "signature": sig,
                "doc":       doc,
            })
            i = j
            continue

        # ── pub const ─────────────────────────────────────────────────────────
        m = re.match(r'^pub const (\w+)', stripped)
        if m:
            name = m.group(1)
            doc  = extract_doc_comment(lines, i)
            entries.append({
                "module":    module,
                "name":      name,
                "kind":      "constant",
                "signature": stripped,
                "doc":       doc,
            })

        i += 1

    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Imprime resumen sin escribir el archivo")
    args = parser.parse_args()

    version = read_version()
    print(f"Stdlib version : {version}")
    print(f"Source         : {STDLIB_LIB}")
    print(f"Output         : {OUT_PATH}")
    print()

    ak_files = sorted(
        p for p in STDLIB_LIB.rglob("*.ak")
        if "test" not in p.name
    )
    print(f"Archivos .ak   : {len(ak_files)}")

    all_entries = []
    for ak_file in ak_files:
        entries = parse_ak_file(ak_file)
        all_entries.extend(entries)
        print(f"  {path_to_module(ak_file):<45} {len(entries):3d} entradas")

    print(f"\nTotal entradas : {len(all_entries)}")

    # Estadísticas por kind
    from collections import Counter
    kinds = Counter(e["kind"] for e in all_entries)
    for k, n in kinds.most_common():
        print(f"  {k:<15} {n}")

    # Embed version in each entry
    for e in all_entries:
        e["stdlib_version"] = version

    if not args.dry_run:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(all_entries, f, indent=2, ensure_ascii=False)
        print(f"\nEscrito → {OUT_PATH}  ({OUT_PATH.stat().st_size // 1024} KB)")
    else:
        print("\n[DRY RUN] No se escribió ningún archivo.")


if __name__ == "__main__":
    main()
