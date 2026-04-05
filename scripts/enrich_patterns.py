#!/usr/bin/env python3
"""
enrich_patterns.py — Cardumen Forge
Enriches thin Aiken pattern files by adding or rewriting validator handlers.

Two modes:
  ADD    — file has no validator block; Claude writes one using existing helpers
  ENRICH — file has validator but handler body is ≤ 2 lines; Claude rewrites it

Every enriched file is verified with `aiken check --max-success=200`.
Only files that pass are overwritten.

Usage:
    python3 scripts/enrich_patterns.py --dry-run
    python3 scripts/enrich_patterns.py --n 20
    python3 scripts/enrich_patterns.py --n 200
    python3 scripts/enrich_patterns.py --mode add        # only ADD mode
    python3 scripts/enrich_patterns.py --mode enrich     # only ENRICH mode
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
LOGS_DIR     = ROOT / "logs" / "enrich"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 45
MODEL        = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
<role>
You are an expert Aiken v3 smart contract developer. Your job is to enrich Aiken files by
adding or rewriting validator handlers that demonstrate the helper functions already defined
in each file.
</role>

<output_format>
Return only the complete Aiken source file. Begin your response with the first line of the
file (a `use` statement or `//` comment). No explanation, no preamble, no markdown fences.
</output_format>

<goal>
The validator handler must call the helper functions already defined in the file.
The purpose is to show those helpers being used in a realistic validator — 5 to 15 lines
of handler body is the right size. Do not duplicate logic that helpers already handle.
Only use functions and types that exist in the file or in the stdlib.
</goal>

<import_rules>
Every module you call must have a corresponding `use` statement. Place all `use` statements
at the very top of the file — before any fn, type, const, or validator. Aiken's parser
rejects imports that appear anywhere else.

Common modules and when to import them:
  use aiken/collection/list      — list.all, list.any, list.filter, list.map, list.find
  use aiken/collection/dict      — dict.get, dict.size, dict.to_pairs, dict.foldl
  use aiken/primitive/bytearray  — bytearray.length, bytearray.take, bytearray.drop
  use cardano/assets             — assets.tokens, assets.lovelace_of, assets.flatten
  use cardano/transaction.{Transaction, OutputReference}
  use cardano/governance.{Voter} — Voter lives here, not in cardano/transaction
  use aiken/fuzz                 — generic fuzzers: int, bytearray, bool, both, map, list
  use cardano/fuzz               — Cardano-domain fuzzers: asset_name, policy_id,
                                   verification_key_hash, address, value
  These are two separate modules. Use aiken/fuzz for primitives, cardano/fuzz for Cardano types.

The file structure must always be: all `use` statements first, then types, then functions,
then the validator. Adding a `use` anywhere else causes an immediate parser error.

  Correct file order:
    use aiken/collection/list
    use cardano/transaction.{Transaction}

    pub type MyDatum { ... }

    fn my_helper(...) { ... }

    validator my_val { ... }

  Wrong (use after validator):
    validator my_val { ... }
    use aiken/collection/list    ← parser error: unexpected token 'use'
</import_rules>

<aiken_syntax>
Type definitions
  pub type is required — plain `type` causes a private_leak error.
  Fields are comma-separated, one per line, no extra spaces before the colon.

  Correct:
    pub type MyDatum {
      owner: ByteArray,
      amount: Int,
    }

Anonymous functions
  Separate statements with newlines, not semicolons.

  Correct:   fn(p) {
               let Pair(_, qty) = p
               qty > 0
             }
  Wrong:     fn(p) { let Pair(_, qty) = p; qty > 0 }

Pattern matching on constructors
  Import the constructor name first, then use it unqualified in the match arm.

  Correct:
    use cardano/address.{VerificationKey}
    ...
    when credential is {
      VerificationKey(vk) -> vk == owner
    }
  Wrong:  cardano/address.VerificationKey(vk) -> ...

assets.reduce
  Takes exactly 3 arguments: the Value, an initial accumulator, and a 4-arg callback.
  Correct: assets.reduce(self.mint, 0, fn(_policy, _name, qty, acc) { acc + qty })
  When simpler, use dict.foldl on assets.tokens(self.mint, policy_id) instead.

Option type
  Option is a prelude type — no import needed.
  In a spend handler, datum arrives as Option<YourDatum>.
  Unwrap with: expect Some(d) = datum

Governance vote handler
  Signature: vote(redeemer, voter: Voter, self: Transaction) — exactly 3 arguments.
  GovernanceActionId is not a handler parameter.

Interval helper
  interval.is_entirely_after(interval_value, int_deadline)
  First argument is the Interval, second is the Int deadline.

Pipe operator |>
  The pipe passes the left value as the first argument to the right function.
  Use it to chain data transformations, not to suppress or ignore a boolean result.

  Correct:   assets.tokens(self.mint, policy_id) |> dict.size >= 1
  Wrong:     some_bool |> fn(_) { True }   ← type mismatch; just write True directly
  Wrong:     expr |> fn(_) { other_expr }  ← use `let _ = expr\n other_expr` instead
</aiken_syntax>

<example>
A file with a thin spend handler that has helpers `is_signed_by` and `min_ada_paid`:

  Before (thin):
    validator vault {
      spend(_datum, _redeemer, _ref, self: Transaction) {
        True
      }
    }

  After (enriched):
    validator vault {
      spend(datum: Option<VaultDatum>, _redeemer, _ref, self: Transaction) {
        expect Some(d) = datum
        let signed = is_signed_by(self.extra_signatories, d.owner)
        let paid   = min_ada_paid(self.outputs, d.min_lovelace)
        signed && paid
      }
    }
</example>
"""


# ── Compile check ─────────────────────────────────────────────────────────────

def compile_check(code: str) -> tuple[bool, str]:
    """Write code to sandbox and run aiken check. Returns (passed, output)."""
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
        passed = proc.returncode == 0
        return passed, clean
    except Exception as e:
        return False, str(e)


# ── Classifier ────────────────────────────────────────────────────────────────

def classify_file(content: str) -> tuple[str, int]:
    """Returns ('add'|'enrich'|'ok', handler_line_count)."""
    if "validator" not in content:
        return "add", 0

    handler_match = re.search(
        r'\b(spend|mint|vote|withdraw|publish|propose)\s*\([^{]+\)\s*(?:->\s*\w+\s*)?\{',
        content
    )
    if not handler_match:
        return "add", 0

    start = handler_match.end()
    depth = 1
    i = start
    while i < len(content) and depth > 0:
        if content[i] == '{': depth += 1
        elif content[i] == '}': depth -= 1
        i += 1
    body = content[start:i-1]

    real_lines = [
        l.strip() for l in body.splitlines()
        if l.strip()
        and l.strip() not in ('{', '}', 'True', 'False', 'todo', 'fail')
        and not l.strip().startswith('//')
    ]
    n = len(real_lines)
    if n <= 2:
        return "enrich", n
    return "ok", n


# ── Claude enrichment ─────────────────────────────────────────────────────────

def enrich_with_claude(client: anthropic.Anthropic, filepath: Path, mode: str) -> str | None:
    """Ask Claude to add/enrich the validator. Returns new file content or None."""
    content = filepath.read_text(encoding="utf-8")

    if mode == "add":
        instruction = f"""\
This Aiken file defines helper functions and fuzz tests but has NO validator block.

Your task: Add a `validator` block at the end of the file (before the tests section if any,
or at the end) that uses the helper functions already defined above.

The validator should:
- Choose the most appropriate handler type (spend/mint/withdraw) based on the helpers
- Call the helper functions — don't duplicate their logic inline
- Be realistic: 5-15 lines of handler body
- Add any missing `use` imports at the top if needed (keep them before the validator)

Return the COMPLETE modified file. Do not change helpers or tests — only add the validator.
CRITICAL: Output ONLY the raw Aiken source code. No explanation, no preamble, no reasoning, no markdown.
Your response must start with the very first character of the file (a `use` statement or `//` comment).

File: {filepath.name}
---
{content}
"""
    else:  # enrich
        instruction = f"""\
This Aiken file has a validator, but the handler body is too thin (≤ 2 lines).
The file defines helper functions that are NOT being used in the validator.

Your task: Rewrite ONLY the validator handler body to:
- Actually call the helper functions defined in this file
- Add meaningful logic: check multiple conditions, use the datum, check outputs
- Be realistic: 5-15 lines of handler body
- Do NOT add new helper functions — use only what's already defined

Return the COMPLETE modified file. Do not change helpers or tests — only rewrite the handler body.
CRITICAL: Output ONLY the raw Aiken source code. No explanation, no preamble, no reasoning, no markdown.
Your response must start with the very first character of the file (a `use` statement or `//` comment).

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
        # Strip markdown fences if present
        if result.startswith("```"):
            result = re.sub(r'^```[a-z]*\n?', '', result)
            result = re.sub(r'\n?```$', '', result)
        return result
    except Exception as e:
        print(f"    API error: {e}")
        return None


# ── Use-order fixer ───────────────────────────────────────────────────────────

def fix_use_order(code: str) -> str:
    """Move any stray `use` statements to the top of the file (Aiken parser requirement)."""
    lines = code.splitlines()
    use_lines = []
    other_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("use ") and not stripped.startswith("//"):
            if line not in use_lines:
                use_lines.append(line)
        else:
            other_lines.append(line)

    # Find where to insert: after leading blank lines / file-level comments
    insert_at = 0
    for i, line in enumerate(other_lines):
        s = line.strip()
        if s.startswith("//") or s == "":
            insert_at = i + 1
        else:
            break

    result = other_lines[:insert_at] + use_lines + other_lines[insert_at:]
    return "\n".join(result)


# ── Missing-import fixer ───────────────────────────────────────────────────────

# Map: regex pattern that detects usage → canonical `use` line to inject
_IMPLICIT_IMPORTS = [
    (re.compile(r'\blist\.'),       "use aiken/collection/list"),
    (re.compile(r'\bdict\.'),       "use aiken/collection/dict"),
    (re.compile(r'\bbytearray\.'),  "use aiken/primitive/bytearray"),
    (re.compile(r'\bassets\.'),     "use cardano/assets"),
    (re.compile(r'\binterval\.'),   "use aiken/interval"),
    (re.compile(r'\bmath\.'),       "use aiken/math"),
    (re.compile(r'\bstring\.'),     "use aiken/primitive/string"),
]

def fix_missing_imports(code: str) -> str:
    """Inject missing `use` statements inferred from module calls in the code."""
    for pattern, use_line in _IMPLICIT_IMPORTS:
        already_imported = use_line in code
        if not already_imported and pattern.search(code):
            code = use_line + "\n" + code
    return code


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n",       type=int, default=20,
                        help="Max files to process (default: 20)")
    parser.add_argument("--mode",    choices=["add", "enrich", "both"], default="both",
                        help="Which mode to run: add (missing validator), enrich (thin handler), both")
    parser.add_argument("--dry-run", action="store_true",
                        help="Classify files and show plan, don't call API")
    parser.add_argument("--log-failures", action="store_true")
    args = parser.parse_args()

    client = anthropic.Anthropic()

    # Classify all files
    candidates = []
    for f in sorted(PATTERNS_DIR.glob("*.ak")):
        content = f.read_text(encoding="utf-8")
        mode, n = classify_file(content)
        if mode != "ok":
            if args.mode == "both" or args.mode == mode:
                candidates.append((f, mode, n))

    print(f"\n{'═'*60}")
    print(f"  enrich_patterns — mode: {args.mode}")
    print(f"  candidates: {len(candidates)}  (processing up to {args.n})")
    print(f"{'═'*60}\n")

    if args.dry_run:
        print(f"{'File':<45} {'Mode':<8} {'Lines'}")
        print("-" * 60)
        for f, mode, n in candidates:
            print(f"{f.name:<45} {mode.upper():<8} {n}")
        print(f"\n  Total ADD:    {sum(1 for _,m,_ in candidates if m=='add')}")
        print(f"  Total ENRICH: {sum(1 for _,m,_ in candidates if m=='enrich')}")
        print(f"\n  (dry-run — nothing written)")
        return

    passed_files = []
    failed_files = []

    for i, (filepath, mode, n_lines) in enumerate(candidates[:args.n]):
        print(f"  [{i+1:3d}/{min(args.n, len(candidates))}] {filepath.name} ({mode.upper()}, {n_lines} lines)")
        print(f"         generating...", end="", flush=True)

        new_content = enrich_with_claude(client, filepath, mode)
        if new_content is None:
            print(" ✗ API failed")
            failed_files.append({"file": filepath.name, "mode": mode, "reason": "api_failed"})
            continue

        print(f" compiling...", end="", flush=True)
        new_content = fix_missing_imports(new_content)
        new_content = fix_use_order(new_content)
        ok, output = compile_check(new_content)

        if ok:
            # Re-classify to check improvement
            _, new_n = classify_file(new_content)
            if new_n <= n_lines and mode == "enrich":
                print(f" ⚠️  no improvement ({n_lines} → {new_n} lines), skipping")
                failed_files.append({"file": filepath.name, "mode": mode, "reason": "no_improvement",
                                     "lines_before": n_lines, "lines_after": new_n})
                continue
            print(f" ✅  ({n_lines} → {new_n} lines)")
            # Overwrite the original file
            filepath.write_text(new_content, encoding="utf-8")
            passed_files.append({"file": filepath.name, "mode": mode, "lines_before": n_lines, "lines_after": new_n})
        else:
            err = next((l.strip() for l in output.splitlines()
                        if l.strip() and any(k in l.lower()
                            for k in ("error", "×", "unexpected", "unknown", "unbound"))), "")
            print(f" ❌  {err[:70]}")
            failed_files.append({
                "file":    filepath.name,
                "mode":    mode,
                "reason":  "compile_failed",
                "error":   output[:400],
                "content": new_content,
            })

        time.sleep(0.3)

    # Summary
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
        log_path = LOGS_DIR / f"enrich_failures_{ts}.json"
        log_path.write_text(json.dumps({
            "run_at": ts, "model": MODEL,
            "passed": len(passed_files), "failed": len(failed_files),
            "failures": failed_files,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Failure log → {log_path}")

    if passed_files:
        print(f"\nEnriched files:")
        for f in passed_files:
            print(f"  ✅ {f['file']} ({f['lines_before']} → {f['lines_after']} lines)")


if __name__ == "__main__":
    main()
