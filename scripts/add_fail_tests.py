#!/usr/bin/env python3
"""
add_fail_tests.py — Cardumen Forge
Adds semantic `test ... fail` blocks to Aiken pattern files.

A `fail` test passes when its body ALWAYS produces a runtime failure for every
fuzzer input. This lets us verify that helper functions correctly REJECT invalid
inputs — something `aiken check` alone cannot prove.

Pattern used:
    test prop_name(arg via fuzzer) fail {
      expect helper_fn(arg)   // fails at runtime when helper returns False
    }

Only helper functions (fn ... -> Bool) are targeted. The top-level validator is
skipped — it requires a full Transaction to construct.

Usage:
    python3 scripts/add_fail_tests.py --dry-run
    python3 scripts/add_fail_tests.py --n 20
    python3 scripts/add_fail_tests.py --n 200 --log-failures
"""

import os
import re
import pty
import select
import shutil
import time
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import anthropic

ROOT         = Path(__file__).parent.parent
PATTERNS_DIR = ROOT / "data" / "patterns"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
LOGS_DIR     = ROOT / "logs" / "fail_tests"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 60
MODEL        = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
<role>
You are an expert Aiken v3 smart contract developer writing semantic negative tests.
Your job is to add `test ... fail` blocks to Aiken files that prove helper functions
correctly REJECT invalid inputs.
</role>

<goal>
Add 2–4 new `test ... fail` property tests to the file. Each test must:
- Target a helper function that returns Bool
- Choose fuzzer input ranges that GUARANTEE the helper returns False
- Use `expect helper(args)` as the body — this converts False → runtime failure
- Be a realistic negative case (wrong signer, undercollateralized, zero quantity, etc.)

Do NOT add fail tests for the top-level validator — it requires a full Transaction.
Do NOT modify existing tests, helpers, types, or the validator.
Append the new tests at the end of the file.
</goal>

<fail_test_syntax>
A `fail` test passes when its body ALWAYS fails at runtime for every fuzzer input.

Pattern:
    test prop_name(arg via fuzzer) fail {
      expect helper_fn(arg)
    }

`expect expr` fails at runtime when expr evaluates to False.
So the test passes only when helper_fn always returns False for the given range.

Unit fail test (no fuzzer):
    test name() fail {
      expect helper_fn(known_bad_input)
    }

Property fail test (with fuzzer):
    test prop_name(
      vals via fuzz.both(fuzz.int_between(1, 10), fuzz.int_between(200, 500)),
    ) fail {
      let (small, big) = vals
      expect helper_fn(small, big)
    }
</fail_test_syntax>

<choosing_ranges>
The key challenge: pick fuzzer ranges where the helper ALWAYS returns False.

Examples:
  is_signed_by(signatories, owner) — fails when signatories is empty:
    test prop_unsigned_tx_rejected(
      owner via fuzz.bytearray(),
    ) fail {
      expect is_signed_by([], owner)
    }

  healthy_after_repay(collateral, debt, repay, ratio) — fails when collateral too low:
    test prop_undercollateralized_unhealthy(
      debt via fuzz.int_between(101, 500),
    ) fail {
      // collateral=1, target_ratio=150: 1*100=100 < debt*150 for debt>=1
      expect healthy_after_repay(1, debt, 0, 150)
    }

  min_qty_met(outputs, min) — fails when outputs is empty:
    test prop_no_outputs_fails_min_qty(
      min via fuzz.int_at_least(1),
    ) fail {
      expect min_qty_met([], min)
    }

Use tight ranges. If unsure, use a unit test with hardcoded bad inputs instead.
</choosing_ranges>

<fuzz_modules>
  use aiken/fuzz           — int, int_between, int_at_least, bytearray, bool, both, map
  use cardano/fuzz         — asset_name, policy_id, verification_key_hash, address, value
  fuzz.both(a, b)          — pair of two fuzzers; nest for 3+: fuzz.both(fuzz.both(a,b),c)
  No import needed for []  — empty list literal, always valid
</fuzz_modules>

<import_rules>
All `use` statements must be at the top of the file — before any fn, type, or validator.
If you need `use cardano/fuzz` and it is not already imported, add it at the top.
Do NOT add duplicate imports.

CRITICAL — when constructing Cardano types in tests, import the module:
  use cardano/assets        — needed for assets.zero, assets.from_asset(...)
  use cardano/transaction   — needed for NoDatum, InlineDatum, Output, Input, Transaction
  use cardano/address       — needed for address.from_verification_key(...)
Only add these if your test actually uses them AND they are not already imported.
</import_rules>

<arity_rules>
Property fail tests may have AT MOST ONE top-level parameter from a fuzzer.
To pass multiple values, combine fuzzers with fuzz.both():
  WRONG:
    test prop_name(a via fuzz.int(), b via fuzz.bytearray()) fail { ... }
  CORRECT:
    test prop_name(vals via fuzz.both(fuzz.int(), fuzz.bytearray())) fail {
      let (a, b) = vals
      ...
    }

If you need 3 values: fuzz.both(fuzz.both(a, b), c) → let ((x, y), z) = vals
If constructing complex types is error-prone, use a UNIT fail test with hardcoded inputs instead.
</arity_rules>

<construction_rules>
NEVER use `...` or `_` as a placeholder value inside a record or function call.
NEVER leave fields incomplete. If you need a dummy Output, construct it fully:
  Output {
    address: address.from_verification_key(#"deadbeef00"),
    value: assets.zero,
    datum: NoDatum,
    reference_script: None,
  }
If constructing Output/Input/Transaction is too complex for the test, use simpler
helper arguments (Int, ByteArray, List<ByteArray>) instead of full Cardano types.
Prefer helpers that take primitive arguments over helpers that take Transaction.
</construction_rules>

<output_format>
Return only the complete Aiken source file.
Begin with the first line of the file (a `use` or `//`).
No explanation, no preamble, no markdown fences.
</output_format>
"""


# ── Compile check ─────────────────────────────────────────────────────────────

def compile_check(code: str) -> tuple[bool, str]:
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    try:
        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            [AIKEN_BIN, "check", "--max-success", "200"],
            cwd=str(SANDBOX_DIR),
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        buf = []
        deadline = time.time() + TIMEOUT_SECS
        while time.time() < deadline:
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if r:
                try:
                    chunk = os.read(master_fd, 4096).decode("utf-8", errors="replace")
                    buf.append(chunk)
                except OSError:
                    break
            if proc.poll() is not None:
                break
        proc.wait(timeout=5)
        os.close(master_fd)
        raw = "".join(buf)
        clean = ANSI.sub("", raw)
        return proc.returncode == 0, clean
    except Exception as e:
        return False, str(e)


# ── Classifier ────────────────────────────────────────────────────────────────

def needs_fail_tests(content: str) -> bool:
    """True if file has Bool-returning helpers but no existing fail tests."""
    has_bool_helper = bool(re.search(r'fn\s+\w+\s*\([^)]*\)\s*->\s*Bool', content))
    has_fail_test   = bool(re.search(r'\btest\b[^{]+\bfail\b\s*\{', content))
    return has_bool_helper and not has_fail_test


# ── Claude generation ──────────────────────────────────────────────────────────

def add_fail_tests_with_claude(client: anthropic.Anthropic, filepath: Path) -> str | None:
    content = filepath.read_text(encoding="utf-8")

    instruction = f"""\
This Aiken file has helper functions that return Bool but no `fail` tests yet.

Your task: Add 2–4 `test ... fail` property tests at the end of the file that prove
the helper functions correctly reject invalid inputs.

Rules:
- Choose fuzzer ranges that GUARANTEE the helper returns False
- Use `expect helper(args)` as the test body
- Do not modify anything already in the file
- Add any needed `use` imports (e.g. `use cardano/fuzz`) at the top if missing

Return the COMPLETE modified file.
Output ONLY the raw Aiken source code — no explanation, no markdown.
Start with the very first character of the file.

File: {filepath.name}
---
{content}
"""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=3000,
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


# ── Use-order fixer ────────────────────────────────────────────────────────────

def fix_use_order(code: str) -> str:
    """Move stray `use` statements to the top."""
    lines = code.splitlines()
    use_lines, other_lines = [], []
    for line in lines:
        s = line.strip()
        if s.startswith("use ") and not s.startswith("//"):
            if line not in use_lines:
                use_lines.append(line)
        else:
            other_lines.append(line)
    insert_at = 0
    for i, line in enumerate(other_lines):
        s = line.strip()
        if s.startswith("//") or s == "":
            insert_at = i + 1
        else:
            break
    result = other_lines[:insert_at] + use_lines + other_lines[insert_at:]
    return "\n".join(result)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n",           type=int, default=20)
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument("--log-failures",action="store_true")
    parser.add_argument("--files",       type=str, default=None,
                        help="Comma-separated list of filenames to process (e.g. 08b_cdp.ak,15_beacon.ak)")
    args = parser.parse_args()

    client = anthropic.Anthropic()

    if args.files:
        names = [n.strip() for n in args.files.split(",")]
        candidates = [PATTERNS_DIR / name for name in names if (PATTERNS_DIR / name).exists()]
        missing = [n for n in names if not (PATTERNS_DIR / n).exists()]
        if missing:
            print(f"  [WARN] Files not found: {missing}")
    else:
        candidates = [
            f for f in sorted(PATTERNS_DIR.glob("*.ak"))
            if needs_fail_tests(f.read_text(encoding="utf-8"))
        ]

    print(f"\n{'═'*60}")
    print(f"  add_fail_tests — candidates: {len(candidates)}  (processing up to {args.n})")
    print(f"{'═'*60}\n")

    if args.dry_run:
        print(f"{'File':<50}")
        print("-" * 50)
        for f in candidates:
            print(f"  {f.name}")
        print(f"\n  Total: {len(candidates)}")
        print(f"\n  (dry-run — nothing written)")
        return

    passed_files, failed_files = [], []

    for i, filepath in enumerate(candidates[:args.n]):
        print(f"  [{i+1:3d}/{min(args.n, len(candidates))}] {filepath.name}")
        print(f"         generating...", end="", flush=True)

        new_content = add_fail_tests_with_claude(client, filepath)
        if new_content is None:
            print(" ✗ API failed")
            failed_files.append({"file": filepath.name, "reason": "api_failed"})
            continue

        # Verify fail tests were actually added
        if not re.search(r'\btest\b[^{]+\bfail\b\s*\{', new_content):
            print(" ✗ no fail tests found in output")
            failed_files.append({"file": filepath.name, "reason": "no_fail_tests_generated"})
            continue

        print(f" compiling...", end="", flush=True)
        new_content = fix_use_order(new_content)
        ok, output = compile_check(new_content)

        if ok:
            n_fail = len(re.findall(r'\btest\b[^{]+\bfail\b\s*\{', new_content))
            print(f" ✅  (+{n_fail} fail tests)")
            filepath.write_text(new_content, encoding="utf-8")
            passed_files.append({"file": filepath.name, "fail_tests_added": n_fail})
        else:
            err = next((l.strip() for l in output.splitlines()
                        if l.strip() and any(k in l.lower()
                            for k in ("error", "×", "unexpected", "unknown", "unbound"))), "")
            print(f" ❌  {err[:70]}")
            failed_files.append({
                "file":    filepath.name,
                "reason":  "compile_failed",
                "error":   output[:400],
                "content": new_content,
            })

        time.sleep(0.3)

    print(f"\n{'═'*60}")
    print(f"  Passed : {len(passed_files)}/{min(args.n, len(candidates))}")
    print(f"  Failed : {len(failed_files)}/{min(args.n, len(candidates))}")
    print(f"{'═'*60}")

    if failed_files:
        print("\nFailed:")
        for f in failed_files:
            print(f"  ❌ {f['file']} — {f['reason']}")

    if failed_files and args.log_failures:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = LOGS_DIR / f"fail_tests_failures_{ts}.json"
        log_path.write_text(json.dumps({
            "run_at": ts, "model": MODEL,
            "passed": len(passed_files), "failed": len(failed_files),
            "failures": failed_files,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Failure log → {log_path}")

    if passed_files:
        print(f"\nUpdated files:")
        for f in passed_files:
            print(f"  ✅ {f['file']} (+{f['fail_tests_added']} fail tests)")


if __name__ == "__main__":
    main()
