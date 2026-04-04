#!/usr/bin/env python3
"""
add_tests_to_verified.py — Cardumen Forge

Retroactively adds test blocks to VERIFIED_V3_ALIGNED examples that have
helper functions but no tests. Uses Claude to generate appropriate tests
based on the existing helper logic, then re-verifies with `aiken check`
(which runs tests automatically).

Target: ~111 examples with `fn` helpers but no `test` blocks.

Strategy:
  - Keep the validator code UNCHANGED
  - Add 3-5 test blocks at the end of the file
  - Tests cover helper functions with concrete values
  - At least one `fail` test for an edge case
  - No mock transaction construction — unit test helpers only

Usage:
    python3 scripts/add_tests_to_verified.py --dry-run --limit 5
    python3 scripts/add_tests_to_verified.py --apply --limit 20
    python3 scripts/add_tests_to_verified.py --apply
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

ROOT         = Path(__file__).parent.parent
DATASET      = ROOT / "data" / "processed" / "dataset_v22.jsonl"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
STDLIB_LIB   = SANDBOX_DIR / "build" / "packages" / "aiken-lang-stdlib" / "lib"
LOG_FILE     = ROOT / "logs" / "add_tests_report.jsonl"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30
MAX_RETRIES  = 3


def load_stdlib_context() -> str:
    """Load key type definitions from local stdlib for context."""
    files = [
        ("cardano/transaction", STDLIB_LIB / "cardano" / "transaction.ak"),
        ("cardano/assets",      STDLIB_LIB / "cardano" / "assets.ak"),
        ("aiken/interval",      STDLIB_LIB / "aiken" / "interval.ak"),
    ]
    parts = []
    for label, path in files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        blocks = re.findall(
            r'pub type \w+\b[^{]*\{[^}]+\}',
            text, re.DOTALL
        )
        if blocks:
            snippet = "\n".join(b.strip()[:400] for b in blocks[:6])
            parts.append(f"// === {label} ===\n{snippet}")
    return "\n\n".join(parts)


STDLIB_CONTEXT = load_stdlib_context()

SYSTEM_PROMPT = f"""\
You are an expert Aiken v3 developer. Your task is to add test blocks to an
existing Aiken v3 validator that has helper functions but no tests.

=== AVAILABLE MODULES IN THIS SANDBOX (these are the ONLY valid `use` paths) ===
  aiken/cbor
  aiken/collection
  aiken/collection/dict
  aiken/collection/dict/strategy
  aiken/collection/list
  aiken/collection/pairs
  aiken/crypto
  aiken/crypto/bitwise
  aiken/interval
  aiken/math
  aiken/math/rational
  aiken/option
  aiken/primitive/bytearray
  aiken/primitive/int
  aiken/primitive/string
  cardano/address
  cardano/address/credential
  cardano/assets
  cardano/assets/strategy
  cardano/certificate
  cardano/governance
  cardano/governance/protocol_parameters
  cardano/governance/voter
  cardano/script_context
  cardano/transaction
  cardano/transaction/output_reference
  cardano/transaction/script_purpose

=== RULES ===
1. CRITICAL: Do NOT add any new `use` import statements. The file's existing imports are the ONLY ones allowed.
2. Keep the existing validator code COMPLETELY UNCHANGED — do NOT modify, reformat, or rewrite any existing line.
3. ONLY append new `test` blocks at the very END of the file, after all existing code.
4. Write 3-5 tests that cover the helper functions with CONCRETE values.
5. Include at least one `fail` test for an edge case (division by zero, empty list, etc.).
6. Tests must be self-contained — unit test the helpers directly, do NOT construct mock transactions.
7. CRITICAL: The output must be syntactically valid Aiken. Do not add any text outside of Aiken code.
8. CRITICAL: In test blocks, ALL values must be INLINE LITERALS. Never use `tx`, `self`, `transaction`,
   `outputs`, or any variable that isn't defined inside the test block itself.
   WRONG:  test foo() {{ sum_outputs(tx.outputs) == 5_000_000 }}
   CORRECT: test foo() {{ sum_outputs([]) == 0 }}
   SIMPLEST: test foo() {{ my_helper(1_000_000, 2) == 500_000 }}  -- pass Int/ByteArray literals directly
11. For helpers returning List<tuple> (e.g. List<(ByteArray, ByteArray, Int)>):
    use `list.length(result) == N` — NEVER direct equality like `result == [(a, b, c)]`.
    CORRECT: test foo() {{ list.length(my_helper(assets.zero)) == 0 }}
    WRONG:   test foo() {{ my_helper(assets.zero) == [] }}
12. For `dict.Dict<K, V>` params: construct with `dict.empty |> dict.insert(key, value)` — only TWO args (no compare fn).
    Or use `dict.from_pairs([Pair(#"key", value), ...])`.
    CORRECT: let tokens = dict.empty |> dict.insert(#"000643b0aabb", 1)
    CORRECT: let tokens = dict.from_pairs([Pair(#"000643b0aabb", 1)])
    WRONG:   dict.empty |> dict.insert(#"key", 1, bytearray.compare)  -- insert takes NO compare fn!
13. If the validator has an `else(_) {{ fail }}` block, the file ends with two closing braces `}}\\n}}`.
    Append tests AFTER the very last `}}` that closes the validator block.
9. For helpers that take Output, Input, or Address — construct them using these EXACT patterns:

   -- Address (use address.from_verification_key or address.from_script):
   use cardano/address  -- only if NOT already imported
   let addr = address.from_verification_key(#"aabbccdd00112233aabbccdd00112233aabbccdd00112233aabbccdd")

   -- Output (4 required fields):
   use cardano/transaction.{{Output, NoDatum}}  -- only if NOT already imported
   let out = Output {{
     address: address.from_verification_key(#"aabbccdd00112233aabbccdd00112233aabbccdd00112233aabbccdd"),
     value: assets.from_lovelace(2_000_000),
     datum: NoDatum,
     reference_script: None,
   }}

   -- Input (2 required fields):
   use cardano/transaction.{{Input, OutputReference}}  -- only if NOT already imported
   let inp = Input {{
     output_reference: OutputReference {{ transaction_id: #"abcd", output_index: 0 }},
     output: Output {{ address: addr, value: assets.from_lovelace(1_000_000), datum: NoDatum, reference_script: None }},
   }}

   -- Assets / Value:
   assets.from_lovelace(1_000_000)   -- lovelace only
   assets.zero                        -- empty value

   REMEMBER: only add `use` statements for modules NOT already in the file.

10. If a helper takes Transaction — skip it. Transaction has too many required fields.

=== AIKEN TEST SYNTAX ===
  test name() {{
    expression == expected_value   -- body must evaluate to True
  }}

  test name() fail {{
    expression                     -- must fail/trap (for edge cases like division by zero)
  }}

=== EXAMPLES OF GOOD TESTS ===
For a `fn compute_value(ada: Int, price: Int, exp: Int) -> Int` helper:
  test compute_value_1_ada() {{
    compute_value(1_000_000, 70_000_000, -8) == 700_000
  }}
  test compute_value_2_ada() {{
    compute_value(2_000_000, 70_000_000, -8) == 1_400_000
  }}

For a `fn pow(base: Int, exp: Int) -> Int` helper:
  test pow_zero() {{
    pow(10, 0) == 1
  }}
  test pow_eight() {{
    pow(10, 8) == 100_000_000
  }}

For a `fn count_signatures(sigs: List<ByteArray>, required: List<ByteArray>) -> Int` helper:
  test count_signatures_all_match() {{
    count_signatures([#"aabb", #"ccdd"], [#"aabb", #"ccdd"]) == 2
  }}
  test count_signatures_none_match() {{
    count_signatures([#"aabb"], [#"ccdd"]) == 0
  }}

For a `fn max(a: Int, b: Int) -> Int` helper:
  test max_first_larger() {{
    max(10, 5) == 10
  }}
  test max_second_larger() {{
    max(3, 7) == 7
  }}
  test max_equal() {{
    max(5, 5) == 5
  }}

For a `fn validate_burn(name: AssetName, qty: Int) -> Bool` helper:
  test validate_burn_nft_correct() {{
    validate_burn(#"000de140aabbccdd", -1)
  }}
  test validate_burn_wrong_qty() fail {{
    validate_burn(#"000de140aabbccdd", -2)
  }}

For a `fn validate_mint(name: AssetName, qty: Int, tokens: dict.Dict<AssetName, Int>) -> Bool`:
  test validate_mint_with_ref_nft() {{
    let tokens = dict.empty |> dict.insert(#"000643b0aabb", 1)
    validate_mint(#"000de140aabb", 1, tokens)
  }}
  test validate_mint_without_ref_fails() fail {{
    validate_mint(#"000de140aabb", 1, dict.empty)
  }}

For a `fn positive_mints(v: Value) -> List<(PolicyId, AssetName, Int)>`:
  test positive_mints_empty_value() {{
    list.length(positive_mints(assets.zero)) == 0
  }}
  test positive_mints_lovelace_only() {{
    list.length(positive_mints(assets.from_lovelace(1_000_000))) == 0
  }}

=== LOCAL STDLIB TYPES (ground truth) ===
{STDLIB_CONTEXT}

=== YOUR TASK ===
Given the existing Aiken code, return the COMPLETE file with tests appended.
Return ONLY the Aiken code — no explanation, no markdown fences.
"""


def _run_aiken_check(code: str) -> tuple[bool, str]:
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


def add_tests_with_claude(client, code: str, fn_names: list[str]) -> tuple[str | None, str]:
    """Returns (code_with_tests, last_error). last_error is empty on success."""
    user_msg = f"""\
Helper functions in this validator: {', '.join(fn_names)}

Existing Aiken code:
{code}

Add 3-5 test blocks for the helper functions. Return the complete file with tests appended.
"""
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        resp = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        result = resp.content[0].text.strip()
        result = re.sub(r'^```\w*\n?', '', result)
        result = re.sub(r'\n?```$', '', result)

        # Verify tests were actually added
        if 'test ' not in result:
            last_error = "no test blocks in response"
            continue

        # Verify the original code is mostly preserved (not rewritten)
        original_lines = set(code.strip().splitlines())
        result_lines   = set(result.strip().splitlines())
        preserved = len(original_lines & result_lines) / max(len(original_lines), 1)
        if preserved < 0.7:
            last_error = f"code preservation too low ({preserved:.0%})"
            continue

        passed, err = _run_aiken_check(result)
        if passed:
            return result, ""
        last_error = next((l.strip() for l in err.splitlines() if "Error" in l or "FAIL" in l), err[:120])

        if attempt < MAX_RETRIES:
            user_msg = f"""\
The tests you added caused a compile/test failure. Error:
{err[:800]}

Please fix the tests. Return the complete file with corrected tests appended.
The validator code must remain unchanged.

Current code (with broken tests):
{result}
"""
    return None, last_error


def is_pure_aiken(output: str) -> bool:
    """Returns True only if the output is a standalone Aiken source file (no prose)."""
    stripped = output.strip()
    if not stripped or "validator" not in stripped:
        return False
    lines = stripped.split("\n")
    prose_count = 0
    code_count  = 0
    AIKEN_STARTS = (
        "use ", "pub ", "type ", "validator", "fn ", "let ", "//", "  ", "\t",
        "}", "{", "|", "when ", "if ", "else", "expect ", "trace ", "todo", "test ",
    )
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith(tuple(AIKEN_STARTS)):
            code_count += 1
        elif re.match(r'^[A-Z][a-z]', s) and not re.match(r'^[A-Z]\w*\s*[\({<]', s):
            prose_count += 1
        elif s.startswith(("#", "*", "-", ">", "```", "##")):
            prose_count += 1
        elif re.search(r'[.!?]$', s) and len(s) > 40:
            prose_count += 1
        else:
            code_count += 1
    if prose_count == 0 and code_count > 0:
        return True
    if code_count > 0 and prose_count / (prose_count + code_count) < 0.1:
        return True
    return False


# Sources that import external packages not available in sandbox
SANDBOX_INCOMPATIBLE_SOURCES = {"aiken_design_patterns"}

# Instruction prefixes that indicate Q&A / explanation (not standalone validators)
QA_PREFIXES = (
    "what ", "what's ", "how ", "explain", "describe", "why ", "when ",
    "¿qué", "¿cómo", "¿por qué", "¿cuándo", "qué ", "cómo ",
)

def _needs_nodat_for_output_input(code: str) -> bool:
    """Returns True if any top-level helper takes Output or Input as a direct param type."""
    for m in re.finditer(r'\bfn \w+\(([^)]*)\)', code):
        if re.search(r':\s*(Output|Input)\b', m.group(1)):
            return True
    return False


def _nodat_available(code: str) -> bool:
    """Returns True if NoDatum constructor is accessible without adding new imports."""
    # Already explicitly used or imported
    if re.search(r'\bNoDatum\b', code):
        return True
    # cardano/transaction imported without braces (exposes all constructors)
    if re.search(r'use cardano/transaction\s*\n', code):
        return True
    return False


def find_candidates(examples: list[dict]) -> list[tuple[int, dict, list[str]]]:
    candidates = []
    for i, ex in enumerate(examples):
        if ex.get("review_status") != "VERIFIED_V3_ALIGNED":
            continue
        # Skip sources with external package dependencies not in sandbox
        if ex.get("source", "") in SANDBOX_INCOMPATIBLE_SOURCES:
            continue
        # Skip Q&A / explanation instructions
        instr_lower = ex.get("instruction", "").lower().strip()
        if instr_lower.startswith(QA_PREFIXES):
            continue
        code = ex.get("output", "")
        if not is_pure_aiken(code):
            continue
        if not (re.search(r'\bfn \w+\(', code) and "test " not in code):
            continue
        # Skip if helpers need Output/Input construction but NoDatum is not imported
        if _needs_nodat_for_output_input(code) and not _nodat_available(code):
            continue
        fn_names = re.findall(r'\bfn (\w+)\(', code)
        candidates.append((i, ex, fn_names))
    return candidates


def audit_dataset(examples: list[dict]):
    """Show full breakdown of VERIFIED examples by testability."""
    from collections import defaultdict
    buckets = defaultdict(list)

    for i, ex in enumerate(examples):
        if ex.get("review_status") != "VERIFIED_V3_ALIGNED":
            continue
        code   = ex.get("output", "")
        source = ex.get("source", "?")
        instr  = ex.get("instruction", "").lower().strip()
        has_fn   = bool(re.search(r'\bfn \w+\(', code))
        has_test = "test " in code

        if has_test:
            buckets["✅ already has tests"].append((i, source))
        elif not has_fn:
            buckets["— no helper fns"].append((i, source))
        elif not is_pure_aiken(code):
            buckets["— not pure Aiken (Q&A/mixed)"].append((i, source))
        elif instr.startswith(QA_PREFIXES):
            buckets["— Q&A instruction"].append((i, source))
        elif source in SANDBOX_INCOMPATIBLE_SOURCES:
            buckets["— incompatible source (ext deps)"].append((i, source))
        elif _needs_nodat_for_output_input(code) and not _nodat_available(code):
            buckets["⚠️  Output/Input params, NoDatum not imported"].append((i, source))
        else:
            buckets["🎯 testable"].append((i, source))

    total_verified = sum(len(v) for v in buckets.values())
    print(f"\n{'='*60}")
    print(f"VERIFIED_V3_ALIGNED audit — {total_verified} total")
    print(f"{'='*60}")
    for label, items in sorted(buckets.items()):
        print(f"\n  {label}: {len(items)}")
        # Show source breakdown
        from collections import Counter
        by_src = Counter(src for _, src in items)
        for src, n in by_src.most_common(6):
            print(f"    {src:<35} {n}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply",   action="store_true")
    parser.add_argument("--audit",   action="store_true", help="Show testability breakdown")
    parser.add_argument("--limit",   type=int, default=None)
    args = parser.parse_args()

    if not args.dry_run and not args.apply and not args.audit:
        parser.error("Specify --dry-run, --apply, or --audit")

    examples = []
    with DATASET.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    if args.audit:
        audit_dataset(examples)
        return

    candidates = find_candidates(examples)
    if args.limit:
        candidates = candidates[:args.limit]

    print(f"Dataset     : {len(examples)} total")
    print(f"Candidates  : {len(candidates)} (helpers, no tests)")
    print(f"Stdlib ctx  : {len(STDLIB_CONTEXT)} chars")
    print()

    if args.dry_run:
        print("DRY RUN — sample candidates:")
        for idx, ex, fns in candidates[:10]:
            print(f"  [{idx:4d}] {ex.get('source','?'):<30} fns: {fns[:3]}")
        return

    client = anthropic.Anthropic()
    updated  = []
    failed   = []
    records  = []

    for n, (idx, ex, fn_names) in enumerate(candidates, 1):
        source = ex.get("source", "?")
        instr  = ex.get("instruction", "")[:55]
        print(f"[{n:3d}/{len(candidates)}] {source:<28} fns:{fn_names[:2]} | {instr}")

        # Pre-check: verify original code compiles before attempting to add tests
        orig_ok, orig_err = _run_aiken_check(ex["output"])
        if not orig_ok:
            err_short = next((l.strip() for l in orig_err.splitlines() if "Error" in l), orig_err[:80])
            failed.append(idx)
            records.append({"idx": idx, "source": source, "status": "original_compile_error",
                            "fns": fn_names[:4], "instruction": ex.get("instruction","")[:80],
                            "error": err_short})
            print(f"  ⚠️  original code broken: {err_short[:70]}")
            continue

        code_with_tests, last_err = add_tests_with_claude(client, ex["output"], fn_names)

        if code_with_tests:
            examples[idx]["output"] = code_with_tests
            updated.append(idx)
            records.append({"idx": idx, "source": source, "status": "ok",
                            "fns": fn_names[:4], "instruction": ex.get("instruction","")[:80]})
            print(f"  ✅ tests added")
        else:
            failed.append(idx)
            records.append({"idx": idx, "source": source, "status": "failed",
                            "fns": fn_names[:4], "instruction": ex.get("instruction","")[:80],
                            "error": last_err})
            print(f"  ❌ {last_err[:80]}")

    print(f"\n{'='*60}")
    print(f"  Updated : {len(updated)}")
    print(f"  Failed  : {len(failed)}")

    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  Log     : {LOG_FILE}")

    if not updated:
        print("  Nothing to write.")
        return

    with DATASET.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"  Written : {DATASET} ({len(updated)} examples updated)")


if __name__ == "__main__":
    main()
