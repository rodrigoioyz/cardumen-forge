#!/usr/bin/env python3
"""
repair_dataset_v23.py — Repara ejemplos con errores de tipo en dataset_v22.jsonl

Fuente de verdad: data/raw/aiken_stdlib.json (stdlib v3.0.0)
Validación: aiken check en eval/aiken_sandbox/

Fixes aplicados (basados estrictamente en stdlib local):
  1. owner/signer/beneficiary: ByteArray → VerificationKeyHash (aiken/crypto)
     Razón: extra_signatories es List<VerificationKeyHash>, no List<ByteArray>
  2. VerificationKeyHash sin import → agregar use aiken/crypto.{VerificationKeyHash}
  3. OutputReference sin import cardano/transaction → agregar al import existente
  4. Withdraw en certificate import → remover (Withdraw es constructor de ScriptPurpose, no importable)
  5. input.value → input.output.value (Input tiene .output: Output, Output tiene .value)

Uso:
    python3 scripts/repair_dataset_v23.py
    python3 scripts/repair_dataset_v23.py --dry-run   # solo diagnóstico, no escribe
"""

import json
import re
import subprocess
import shutil
import argparse
from pathlib import Path
from datetime import datetime

BASE_DIR    = Path(__file__).parent.parent
DATASET_IN  = BASE_DIR / "data/processed/dataset_v22.jsonl"
DATASET_OUT = BASE_DIR / "data/processed/dataset_v23.jsonl"
SANDBOX_DIR = BASE_DIR / "eval/aiken_sandbox"
VALIDATOR   = SANDBOX_DIR / "validators/output.ak"
LOG_OUT     = BASE_DIR / "logs/repair_v23_report.md"

# ─── Helpers de import ────────────────────────────────────────────────────────

def has_import(code: str, module: str, symbol: str = None) -> bool:
    """Verifica si un módulo/símbolo está importado."""
    if symbol:
        # Busca use module.{..., symbol, ...}  — dot before brace is required in Aiken
        pattern = rf'use {re.escape(module)}\.\{{[^}}]*\b{re.escape(symbol)}\b'
        return bool(re.search(pattern, code))
    return f"use {module}" in code


def add_symbol_to_import(code: str, module: str, symbol: str) -> str:
    """Agrega un símbolo a un import existente o crea la línea si no existe."""
    # Si ya existe el import del módulo con llaves, agrega el símbolo
    # Aiken syntax: use module.{Symbol1, Symbol2}  — dot before brace
    pattern = rf'(use {re.escape(module)}\.\{{)([^}}]+)(\}})'
    match = re.search(pattern, code)
    if match:
        symbols = match.group(2)
        if symbol not in symbols:
            new_symbols = symbols.rstrip() + f", {symbol}"
            code = code[:match.start()] + f"use {module}.{{{new_symbols}}}" + code[match.end():]
        return code

    # Si existe import sin llaves, reemplaza por import con llaves
    simple = f"use {module}\n"
    if simple in code:
        return code.replace(simple, f"use {module}.{{{symbol}}}\n")

    # No existe — insertar antes del primer 'use' o al inicio
    first_use = re.search(r'^use ', code, re.MULTILINE)
    if first_use:
        pos = first_use.start()
        return code[:pos] + f"use {module}.{{{symbol}}}\n" + code[pos:]

    return f"use {module}.{{{symbol}}}\n" + code


def remove_symbol_from_import(code: str, module: str, symbol: str) -> str:
    """Remueve un símbolo de un import. Si queda vacío, remueve la línea."""
    pattern = rf'use {re.escape(module)}\.\{{([^}}]+)\}}'
    match = re.search(pattern, code)
    if not match:
        return code
    symbols = [s.strip() for s in match.group(1).split(',') if s.strip() != symbol]
    if not symbols:
        # Remover la línea completa
        line_pattern = rf'\nuse {re.escape(module)}\.\{{[^}}]+\}}'
        return re.sub(line_pattern, '', code)
    new_import = f"use {module}.{{{', '.join(symbols)}}}"
    return code[:match.start()] + new_import + code[match.end():]


# ─── Fixes individuales ───────────────────────────────────────────────────────

def fix_vkh_bytearray(code: str) -> tuple[str, list]:
    """
    Fix 1+2: Reemplaza ByteArray por VerificationKeyHash en campos de datum/redeemer
    que se usan con extra_signatories, y agrega el import necesario.
    Fuente: extra_signatories: List<VerificationKeyHash> (aiken_stdlib.json línea 3524)
    """
    changes = []
    VKH_FIELDS = ['owner', 'signer', 'beneficiary', 'admin', 'committee_member',
                  'admin1', 'admin2', 'admin3', 'operator', 'treasury']

    for field in VKH_FIELDS:
        pattern = rf'\b({re.escape(field)})\s*:\s*ByteArray\b'
        if re.search(pattern, code) and 'extra_signatories' in code:
            code = re.sub(pattern, rf'\1: VerificationKeyHash', code)
            changes.append(f"  {field}: ByteArray → VerificationKeyHash")

    # Agregar import si se usa VerificationKeyHash y no está importado
    if 'VerificationKeyHash' in code and not has_import(code, 'aiken/crypto', 'VerificationKeyHash'):
        code = add_symbol_to_import(code, 'aiken/crypto', 'VerificationKeyHash')
        changes.append("  + import aiken/crypto.{VerificationKeyHash}")

    return code, changes


def fix_missing_vkh_import(code: str) -> tuple[str, list]:
    """
    Fix 2: Agrega import de VerificationKeyHash si se usa sin importar.
    Fuente: aiken.crypto module en aiken_stdlib.json
    """
    changes = []
    if 'VerificationKeyHash' in code and not has_import(code, 'aiken/crypto', 'VerificationKeyHash'):
        code = add_symbol_to_import(code, 'aiken/crypto', 'VerificationKeyHash')
        changes.append("  + import aiken/crypto.{VerificationKeyHash}")
    return code, changes


def fix_missing_outputref_import(code: str) -> tuple[str, list]:
    """
    Fix 3: Agrega OutputReference al import de cardano/transaction si falta.
    Fuente: OutputReference en cardano.transaction (aiken_stdlib.json)
    """
    changes = []
    if 'OutputReference' in code and not has_import(code, 'cardano/transaction', 'OutputReference'):
        code = add_symbol_to_import(code, 'cardano/transaction', 'OutputReference')
        changes.append("  + import cardano/transaction.{OutputReference}")
    return code, changes


def fix_withdraw_from_certificate(code: str) -> tuple[str, list]:
    """
    Fix 4: Remueve Withdraw de cardano/certificate — no existe ahí.
    Fuente: Withdraw es constructor de ScriptPurpose en cardano.transaction, no importable.
    """
    changes = []
    if 'cardano/certificate' in code and 'Withdraw' in code:
        orig = code
        code = remove_symbol_from_import(code, 'cardano/certificate', 'Withdraw')
        if code != orig:
            changes.append("  - Withdraw removido de cardano/certificate (no existe ahí)")
    return code, changes


def fix_input_value(code: str) -> tuple[str, list]:
    """
    Fix 5: input.value → input.output.value
    Fuente: Input tiene campo output: Output, Output tiene campo value: Value (aiken_stdlib.json)
    """
    changes = []
    # Solo reemplaza si NO es ya input.output.value
    pattern = r'\binput\.value\b'
    if re.search(pattern, code) and 'input.output.value' not in code:
        code = re.sub(pattern, 'input.output.value', code)
        changes.append("  input.value → input.output.value")
    return code, changes


def fix_redeemer_import_conflict(code: str) -> tuple[str, list]:
    """
    Fix 6: Remueve 'Redeemer' del import de cardano/transaction cuando el archivo
    define su propio 'pub type Redeemer'. Importar y redefinir el mismo nombre es
    un conflicto que impide compilar.
    Fuente: Aiken no permite shadowing de imports con tipos locales del mismo nombre.
    """
    changes = []
    has_local_redeemer = bool(re.search(r'\bpub type Redeemer\b', code))
    if has_local_redeemer and has_import(code, 'cardano/transaction', 'Redeemer'):
        code = remove_symbol_from_import(code, 'cardano/transaction', 'Redeemer')
        changes.append("  - Redeemer removido de cardano/transaction (redefinido localmente)")
    return code, changes


# ─── Validación con aiken check ───────────────────────────────────────────────

def aiken_check(code: str) -> tuple[bool, str]:
    """Escribe el código al sandbox y corre aiken check. Retorna (ok, output_completo)."""
    VALIDATOR.write_text(code, encoding='utf-8')
    result = subprocess.run(
        ['aiken', 'check'],
        cwd=SANDBOX_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    ok = result.returncode == 0
    # aiken imprime errores reales a stdout; progreso ("Compiling...") va a stderr
    combined = (result.stdout or "") + (result.stderr or "")
    return ok, combined if not ok else ""


# ─── Pipeline principal ───────────────────────────────────────────────────────

FIXES = [
    fix_vkh_bytearray,
    fix_missing_vkh_import,
    fix_missing_outputref_import,
    fix_withdraw_from_certificate,
    fix_input_value,
    fix_redeemer_import_conflict,
]

def repair_example(ex: dict) -> tuple[dict, list, bool, str]:
    """
    Aplica todos los fixes a un ejemplo.
    Retorna (ejemplo_reparado, lista_de_cambios, compiló, aiken_error).
    """
    code = ex.get('output', '')
    if not code.strip():
        return ex, [], True, ""

    # Solo aplicar fixes a código Aiken real — saltar ejemplos de documentación markdown
    # (documentación usa bloques ```aiken dentro de texto en prosa)
    if '```' in code:
        return ex, [], True, ""
    if 'validator' not in code and 'pub type' not in code and not re.search(r'^use ', code, re.MULTILINE):
        return ex, [], True, ""

    # Detectar si hay algún problema antes de aplicar fixes
    needs_fix = (
        any(f'_{f}: ByteArray' in code or f'{f}: ByteArray' in code
            for f in ['owner', 'signer', 'beneficiary', 'admin', 'committee_member',
                      'admin1', 'admin2', 'admin3', 'operator', 'treasury'])
        or ('VerificationKeyHash' in code and 'aiken/crypto' not in code)
        or ('OutputReference' in code and 'cardano/transaction' not in code)
        or ('cardano/certificate' in code and 'Withdraw' in code)
        or (re.search(r'\binput\.value\b', code) and 'input.output.value' not in code)
        or (bool(re.search(r'\bpub type Redeemer\b', code)) and has_import(code, 'cardano/transaction', 'Redeemer'))
    )

    if not needs_fix:
        return ex, [], True, ""

    all_changes = []
    fixed_code = code
    for fix_fn in FIXES:
        fixed_code, changes = fix_fn(fixed_code)
        all_changes.extend(changes)

    if not all_changes:
        return ex, [], True, ""

    # Validar con aiken check
    ok, err = aiken_check(fixed_code)
    if ok:
        fixed_ex = dict(ex)
        fixed_ex['output'] = fixed_code
        return fixed_ex, all_changes, True, ""
    else:
        return ex, all_changes, False, err


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                        help='Solo diagnóstico, no escribe dataset_v23.jsonl')
    parser.add_argument('--drop-unfixable', action='store_true',
                        help='Elimina del output ejemplos que no compilan tras el fix (default: conserva el original)')
    args = parser.parse_args()

    mode = '[DRY RUN] ' if args.dry_run else ''
    mode += '[DROP-UNFIXABLE] ' if args.drop_unfixable else ''
    print(f"{mode}repair_dataset_v23.py")
    print(f"Input : {DATASET_IN}")
    print(f"Output: {DATASET_OUT}")
    print()

    examples = []
    with open(DATASET_IN, encoding='utf-8') as f:
        for line in f:
            examples.append(json.loads(line))

    total       = len(examples)
    fixed_ok    = 0
    fixed_fail  = 0
    dropped     = 0
    skipped     = 0
    report_lines = []

    out_examples = []
    for i, ex in enumerate(examples):
        fixed_ex, changes, compiled, err = repair_example(ex)

        if not changes:
            skipped += 1
            out_examples.append(ex)
            continue

        if compiled:
            fixed_ok += 1
            out_examples.append(fixed_ex)
            report_lines.append(f"### [{i}] ✅ FIXED — {ex.get('source','?')}")
        else:
            fixed_fail += 1
            if args.drop_unfixable:
                dropped += 1
                # No agregar al output — se elimina del dataset
            else:
                out_examples.append(ex)  # conserva el original sin cambios
            report_lines.append(f"### [{i}] ❌ UNFIXABLE — {ex.get('source','?')}")
            if err:
                # Error completo al log (saltando líneas de progreso "Compiling ...")
                err_lines = [
                    l for l in err.strip().splitlines()
                    if l.strip() and not l.strip().startswith('Compiling')
                ]
                for el in err_lines:
                    report_lines.append(f"  {el}")

        for c in changes:
            report_lines.append(c)
        report_lines.append("")

        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{total}] fixed_ok={fixed_ok} fixed_fail={fixed_fail}")

    print(f"\nResultados:")
    print(f"  Total          : {total}")
    print(f"  Sin cambios    : {skipped}")
    print(f"  Reparados ✅   : {fixed_ok}")
    print(f"  No reparables ❌: {fixed_fail}", end="")
    print(f" (eliminados: {dropped})" if args.drop_unfixable else " (conservados en output)")

    if not args.dry_run:
        with open(DATASET_OUT, 'w', encoding='utf-8') as f:
            for ex in out_examples:
                f.write(json.dumps(ex, ensure_ascii=False) + '\n')
        final_count = len(out_examples)
        print(f"\nDataset guardado → {DATASET_OUT}  ({final_count} ejemplos)")

        LOG_OUT.parent.mkdir(exist_ok=True)
        with open(LOG_OUT, 'w', encoding='utf-8') as f:
            f.write(f"# Repair Report v23\n\n")
            f.write(f"Date: {datetime.now().isoformat()}\n")
            f.write(f"Input: {DATASET_IN}\n")
            f.write(f"Total: {total} | Fixed: {fixed_ok} | Unfixable: {fixed_fail} | Dropped: {dropped}\n\n")
            f.write('\n'.join(report_lines))
        print(f"Log guardado    → {LOG_OUT}")
    else:
        print("\n[DRY RUN] No se escribió ningún archivo.")
        print("\nPrimeros 20 problemas detectados:")
        for line in report_lines[:80]:
            print(line)


if __name__ == '__main__':
    main()
