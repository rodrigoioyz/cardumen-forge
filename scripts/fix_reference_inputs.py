#!/usr/bin/env python3
"""
fix_reference_inputs.py
Repara los 14 ejemplos fallidos de reference_input_examples en dataset_v23.jsonl
usando el log de audit para identificarlos y aplicar fixes quirúrgicos.

Patrones corregidos:
  A. cardano/address.from_verification_key(x) en expresiones → address.from_verification_key(x)
  B. cardano/address.Script(h) / VerificationKey(h) en pattern match → quitar prefijo
  C. builtin.length_of_bytearray / slice_bytearray → bytearray.starts_with / length
  D. if cond then → if cond {
  E. hex inválido #"face7c0ff1g" → #"face7c0ff1e"

Uso:
  python3 scripts/fix_reference_inputs.py
  python3 scripts/fix_reference_inputs.py --dry-run
"""

import re
import os
import sys
import json
import time
import subprocess
import argparse
from pathlib import Path

ROOT         = Path(__file__).parent.parent
DATASET_PATH = ROOT / "data" / "processed" / "dataset_v23.jsonl"
AUDIT_LOG    = ROOT / "logs" / "audit_v23.json"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
TIMEOUT_SECS = 30


# ─────────────────────────────────────────────────────────────────────────────
# Fix helpers
# ─────────────────────────────────────────────────────────────────────────────

def fix_cardano_slash_in_expressions(code: str) -> str:
    """
    Patrón A: cardano/address.from_verification_key(x) en expresiones.
    En Aiken la barra solo va en 'use'. En expresiones se usa el alias del módulo.
    Fix: quitar 'cardano/' para dejar solo 'address.from_verification_key(x)'
    y asegurarse de que 'from_verification_key' está importado.
    """
    if "cardano/address.from_verification_key(" not in code:
        return code

    code = code.replace("cardano/address.from_verification_key(", "address.from_verification_key(")

    # Asegurar que 'from_verification_key' está en el import de cardano/address
    code = _ensure_symbol_imported(code, "cardano/address", "from_verification_key")
    return code


def fix_module_prefix_in_patterns(code: str) -> str:
    """
    Patrón B: cardano/address.Script(h) o cardano/address.VerificationKey(h)
    en posición de pattern match. El módulo ya está importado con 'use cardano/address.{...}'.
    Fix: quitar el prefijo 'cardano/address.' en esas posiciones.
    """
    # Solo aplica dentro de 'when ... is { ... }' pero la sustitución directa es segura
    # porque 'cardano/address.Script(' y 'cardano/address.VerificationKey(' no son válidos
    # en ninguna posición en Aiken.
    code = re.sub(r'cardano/address\.(Script|VerificationKey)\(', r'\1(', code)
    return code


def fix_builtin_bytearray(code: str) -> str:
    """
    Patrón C: builtin.length_of_bytearray / builtin.slice_bytearray no existen en stdlib v3.

    Caso específico encontrado en los fallos:
      let prefix_len = builtin.length_of_bytearray(prefix)
      let name_prefix = builtin.slice_bytearray(0, prefix_len, name)
      let has_valid_prefix = name_prefix == prefix

    Se reemplaza el bloque entero por bytearray.starts_with(name, prefix),
    que es más idiomático en v3.
    """
    if "builtin." not in code:
        return code

    # Reemplazar el patrón de prefix check en 2 variantes (EN y ES)
    # Variante EN
    code = re.sub(
        r'let prefix_len\s*=\s*builtin\.length_of_bytearray\((\w+)\)\s*\n'
        r'\s*let name_prefix\s*=\s*builtin\.slice_bytearray\(0,\s*prefix_len,\s*(\w+)\)\s*\n'
        r'\s*let has_valid_prefix\s*=\s*name_prefix\s*==\s*\1',
        r'let has_valid_prefix = bytearray.starts_with(\2, \1)',
        code
    )
    # Variante ES
    code = re.sub(
        r'let longitud_prefijo\s*=\s*builtin\.length_of_bytearray\((\w+)\)\s*\n'
        r'\s*let prefijo_actual\s*=\s*\n\s*builtin\.slice_bytearray\(0,\s*longitud_prefijo,\s*(\w+)\)\s*\n'
        r'\s*let prefijo_valido\s*=\s*prefijo_actual\s*==\s*\1',
        r'let prefijo_valido = bytearray.starts_with(\2, \1)',
        code
    )

    # Si quedaron restos de builtin.*, reemplazar con formas conocidas
    code = re.sub(r'builtin\.length_of_bytearray\((\w+)\)', r'bytearray.length(\1)', code)
    code = re.sub(r'builtin\.slice_bytearray\((\d+),\s*(\w+),\s*(\w+)\)', r'bytearray.take(\3, \2)', code)

    # Agregar import si bytearray está en uso
    if "bytearray." in code:
        code = _ensure_module_imported(code, "aiken/primitive/bytearray")

    return code


def fix_if_then_syntax(code: str) -> str:
    """
    Patrón D: 'if cond then' no es válido en Aiken. Debe ser 'if cond {'.
    """
    # Reemplaza 'if <expr> then\n  <body>\nelse\n  <alt>' por 'if <expr> {\n  <body>\n} else {\n  <alt>\n}'
    # Primero el caso simple de una línea: 'if expr then'
    code = re.sub(r'\bif\b(.+?)\bthen\b\s*\n', lambda m: f'if{m.group(1)}{{\n', code)
    # Ahora asegurarse de que el else también tenga llaves si no las tiene
    # Patrón: línea vacía/indent + else\n + indent + expr (sin llave)
    code = re.sub(r'\n(\s*)else\s*\n(\s*)([^{{\n])', lambda m: f'\n{m.group(1)}}} else {{\n{m.group(2)}{m.group(3)}', code)
    # Cerrar el bloque else — encontrar la línea después y agregar } después
    # Esto es frágil; mejor hacer una pasada más simple detectando el patrón exacto
    return code


def fix_invalid_hex(code: str) -> str:
    """
    Patrón E: #"face7c0ff1g" tiene 'g' (no hex) y 11 chars (impar = no válido).
    Reemplazar con un policy ID válido de 56 hex chars (28 bytes).
    """
    # Usar 56 chars = 28 bytes (tamaño correcto de policy ID en Cardano)
    VALID_POLICY = '#"f4c9f9c4252d86702c2f4c2e49e6648c7cffe3c8f2b6b7d779788f50"'
    code = code.replace('#"face7c0ff1g"', VALID_POLICY)
    return code


def _ensure_symbol_imported(code: str, module_path: str, symbol: str) -> str:
    """Asegura que 'symbol' está en el import de 'module_path'."""
    # Busca línea: use module_path.{...}
    pattern = re.compile(
        r'^(use ' + re.escape(module_path) + r'\.\{)([^}]*?)(\})',
        re.MULTILINE
    )
    m = pattern.search(code)
    if m:
        symbols = [s.strip() for s in m.group(2).split(",")]
        if symbol not in symbols:
            symbols.append(symbol)
            new_import = m.group(1) + ", ".join(symbols) + m.group(3)
            code = code[:m.start()] + new_import + code[m.end():]
    else:
        # No hay import del módulo, agregar línea use
        code = f"use {module_path}.{{{symbol}}}\n" + code
    return code


def _ensure_module_imported(code: str, module_path: str) -> str:
    """Asegura 'use module_path' (sin símbolos) está presente."""
    alias = module_path.split("/")[-1]
    pattern = re.compile(r'^use ' + re.escape(module_path) + r'(\.\{|$|\s)', re.MULTILINE)
    if not pattern.search(code):
        code = f"use {module_path}\n" + code
    return code


def fix_pairs_keys_on_dict(code: str) -> str:
    """
    assets.tokens() devuelve Dict<AssetName, Int>, no Pairs.
    pairs.keys(dict_value) falla con type mismatch.
    Fix: usar dict.keys(tokens) e importar aiken/collection/dict.
    """
    if "pairs.keys(" not in code:
        return code
    # Reemplazar solo cuando el argumento viene de assets.tokens (patrón foldl de conteo)
    # También puede aparecer let tokens = assets.tokens(...); pairs.keys(tokens)
    code = re.sub(r'\bpairs\.keys\b', 'dict.keys', code)
    # Cambiar import: use aiken/collection/pairs → use aiken/collection/dict
    code = re.sub(r'^use aiken/collection/pairs\b', 'use aiken/collection/dict', code, flags=re.MULTILINE)
    # Si no había import de pairs pero sí de dict, o no hay ninguno, agregar dict
    if "dict.keys(" in code:
        code = _ensure_module_imported(code, "aiken/collection/dict")
    return code


def fix_if_then_syntax(code: str) -> str:
    """
    Patrón D: 'if cond then' no es válido en Aiken. Debe ser 'if cond { ... } else { ... }'.
    Solo aplica cuando ambas ramas son expresiones de una sola línea (sin multi-línea).
    Si la rama else es multi-línea (empieza con nombre_fn() con paréntesis abierto)
    se omite — esos casos se manejan con fix_vesting_if_then.
    """
    def replace_if_then(m):
        indent = m.group(1)
        cond   = m.group(2).rstrip()
        body   = m.group(3).strip()
        alt    = m.group(4).strip()
        # No procesar si alt abre una expresión multi-línea
        if alt.endswith("("):
            return m.group(0)
        return f"{indent}if {cond} {{\n{indent}  {body}\n{indent}}} else {{\n{indent}  {alt}\n{indent}}}"

    code = re.sub(
        r'^(\s*)if (.+?) then\s*\n\s*(.+?)\n\s*else\s*\n\s*(.+?)$',
        replace_if_then,
        code,
        flags=re.MULTILINE
    )
    return code


VESTING_ES_FIXED = '''\
use cardano/transaction.{Transaction, OutputReference, Input, find_input, InlineDatum}
use cardano/assets
use aiken/collection/list
use aiken/interval.{Finite}
use cardano/address.{VerificationKey}

pub type CalendarioVesting {
  tiempo_inicio: Int,
  duracion_cliff_ms: Int,
  duracion_total_ms: Int,
  total_tokens: Int,
  policy_token: ByteArray,
  nombre_token: ByteArray,
}

pub type DatoVesting {
  beneficiario: ByteArray,
  tokens_reclamados: Int,
  ref_calendario: OutputReference,
  nft_calendario_policy: ByteArray,
  nft_calendario_nombre: ByteArray,
}

validator contrato_vesting {
  spend(
    datum: Option<DatoVesting>,
    _redeemer: Data,
    own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    expect Some(entrada_calendario) =
      transaction.find_input(self.reference_inputs, d.ref_calendario)
    let calendario_autentico =
      assets.has_nft(
        entrada_calendario.output.value,
        d.nft_calendario_policy,
        d.nft_calendario_nombre,
      )
    expect InlineDatum(raw_cal) = entrada_calendario.output.datum
    expect cal: CalendarioVesting = raw_cal
    expect Finite(ahora) = self.validity_range.lower_bound.bound_type
    let transcurrido = ahora - cal.tiempo_inicio
    let paso_cliff = transcurrido >= cal.duracion_cliff_ms
    let desbloqueados =
      if transcurrido >= cal.duracion_total_ms {
        cal.total_tokens
      } else {
        cal.total_tokens * transcurrido / cal.duracion_total_ms
      }
    let reclamables = desbloqueados - d.tokens_reclamados
    let firmado = list.has(self.extra_signatories, d.beneficiario)
    let entrada_propia = transaction.resolve_input(self.inputs, own_ref)
    let dir_script = entrada_propia.address
    let beneficiario_recibe =
      list.any(
        self.outputs,
        fn(o) {
          when o.address.payment_credential is {
            VerificationKey(hash) ->
              hash == d.beneficiario && assets.quantity_of(
                o.value,
                cal.policy_token,
                cal.nombre_token,
              ) >= reclamables
            _ -> False
          }
        },
      )
    let es_cierre_total =
      desbloqueados == cal.total_tokens && d.tokens_reclamados + reclamables == cal.total_tokens
    let continuacion_valida =
      if es_cierre_total {
        True
      } else {
        list.any(
          self.outputs,
          fn(o) {
            if o.address == dir_script {
              when o.datum is {
                InlineDatum(raw_nuevo) -> {
                  expect nuevo: DatoVesting = raw_nuevo
                  nuevo.beneficiario == d.beneficiario
                    && nuevo.tokens_reclamados == d.tokens_reclamados + reclamables
                    && nuevo.ref_calendario == d.ref_calendario
                }
                _ -> False
              }
            } else {
              False
            }
          },
        )
      }
    calendario_autentico && paso_cliff && reclamables > 0 && firmado && beneficiario_recibe && continuacion_valida
  }
}
'''


def fix_vesting_full_rewrite(code: str, instruction: str) -> str:
    """
    El validador de vesting tiene múltiples if...then anidados que no pueden
    corregirse con regex. Se reescribe completamente la versión ES.
    """
    if "contrato de vesting" not in instruction.lower():
        return code
    if "if" not in code or "then" not in code:
        return code
    return VESTING_ES_FIXED


def apply_all_fixes(code: str, instruction: str = "") -> str:
    code = fix_vesting_full_rewrite(code, instruction)
    code = fix_cardano_slash_in_expressions(code)
    code = fix_module_prefix_in_patterns(code)
    code = fix_builtin_bytearray(code)
    code = fix_pairs_keys_on_dict(code)
    code = fix_if_then_syntax(code)
    code = fix_invalid_hex(code)
    return code


# ─────────────────────────────────────────────────────────────────────────────
# Aiken check
# ─────────────────────────────────────────────────────────────────────────────

def aiken_check(code: str) -> tuple[bool, str]:
    SANDBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    aiken_bin = os.path.expanduser("~/.aiken/bin/aiken")
    aiken_cmd = aiken_bin if os.path.exists(aiken_bin) else "aiken"
    try:
        result = subprocess.run(
            [aiken_cmd, "check"],
            cwd=SANDBOX_DIR,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECS,
        )
        output = (result.stdout + result.stderr).strip()
        # Filter noise
        lines = [l for l in output.splitlines() if not l.strip().startswith("Compiling")]
        return result.returncode == 0, "\n".join(lines)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError:
        return False, "aiken not found"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No modifica el dataset")
    parser.add_argument("--dataset", default=str(DATASET_PATH))
    parser.add_argument("--audit",   default=str(AUDIT_LOG))
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    audit_path   = Path(args.audit)

    # Cargar audit para saber qué instrucciones fallaron en reference_input_examples
    audit = json.load(audit_path.open(encoding="utf-8"))
    failing_instructions = {
        r["instruction"]
        for r in audit["results"]
        if r["source"] == "reference_input_examples" and r.get("check_pass") == False
    }
    print(f"Instrucciones fallidas en audit: {len(failing_instructions)}")

    # Cargar dataset
    examples = []
    with dataset_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    print(f"Dataset: {len(examples)} ejemplos\n")

    fixed = 0
    still_broken = 0
    not_found = len(failing_instructions)

    for ex in examples:
        if ex.get("source") != "reference_input_examples":
            continue
        instr = ex.get("instruction", "")
        if instr not in failing_instructions:
            continue

        not_found -= 1
        original = ex["output"]
        repaired = apply_all_fixes(original, instruction=instr)

        if repaired == original:
            print(f"  [NO CHANGE] {instr[:70]}")
            still_broken += 1
            continue

        ok, error = aiken_check(repaired)
        status = "✅" if ok else "❌"
        print(f"  {status} {instr[:70]}")
        if not ok:
            for line in error.splitlines()[:5]:
                print(f"     {line[:120]}")
            still_broken += 1
        else:
            fixed += 1
            if not args.dry_run:
                ex["output"] = repaired

    if not_found > 0:
        print(f"\n⚠  {not_found} instrucciones del audit no encontradas en dataset (ya pueden estar corregidas)")

    print(f"\n{'─'*60}")
    print(f"  Corregidos : {fixed}")
    print(f"  Aún rotos  : {still_broken}")
    print(f"{'─'*60}")

    if not args.dry_run and fixed > 0:
        backup = dataset_path.with_suffix(".jsonl.ref_backup")
        import shutil
        shutil.copy2(dataset_path, backup)
        print(f"  Backup → {backup.name}")

        with dataset_path.open("w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"  Dataset actualizado: {dataset_path.name}")
    elif args.dry_run:
        print("  [dry-run] No se modificó nada")


if __name__ == "__main__":
    main()
