#!/usr/bin/env python3
"""
generate_string_examples.py — Generate aiken/primitive/string training examples
Fills coverage gap: string at 0.3% (critical GAP).

Usage:
    python3 scripts/generate/generate_string_examples.py
    python3 scripts/generate/generate_string_examples.py --n 30
    python3 scripts/generate/generate_string_examples.py --dry-run
"""

import os, re, pty, select, shutil, time, json, argparse, subprocess
from pathlib import Path
from datetime import datetime, timezone

import anthropic

ROOT         = Path(__file__).parent.parent.parent
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
OUT_FILE     = ROOT / "data" / "processed" / "components" / "string_examples.jsonl"
LOGS_DIR     = ROOT / "logs" / "generate"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30
MODEL        = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are an expert Aiken v3 smart contract developer.
Generate complete, compilable Aiken v3 validators that use aiken/primitive/string.

── string module API ──
  use aiken/primitive/string

  string.from_bytearray(bytes: ByteArray) -> String   // ByteArray to String (requires valid UTF-8)
  string.to_bytearray(s: String) -> ByteArray         // String to ByteArray
  string.from_int(n: Int) -> String                   // Int to its string representation
  string.concat(left: String, right: String) -> String // concatenate two strings
  string.join(list: List<String>, sep: String) -> String // join list with separator

── String literals in Aiken ──
  @"hello"           // String literal (prefix @)
  @"" == @""         // equality check
  string.concat(@"prefix_", string.from_int(42)) == @"prefix_42"
  string.to_bytearray(@"hello")  // -> #"68656c6c6f"

── list module — import when using list functions ──
  use aiken/collection/list
  list.has(xs, x) -> Bool    // self.extra_signatories is a List — always import!

── bytearray module — for length checks ──
  use aiken/primitive/bytearray
  bytearray.length(ba) -> Int    // CORRECT way to get bytearray length
  // NEVER use: builtin.length_of_bytearray  ← does NOT compile

── Common patterns ──
  // Build a label for tracing or datum tagging
  let label = string.concat(@"op:", string.from_int(amount))

  // Convert datum bytearray field to string for comparison
  let name = string.from_bytearray(datum.name_bytes)

  // Check string prefix by converting to bytearray and slicing
  let tag = string.to_bytearray(string.from_bytearray(datum.tag))

── Import rules — CRITICAL ──
  use statements go at the TOP of the file, before any type/validator.
  Slash ONLY in use statements. NEVER in type annotations or expressions.

  WRONG: _ref: cardano/transaction.OutputReference   // ❌ slash in type annotation
  RIGHT: use cardano/transaction.{Transaction, OutputReference}
         then use bare OutputReference in handler    // ✅

  ALWAYS import OutputReference explicitly:
    use cardano/transaction.{Transaction, OutputReference}

  Handler signatures (no `fn` keyword prefix):
    spend(datum: Option<T>, _redeemer: Data, _ref: OutputReference, self: Transaction) -> Bool
    mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool

File structure: use statements, pub types, helper fns, validator.
Output ONLY raw Aiken source code. No markdown, no explanation."""

PROMPTS = [
    # Label / tagging patterns
    ("Write an Aiken v3 spend validator `tagged_output` with TagDatum "
     "(tag: ByteArray, value: Int). Use string.from_bytearray to convert tag to String, "
     "then string.concat with string.from_int(value) to build a label and verify "
     "the tag is non-empty by checking string.to_bytearray is non-empty.",
     ["string.from_bytearray", "string.from_int", "string.concat", "spend("]),

    ("Write an Aiken v3 spend validator `version_check` with VersionDatum "
     "(version_bytes: ByteArray, min_version: String). "
     "Use string.from_bytearray to convert version_bytes to a String and verify it "
     "equals min_version.",
     ["string.from_bytearray", "min_version", "spend("]),

    # from_int patterns
    ("Write an Aiken v3 spend validator `amount_label_validator` with LabelDatum "
     "(amount: Int, expected_label: ByteArray). "
     "Use string.from_int and string.to_bytearray to build a bytearray label from amount "
     "and verify it equals expected_label.",
     ["string.from_int", "string.to_bytearray", "expected_label", "spend("]),

    ("Write an Aiken v3 mint validator `labeled_mint` with a redeemer containing "
     "sequence_number: Int. Use string.from_int to build a token name string, convert "
     "with string.to_bytearray, and verify the minted asset uses that exact name.",
     ["string.from_int", "string.to_bytearray", "sequence_number", "mint("]),

    # concat patterns
    ("Write an Aiken v3 spend validator `prefix_tag_validator` with PrefixDatum "
     "(prefix: ByteArray, id: Int, expected: ByteArray). "
     "Use string.concat(string.from_bytearray(prefix), string.from_int(id)) and "
     "string.to_bytearray to verify the constructed tag equals expected.",
     ["string.concat", "string.from_bytearray", "string.from_int", "string.to_bytearray", "spend("]),

    ("Write an Aiken v3 spend validator `message_builder` with MessageDatum "
     "(greeting: ByteArray, name: ByteArray, separator: ByteArray). "
     "Use string.concat to build a full message from the parts and verify the resulting "
     "bytearray is non-empty.",
     ["string.concat", "string.from_bytearray", "string.to_bytearray", "spend("]),

    # join patterns
    ("Write an Aiken v3 spend validator `join_validator` with JoinDatum "
     "(parts: List<ByteArray>, separator: ByteArray, expected_hash: ByteArray). "
     "Convert parts to List<String> using list.map and string.from_bytearray, "
     "join with string.join, convert back and verify the result matches expected.",
     ["string.join", "string.from_bytearray", "string.to_bytearray", "spend("]),

    # to_bytearray for asset name construction
    ("Write an Aiken v3 mint validator `sequential_nft_mint` with redeemer index: Int. "
     "Build the token name as string.to_bytearray(string.concat(@\"NFT#\", string.from_int(index))). "
     "Verify exactly one token is minted with that asset name under policy_id.",
     ["string.to_bytearray", "string.concat", "string.from_int", "mint("]),

    ("Write an Aiken v3 mint validator `prefixed_token_mint` with redeemer "
     "(prefix: ByteArray, seq: Int). Use string.concat and string.from_int to build "
     "the asset name and verify the minted token uses it.",
     ["string.concat", "string.from_bytearray", "string.from_int", "mint("]),

    # String comparison in datum
    ("Write an Aiken v3 spend validator `string_equality_gate` with GateDatum "
     "(key_bytes: ByteArray, expected: ByteArray). "
     "Convert both to String with string.from_bytearray and verify they are equal.",
     ["string.from_bytearray", "key_bytes", "expected", "spend("]),

    # Tracing with string
    ("Write an Aiken v3 spend validator `trace_validator` with TraceDatum "
     "(owner: ByteArray, amount: Int). "
     "Use string.concat and string.from_int to build a trace message and use trace "
     "for debugging. Verify owner is in extra_signatories.",
     ["string.concat", "string.from_int", "extra_signatories", "spend("]),

    # Parametric
    ("Write a parametric Aiken v3 spend validator `labeled_registry(label_prefix: ByteArray)` "
     "with RegistryDatum (id: Int, owner: ByteArray). "
     "Build the full label with string.concat(string.from_bytearray(label_prefix), string.from_int(id)) "
     "and verify owner signed. No must_contain enforcement on the label.",
     ["string.concat", "string.from_bytearray", "string.from_int", "spend("]),

    # from_bytearray + length check via to_bytearray
    ("Write an Aiken v3 spend validator `name_length_check` with NameDatum "
     "(name_bytes: ByteArray, min_len: Int). "
     "Convert name_bytes to String and back to ByteArray with string.to_bytearray, "
     "then use bytearray.length (from aiken/primitive/bytearray) to verify length >= min_len.",
     ["string.from_bytearray", "string.to_bytearray", "bytearray.length", "spend("]),
]


def compile_check(code: str) -> tuple[bool, str]:
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    try:
        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            [AIKEN_BIN, "check", "--max-success", "0"],
            cwd=str(SANDBOX_DIR), stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True,
        )
        os.close(slave_fd)
        buf = []
        deadline = time.time() + TIMEOUT_SECS
        while time.time() < deadline:
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if r:
                try:
                    buf.append(os.read(master_fd, 4096).decode("utf-8", errors="replace"))
                except OSError:
                    break
            if proc.poll() is not None:
                break
        proc.wait(timeout=5)
        os.close(master_fd)
        return proc.returncode == 0, ANSI.sub("", "".join(buf))
    except Exception as e:
        return False, str(e)


def generate_one(client, prompt: str) -> str | None:
    instruction = (
        f"{prompt}\n\n"
        "Return ONLY the complete Aiken source file. "
        "No explanation, no markdown. Start with the first line."
    )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": instruction}],
        )
        result = resp.content[0].text.strip()
        if result.startswith("```"):
            result = re.sub(r'^```[a-z]*\n?', '', result)
            result = re.sub(r'\n?```$', '', result)
        return result
    except Exception as e:
        print(f"    API error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=len(PROMPTS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    client = None if args.dry_run else anthropic.Anthropic()
    prompts = PROMPTS[:args.n]

    already_done = set()
    if OUT_FILE.exists():
        with OUT_FILE.open() as f:
            for line in f:
                try:
                    already_done.add(json.loads(line)["instruction"])
                except Exception:
                    pass
    if already_done:
        print(f"Skipping {len(already_done)} already-verified prompts")

    passed, failed_list = 0, []
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for i, (prompt, must_contain) in enumerate(prompts):
        if prompt in already_done:
            print(f"[{i+1}/{len(prompts)}] skip (already verified)")
            continue
        print(f"[{i+1}/{len(prompts)}] {prompt[:80]}...")
        if args.dry_run:
            print("  [dry-run] skip")
            continue

        code = generate_one(client, prompt)
        if not code:
            failed_list.append({"prompt": prompt, "error": "API returned None"})
            continue

        missing = [kw for kw in must_contain if kw not in code]
        if missing:
            print(f"  ✗ missing keywords: {missing}")
            failed_list.append({"prompt": prompt, "error": f"missing: {missing}", "code": code})
            continue

        ok, output = compile_check(code)
        if ok:
            print(f"  ✓ compile ok")
            record = {
                "instruction": prompt,
                "input": "",
                "output": code,
                "source": "generate/string_examples",
                "topic": "aiken/primitive/string",
                "review_status": "VERIFIED",
                "lang": "en",
            }
            with OUT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            passed += 1
        else:
            print(f"  ✗ compile error")
            failed_list.append({"prompt": prompt, "error": output[:500], "code": code})

    if failed_list:
        log_path = LOGS_DIR / f"string_failures_{ts}.json"
        log_path.write_text(json.dumps({"run_at": ts, "failures": failed_list}, indent=2))
        print(f"\nFailures saved to {log_path}")

    print(f"\nDone: {passed}/{len(prompts)} verified → {OUT_FILE}")


if __name__ == "__main__":
    main()
