#!/usr/bin/env python3
"""
add_property_tests.py
Retroactively adds aiken-fuzz property tests to existing dataset examples
that already have unit test blocks and helper functions.

Approach:
  1. Parse each example for helper fn signatures + existing test names
  2. Classify helpers by return type and name pattern
  3. Generate property tests based on the pattern
  4. Verify the augmented code compiles with aiken check
  5. Save passing examples back to dataset

Usage:
  python3 scripts/add_property_tests.py --dry-run --sample 20
  python3 scripts/add_property_tests.py --source with_tests_examples --all
  python3 scripts/add_property_tests.py --all --out logs/property_tests_report.json
"""

import re
import os
import sys
import json
import random
import argparse
import subprocess
import shutil
from pathlib import Path

ROOT         = Path(__file__).parent.parent
DATASET_PATH = ROOT / "data" / "processed" / "dataset_v23.jsonl"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
TIMEOUT_SECS = 45

# Max list length for fuzz — prevents timeout on sort/expand operations
MAX_LIST_LEN = 10


# ─────────────────────────────────────────────────────────────────────────────
# Aiken helpers
# ─────────────────────────────────────────────────────────────────────────────

def aiken_check(code: str) -> tuple[bool, str]:
    SANDBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    aiken_bin = os.path.expanduser("~/.aiken/bin/aiken")
    aiken_cmd = aiken_bin if os.path.exists(aiken_bin) else "aiken"
    try:
        result = subprocess.run(
            [aiken_cmd, "check", "--max-success", "100"],
            cwd=SANDBOX_DIR,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECS,
        )
        output = (result.stdout + result.stderr).strip()
        lines = [l for l in output.splitlines() if not l.strip().startswith("Compiling")]
        return result.returncode == 0, "\n".join(lines)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError:
        return False, "aiken not found"


# ─────────────────────────────────────────────────────────────────────────────
# Code parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_helpers(code: str) -> list[dict]:
    """Extract non-validator fn definitions with their signatures."""
    helpers = []
    pattern = re.compile(
        r'^(pub )?fn\s+(\w+)\s*\(([^)]{0,200})\)\s*->\s*([\w<>\s,()\[\]]+)',
        re.MULTILINE
    )
    SKIP = {'spend', 'mint', 'withdraw', 'publish', 'else', 'vote', 'propose'}
    for m in pattern.finditer(code):
        name = m.group(2)
        if name in SKIP:
            continue
        helpers.append({
            'name':     name,
            'args_raw': m.group(3).strip(),
            'ret':      m.group(4).strip(),
            'pub':      bool(m.group(1)),
        })
    return helpers


def classify_helper(h: dict) -> str:
    name = h['name'].lower()
    ret  = h['ret']
    if ret == 'Int':
        if any(w in name for w in [
            'count','conteo','contar','size','length','suma','sum',
            'product','producto','max','min','total','score','weight',
            'cantidad','maximo','minimo','weighted','dot','ponderada',
            'positivos_unicos',
        ]):
            return 'int_aggregator'
        return 'int_fn'
    if ret == 'Bool':
        if any(w in name for w in [
            'has','is_','check','tiene','es_','all_','every',
            'contiene','ninguno','empty','vacio','sorted','duplicates',
            'sorted','is_sorted','is_already',
        ]):
            return 'bool_predicate'
        return 'bool_fn'
    if ret.startswith('Option'):
        return 'option_fn'
    if ret.startswith('List'):
        return 'list_fn'
    if 'Dict' in ret:
        return 'dict_fn'
    return 'other'


def get_existing_test_names(code: str) -> set:
    return set(re.findall(r'^\s*test\s+(\w+)', code, re.MULTILINE))


# ─────────────────────────────────────────────────────────────────────────────
# Fuzzer inference — the key improvement
# ─────────────────────────────────────────────────────────────────────────────

# Name-based heuristics to choose better fuzzers
NAME_FUZZ_HINTS = {
    # int args that must be positive/bounded
    'nivel':   'fuzz.int_between(1, 20)',   # log2(0) undefined
    'level':   'fuzz.int_between(0, 20)',
    'n':       f'fuzz.int_between(0, {MAX_LIST_LEN})',
    'indice':  f'fuzz.int_between(0, {MAX_LIST_LEN})',
    'index':   f'fuzz.int_between(0, {MAX_LIST_LEN})',
    'offset':  f'fuzz.int_between(0, {MAX_LIST_LEN})',
    'size':    f'fuzz.int_between(1, {MAX_LIST_LEN})',
    'tamano':  f'fuzz.int_between(1, {MAX_LIST_LEN})',
    'tamanio': f'fuzz.int_between(1, {MAX_LIST_LEN})',
    'times':   f'fuzz.int_between(1, 5)',
    'count':   f'fuzz.int_between(0, {MAX_LIST_LEN})',
    'min':     'fuzz.int_between(0, 1000)',
    'minimo':  'fuzz.int_between(0, 1000)',
    'max':     'fuzz.int_between(0, 1000)',
    'maximo':  'fuzz.int_between(0, 1000)',
    'tokens':  'fuzz.int_between(0, 10000)',
    'amount':  'fuzz.int_between(0, 10000)',
    'monto':   'fuzz.int_between(0, 10000)',
    'price':   'fuzz.int_between(1, 10000)',
    'precio':  'fuzz.int_between(1, 10000)',
    'threshold': 'fuzz.int_between(0, 1000)',
    'umbral':  'fuzz.int_between(0, 1000)',
}

# Name-based heuristics for list args
LIST_FUZZ_HINTS = {
    # functions known to be slow with large inputs
    'sort':    f'fuzz.list_between(fuzz.int(), 0, {MAX_LIST_LEN})',
    'expand':  f'fuzz.list_between(fuzz.int(), 0, 5)',
    'flat':    f'fuzz.list_between(fuzz.int(), 0, 5)',
}


def type_to_fuzzer(arg_name: str, arg_type: str, fn_name: str = '') -> str | None:
    """
    Convert an Aiken type to a fuzzer expression.
    Uses name hints to pick better fuzzers (bounded ints, short lists).
    """
    t = arg_type.strip()
    name_lower = arg_name.lower()
    fn_lower   = fn_name.lower()

    # Int — check name hints first
    if t == 'Int':
        for hint, fuzzer in NAME_FUZZ_HINTS.items():
            if hint in name_lower:
                return fuzzer
        return 'fuzz.int()'

    # Bool
    if t == 'Bool':
        return 'fuzz.bool()'

    # ByteArray
    if t == 'ByteArray':
        if any(w in name_lower for w in ['tamano','size','indice','offset']):
            return f'fuzz.bytearray_between(1, {MAX_LIST_LEN})'
        return f'fuzz.bytearray_between(0, 32)'

    # Lovelace (= Int but always non-negative)
    if t == 'Lovelace':
        return 'fuzz.int_at_least(0)'

    # Cardano scalar types — EXACT match first to avoid matching List<X>
    if t == 'VerificationKeyHash':
        return 'cfuzz.verification_key_hash()'
    if t == 'ScriptHash':
        return 'cfuzz.script_hash()'
    if t == 'PolicyId':
        return 'cfuzz.policy_id()'
    if t == 'AssetName':
        return 'cfuzz.asset_name()'
    if t in ('Address', 'cardano/address.Address'):
        return 'cfuzz.address()'
    if t in ('OutputReference', 'cardano/transaction.OutputReference'):
        return 'cfuzz.output_reference()'
    if t in ('Credential', 'cardano/address.Credential'):
        return 'cfuzz.credential()'
    if t in ('Input', 'cardano/transaction.Input'):
        return 'cfuzz.input()'
    if t in ('Output', 'cardano/transaction.Output'):
        return 'cfuzz.output()'
    if t in ('Value', 'assets.Value', 'cardano/assets.Value'):
        return 'cfuzz.lovelace()'

    # Generic List<X> — recurse into element type
    if t.startswith('List<') and t.endswith('>'):
        inner = t[5:-1]
        # Slow functions: use hint-based bounds
        if inner == 'Int':
            for hint, fuzzer in LIST_FUZZ_HINTS.items():
                if hint in fn_lower:
                    return fuzzer
            return f'fuzz.list_between(fuzz.int(), 0, {MAX_LIST_LEN})'
        inner_fuzz = type_to_fuzzer(arg_name, inner, fn_name)
        if inner_fuzz:
            return f'fuzz.list_between({inner_fuzz}, 0, {MAX_LIST_LEN})'
        return None

    # Generic Option<X> — recurse into inner type
    if t.startswith('Option<') and t.endswith('>'):
        inner = t[7:-1]
        inner_fuzz = type_to_fuzzer(arg_name, inner, fn_name)
        if inner_fuzz:
            return f'fuzz.option({inner_fuzz})'
        return None

    return None  # Can't handle


def infer_arg_fuzzers(args_raw: str, fn_name: str = '') -> list[tuple[str, str]] | None:
    """
    Parse args string and infer fuzzer for each.
    Returns list of (arg_name, fuzzer_expr) or None if any arg is unhandleable.
    """
    if not args_raw.strip():
        return []

    result = []
    # Split on comma, but not inside <> brackets
    parts = re.split(r',\s*(?![^<>]*>)', args_raw)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if ':' in part:
            arg_name, arg_type = part.split(':', 1)
            arg_name = arg_name.strip()
            arg_type = arg_type.strip()
        else:
            arg_name = f'arg{len(result)}'
            arg_type = part.strip()

        fuzzer = type_to_fuzzer(arg_name, arg_type, fn_name)
        if fuzzer is None:
            return None
        result.append((arg_name, fuzzer))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Import management
# ─────────────────────────────────────────────────────────────────────────────

def ensure_import(code: str, import_line: str) -> str:
    if import_line in code:
        return code
    lines = code.splitlines()
    last_use = -1
    for i, l in enumerate(lines):
        if l.startswith('use '):
            last_use = i
    if last_use >= 0:
        lines.insert(last_use + 1, import_line)
    else:
        lines.insert(0, import_line)
    return '\n'.join(lines)


def needs_cardano_fuzz(args: list[tuple[str, str]]) -> bool:
    return any('cfuzz.' in f for _, f in args)


def needs_list_import(test_code: str) -> bool:
    return 'list.length(' in test_code


# ─────────────────────────────────────────────────────────────────────────────
# Property test generators — one per pattern
# ─────────────────────────────────────────────────────────────────────────────

def build_test_body(name: str, args: list[tuple[str, str]], assertion: str) -> str:
    """
    Build a complete test block using fuzz.both/tuple for multiple args.
    assertion uses the arg names and fn name directly.
    """
    if not args:
        return f'{assertion}'

    if len(args) == 1:
        arg_name, fuzzer = args[0]
        via   = fuzzer
        param = f'{arg_name} via {via}'
        setup = ''
        call_args = arg_name
    elif len(args) == 2:
        (n1, f1), (n2, f2) = args
        param = f'vals via fuzz.both({f1}, {f2})'
        setup = f'let ({n1}, {n2}) = vals\n  '
        call_args = f'{n1}, {n2}'
    elif len(args) == 3:
        (n1, f1), (n2, f2), (n3, f3) = args
        param = f'vals via fuzz.tuple3({f1}, {f2}, {f3})'
        setup = f'let ({n1}, {n2}, {n3}) = vals\n  '
        call_args = f'{n1}, {n2}, {n3}'
    elif len(args) == 4:
        (n1, f1), (n2, f2), (n3, f3), (n4, f4) = args
        param = f'vals via fuzz.tuple4({f1}, {f2}, {f3}, {f4})'
        setup = f'let ({n1}, {n2}, {n3}, {n4}) = vals\n  '
        call_args = f'{n1}, {n2}, {n3}, {n4}'
    else:
        return None  # too many args

    filled = assertion.replace('CALL', f'{name}({call_args})')
    for n, _ in args:
        filled = filled.replace(f'ARG_{n}', n)

    return f'test PROP_NAME({param}) {{\n  {setup}{filled}\n}}'


def gen_properties(h: dict, existing_tests: set) -> list[str]:
    """Main dispatcher — generate all applicable property tests for a helper."""
    name  = h['name']
    kind  = classify_helper(h)
    args  = infer_arg_fuzzers(h['args_raw'], fn_name=name)

    if args is None or len(args) > 4:
        return []

    tests = []

    # ── int_aggregator: result >= 0 for non-negative inputs ──────────────────
    if kind == 'int_aggregator':
        name_lower = name.lower()

        # Skip functions whose result can be negative by design or use math builtins
        # with domain restrictions (log2, pow2 need positive inputs)
        SKIP_NON_NEG = [
            'negativ','dot_product','weighted','ponderada','indice','indexed',
            'log','pow','nivel','level','reward','recompensa','borrow','votes',
            'votos','collateral','colateral','ratio','interest','interes',
            'segmento','segment',
        ]
        if any(w in name_lower for w in SKIP_NON_NEG):
            return tests

        prop = f'prop_{name}_non_negative'
        if prop not in existing_tests:
            # Use non-negative fuzzers for ALL int args (list elements too)
            safe_args = []
            for arg_name, fuzzer in args:
                if fuzzer == 'fuzz.int()':
                    safe_args.append((arg_name, 'fuzz.int_at_least(0)'))
                elif fuzzer.startswith('fuzz.list_between(fuzz.int()'):
                    safe_args.append((arg_name, f'fuzz.list_between(fuzz.int_at_least(0), 0, {MAX_LIST_LEN})'))
                elif fuzzer.startswith('fuzz.list(fuzz.int()'):
                    safe_args.append((arg_name, f'fuzz.list_between(fuzz.int_at_least(0), 0, {MAX_LIST_LEN})'))
                # den args must be > 0 to avoid division by zero
                elif arg_name in ('den','denominator','ratio_den','min_ratio_den'):
                    safe_args.append((arg_name, 'fuzz.int_at_least(1)'))
                else:
                    safe_args.append((arg_name, fuzzer))
            body = build_test_body(name, safe_args, 'CALL >= 0')
            if body:
                tests.append(body.replace('PROP_NAME', prop))

    # ── bool_predicate ────────────────────────────────────────────────────────
    elif kind == 'bool_predicate':
        name_lower = name.lower()

        # is_sorted / is_already_sorted: empty → True, singleton → True
        if 'sorted' in name_lower and len(args) == 1:
            prop = f'prop_{name}_empty_is_sorted'
            if prop not in existing_tests:
                tests.append(f'test {prop}() {{\n  {name}([]) == True\n}}')
            prop2 = f'prop_{name}_singleton_is_sorted'
            if prop2 not in existing_tests:
                # Extract element fuzzer from list fuzzer: fuzz.list_between(X, min, max) → X
                # Must count parens to handle fuzz.bytearray_between(0, 16) correctly
                _, list_fuzzer = args[0]
                elem_fuzzer = 'fuzz.int()'
                prefix = 'fuzz.list_between('
                if list_fuzzer.startswith(prefix):
                    rest = list_fuzzer[len(prefix):]
                    depth, i = 0, 0
                    for i, c in enumerate(rest):
                        if c == '(':
                            depth += 1
                        elif c == ')':
                            depth -= 1
                        elif c == ',' and depth == 0:
                            elem_fuzzer = rest[:i].strip()
                            break
                tests.append(
                    f'test {prop2}(x via {elem_fuzzer}) {{\n'
                    f'  {name}([x]) == True\n}}'
                )

        # has_no_duplicates: singleton always has no duplicates
        elif 'duplicate' in name_lower and len(args) == 1:
            prop = f'prop_{name}_singleton_no_duplicates'
            if prop not in existing_tests:
                tests.append(
                    f'test {prop}(x via fuzz.int()) {{\n'
                    f'  {name}([x]) == True\n}}'
                )

        # General: empty list → False for membership/has checks
        # Only generate if the function takes exactly 1 list arg (to avoid arity mismatch)
        elif any(w in name_lower for w in ['has','contiene','is_allowed','authorized','in_']):
            prop = f'prop_{name}_empty_false'
            if prop not in existing_tests and len(args) == 1:
                arg_name, fuzzer = args[0]
                if 'list' in fuzzer.lower():
                    tests.append(f'test {prop}() {{\n  {name}([]) == False\n}}')

    # ── list_fn: length of result <= length of input ─────────────────────────
    elif kind == 'list_fn':
        name_lower = name.lower()

        # zip_lists: length(zip(a,b)) == min(length(a), length(b))
        # Use same-length lists to make property deterministic
        if 'zip' in name_lower and len(args) == 2:
            prop = f'prop_{name}_same_length_input'
            if prop not in existing_tests:
                (n1, f1), (n2, f2) = args
                # Generate same list twice to ensure equal length
                tests.append(
                    f'test {prop}({n1} via fuzz.list_between(fuzz.int(), 0, {MAX_LIST_LEN})) {{\n'
                    f'  list.length({name}({n1}, {n1})) == list.length({n1})\n}}'
                )
            return tests

        # expand/flat_map: result is LONGER than input — skip length_bounded
        if any(w in name_lower for w in ['expand','flat_map','flatmap']):
            # Only safe property: empty input → empty result
            prop = f'prop_{name}_empty_input_empty_result'
            if prop not in existing_tests and len(args) >= 1:
                if len(args) == 1:
                    arg_name, _ = args[0]
                    tests.append(
                        f'test {prop}() {{\n'
                        f'  {name}([]) == []\n}}'
                    )
                elif len(args) >= 2:
                    # second arg assumed to be a multiplier/times Int
                    arg_name, _ = args[0]
                    tests.append(
                        f'test {prop}() {{\n'
                        f'  {name}([], 1) == []\n}}'
                    )
            return tests

        # concat: length(a ++ b) == length(a) + length(b)
        if 'concat' in name_lower and len(args) == 2:
            prop = f'prop_{name}_length_sum'
            if prop not in existing_tests:
                (n1, f1), (n2, f2) = args
                body = build_test_body(name, args,
                    f'list.length(CALL) == list.length({n1}) + list.length({n2})')
                if body:
                    tests.append(body.replace('PROP_NAME', prop))
            return tests

        # indexed_map / label functions: output length == input length
        # Note: 'indexed' alone is NOT enough — even_indexed_* are filters, not maps
        if any(w in name_lower for w in ['label','map']) or re.search(r'indexed.map|map.indexed', name_lower):
            prop = f'prop_{name}_preserves_length'
            if prop not in existing_tests and len(args) == 1:
                arg_name, fuzzer = args[0]
                if 'list' in fuzzer.lower():
                    body = build_test_body(name, args,
                        f'list.length(CALL) == list.length({arg_name})')
                    if body:
                        tests.append(body.replace('PROP_NAME', prop))
            return tests

        prop = f'prop_{name}_length_bounded'
        if prop not in existing_tests and len(args) >= 1:
            arg_name, fuzzer = args[0]
            if 'list' not in fuzzer.lower():
                return tests

            if len(args) == 1:
                body = build_test_body(name, args,
                    f'list.length(CALL) <= list.length({arg_name})')
                if body:
                    tests.append(body.replace('PROP_NAME', prop))

            elif len(args) == 2:
                (n1, f1), (n2, f2) = args
                # Only if second arg is not a list (pure filter pattern)
                if 'list' not in f2.lower():
                    body = build_test_body(name, args,
                        f'list.length(CALL) <= list.length({n1})')
                    if body:
                        tests.append(body.replace('PROP_NAME', prop))

    # ── bool_fn: only safe universal properties (skip ambiguous ones) ────────
    elif kind == 'bool_fn':
        # Don't generate properties for generic bool fns — too many false counterexamples
        # Only handle well-known patterns:
        name_lower = name.lower()
        if any(w in name_lower for w in ['segmentos_iguales','segments_equal']):
            # segmentos_iguales(x, x, i, t) is always True (reflexivity)
            prop = f'prop_{name}_reflexive'
            if prop not in existing_tests and len(args) == 4:
                (n1, f1), (n2, f2), (n3, f3), (n4, f4) = args
                safe = [
                    (n1, 'fuzz.bytearray_between(4, 32)'),
                    (n3, f'fuzz.int_between(0, 3)'),
                    (n4, f'fuzz.int_between(1, 4)'),
                ]
                tests.append(
                    f'test {prop}(vals via fuzz.tuple3(fuzz.bytearray_between(4, 32), fuzz.int_between(0, 3), fuzz.int_between(1, 4))) {{\n'
                    f'  let (data, idx, sz) = vals\n'
                    f'  {name}(data, data, idx, sz) == True\n}}'
                )

    # ── option_fn: Some on non-empty list, None on empty ─────────────────────
    elif kind == 'option_fn':
        name_lower = name.lower()
        # Only generate for functions that take a single List<Int> — type inference is safe
        if (any(w in name_lower for w in ['ultimo','last','head','first'])
                and len(args) == 1):
            arg_name, fuzzer = args[0]
            if 'list' not in fuzzer.lower():
                return tests

            # Empty list → None: use option.is_none() to avoid type annotation issues
            prop = f'prop_{name}_empty_is_none'
            if prop not in existing_tests:
                tests.append(
                    f'test {prop}() {{\n'
                    f'  option.is_none({name}([]))\n}}'
                )
                # Ensure option import
                # (handled by caller via 'use aiken/option' detection)

            # Singleton → Some: use option.is_some()
            # Skip if elements are Option<X> — [None] would make result None
            prop2 = f'prop_{name}_singleton_is_some'
            if prop2 not in existing_tests:
                # Count-paren-aware extraction of element fuzzer
                prefix = 'fuzz.list_between('
                inner = 'fuzz.int()'
                if fuzzer.startswith(prefix):
                    rest = fuzzer[len(prefix):]
                    depth = 0
                    for ci, c in enumerate(rest):
                        if c == '(':
                            depth += 1
                        elif c == ')':
                            depth -= 1
                        elif c == ',' and depth == 0:
                            inner = rest[:ci].strip()
                            break
                # Don't generate if elements are themselves Options
                if 'fuzz.option' not in inner:
                    tests.append(
                        f'test {prop2}(x via {inner}) {{\n'
                        f'  option.is_some({name}([x]))\n}}'
                    )

        # find_* functions take 2 args — skip None comparison (arity issue)
        elif 'find' in name_lower:
            pass  # too ambiguous to generate safely

    # ── bytearray segment fn ─────────────────────────────────────────────────
    # Skip: segmento(datos, indice, tamano) can panic if indice+tamano > length(datos)
    # The safe property would need such_that which is slow — skip entirely
    elif kind == 'other':
        pass  # Don't attempt properties for 'other' type functions

    return tests


# ─────────────────────────────────────────────────────────────────────────────
# Augment one example
# ─────────────────────────────────────────────────────────────────────────────

def generate_properties_for_example(code: str) -> str | None:
    # Skip markdown-wrapped examples (explanations, not pure Aiken source)
    if '```' in code:
        return None
    helpers = parse_helpers(code)
    if not helpers:
        return None

    existing  = get_existing_test_names(code)
    new_tests = []
    use_cfuzz  = False
    use_list   = False
    use_option = False

    for h in helpers:
        props = gen_properties(h, existing)
        for p in props:
            args = infer_arg_fuzzers(h['args_raw'], fn_name=h['name']) or []
            if needs_cardano_fuzz(args):
                use_cfuzz = True
            if 'list.length' in p:
                use_list = True
            if 'option.is_none' in p or 'option.is_some' in p:
                use_option = True
            new_tests.append(p)

    if not new_tests:
        return None

    augmented = ensure_import(code, 'use aiken/fuzz')
    if use_cfuzz:
        augmented = ensure_import(augmented, 'use cardano/fuzz as cfuzz')
    if use_list and 'use aiken/collection/list' not in augmented:
        augmented = ensure_import(augmented, 'use aiken/collection/list')
    if use_option and 'use aiken/option' not in augmented:
        augmented = ensure_import(augmented, 'use aiken/option')
    if 'bytearray.length' in '\n'.join(new_tests) and 'use aiken/primitive/bytearray' not in augmented:
        augmented = ensure_import(augmented, 'use aiken/primitive/bytearray')
    # Fix pre-existing missing imports in source code
    if re.search(r'\bbytearray\.', augmented) and 'use aiken/primitive/bytearray' not in augmented:
        augmented = ensure_import(augmented, 'use aiken/primitive/bytearray')
    if re.search(r'\bDict<', augmented) and 'use aiken/collection/dict' in augmented:
        # Ensure Dict type is explicitly imported
        augmented = re.sub(
            r'^(use aiken/collection/dict)$',
            r'use aiken/collection/dict.{Dict}',
            augmented, flags=re.MULTILINE
        )

    augmented = augmented.rstrip() + '\n\n' + '\n\n'.join(new_tests) + '\n'
    return augmented


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default=str(DATASET_PATH))
    parser.add_argument('--source',  default=None)
    parser.add_argument('--sample',  type=int, default=50)
    parser.add_argument('--all',     action='store_true')
    parser.add_argument('--seed',    type=int, default=42)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--out',     default=None)
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    examples = []
    with dataset_path.open(encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    def has_helpers(code: str) -> bool:
        return bool(re.search(r'^(pub )?fn\s+\w+\s*\(', code, re.MULTILINE))

    candidates = [
        ex for ex in examples
        if (re.search(r'^\s*test\s+\w+', ex.get('output',''), re.MULTILINE)
            or has_helpers(ex.get('output','')))
        and (args.source is None or ex.get('source') == args.source)
    ]

    if not args.all:
        random.seed(args.seed)
        candidates = random.sample(candidates, min(args.sample, len(candidates)))

    print(f'Candidates (tests or helpers): {len(candidates)}')

    generated = 0
    compiled  = 0
    failed    = 0
    skipped   = 0
    results   = []

    instr_to_idx = {ex['instruction']: i for i, ex in enumerate(examples)}

    for i, ex in enumerate(candidates, 1):
        code      = ex.get('output', '')
        augmented = generate_properties_for_example(code)

        if augmented is None:
            skipped += 1
            print(f'[{i:4d}/{len(candidates)}] ⬜  {ex["source"]:<25} | {ex["instruction"][:55]}')
            continue

        old_count = len(get_existing_test_names(code))
        new_count = len(get_existing_test_names(augmented)) - old_count

        ok, error = aiken_check(augmented)
        if ok:
            compiled  += 1
            generated += new_count
            symbol = '✅'
            if not args.dry_run:
                idx = instr_to_idx.get(ex['instruction'])
                if idx is not None:
                    examples[idx]['output'] = augmented
        else:
            failed += 1
            symbol = '❌'
            if args.verbose:
                for line in error.splitlines()[:4]:
                    if line.strip():
                        print(f'      {line.strip()[:120]}')

        print(f'[{i:4d}/{len(candidates)}] {symbol}  {ex["source"]:<25} | +{new_count} props | {ex["instruction"][:50]}')

        results.append({
            'source':      ex['source'],
            'instruction': ex['instruction'][:120],
            'ok':          ok,
            'new_tests':   new_count if ok else 0,
            'error':       error[:400] if not ok else '',
        })

    print()
    print('═' * 65)
    print(f'  Candidates  : {len(candidates)}')
    print(f'  Skipped     : {skipped}  (no patterns found)')
    print(f'  Compiled ✅ : {compiled}  ({generated} new property tests)')
    print(f'  Failed   ❌ : {failed}')
    print('═' * 65)

    if not args.dry_run and compiled > 0:
        backup = dataset_path.with_suffix('.jsonl.pre_props_backup')
        if not backup.exists():
            shutil.copy2(dataset_path, backup)
            print(f'  Backup → {backup.name}')
        with dataset_path.open('w', encoding='utf-8') as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + '\n')
        print(f'  Dataset updated: {dataset_path.name}')
    elif args.dry_run:
        print('  [dry-run] no changes written')

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open('w', encoding='utf-8') as f:
            json.dump({'results': results, 'generated': generated,
                       'compiled': compiled, 'failed': failed}, f, indent=2)
        print(f'  Report → {out_path}')


if __name__ == '__main__':
    main()
