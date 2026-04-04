#!/usr/bin/env python3
"""
generate_with_tests.py — Cardumen Forge

Generates VERIFIED Aiken v3 examples where EVERY output includes:
  - Named helper functions
  - A validator that uses those helpers
  - 3-5 test blocks that unit-test the helpers directly

Targets stdlib areas underrepresented in the dataset:
  dict ops, pairs ops, list advanced, math, bytearray bitwise

Deduplication: skips generation for any topic already present in the dataset.

Usage:
    python3 scripts/generate/generate_with_tests.py --dry-run
    python3 scripts/generate/generate_with_tests.py --apply --count 4
    python3 scripts/generate/generate_with_tests.py --apply --count 4 --topics dict_ops math_ops
"""

import os
import re
import json
import time
import shutil
import argparse
import subprocess
import pty
import select
from pathlib import Path

import anthropic

ROOT         = Path(__file__).parent.parent.parent
DATASET      = ROOT / "data" / "processed" / "dataset_v22.jsonl"
OUT_FILE     = ROOT / "data" / "processed" / "components" / "with_tests_examples.jsonl"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30


# ── Topic definitions ────────────────────────────────────────────────────────

PATTERNS = [
    {
        "id": "dict_ops",
        "topic": "aiken/collection/dict",
        "description": "Dict helpers: insert, delete, get, has_key, merge, filter, map, size",
        "prompt": """\
Generate {{count}} Aiken v3 mint or spend validators that use helper functions built on
`aiken/collection/dict`. Each validator must:
  - Define 1-3 named helper fns that use dict operations (insert, delete, get, has_key,
    merge, union, filter, map, foldl, size, keys, values, to_pairs, from_pairs)
  - Use the helper in the validator body
  - Include 3-5 test blocks that unit-test the helpers with concrete ByteArray/Int literals

Dict API reminders:
  dict.empty                                    -- const, no parens
  dict.insert(d, key: ByteArray, val)           -- 2 args after self, NO compare fn
  dict.delete(d, key: ByteArray)
  dict.get(d, key: ByteArray) -> Option<v>
  dict.has_key(d, key: ByteArray) -> Bool
  dict.size(d) -> Int
  dict.union(a, b)                              -- merge, left-biased
  dict.filter(d, fn(k, v) -> Bool)
  dict.map(d, fn(k, v) -> w)
  dict.foldl(d, init, fn(k, v, acc) -> acc)
  dict.keys(d) -> List<ByteArray>
  dict.values(d) -> List<v>
  dict.to_pairs(d) -> Pairs<ByteArray, v>
  dict.from_pairs(pairs) -> Dict<k, v>          -- DOES exist

Half in English, half in Spanish.
""",
    },
    {
        "id": "pairs_ops",
        "topic": "aiken/collection/pairs",
        "description": "Pairs helpers: get_first, get_all, has_key, keys, values, delete_first, foldl",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helper functions that use `aiken/collection/pairs`.
Pairs<k,v> = List<Pair<k,v>>. Use:
  pairs.get_first(ps, key: k) -> Option<v>
  pairs.get_all(ps, key: k) -> List<v>
  pairs.has_key(ps, k: k) -> Bool
  pairs.keys(ps) -> List<k>
  pairs.values(ps) -> List<v>
  pairs.delete_first(ps, key: k)
  pairs.foldl(ps, init, fn(k, v, acc) -> acc)

Each example must include helper fns AND 3-5 test blocks with concrete values.
Pairs literals: [Pair(#"aabb", 1), Pair(#"ccdd", 2)]

Half in English, half in Spanish.
""",
    },
    {
        "id": "list_advanced",
        "topic": "aiken/collection/list/advanced",
        "description": "Advanced list: partition, zip, map2, indexed_map, foldl2, reduce, unique",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers that use ADVANCED list functions.
EXACT SIGNATURES (use these precisely):
  list.partition(xs: List<a>, predicate: fn(a) -> Bool) -> (List<a>, List<a>)
  list.span(xs: List<a>, n: Int) -> (List<a>, List<a>)   -- split at index n, NOT a predicate
  list.zip(a: List<a>, b: List<b>) -> List<(a, b)>
  list.map2(a: List<a>, b: List<b>, with: fn(a, b) -> c) -> List<c>
  list.indexed_map(xs: List<a>, with: fn(Int, a) -> b) -> List<b>
  list.foldl2(a: List<a>, b: List<b>, zero: c, with: fn(a, b, c) -> c) -> c
  list.reduce(xs: List<a>, zero: b, with: fn(b, a) -> b) -> b   -- like foldl with zero
  list.unique(xs: List<a>) -> List<a>

TUPLE DESTRUCTURING: use `let (left, right) = list.partition(...)` or `let (a, b) = list.span(...)`

Each must have helper fns + 3-5 test blocks with inline literal lists.
Test with concrete values: [1, 2, 3], [#"aa", #"bb"], etc.

Half in English, half in Spanish.
""",
    },
    {
        "id": "math_ops",
        "topic": "aiken/math",
        "description": "Math helpers: pow, sqrt, log, gcd, clamp, abs using aiken/math",
        "prompt": """\
Generate {{count}} Aiken v3 validators where helpers use `aiken/math`.
EXACT SIGNATURES:
  math.pow(self: Int, e: Int) -> Int
  math.pow2(e: Int) -> Int
  math.sqrt(self: Int) -> Option<Int>    -- returns Option<Int>, must unwrap with when/expect
  math.is_sqrt(self: Int, x: Int) -> Bool
  math.log(self: Int, base: Int) -> Int
  math.log2(x: Int) -> Int
  math.gcd(x: Int, y: Int) -> Int
  math.abs(self: Int) -> Int
  math.clamp(self: Int, min: Int, max: Int) -> Int
  math.min(a: Int, b: Int) -> Int
  math.max(a: Int, b: Int) -> Int

IMPORTANT: math.sqrt returns Option<Int> — unwrap: `when math.sqrt(n) is { Some(s) -> s | None -> 0 }`
AVOID: math.sqrt — prefer math.pow, math.gcd, math.abs, math.clamp for simpler tests.

Build validators for price calculations, thresholds, or supply logic.
Each must have helper fns + 3-5 test blocks with concrete Int values.

Half in English, half in Spanish.
""",
    },
    {
        "id": "bytearray_bitwise",
        "topic": "aiken/primitive/bytearray/bitwise",
        "description": "Bytearray bitwise ops: and_bytes, or_bytes, xor_bytes, test_bit",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers using bytearray bitwise operations.
EXACT SIGNATURES — note the 3-argument bitwise functions:
  bytearray.and_bytes(left: ByteArray, right: ByteArray, pad_end: Bool) -> ByteArray
  bytearray.or_bytes(left: ByteArray, right: ByteArray, pad_end: Bool) -> ByteArray
  bytearray.xor_bytes(left: ByteArray, right: ByteArray, pad_end: Bool) -> ByteArray
  bytearray.test_bit(self: ByteArray, ix: Int) -> Bool
  bytearray.push(self: ByteArray, byte: Int) -> ByteArray   -- Byte = Int alias

The `pad_end: Bool` arg: True = pad shorter input at end, False = pad at start.

Use cases: bitmask permissions, flag checking, compact encoding.
Each must have helper fns + 3-5 test blocks.
Test examples:
  bytearray.and_bytes(#"ff", #"0f", False) == #"0f"
  bytearray.or_bytes(#"f0", #"0f", False) == #"ff"
  bytearray.xor_bytes(#"ff", #"ff", False) == #"00"
  bytearray.test_bit(#"80", 0) == True   -- MSB of 0x80 is 1

Half in English, half in Spanish.
""",
    },
    {
        "id": "rational_math",
        "topic": "aiken/math/rational",
        "description": "Rational arithmetic helpers for price/ratio/percentage calculations",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers using `aiken/math/rational`.
IMPORT: `use aiken/math/rational.{{Rational}}` — MUST import Rational explicitly.
EXACT SIGNATURES:
  rational.new(numerator: Int, denominator: Int) -> Option<Rational>
  rational.from_int(numerator: Int) -> Rational
  rational.numerator(self: Rational) -> Int
  rational.denominator(self: Rational) -> Int
  rational.add(left: Rational, right: Rational) -> Rational
  rational.sub(left: Rational, right: Rational) -> Rational
  rational.mul(left: Rational, right: Rational) -> Rational
  rational.floor(self: Rational) -> Int
  rational.ceil(self: Rational) -> Int
  rational.truncate(self: Rational) -> Int

IMPORTANT: rational.new returns Option<Rational>. Construct with:
  expect Some(r) = rational.new(3, 4)
DO NOT use: rational.to_int (doesn't exist), rational.compare without Ordering import.
USE: rational.floor(r) to get Int from Rational.

Use cases: fee % calculations, ratio checks, price oracle thresholds.
Each must have helper fns + 3-5 test blocks.

Half in English, half in Spanish.
""",
    },
    {
        "id": "bytearray_conversion",
        "topic": "aiken/primitive/bytearray/conversion",
        "description": "Bytearray encoding: from_int, to_int, starts_with, slice, is_empty",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers using bytearray encoding/conversion.
EXACT SIGNATURES:
  bytearray.from_int_big_endian(self: Int, size: Int) -> ByteArray
  bytearray.to_int_big_endian(self: ByteArray) -> Int
  bytearray.from_int_little_endian(self: Int, size: Int) -> ByteArray
  bytearray.to_int_little_endian(self: ByteArray) -> Int
  bytearray.starts_with(self: ByteArray, prefix: ByteArray) -> Bool
  bytearray.slice(self: ByteArray, start: Int, end: Int) -> ByteArray
  bytearray.is_empty(self: ByteArray) -> Bool
  bytearray.length(self: ByteArray) -> Int
  bytearray.drop(self: ByteArray, n: Int) -> ByteArray
  bytearray.take(self: ByteArray, n: Int) -> ByteArray

AVOID: bytearray.to_hex (returns String, harder to test), bytearray.index_of.
PREFER: from_int/to_int, starts_with, slice, length — easiest to test with literals.

Test examples:
  bytearray.from_int_big_endian(255, 1) == #"ff"
  bytearray.to_int_big_endian(#"0a") == 10
  bytearray.starts_with(#"000643b0aabb", #"000643b0") == True
  bytearray.length(#"aabbcc") == 3

Half in English, half in Spanish.
""",
    },
    {
        "id": "list_search",
        "topic": "aiken/collection/list/search",
        "description": "List search helpers: find, index_of, count, at, last, head",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers using list search/lookup functions:
  list.find(xs, fn(x) -> Bool) -> Option<a>
  list.index_of(xs, elem) -> Option<Int>
  list.count(xs, fn(x) -> Bool) -> Int
  list.at(xs, idx: Int) -> Option<a>
  list.last(xs) -> Option<a>
  list.head(xs) -> Option<a>
  list.tail(xs) -> Option<List<a>>

Build validators that look up signatories, check allowlists, or find specific outputs.
Test with concrete lists: [#"aabb", #"ccdd"], [1, 2, 3, 4], etc.
Each must have helper fns + 3-5 test blocks.

Half in English, half in Spanish.
""",
    },
    {
        "id": "option_ops",
        "topic": "aiken/option",
        "description": "Option combinators: map, and_then, or_else, is_some, is_none, flatten, choice",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers that use `aiken/option`.
EXACT SIGNATURES:
  option.is_none(self: Option<a>) -> Bool
  option.is_some(self: Option<a>) -> Bool
  option.map(self: Option<a>, with: fn(a) -> b) -> Option<b>
  option.and_then(self: Option<a>, then: fn(a) -> Option<b>) -> Option<b>
  option.or_else(self: Option<a>, default: a) -> a
  option.or_try(self: Option<a>, compute: fn() -> Option<a>) -> Option<a>
  option.flatten(opt: Option<Option<a>>) -> Option<a>
  option.choice(self: List<Option<a>>) -> Option<a>  -- first Some in list
  option.map2(opt_a, opt_b, with: fn(a, b) -> c) -> Option<c>

Use cases: safe lookups, chained optional validations, default fallback logic.
Tests use: Some(42), None, Some(#"aabb"), Some(True).

Half in English, half in Spanish.
""",
    },
    {
        "id": "interval_ops",
        "topic": "aiken/interval",
        "description": "Interval construction and checks: between, contains, intersection, hull, includes",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers that use `aiken/interval`.
CRITICAL: `Interval` is NOT a generic type — it has NO type parameter.
  WRONG: Interval<Int>   CORRECT: Interval

IMPORT: `use aiken/interval.{{Interval}}`
EXACT SIGNATURES (all return/take plain `Interval`, no generics):
  interval.after(lower_bound: Int) -> Interval
  interval.before(upper_bound: Int) -> Interval
  interval.between(lower_bound: Int, upper_bound: Int) -> Interval
  interval.entirely_between(lower_bound: Int, upper_bound: Int) -> Interval
  interval.contains(self: Interval, elem: Int) -> Bool
  interval.is_empty(self: Interval) -> Bool
  interval.is_entirely_after(self: Interval, point: Int) -> Bool
  interval.is_entirely_before(self: Interval, point: Int) -> Bool
  interval.hull(iv1: Interval, iv2: Interval) -> Interval
  interval.includes(self: Interval, other: Interval) -> Bool
  interval.intersection(iv1: Interval, iv2: Interval) -> Interval

Use cases: deadline checking, epoch validation, validity range verification.
Test examples (all correct — Interval is not generic):
  interval.contains(interval.between(10, 20), 15) == True
  interval.contains(interval.before(100), 50) == True
  interval.is_entirely_before(interval.between(5, 10), 20) == True
  interval.is_entirely_after(interval.after(100), 50) == False

Half in English, half in Spanish.
""",
    },
    {
        "id": "string_int_ops",
        "topic": "aiken/primitive/string",
        "description": "String and int primitive ops: concat, join, from_int, to_bytearray, int.compare",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers using string and int primitives.
EXACT SIGNATURES:
  string.from_bytearray(bytes: ByteArray) -> String    -- UTF-8 decode (use carefully)
  string.from_int(n: Int) -> String                    -- digit string
  string.concat(left: String, right: String) -> String
  string.join(list: List<String>, delimiter: String) -> String
  string.to_bytearray(self: String) -> ByteArray

  int.compare(left: Int, right: Int) -> Ordering       -- Less | Equal | Greater
  int.to_string(n: Int) -> String                      -- same as string.from_int

IMPORTS:
  use aiken/primitive/string as string_utils  OR  use aiken/primitive/string
  use aiken/primitive/int as int_utils        OR  use aiken/primitive/int

String literals in Aiken: @"hello"   (@ prefix)
Test examples:
  string.from_int(42) == @"42"
  string.concat(@"foo", @"bar") == @"foobar"
  string.join([@"a", @"b", @"c"], @"-") == @"a-b-c"
  int.compare(3, 5) == Less

Half in English, half in Spanish.
""",
    },
    {
        "id": "list_transform",
        "topic": "aiken/collection/list/transform",
        "description": "More list: filter_map, find_map, sort, unzip, take_while, drop_while, concat, difference",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers using more list transformation functions.
EXACT SIGNATURES:
  list.filter_map(xs: List<a>, with: fn(a) -> Option<b>) -> List<b>
  list.find_map(xs: List<a>, with: fn(a) -> Option<b>) -> Option<b>  -- first Some
  list.sort(xs: List<a>, compare: fn(a, a) -> Ordering) -> List<a>
  list.unzip(xs: List<(a, b)>) -> (List<a>, List<b>)
  list.take_while(xs: List<a>, predicate: fn(a) -> Bool) -> List<a>
  list.drop_while(xs: List<a>, predicate: fn(a) -> Bool) -> List<a>
  list.concat(left: List<a>, right: List<a>) -> List<a>
  list.difference(xs: List<a>, ys: List<a>) -> List<a>  -- xs minus ys
  list.flat_map(xs: List<a>, with: fn(a) -> List<b>) -> List<b>
  list.repeat(elem: a, count: Int) -> List<a>
  list.range(start: Int, end: Int) -> List<Int>  -- inclusive [start..end]

For sort: use `int.compare` from `aiken/primitive/int` as compare fn.
Test with concrete lists: [3,1,2], [#"aa",#"bb"], [Some(1), None, Some(3)], etc.

Half in English, half in Spanish.
""",
    },
    {
        "id": "dict_strategy",
        "topic": "aiken/collection/dict/strategy",
        "description": "Dict union strategies: union_with sum/keep_left/keep_right",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers that merge dicts using built-in strategies.

FOLLOW THIS EXACT TEMPLATE STRUCTURE (Aiken code, no markdown fences):

  use aiken/collection/dict
  use aiken/collection/dict/strategy
  use cardano/transaction.{Transaction, OutputReference}

  fn merge_balances(
    a: dict.Dict<ByteArray, Int>,
    b: dict.Dict<ByteArray, Int>,
  ) -> dict.Dict<ByteArray, Int> {
    dict.union_with(a, b, strategy.sum())
  }

  fn safe_get(d: dict.Dict<ByteArray, Int>, key: ByteArray) -> Int {
    when dict.get(d, key) is {
      Some(v) -> v
      None -> 0
    }
  }

  validator my_validator {
    spend(_datum: Option<Data>, _redeemer: Data, _own_ref: OutputReference, self: Transaction) -> Bool {
      let a = dict.empty |> dict.insert(#"aa", 100)
      let b = dict.empty |> dict.insert(#"aa", 50)
      safe_get(merge_balances(a, b), #"aa") == 150
    }
  }

  test merge_sum_same_key() {
    let a = dict.empty |> dict.insert(#"aa", 10)
    let b = dict.empty |> dict.insert(#"aa", 5)
    dict.get(merge_balances(a, b), #"aa") == Some(15)
  }

  test merge_keeps_distinct_keys() {
    let a = dict.empty |> dict.insert(#"aa", 10)
    let b = dict.empty |> dict.insert(#"bb", 3)
    dict.size(merge_balances(a, b)) == 2
  }

  test safe_get_missing_key() {
    safe_get(dict.empty, #"aa") == 0
  }

AVAILABLE STRATEGIES (pass directly to dict.union_with — do NOT annotate as UnionStrategy):
  strategy.sum()                  -- sum Int values on duplicate key
  strategy.keep_left()            -- keep left value on duplicate key
  strategy.keep_right()           -- keep right value on duplicate key
  strategy.expect_no_duplicate()  -- fail/trap on duplicate key

Generate {{count}} VARIATIONS of this pattern with different use cases:
merging token balances, vote counts, reward pools, asset registries, allowlists.
Half in English, half in Spanish.
""",
    },
    {
        "id": "crypto_hash",
        "topic": "aiken/crypto/hashing",
        "description": "Cryptographic hashing helpers: blake2b_256, sha2_256, sha3_256, keccak_256",
        "prompt": """\
Generate {{count}} Aiken v3 validators with helpers using `aiken/crypto` hash functions.
IMPORT: `use aiken/crypto`
EXACT SIGNATURES (all return ByteArray-like Hash type):
  crypto.blake2b_256(bytes: ByteArray) -> Hash<Blake2b_256, a>
  crypto.blake2b_224(bytes: ByteArray) -> Hash<Blake2b_224, a>
  crypto.sha2_256(bytes: ByteArray) -> Hash<Sha2_256, a>
  crypto.sha3_256(bytes: ByteArray) -> Hash<Sha3_256, a>
  crypto.keccak_256(bytes: ByteArray) -> Hash<Keccak_256, a>

IMPORTANT: Hash<algo, a> is just a ByteArray alias — compare with `==` directly.
  let h = crypto.blake2b_256(#"deadbeef")
  bytearray.length(h) == 32   -- blake2b_256 always produces 32 bytes

Use cases: commitment schemes, hash-lock validators, preimage checks.
IMPORT: use `use aiken/crypto` only — do NOT import specific function names from it.
  CORRECT: use aiken/crypto   then call crypto.blake2b_256(...)
  WRONG:   use aiken/crypto.{{blake2b_256}}

IMPORTANT test pattern: compare length, or compare same-input hashes.
  bytearray.length(crypto.blake2b_256(#"aabb")) == 32
  bytearray.length(crypto.sha2_256(#"aabb")) == 32
  crypto.blake2b_256(#"deadbeef") == crypto.blake2b_256(#"deadbeef")
  crypto.blake2b_256(#"aa") != crypto.blake2b_256(#"bb")

Half in English, half in Spanish.
""",
    },
]


SYSTEM_PROMPT = """\
You are an expert Aiken v3 smart contract developer generating training examples.

=== MANDATORY OUTPUT STRUCTURE ===
Every example output MUST contain ALL THREE parts:
  1. Named helper function(s) — at least one `fn name(params) -> ReturnType { ... }`
  2. A validator block that uses the helper(s)
  3. At least 3 test blocks that unit-test the helper(s) with CONCRETE values

=== AIKEN v3 RULES ===
IMPORTS:
  use aiken/collection/list
  use aiken/collection/dict
  use aiken/collection/pairs
  use aiken/primitive/bytearray
  use aiken/primitive/int
  use aiken/math
  use aiken/math/rational.{Rational}    -- MUST import Rational explicitly
  use cardano/assets.{PolicyId, AssetName}
  use cardano/transaction.{Transaction, OutputReference}

HANDLER SIGNATURES (use these exactly):
  spend(datum: Option<Data>, redeemer: r, own_ref: OutputReference, self: Transaction)
  mint(_redeemer: Data, policy_id: PolicyId, self: Transaction)

DICT API (key is ALWAYS ByteArray, insert has NO compare fn):
  dict.empty                              -- const, no parens needed
  dict.insert(d, key: ByteArray, value)   -- only 2 args after self
  dict.get(d, key: ByteArray)             -- returns Option<v>
  dict.from_pairs([Pair(#"key", val)])    -- DOES exist and works
  dict.size(d) -> Int
  dict.union(a, b), dict.filter(d, fn(k,v)->Bool), dict.foldl(d, init, fn(k,v,acc)->acc)

RATIONAL:
  expect Some(r) = rational.new(3, 4)     -- always unwrap with expect
  rational.numerator(r), rational.denominator(r)

=== TEST SYNTAX ===
  test name() {
    expression == expected    // must evaluate to Bool True
  }
  test name() fail {
    failing_expression        // must trap/fail at runtime
  }

=== TEST RULES ===
  - ALL values must be INLINE LITERALS — no tx, self, transaction references
  - For List<tuple> results: use `list.length(result) == N`, not `result == [(...)]`
  - Test with real concrete values: #"aabb", 1_000_000, [1, 2, 3], True/False
  - At least one `fail` test for an edge case

=== OUTPUT FORMAT ===
JSON array of objects, each with:
  "lang": "en" or "es"
  "instruction": short description of what the validator does
  "input": ""
  "output": complete Aiken v3 code as string (helpers + validator + tests)
  "topic": the topic string given in the prompt
  "review_status": "VERIFIED_V3_ALIGNED"

Output ONLY the JSON array — no explanation, no markdown fences.
"""


def load_existing_topics(dataset: Path) -> set[str]:
    """Load all existing topic values from the dataset."""
    topics = set()
    with dataset.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ex = json.loads(line)
                t = ex.get("topic", "")
                if t:
                    topics.add(t)
            except json.JSONDecodeError:
                continue
    return topics


def load_existing_instructions(dataset: Path) -> set[str]:
    """Load normalized instruction prefixes for deduplication."""
    instrs = set()
    with dataset.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ex = json.loads(line)
                instr = ex.get("instruction", "").lower().strip()[:60]
                if instr:
                    instrs.add(instr)
            except json.JSONDecodeError:
                continue
    return instrs


def fix_missing_imports(code: str) -> str:
    """Auto-inject missing imports that Claude commonly forgets."""
    lines = code.splitlines()
    existing_uses = [l for l in lines if l.startswith("use ")]

    def has_import(module: str, symbol: str = "") -> bool:
        for u in existing_uses:
            if module in u:
                if not symbol or symbol in u:
                    return True
        return False

    injections = []

    # Transaction / OutputReference used in validator handlers
    needs_tx = bool(re.search(r'\b(Transaction|OutputReference)\b', code))
    if needs_tx and not has_import("cardano/transaction"):
        injections.append('use cardano/transaction.{Transaction, OutputReference}')
    elif needs_tx and has_import("cardano/transaction"):
        # Check if Transaction and OutputReference are both imported
        for sym in ["Transaction", "OutputReference"]:
            if re.search(r'\b' + sym + r'\b', code) and not has_import("cardano/transaction", sym):
                # Rewrite the existing cardano/transaction import to add missing symbols
                for i, line in enumerate(lines):
                    if line.startswith("use cardano/transaction"):
                        existing = re.findall(r'\{([^}]*)\}', line)
                        if existing:
                            syms = [s.strip() for s in existing[0].split(",")]
                            if sym not in syms:
                                syms.append(sym)
                            lines[i] = f'use cardano/transaction.{{{", ".join(syms)}}}'
                        break

    # PolicyId used without assets import
    if re.search(r'\bPolicyId\b', code) and not has_import("cardano/assets", "PolicyId"):
        if not has_import("cardano/assets"):
            injections.append('use cardano/assets.{PolicyId}')

    if not injections:
        return "\n".join(lines)

    # Insert after last existing `use` line
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("use "):
            insert_at = i + 1
    for imp in reversed(injections):
        lines.insert(insert_at, imp)
    return "\n".join(lines)


def compile_check(code: str) -> tuple[bool, str]:
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        [AIKEN_BIN, "check"],
        cwd=SANDBOX_DIR,
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        close_fds=True,
        env={**os.environ, "TERM": "xterm-256color", "COLUMNS": "200"},
    )
    os.close(slave_fd)
    chunks = []
    deadline = time.time() + TIMEOUT_SECS
    while time.time() < deadline:
        r, _, _ = select.select([master_fd], [], [], 0.2)
        if r:
            try: chunks.append(os.read(master_fd, 4096))
            except OSError: break
        elif proc.poll() is not None:
            try:
                while True: chunks.append(os.read(master_fd, 4096))
            except OSError: break
            break
    proc.wait()
    try: os.close(master_fd)
    except: pass
    raw = b"".join(chunks).decode("utf-8", errors="replace")
    text = ANSI.sub("", raw).strip()
    return proc.returncode == 0, text


def sanitize_json(raw: str) -> str:
    result = []
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == '\\':
            result.append(ch)
            escape_next = True
        elif ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            pass
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)
    return ''.join(result)


def parse_json(raw: str) -> list | None:
    for text in [raw, sanitize_json(raw),
                 re.sub(r',\s*([}\]])', r'\1', sanitize_json(raw))]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


def has_tests(code: str) -> bool:
    return bool(re.search(r'\btest \w+\(\)', code))


def generate_batch(client, pattern: dict, count: int) -> list[dict]:
    prompt = pattern["prompt"].replace("{{count}}", str(count))
    prompt += f'\n\nUse "topic": "{pattern["topic"]}" in every example.'
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r'^```\w*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    result = parse_json(raw)
    if result is None:
        print(f"  JSON parse error — raw[:200]: {raw[:200]}")
        return []
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply",   action="store_true")
    parser.add_argument("--count",   type=int, default=4, help="Examples per pattern")
    parser.add_argument("--topics",  nargs="+",
                        default=[p["id"] for p in PATTERNS],
                        choices=[p["id"] for p in PATTERNS])
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    # Load existing coverage
    existing_topics   = load_existing_topics(DATASET)
    existing_instrs   = load_existing_instructions(DATASET)
    print(f"Existing dataset : {sum(1 for _ in DATASET.open())} examples")
    print(f"Existing topics  : {len(existing_topics)} unique")

    client = anthropic.Anthropic() if args.apply else None
    all_verified = []

    for p in PATTERNS:
        if p["id"] not in args.topics:
            continue

        # Check if this topic is already well-covered
        already = sum(1 for t in existing_topics if t == p["topic"])
        print(f"\n{'='*60}")
        print(f"Pattern  : {p['id']}")
        print(f"Topic    : {p['topic']}")
        print(f"Existing : {already} examples with this exact topic")
        print(f"Count    : {args.count}")

        if args.dry_run:
            print(f"  → Would generate {args.count} examples")
            continue

        raw_examples = generate_batch(client, p, args.count)
        print(f"  Got {len(raw_examples)} from Claude")

        verified = []
        for ex in raw_examples:
            code  = ex.get("output", "")
            instr = ex.get("instruction", "").lower().strip()[:60]

            if not code.strip():
                print(f"  ⚠️  empty output")
                continue

            # Skip if no tests were generated
            if not has_tests(code):
                print(f"  ⚠️  no tests in output — skipping")
                continue

            # Deduplication check against existing instructions
            if instr in existing_instrs:
                print(f"  ⚠️  duplicate instruction — skipping")
                continue

            # Auto-fix commonly missing imports
            code = fix_missing_imports(code)
            ex["output"] = code

            passed, err = compile_check(code)
            if passed:
                record = {
                    "lang":          ex.get("lang", "en"),
                    "instruction":   ex.get("instruction", ""),
                    "input":         "",
                    "output":        code,
                    "source":        "with_tests_examples",
                    "topic":         p["topic"],
                    "review_status": "VERIFIED_V3_ALIGNED",
                }
                verified.append(record)
                existing_instrs.add(instr)
                print(f"  ✅ {ex.get('instruction','')[:65]}")
            else:
                err_short = next((l.strip() for l in err.splitlines() if "Error" in l), err[:80])
                print(f"  ❌ {err_short}")

        print(f"  Verified: {len(verified)}/{len(raw_examples)}")
        all_verified.extend(verified)

    if args.dry_run:
        print(f"\nDRY RUN — no changes written.")
        return

    print(f"\n{'='*60}")
    print(f"Total verified: {len(all_verified)}")

    if not all_verified:
        print("Nothing to save.")
        return

    OUT_FILE.parent.mkdir(exist_ok=True)
    with OUT_FILE.open("a", encoding="utf-8") as f:
        for ex in all_verified:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Saved component : {OUT_FILE}")

    with DATASET.open("a", encoding="utf-8") as f:
        for ex in all_verified:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Appended {len(all_verified)} examples to {DATASET}")


if __name__ == "__main__":
    main()
