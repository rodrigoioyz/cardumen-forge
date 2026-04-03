#!/usr/bin/env python3
"""
regenerate_failing.py — Cardumen Forge

Uses Claude API to rewrite dataset examples that fail aiken check.
Extracts the compile error, sends instruction + broken code + error to Claude,
replaces the output with the corrected code.

Usage:
    python3 scripts/regenerate_failing.py --source generated_governance_v1 --dry-run
    python3 scripts/regenerate_failing.py --source generated_governance_v1 --apply
    python3 scripts/regenerate_failing.py --source generated_governance_v1 --apply --limit 5
"""

import re
import os
import sys
import json
import time
import argparse
import subprocess
import pty
import select
from pathlib import Path
from collections import defaultdict

import anthropic

ROOT          = Path(__file__).parent.parent
DATASET       = ROOT / "data" / "processed" / "dataset_v22.jsonl"
SANDBOX_DIR   = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE  = SANDBOX_DIR / "validators" / "output.ak"

ANSI = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')

STDLIB_REF = """\
=== IMPORT RULES ===
CORRECT import style (always use slash, never dot):
  use aiken/collection/list
  use aiken/collection/dict
  use aiken/crypto.{VerificationKeyHash, ScriptHash}
  use aiken/interval.{Interval, Finite, NegativeInfinity, PositiveInfinity}
  use cardano/address.{Credential, Address}
  use cardano/assets.{PolicyId, AssetName, Value, Lovelace}
  use cardano/transaction.{Transaction, Input, Output, OutputReference}
  use cardano/governance.{Voter, GovernanceAction, ProposalProcedure}
  use cardano/certificate.{Certificate}

WRONG (never use dot-style): use cardano.transaction  use aiken.interval
WRONG (no nested slashes): use cardano/governance/transaction
WRONG (braces on path): use cardano/assets/{Assets}

=== ASSETS API (cardano/assets) ===
  assets.lovelace(value: Value) -> Int              -- NOT output.value.lovelace
  assets.quantity_of(value: Value, policy: PolicyId, name: AssetName) -> Int
  assets.policies(value: Value) -> List<PolicyId>   -- NOT dict.to_pairs(value)
  assets.tokens(value: Value, policy: PolicyId) -> Dict<AssetName, Int>
  assets.flatten(value: Value) -> List<(PolicyId, AssetName, Int)>

=== INTERVAL API (aiken/interval) ===
  -- Check if a point is after/before a bound:
  interval.is_entirely_before(interval: Interval<Int>, point: Int) -> Bool
  interval.is_entirely_after(interval: Interval<Int>, point: Int) -> Bool
  -- There is NO interval.is_after or interval.is_before function
  -- Use validity_range field directly: self.validity_range
  -- Bound types: Finite(Int), NegativeInfinity, PositiveInfinity
  -- Example: when self.validity_range.lower_bound.bound_type is { Finite(t) -> t > deadline ... }

=== LIST API (aiken/collection/list) ===
  list.any(list, fn) -> Bool     -- NOT list.has_any
  list.all(list, fn) -> Bool
  list.has(list, item) -> Bool   -- checks membership
  list.filter(list, fn) -> List
  list.map(list, fn) -> List
  list.foldl(list, zero, fn) -> b
  list.length(list) -> Int
  -- There is NO list.has_any, list.count

=== TRANSACTION (cardano/transaction) ===
  -- In v3 handlers, the transaction param is named 'self', NOT 'tx' or 'ctx'
  -- self.extra_signatories : List<VerificationKeyHash>
  -- self.validity_range    : Interval<Int>
  -- self.inputs            : List<Input>
  -- self.outputs           : List<Output>
  -- self.mint              : Value
  -- self.withdrawals       : Pairs<Credential, Lovelace>
  -- Output fields: output.address, output.value (Value), output.datum, output.reference_script

=== HANDLER SIGNATURES (v3) ===
  spend(datum: Option<Data>, redeemer: r, own_ref: OutputReference, self: Transaction)
  mint(redeemer: r, policy_id: PolicyId, self: Transaction)
  withdraw(redeemer: r, account: Credential, self: Transaction)
  vote(redeemer: r, voter: Voter, self: Transaction)
  publish(redeemer: r, cert: Certificate, self: Transaction)
  propose(redeemer: r, proposal: ProposalProcedure, self: Transaction)
  -- No 'fn' keyword inside validator block
  -- All top-level types used in handlers must be 'pub type'

=== GOVERNANCE TYPES (cardano/governance) ===
  pub type Voter {
    ConstitutionalCommitteeMember(Credential)
    DelegateRepresentative(Credential)
    StakePool(VerificationKeyHash)
  }
  pub type GovernanceAction {
    ProtocolParameters { .. }
    HardFork { .. }
    TreasuryWithdrawal { beneficiaries: Pairs<Credential, Lovelace>, guardrails: Option<ScriptHash> }
    NoConfidence { .. }
    ConstitutionalCommittee { .. }
    NewConstitution { .. }
    NicePoll
  }
  pub type ProposalProcedure {
    deposit: Lovelace,
    return_address: Credential,
    governance_action: GovernanceAction,
  }

=== CERTIFICATE TYPES (cardano/certificate) ===
  RegisterCredential { credential: Credential, deposit: Option<Lovelace> }
  UnregisterCredential { credential: Credential, refund: Option<Lovelace> }
  DelegateCredential { credential: Credential, delegate: Delegate }
  RegisterAndDelegateCredential { credential: Credential, delegate: Delegate, deposit: Lovelace }
  RegisterDelegateRepresentative { delegate_representative: Credential, deposit: Lovelace }
  UnregisterDelegateRepresentative { delegate_representative: Credential, refund: Lovelace }
  UpdateDelegateRepresentative { delegate_representative: Credential }
  RetireStakePool { stake_pool: StakePoolId, at_epoch: Int }
  AuthorizeConstitutionalCommitteeProxy { .. }
  RetireFromConstitutionalCommittee { .. }
"""

SYSTEM_PROMPT = """\
You are an expert Aiken v3 smart contract developer. Your task is to fix broken Aiken v3 code.
You will receive:
1. The original instruction
2. The broken code that fails to compile
3. The exact compiler error

Fix the code so it compiles correctly with aiken-lang/stdlib v3.0.0.

""" + STDLIB_REF + """
Output ONLY the corrected Aiken code — no explanation, no markdown fences, no commentary.
"""


def compile_check(code: str) -> tuple[bool, str]:
    """Returns (passed, error_text)."""
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        ["aiken", "check"],
        cwd=SANDBOX_DIR,
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        close_fds=True,
        env={**os.environ, "TERM": "xterm-256color", "COLUMNS": "200"},
    )
    os.close(slave_fd)
    chunks = []
    deadline = time.time() + 30
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


def rewrite_with_claude(client, instruction: str, broken_code: str, error: str) -> str:
    user_msg = f"""Instruction: {instruction}

Broken code:
```
{broken_code}
```

Compiler error:
{error}

Fix the code."""

    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text.strip()
    # Strip any accidental fences
    raw = re.sub(r'^```\w*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    return raw.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source",  required=True, help="Source to process (e.g. generated_governance_v1)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, don't write")
    parser.add_argument("--apply",   action="store_true", help="Write fixed examples back to dataset")
    parser.add_argument("--limit",   type=int, default=None, help="Max examples to attempt")
    parser.add_argument("--retries", type=int, default=3, help="Max Claude retries per example")
    parser.add_argument("--out",     default=None, help="Output path (default: overwrite input)")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    client = anthropic.Anthropic()

    # Load dataset
    examples = []
    with DATASET.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    subset_indices = [i for i, e in enumerate(examples) if e.get("source") == args.source]
    print(f"Loaded  : {len(examples)} examples")
    print(f"Source  : {args.source} ({len(subset_indices)} examples)")

    # Find failing ones
    print("\nRunning compile check to find failures...")
    failing = []
    for idx in subset_indices:
        ex = examples[idx]
        code = ex.get("output", "")
        if not code.strip():
            continue
        passed, error_text = compile_check(code)
        if not passed:
            failing.append((idx, ex, error_text))

    print(f"Failing : {len(failing)}/{len(subset_indices)}")

    if args.limit:
        failing = failing[:args.limit]
        print(f"Limited : processing {len(failing)} examples")

    if not failing:
        print("Nothing to fix.")
        return

    if args.dry_run:
        print("\nDry-run — would attempt to fix:")
        for idx, ex, err in failing:
            print(f"  [{idx}] {ex['instruction'][:70]}")
            err_line = next((l for l in err.splitlines() if "Error" in l), "")
            print(f"         {err_line.strip()}")
        return

    # Fix each failing example
    fixed = 0
    still_failing = 0
    log = []

    for idx, ex, error_text in failing:
        instruction = ex["instruction"]
        broken_code = ex["output"]
        print(f"\n[{idx}] {instruction[:70]}")

        err_short = next((l.strip() for l in error_text.splitlines() if "Error" in l), "compile error")
        print(f"  Error: {err_short}")

        success = False
        for attempt in range(1, args.retries + 1):
            print(f"  Attempt {attempt}/{args.retries}...", end=" ", flush=True)
            try:
                new_code = rewrite_with_claude(client, instruction, broken_code, error_text)
                passed, new_error = compile_check(new_code)
                if passed:
                    print("✅")
                    examples[idx] = {**ex, "output": new_code}
                    log.append({"idx": idx, "instruction": instruction, "status": "fixed"})
                    fixed += 1
                    success = True
                    break
                else:
                    err2 = next((l.strip() for l in new_error.splitlines() if "Error" in l), "")
                    print(f"❌ still fails: {err2}")
                    error_text = new_error  # feed new error back for next attempt
                    broken_code = new_code
            except Exception as e:
                print(f"❌ API error: {e}")
                time.sleep(2)

        if not success:
            print(f"  ✗ Could not fix after {args.retries} attempts — keeping original")
            log.append({"idx": idx, "instruction": instruction, "status": "unfixed"})
            still_failing += 1

    # Write output
    output_path = Path(args.out) if args.out else DATASET
    with output_path.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\n{'='*50}")
    print(f"Fixed        : {fixed}/{len(failing)}")
    print(f"Still failing: {still_failing}/{len(failing)}")
    print(f"Written      : {output_path}")

    # Save log
    log_path = ROOT / "logs" / f"regenerate_{args.source}_report.md"
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("w") as f:
        f.write(f"# Regenerate report — {args.source}\n\n")
        for entry in log:
            status = "✅" if entry["status"] == "fixed" else "❌"
            f.write(f"- {status} [{entry['idx']}] {entry['instruction'][:80]}\n")
    print(f"Log          : {log_path}")


if __name__ == "__main__":
    main()
