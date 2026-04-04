#!/usr/bin/env python3
"""
promote_plausible.py — Cardumen Forge

Promotes PLAUSIBLE_NEEDS_CHECK examples to VERIFIED_V3_ALIGNED using two strategies:

  Path A — Compile check (pure validator outputs):
    Only for outputs that are pure Aiken code (no prose).
    Runs `aiken check`. Pass → VERIFIED_V3_ALIGNED.

  Path B — Field/pattern check (Q&A / explanation outputs):
    For outputs that mix explanation with code snippets.
    Checks that no banned patterns or invalid field accesses appear.
    Pass → VERIFIED_V3_ALIGNED.

Valid fields (from local stdlib cardano/transaction.ak):
  Transaction : inputs, reference_inputs, outputs, fee, mint, certificates,
                withdrawals, validity_range, extra_signatories, redeemers, datums,
                id, votes, proposal_procedures, current_treasury_amount, treasury_donation
  Output      : address, value, datum, reference_script
  Input       : output_reference, output
  OutputReference : transaction_id, output_index

Usage:
    python3 scripts/promote_plausible.py --sample 50        # dry-run on 50
    python3 scripts/promote_plausible.py --dry-run          # full scan, no writes
    python3 scripts/promote_plausible.py --apply            # full scan + write
    python3 scripts/promote_plausible.py --apply --path-a-only   # compile-check only
    python3 scripts/promote_plausible.py --apply --path-b-only   # pattern-check only
"""

import os
import re
import sys
import json
import time
import shutil
import argparse
import subprocess
import pty
import select
import random
from pathlib import Path
from collections import defaultdict

ROOT         = Path(__file__).parent.parent
DATASET      = ROOT / "data" / "processed" / "dataset_v22.jsonl"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
FAIL_LOG     = ROOT / "logs" / "promote_plausible_failures.jsonl"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30

# ── Banned patterns (known hallucinations / v2 leftovers) ─────────────────────
BANNED = [
    r'\bfn\s+(spend|mint|withdraw|publish|vote|propose)\s*\(',  # fn prefix on handlers
    r'\blist\.has_any\b',
    r'\btransaction\.signatories\b',
    r'output\.value\.lovelace\b',
    r'\binterval\.is_after\b',
    r'\binterval\.is_before\b',
    r'use cardano/governance/transaction',
    r'\bScriptCredential\b',
    r'\bPubKeyCredential\b',
    r'\bMintedValue\b',
    r'\bGovernanceCommittee\b',
    r'\bGovernanceCouncil\b',
    r'\bself\.proposals\b',         # wrong field (should be proposal_procedures)
    r'\bself\.context\b',           # doesn't exist
    r'\binput\.value\b',            # wrong (should be input.output.value)
    r'\bScriptContext\b',           # v2 pattern, doesn't exist in v3
    r'use aiken/transaction\b',     # v2 import path
]
BANNED_RE = [re.compile(p) for p in BANNED]

# ── Valid field sets from local stdlib ────────────────────────────────────────
VALID_TRANSACTION_FIELDS = {
    "inputs", "reference_inputs", "outputs", "fee", "mint", "certificates",
    "withdrawals", "validity_range", "extra_signatories", "redeemers", "datums",
    "id", "votes", "proposal_procedures", "current_treasury_amount", "treasury_donation",
}
VALID_OUTPUT_FIELDS   = {"address", "value", "datum", "reference_script"}
VALID_INPUT_FIELDS    = {"output_reference", "output"}
VALID_OUTREF_FIELDS   = {"transaction_id", "output_index"}

# Common parameter names used in handlers for Transaction
TX_PARAM_NAMES = {"self", "tx", "transaction", "ctx"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def has_banned_pattern(text: str) -> tuple[bool, str]:
    for pat in BANNED_RE:
        m = pat.search(text)
        if m:
            return True, m.group(0)
    return False, ""


def has_invalid_tx_fields(text: str) -> tuple[bool, str]:
    """Check .field accesses on known tx param names against valid field list."""
    # Pattern: self.field_name or tx.field_name etc.
    for param in TX_PARAM_NAMES:
        for m in re.finditer(rf'\b{re.escape(param)}\.(\w+)', text):
            field = m.group(1)
            if field not in VALID_TRANSACTION_FIELDS:
                return True, f"{param}.{field}"
    return False, ""


def is_pure_aiken(output: str) -> bool:
    """
    Returns True only if the output looks like a standalone Aiken source file
    (no prose lines, no markdown, pure code).
    """
    stripped = output.strip()
    if not stripped:
        return False
    if "validator" not in stripped:
        return False

    lines = stripped.split("\n")
    prose_count = 0
    code_count  = 0

    AIKEN_STARTS = (
        "use ", "pub ", "type ", "validator", "fn ", "let ", "//", "  ", "\t",
        "}", "{", "|", "when ", "if ", "else", "expect ", "trace ", "todo",
    )

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith(tuple(AIKEN_STARTS)):
            code_count += 1
        elif re.match(r'^[A-Z][a-z]', s) and not re.match(r'^[A-Z]\w*\s*[\({<]', s):
            # Starts with capital letter + lowercase → sentence/prose
            prose_count += 1
        elif s.startswith(("#", "*", "-", ">", "```", "##")):
            # Markdown elements
            prose_count += 1
        elif re.search(r'[.!?]$', s) and len(s) > 40:
            # Long line ending with punctuation → prose
            prose_count += 1
        else:
            code_count += 1

    if prose_count == 0 and code_count > 0:
        return True
    if code_count > 0 and prose_count / (prose_count + code_count) < 0.1:
        return True
    return False


# ── Path A: compile check ─────────────────────────────────────────────────────

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


def first_error(text: str) -> str:
    for line in text.splitlines():
        if "Error" in line or "error" in line:
            return line.strip()[:120]
    return text[:120]


# ── Path B: pattern/field check ──────────────────────────────────────────────

def path_b_check(output: str) -> tuple[bool, str]:
    """
    Returns (pass, reason).
    Promotes if: no banned patterns AND no invalid tx field accesses.
    """
    banned, pat = has_banned_pattern(output)
    if banned:
        return False, f"banned pattern: {pat}"
    invalid, field = has_invalid_tx_fields(output)
    if invalid:
        return False, f"invalid tx field: {field}"
    return True, ""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument("--apply",       action="store_true")
    parser.add_argument("--sample",      type=int, default=None)
    parser.add_argument("--seed",        type=int, default=42)
    parser.add_argument("--path-a-only", action="store_true", help="Compile-check only")
    parser.add_argument("--path-b-only", action="store_true", help="Pattern-check only")
    parser.add_argument("--verbose",     action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.apply and args.sample is None:
        parser.error("Specify --dry-run, --apply, or --sample N")

    examples = []
    with DATASET.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    plausible_idx = [
        i for i, ex in enumerate(examples)
        if ex.get("review_status") == "PLAUSIBLE_NEEDS_CHECK"
    ]

    target_idx = plausible_idx
    if args.sample:
        random.seed(args.seed)
        target_idx = random.sample(plausible_idx, min(args.sample, len(plausible_idx)))

    # Split into pure-code vs mixed
    pure_code_idx = [i for i in target_idx if is_pure_aiken(examples[i].get("output", ""))]
    mixed_idx     = [i for i in target_idx if not is_pure_aiken(examples[i].get("output", ""))]

    print(f"Dataset     : {len(examples)} total")
    print(f"PLAUSIBLE   : {len(plausible_idx)}")
    if args.sample:
        print(f"Sample      : {len(target_idx)} (seed={args.seed})")
    print(f"  Path A    : {len(pure_code_idx)} pure-code outputs → compile check")
    print(f"  Path B    : {len(mixed_idx)} Q&A/mixed outputs → pattern check")
    print()

    promoted_a = []
    promoted_b = []
    failures   = []
    stats      = defaultdict(lambda: {"a_pass": 0, "a_fail": 0, "b_pass": 0, "b_fail": 0})

    # ── Path A ────────────────────────────────────────────────────────────────
    if not args.path_b_only:
        print(f"── Path A: compile check ({len(pure_code_idx)} examples) ──")
        for n, i in enumerate(pure_code_idx, 1):
            ex     = examples[i]
            source = ex.get("source", "?")
            instr  = ex.get("instruction", "")[:55]
            code   = ex["output"]

            passed, err = compile_check(code)
            if passed:
                promoted_a.append(i)
                stats[source]["a_pass"] += 1
                symbol = "✅ A"
            else:
                err_short = first_error(err)
                failures.append({"dataset_idx": i, "path": "A", "source": source,
                                  "instruction": ex.get("instruction", ""),
                                  "error": err_short})
                stats[source]["a_fail"] += 1
                symbol = "❌ A"

            print(f"  [{n:4d}/{len(pure_code_idx)}] {symbol} {source:<25} | {instr}")
            if args.verbose and not passed:
                print(f"          {first_error(err)}")

    # ── Path B ────────────────────────────────────────────────────────────────
    if not args.path_a_only:
        print(f"\n── Path B: pattern check ({len(mixed_idx)} examples) ──")
        b_pass = b_fail = 0
        for n, i in enumerate(mixed_idx, 1):
            ex     = examples[i]
            source = ex.get("source", "?")
            instr  = ex.get("instruction", "")[:55]
            output = ex["output"]

            passed, reason = path_b_check(output)
            if passed:
                promoted_b.append(i)
                stats[source]["b_pass"] += 1
                b_pass += 1
                symbol = "✅ B"
            else:
                failures.append({"dataset_idx": i, "path": "B", "source": source,
                                  "instruction": ex.get("instruction", ""),
                                  "error": reason})
                stats[source]["b_fail"] += 1
                b_fail += 1
                symbol = "❌ B"

            if args.verbose or not passed:
                print(f"  [{n:4d}/{len(mixed_idx)}] {symbol} {source:<25} | {instr}")
                if not passed and args.verbose:
                    print(f"          {reason}")

        if not args.verbose:
            print(f"  Pass: {b_pass}  Fail: {b_fail}")

    # ── Summary ───────────────────────────────────────────────────────────────
    total_promoted = len(promoted_a) + len(promoted_b)
    print(f"\n{'='*60}")
    print(f"  Path A (compile)  : {len(promoted_a)} promoted / {len(pure_code_idx)} scanned")
    print(f"  Path B (patterns) : {len(promoted_b)} promoted / {len(mixed_idx)} scanned")
    print(f"  Total promoted    : {total_promoted} → VERIFIED_V3_ALIGNED")
    print(f"  Failures          : {len(failures)}")
    print()
    print("  By source (A_pass / A_fail / B_pass / B_fail):")
    for src, c in sorted(stats.items(), key=lambda x: -(sum(x[1].values()))):
        print(f"    {src:<35} A:{c['a_pass']}/{c['a_pass']+c['a_fail']}  "
              f"B:{c['b_pass']}/{c['b_pass']+c['b_fail']}")

    # Always save failure log
    if failures:
        FAIL_LOG.parent.mkdir(exist_ok=True)
        with FAIL_LOG.open("w", encoding="utf-8") as f:
            for entry in failures:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"\n  Failures → {FAIL_LOG}")

    if args.dry_run or args.sample:
        print(f"\n  DRY RUN — no changes written.")
        print(f"  Re-run with --apply to promote {total_promoted} examples.")
        return

    if not total_promoted:
        print("  Nothing to promote.")
        return

    for i in promoted_a + promoted_b:
        examples[i]["review_status"] = "VERIFIED_V3_ALIGNED"

    with DATASET.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"\n  Written  : {DATASET}")
    print(f"  Promoted : {total_promoted} examples → VERIFIED_V3_ALIGNED")


if __name__ == "__main__":
    main()
