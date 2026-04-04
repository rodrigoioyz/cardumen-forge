#!/usr/bin/env python3
"""
fix_plausible_failures.py — Cardumen Forge

Repairs PLAUSIBLE_NEEDS_CHECK examples that failed compile-check in promote_plausible.py.
Uses Claude API with local stdlib as context ground truth.

Targets: type_cycle (90) + type_mismatch (3) + banned_pattern (6) = ~99 examples.
Skips:   parser_error (8) — not rescatable as standalone Aiken.
         unknown_module (17) — investigated separately.

Strategy per error type:
  type_cycle    — break circular type alias: `type Foo = Option<Foo>` →
                  `pub type Foo { FooConstructor(Option<Foo>) }`
  type_mismatch — fix type usage errors using stdlib type definitions
  banned_pattern — replace ScriptContext / invalid patterns with v3 equivalents

Usage:
    python3 scripts/fix_plausible_failures.py --dry-run --limit 5
    python3 scripts/fix_plausible_failures.py --apply --limit 20
    python3 scripts/fix_plausible_failures.py --apply
    python3 scripts/fix_plausible_failures.py --apply --error-type type_cycle
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
FAIL_LOG     = ROOT / "logs" / "promote_plausible_failures.jsonl"
REPAIR_LOG   = ROOT / "logs" / "fix_plausible_repair.jsonl"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
STDLIB_LIB   = SANDBOX_DIR / "build" / "packages" / "aiken-lang-stdlib" / "lib"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30
MAX_RETRIES  = 3


# ── Load local stdlib as context ──────────────────────────────────────────────

def load_stdlib_context() -> str:
    """Load key type definitions from local stdlib source files."""
    files = [
        ("cardano/transaction",  STDLIB_LIB / "cardano" / "transaction.ak"),
        ("cardano/governance",   STDLIB_LIB / "cardano" / "governance.ak"),
        ("cardano/address",      STDLIB_LIB / "cardano" / "address.ak"),
        ("cardano/assets",       STDLIB_LIB / "cardano" / "assets.ak"),
        ("cardano/certificate",  STDLIB_LIB / "cardano" / "certificate.ak"),
    ]
    parts = []
    for label, path in files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        # Keep only pub type blocks + first comment for each
        blocks = re.findall(
            r'(?:///[^\n]*\n)*pub type \w+.*?(?=\n(?:pub |use |\Z))',
            text, re.DOTALL
        )
        if blocks:
            snippet = "\n".join(b[:800] for b in blocks[:8])
            parts.append(f"// === {label} ===\n{snippet}")
    return "\n\n".join(parts)


STDLIB_CONTEXT = load_stdlib_context()

SYSTEM_PROMPT = f"""\
You are an expert Aiken v3 smart contract developer. Your task is to fix a broken Aiken v3 validator.

=== AIKEN v3 RULES ===
IMPORTS:
  use aiken/collection/list
  use aiken/interval
  use cardano/assets
  use cardano/transaction.{{Transaction, OutputReference, InlineDatum, Input, Output}}
  use cardano/governance.{{ConstitutionalCommitteeMember, DelegateRepresentative, StakePool, Voter}}
  use cardano/address.{{Credential}}
  -- Constructors must be imported explicitly (not auto-imported with the type)

HANDLER SIGNATURES:
  spend(datum: Option<Data>, redeemer: r, own_ref: OutputReference, self: Transaction)
  mint(redeemer: r, policy_id: PolicyId, self: Transaction)
  vote(redeemer: r, voter: Voter, self: Transaction)
  propose(redeemer: r, proposal: ProposalProcedure, self: Transaction)
  -- All types in handler signatures MUST use `pub type`, never bare `type`

TYPE CYCLE FIX:
  WRONG:  type Foo = Option<Foo>           -- recursive type alias, not allowed
  WRONG:  type A = B   +   type B = A      -- mutual alias cycle
  CORRECT: pub type Foo {{ FooSome(Option<Foo>) | FooNone }}  -- ADT, cycles are fine in constructors
  CORRECT: pub type Wrapper {{ Wrap(InnerType) }}  -- use a real ADT, not alias

=== LOCAL STDLIB TYPE DEFINITIONS (ground truth) ===
{STDLIB_CONTEXT}

=== TASK ===
You will receive:
  1. The broken Aiken code
  2. The `aiken check` error message
  3. The error category

Return ONLY the fixed Aiken code — no explanation, no markdown fences, no commentary.
The fix must be minimal: change only what the error requires.
"""


# ── Compile check ─────────────────────────────────────────────────────────────

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


def get_full_error(code: str) -> str:
    _, err = compile_check(code)
    return err


# ── Classify error type ───────────────────────────────────────────────────────

def classify_error(error: str) -> str:
    if "cycle" in error:
        return "type_cycle"
    if "type_mismatch" in error:
        return "type_mismatch"
    if "banned pattern" in error or "ScriptContext" in error or "invalid tx field" in error:
        return "banned_pattern"
    if "parser" in error.lower():
        return "parser_error"
    if "unknown::module" in error:
        return "unknown_module"
    return "other"


SKIPPABLE = {"parser_error", "unknown_module"}


# ── Claude API repair ─────────────────────────────────────────────────────────

def repair_with_claude(client, code: str, error_msg: str, error_type: str) -> str | None:
    user_msg = f"""\
Error category: {error_type}

Compiler error:
{error_msg[:1200]}

Broken Aiken code:
{code}
"""
    for attempt in range(1, MAX_RETRIES + 1):
        resp = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        fixed = resp.content[0].text.strip()
        fixed = re.sub(r'^```\w*\n?', '', fixed)
        fixed = re.sub(r'\n?```$', '', fixed)

        passed, new_err = compile_check(fixed)
        if passed:
            return fixed

        # Feed error back for next attempt
        if attempt < MAX_RETRIES:
            user_msg = f"""\
Error category: {error_type}

Your previous fix still fails. New compiler error:
{new_err[:1200]}

Your previous (still broken) code:
{fixed}

Original broken code for reference:
{code}
"""
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--apply",      action="store_true")
    parser.add_argument("--limit",      type=int, default=None, help="Max examples to process")
    parser.add_argument("--error-type", default=None,
                        choices=["type_cycle", "type_mismatch", "banned_pattern", "all"],
                        help="Filter by error category")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    # Load failures
    failures = []
    with FAIL_LOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                failures.append(json.loads(line))

    # Filter
    target_errors = {"type_cycle", "type_mismatch", "banned_pattern"}
    if args.error_type and args.error_type != "all":
        target_errors = {args.error_type}

    targets = []
    skipped_type = 0
    for entry in failures:
        etype = classify_error(entry["error"])
        if etype in SKIPPABLE or etype not in target_errors:
            skipped_type += 1
            continue
        targets.append({**entry, "error_type": etype})

    if args.limit:
        targets = targets[:args.limit]

    print(f"Failure log     : {len(failures)} entries")
    print(f"Skipped (parser/unknown_module): {skipped_type}")
    print(f"To repair       : {len(targets)}")
    if args.error_type:
        print(f"Filter          : {args.error_type}")
    print(f"Stdlib context  : {len(STDLIB_CONTEXT)} chars loaded from local files")
    print()

    if args.dry_run:
        print("DRY RUN — would repair:")
        from collections import Counter
        ct = Counter(t["error_type"] for t in targets)
        for etype, count in ct.most_common():
            print(f"  {etype:<20} {count}")
        return

    # Load dataset
    examples = []
    with DATASET.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    client = anthropic.Anthropic()

    repaired  = []
    still_bad = []
    repair_records = []

    for n, entry in enumerate(targets, 1):
        idx    = entry["dataset_idx"]
        etype  = entry["error_type"]
        source = entry["source"]
        instr  = entry["instruction"][:55]

        ex   = examples[idx]
        code = ex["output"]

        # Get full compiler error (not just the summary)
        full_err = get_full_error(code)

        print(f"[{n:3d}/{len(targets)}] {etype:<15} {source:<30} | {instr}")

        fixed_code = repair_with_claude(client, code, full_err, etype)

        if fixed_code:
            examples[idx]["output"]        = fixed_code
            examples[idx]["review_status"] = "VERIFIED_V3_ALIGNED"
            repaired.append(idx)
            repair_records.append({
                "dataset_idx": idx, "source": source,
                "error_type": etype, "status": "repaired",
                "instruction": entry["instruction"][:120],
            })
            print(f"  ✅ repaired")
        else:
            still_bad.append(idx)
            repair_records.append({
                "dataset_idx": idx, "source": source,
                "error_type": etype, "status": "failed",
                "instruction": entry["instruction"][:120],
            })
            print(f"  ❌ could not fix after {MAX_RETRIES} attempts")

    print(f"\n{'='*60}")
    print(f"  Repaired  : {len(repaired)}")
    print(f"  Failed    : {len(still_bad)}")

    # Save repair log
    REPAIR_LOG.parent.mkdir(exist_ok=True)
    with REPAIR_LOG.open("w", encoding="utf-8") as f:
        for r in repair_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  Log       : {REPAIR_LOG}")

    if not repaired:
        print("  Nothing to write.")
        return

    with DATASET.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"  Written   : {DATASET}")
    print(f"  Promoted  : {len(repaired)} → VERIFIED_V3_ALIGNED")


if __name__ == "__main__":
    main()
