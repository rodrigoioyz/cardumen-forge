#!/usr/bin/env python3
"""
fix_dataset_v23.py
Fixes three categories of compile errors in dataset_v23.jsonl:

  B) Cycle errors: examples that redefine `pub type VerificationKeyHash`
     while also importing it from `aiken/crypto` — remove the alias.
  C) Slash-in-type-position: `_arg: cardano/module.Type` → `_arg: Type`
     (with proper import added)
  D) Em/en dash in code: `—` `–` → ` -`
"""

import re
import json
import shutil
from pathlib import Path
from collections import Counter

ROOT         = Path(__file__).parent.parent
DATASET_PATH = ROOT / "data" / "processed" / "dataset_v23.jsonl"
BACKUP_SUFFIX = ".pre_v23fix_backup"


# ─────────────────────────────────────────────────────────────────────────────
# B) Fix cycle: remove redundant pub type aliases for crypto types
# ─────────────────────────────────────────────────────────────────────────────

# Aiken/crypto types that are commonly re-aliased (causing cycles)
CRYPTO_TYPE_ALIASES = [
    r'pub type VerificationKeyHash\s*=\s*Hash<Blake2b_224,\s*VerificationKey>',
    r'pub type ScriptHash\s*=\s*Hash<Blake2b_224,\s*Script>',
    r'pub type Blake2b_256Hash\s*=\s*Hash<Blake2b_256,\s*\w+>',
    r'pub type Blake2b_224Hash\s*=\s*Hash<Blake2b_224,\s*\w+>',
]
CRYPTO_IMPORT_RE = re.compile(r'^use aiken/crypto[.\{]', re.MULTILINE)

def fix_cycle_aliases(code: str) -> str:
    """Remove pub type X = Hash<...> aliases when importing from aiken/crypto."""
    if not CRYPTO_IMPORT_RE.search(code):
        return code

    original = code
    for pattern in CRYPTO_TYPE_ALIASES:
        # Match the full line(s) — the alias may span 1 line
        code = re.sub(r'\n?' + pattern + r'\s*\n', '\n', code)

    return code


# ─────────────────────────────────────────────────────────────────────────────
# C) Fix slash-in-type-position: cardano/X.Type → Type (+ import)
# ─────────────────────────────────────────────────────────────────────────────

# Maps slash-module reference → (module_path, type_name)
SLASH_TYPE_MAP = {
    'cardano/transaction.OutputReference': ('cardano/transaction', 'OutputReference'),
    'cardano/transaction.Transaction':     ('cardano/transaction', 'Transaction'),
    'cardano/transaction.Input':           ('cardano/transaction', 'Input'),
    'cardano/transaction.Output':          ('cardano/transaction', 'Output'),
    'cardano/address.Address':             ('cardano/address',     'Address'),
    'cardano/address.Credential':          ('cardano/address',     'Credential'),
    'cardano/assets.PolicyId':             ('cardano/assets',      'PolicyId'),
    'cardano/assets.AssetName':            ('cardano/assets',      'AssetName'),
    'cardano/assets.Value':                ('cardano/assets',      'Value'),
    'aiken/crypto.VerificationKeyHash':    ('aiken/crypto',        'VerificationKeyHash'),
    'aiken/crypto.ScriptHash':             ('aiken/crypto',        'ScriptHash'),
}

def fix_slash_in_types(code: str) -> str:
    """Replace `arg: cardano/X.Type` patterns in function signatures/type annotations."""
    modified = code
    for slash_ref, (mod_path, type_name) in SLASH_TYPE_MAP.items():
        if slash_ref not in modified:
            continue
        # Replace the slash ref with just the type name
        modified = modified.replace(slash_ref, type_name)
        # Ensure the type is imported
        import_line = f'use {mod_path}.{{{type_name}}}'
        # Check if already imported (any form)
        already = re.search(
            r'^use ' + re.escape(mod_path) + r'[.\{]',
            modified, re.MULTILINE
        )
        if not already:
            # Add import after last existing use statement
            last_use = list(re.finditer(r'^use [^\n]+', modified, re.MULTILINE))
            if last_use:
                insert_at = last_use[-1].end()
                modified = modified[:insert_at] + '\n' + import_line + modified[insert_at:]
            else:
                modified = import_line + '\n' + modified
        else:
            # Add the specific type to existing import if not there
            existing_import = re.search(
                r'^(use ' + re.escape(mod_path) + r')\.\{([^}]+)\}',
                modified, re.MULTILINE
            )
            if existing_import:
                current_types = [t.strip() for t in existing_import.group(2).split(',')]
                if type_name not in current_types:
                    new_types = ', '.join(sorted(set(current_types + [type_name])))
                    modified = modified[:existing_import.start()] + \
                               f'use {mod_path}.{{{new_types}}}' + \
                               modified[existing_import.end():]
    return modified


# ─────────────────────────────────────────────────────────────────────────────
# D) Fix em/en dash and other typography artifacts
# ─────────────────────────────────────────────────────────────────────────────

TYPOGRAPHY_REPLACEMENTS = [
    ('\u2014', ' -'),  # em dash —
    ('\u2013', ' -'),  # en dash –
    ('\u201c', '"'),   # left double quote "
    ('\u201d', '"'),   # right double quote "
    ('\u2018', "'"),   # left single quote '
    ('\u2019', "'"),   # right single quote '
    ('\u2026', '...'), # ellipsis …
]

def fix_typography(code: str) -> str:
    """Replace typography Unicode artifacts with ASCII equivalents."""
    for bad, good in TYPOGRAPHY_REPLACEMENTS:
        code = code.replace(bad, good)
    return code


def is_pure_aiken(code: str) -> bool:
    """True if output looks like compilable Aiken code (not docs)."""
    if '```' in code or '**' in code:
        return False
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('//'):
            continue
        return bool(re.match(r'^(use |pub |fn |validator |test |type )', stripped))
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    with DATASET_PATH.open(encoding='utf-8') as f:
        examples = [json.loads(l) for l in f if l.strip()]

    stats = Counter()
    changed = 0

    for ex in examples:
        code = ex.get('output', '')
        if not is_pure_aiken(code):
            continue

        original = code
        code = fix_cycle_aliases(code)
        code = fix_slash_in_types(code)
        code = fix_typography(code)

        if code != original:
            ex['output'] = code
            changed += 1

            if fix_cycle_aliases(original) != original:
                stats['cycle_alias'] += 1
            if fix_slash_in_types(original) != original:
                stats['slash_in_type'] += 1
            if fix_typography(original) != original:
                stats['typography'] += 1

    print(f"Examples changed : {changed}")
    print(f"  cycle aliases  : {stats['cycle_alias']}")
    print(f"  slash in type  : {stats['slash_in_type']}")
    print(f"  typography     : {stats['typography']}")

    if changed > 0:
        backup = DATASET_PATH.with_suffix('.jsonl' + BACKUP_SUFFIX)
        shutil.copy2(DATASET_PATH, backup)
        print(f"Backup           : {backup.name}")

        with DATASET_PATH.open('w', encoding='utf-8') as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + '\n')
        print(f"Saved            : {DATASET_PATH.name}")
    else:
        print("No changes needed.")


if __name__ == '__main__':
    main()
