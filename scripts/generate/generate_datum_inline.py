#!/usr/bin/env python3
"""
generate_datum_inline.py — Generate spend/datum_inline training examples
Fills the critical gap: 0 training examples vs 25 benchmark prompts.

Usage:
    python3 scripts/generate/generate_datum_inline.py --n 35
    python3 scripts/generate/generate_datum_inline.py --dry-run
"""

import os, re, pty, select, shutil, time, json, argparse, subprocess
from pathlib import Path
from datetime import datetime, timezone

import anthropic

ROOT         = Path(__file__).parent.parent.parent
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
OUT_FILE     = ROOT / "data" / "processed" / "components" / "datum_inline_verified.jsonl"
LOGS_DIR     = ROOT / "logs" / "generate"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30
MODEL        = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are an expert Aiken v3 smart contract developer.
Generate complete, compilable Aiken v3 spend validators that use InlineDatum.

── InlineDatum pattern ──
  when output.datum is {
    InlineDatum(raw) -> {
      expect typed: MyDatum = raw
      // use typed.field
    }
    _ -> False
  }

Reading own input datum in spend handler (datum: Option<MyDatum>):
  expect Some(d) = datum

── Time / validity_range ──
  use aiken/interval
  // self.validity_range is of type interval.Interval
  // Check tx is entirely after a deadline (Int):
  interval.is_entirely_after(self.validity_range, deadline)
  // Check tx is entirely before a deadline:
  interval.is_entirely_before(self.validity_range, deadline)
  // NEVER import Interval as a type — use interval.Interval directly in signatures
  // fn check(range: interval.Interval, d: Int) -> Bool { interval.is_entirely_after(range, d) }

── Asset / value operations ──
  use cardano/assets
  assets.lovelace_of(output.value)                               // -> Int
  assets.quantity_of(output.value, policy_id, asset_name)       // -> Int
  assets.tokens(value, policy_id)                                // -> Dict<ByteArray, Int>
  // Import: use cardano/assets (module import — do NOT use cardano/assets.{lovelace_of})
  // Access as: assets.lovelace_of(...), assets.tokens(...), etc.

── Option pattern matching ──
  when datum.optional_field is {
    Some(value) -> value > 0
    None -> False
  }

── Nested types ──
  pub type Inner { x: Int, y: Int }
  pub type Outer { inner: Inner, name: ByteArray }
  // Access: datum.inner.x

── Parametric validator ──
  validator my_validator(param: ByteArray) {
    spend(datum: Option<MyDatum>, _redeemer: Data, _utxo: OutputReference, self: Transaction) {
      expect Some(d) = datum
      list.has(self.extra_signatories, d.owner)
    }
  }

── Transaction fields ──
  self.extra_signatories   // List<ByteArray>
  self.outputs             // List<Output>
  self.inputs              // List<Input>
  self.reference_inputs    // List<Input>
  self.validity_range      // interval.Interval  (use with interval.is_entirely_after)
  self.withdrawals         // Dict<Credential, Int>
  self.mint                // Value

── Output field access ──
  output.address           // Address
  output.value             // Value
  output.datum             // Datum (InlineDatum / DatumHash / NoDatum)
  // Find first output to an address:
  // list.find(self.outputs, fn(o) { o.address == target_addr })

── CRITICAL: type/constructor import rules ──
  The `/` character ONLY appears in `use` statements. NEVER elsewhere.
  This applies to ALL modules, not just cardano/address.

  WRONG — slash in type annotation:
    fn f(d: aiken/collection/dict.Dict<ByteArray, Int>) -> Int   // ❌ parser error
    fn f(a: cardano/address.Address) -> Bool                     // ❌ parser error

  WRONG — slash in pattern / expression:
    when x is { cardano/address.VerificationKey(k) -> ... }      // ❌ parser error
    output.address.payment_credential == cardano/transaction.VerificationKeyCredential(pkh)  // ❌

  CORRECT — import first, then use bare name or module alias:
    use aiken/collection/dict                          // → use as dict.Dict, dict.foldl, etc.
    use aiken/collection/list                          // → list.has, list.find, etc.
    use cardano/address.{Address, VerificationKey, Script}        // → bare name in signatures
    use cardano/transaction.{Output, Input, Transaction, OutputReference,
                             InlineDatum, DatumHash, NoDatum}

    fn sum_dict(d: dict.Dict<ByteArray, Int>) -> Int {           // ✅ dot notation
      dict.foldl(d, 0, fn(_k, v, acc) { acc + v })
    }

    fn find_output(outputs: List<Output>, own_address: Address) -> Option<Output> {  // ✅ bare name
      list.find(outputs, fn(o) { o.address == own_address })
    }

    when output.address.payment_credential is {
      VerificationKey(pkh) -> list.has(self.extra_signatories, pkh)  // ✅ bare constructor
      Script(_)            -> False
    }

  Address type is in cardano/address, NOT in cardano/transaction:
    use cardano/address.{Address}   // ✅ correct
    // transaction.Address          // ❌ Address not exported from cardano/transaction

── list / dict helpers ──
  use aiken/collection/list
  list.has(self.extra_signatories, owner)
  list.any(self.outputs, fn(o) { ... })
  list.count(list, predicate)
  list.foldl(list, init, fn(item, acc) { acc + item_value })   // accumulate

  use aiken/collection/dict
  dict.get(self.withdrawals, credential)

── Continuing output pattern ──
  // Find the script's own continuing output and read its datum:
  expect Some(cont_out) = list.find(self.outputs, fn(o) { o.address == own_address })
  expect InlineDatum(raw) = cont_out.datum
  expect cont: MyDatum = raw

File structure: use statements first, then pub types, then fns, then validator.

Output ONLY raw Aiken source code. No markdown, no explanation.
Start with the first line of the file (a use statement or //)."""

PROMPTS = [
    # Escrow variants
    ("Write an Aiken v3 spend validator `escrow_release` that reads an EscrowDatum "
     "(with fields beneficiary: ByteArray and amount: Int) from the transaction output "
     "using InlineDatum. Verify InlineDatum(raw) pattern, deserialize to EscrowDatum, "
     "and check that the beneficiary signed the transaction.",
     ["InlineDatum", "EscrowDatum", "beneficiary", "extra_signatories", "spend("]),

    ("Write an Aiken v3 spend validator `escrow_timeout` with EscrowDatum containing "
     "beneficiary: ByteArray, deadline: Int, and refund_to: ByteArray. Use InlineDatum "
     "to read the datum from the continuing output. Allow release if beneficiary signed "
     "and deadline not passed, or refund if deadline passed and owner signed.",
     ["InlineDatum", "EscrowDatum", "deadline", "validity_range", "spend("]),

    # Oracle variants
    ("Write an Aiken v3 spend validator `oracle_consumer` that reads an OracleDatum "
     "(price: Int, timestamp: Int, source: ByteArray) from a reference input using "
     "InlineDatum. Verify the price is above a minimum threshold stored in the spend datum.",
     ["InlineDatum", "OracleDatum", "reference_inputs", "price", "spend("]),

    ("Write an Aiken v3 spend validator `price_feed_validator` with a SpendDatum "
     "(min_price: Int, owner: ByteArray) read via InlineDatum from the own input. "
     "Check that a reference input contains an OracleDatum with price >= min_price "
     "and that the owner signed.",
     ["InlineDatum", "min_price", "reference_inputs", "extra_signatories", "spend("]),

    # Vesting variants
    ("Write an Aiken v3 spend validator `vesting_cliff` with VestingDatum "
     "(beneficiary: ByteArray, cliff_time: Int, total_amount: Int) using InlineDatum. "
     "Allow withdrawal only after cliff_time using interval.is_entirely_after.",
     ["InlineDatum", "VestingDatum", "cliff_time", "interval", "spend("]),

    ("Write an Aiken v3 spend validator `vesting_linear` with VestingDatum "
     "(owner: ByteArray, start_time: Int, end_time: Int, amount: Int) via InlineDatum. "
     "Verify the owner signed and the transaction validity range is within vesting period.",
     ["InlineDatum", "VestingDatum", "validity_range", "extra_signatories", "spend("]),

    # Auction variants
    ("Write an Aiken v3 spend validator `auction_bid` with AuctionDatum "
     "(highest_bid: Int, bidder: ByteArray, deadline: Int) using InlineDatum on the "
     "continuing output. Verify the new bid exceeds current highest_bid and deadline "
     "hasn't passed.",
     ["InlineDatum", "AuctionDatum", "highest_bid", "deadline", "spend("]),

    ("Write an Aiken v3 spend validator `auction_close` that reads AuctionDatum "
     "(winner: ByteArray, amount: Int, seller: ByteArray) from InlineDatum. "
     "Allow close only after deadline and verify winner signed.",
     ["InlineDatum", "AuctionDatum", "winner", "extra_signatories", "spend("]),

    # MultiSig datum
    ("Write an Aiken v3 spend validator `multisig_wallet` with a MultiSigDatum "
     "(required_signers: List<ByteArray>, threshold: Int) read via InlineDatum. "
     "Check that at least threshold of the required_signers appear in extra_signatories.",
     ["InlineDatum", "MultiSigDatum", "threshold", "extra_signatories", "list.count", "spend("]),

    # Config/protocol datum
    ("Write an Aiken v3 spend validator `protocol_config` with ConfigDatum "
     "(admin: ByteArray, fee_bps: Int, paused: Bool) using InlineDatum. "
     "Allow actions only when not paused and admin signed.",
     ["InlineDatum", "ConfigDatum", "paused", "extra_signatories", "spend("]),

    # Nested types
    ("Write an Aiken v3 spend validator `nested_config` where the datum contains "
     "a nested type: pub type Limits { min: Int, max: Int } inside pub type VaultDatum "
     "{ owner: ByteArray, limits: Limits }. Read via InlineDatum and verify the "
     "transaction amount is within limits.",
     ["InlineDatum", "VaultDatum", "Limits", "spend("]),

    # Continuing output datum
    ("Write an Aiken v3 spend validator `state_machine` with StateDatum "
     "(state: Int, owner: ByteArray) using InlineDatum. Read the current state from "
     "own input and verify the continuing output has state + 1 in its InlineDatum.",
     ["InlineDatum", "StateDatum", "state", "self.outputs", "spend("]),

    # Liquidity pool
    ("Write an Aiken v3 spend validator `lp_withdraw` with PoolDatum "
     "(reserve_a: Int, reserve_b: Int, lp_supply: Int) using InlineDatum. "
     "Verify the LP token burn amount matches the proportional share of reserves.",
     ["InlineDatum", "PoolDatum", "reserve_a", "lp_supply", "spend("]),

    # NFT marketplace
    ("Write an Aiken v3 spend validator `nft_sale` with ListingDatum "
     "(seller: ByteArray, price: Int, policy_id: ByteArray, asset_name: ByteArray) "
     "read via InlineDatum. Verify the seller receives at least price lovelace.",
     ["InlineDatum", "ListingDatum", "seller", "price", "assets.lovelace_of", "spend("]),

    # Loan
    ("Write an Aiken v3 spend validator `loan_repay` with LoanDatum "
     "(borrower: ByteArray, principal: Int, interest: Int, due_date: Int) "
     "using InlineDatum. Allow repayment if borrower signed and amount >= principal + interest.",
     ["InlineDatum", "LoanDatum", "borrower", "principal", "interest", "spend("]),

    # Governance treasury
    ("Write an Aiken v3 spend validator `treasury_spend` with ProposalDatum "
     "(recipient: ByteArray, amount: Int, votes_for: Int, votes_against: Int) "
     "via InlineDatum. Allow spend if votes_for > votes_against.",
     ["InlineDatum", "ProposalDatum", "votes_for", "votes_against", "spend("]),

    # Staking rewards split
    ("Write an Aiken v3 spend validator `reward_split` with SplitDatum "
     "(party_a: ByteArray, party_b: ByteArray, share_a_bps: Int) via InlineDatum. "
     "Verify outputs to party_a and party_b match their respective shares.",
     ["InlineDatum", "SplitDatum", "party_a", "share_a_bps", "self.outputs", "spend("]),

    # Subscription
    ("Write an Aiken v3 spend validator `subscription` with SubDatum "
     "(subscriber: ByteArray, expiry: Int, fee_per_period: Int) via InlineDatum. "
     "Allow renewal if subscriber signed and fee is paid; allow cancel after expiry.",
     ["InlineDatum", "SubDatum", "subscriber", "expiry", "spend("]),

    # Collateral
    ("Write an Aiken v3 spend validator `collateral_vault` with CollateralDatum "
     "(borrower: ByteArray, loan_ref: ByteArray, liquidation_ratio: Int) via InlineDatum. "
     "Allow liquidation only if borrower signed or loan is in default.",
     ["InlineDatum", "CollateralDatum", "borrower", "liquidation_ratio", "spend("]),

    # Timelock with datum
    ("Write an Aiken v3 spend validator `timed_release` with TimelockDatum "
     "(recipient: ByteArray, unlock_time: Int) read via InlineDatum from the own input. "
     "Release only after unlock_time using validity_range check.",
     ["InlineDatum", "TimelockDatum", "recipient", "unlock_time", "validity_range", "spend("]),

    # Variant: NoDatum fallback
    ("Write an Aiken v3 spend validator `safe_escrow` with EscrowDatum via InlineDatum. "
     "Handle all three datum constructors: InlineDatum (proceed), DatumHash (reject with fail), "
     "NoDatum (reject with fail). Only process when datum is inline.",
     ["InlineDatum", "DatumHash", "NoDatum", "EscrowDatum", "spend("]),

    # Cross-validator check
    ("Write an Aiken v3 spend validator `bridge_release` with BridgeDatum "
     "(amount: Int, recipient: ByteArray, nonce: ByteArray) via InlineDatum. "
     "Verify the nonce hasn't been used by checking a reference input's NonceDatum.",
     ["InlineDatum", "BridgeDatum", "nonce", "reference_inputs", "spend("]),

    # Access control list
    ("Write an Aiken v3 spend validator `acl_gate` with AccessDatum "
     "(allowed: List<ByteArray>, admin: ByteArray) via InlineDatum. "
     "Allow transaction if any signer is in the allowed list or is the admin.",
     ["InlineDatum", "AccessDatum", "allowed", "extra_signatories", "list.any", "spend("]),

    # Upgradeable datum
    ("Write an Aiken v3 spend validator `upgradeable` with VersionedDatum "
     "(version: Int, admin: ByteArray, params: Int) via InlineDatum. "
     "Allow upgrade (version bump) only by admin; allow use by anyone when active.",
     ["InlineDatum", "VersionedDatum", "version", "extra_signatories", "spend("]),

    # Datum with Option field
    ("Write an Aiken v3 spend validator `optional_fee` with TxDatum "
     "(recipient: ByteArray, fee_address: Option<ByteArray>, amount: Int) via InlineDatum. "
     "If fee_address is Some, verify fee output exists; if None, proceed without fee.",
     ["InlineDatum", "TxDatum", "fee_address", "Option", "spend("]),

    # Multi-asset datum
    ("Write an Aiken v3 spend validator `token_sale` with SaleDatum "
     "(seller: ByteArray, token_policy: ByteArray, token_name: ByteArray, price: Int) "
     "via InlineDatum. Verify seller gets price lovelace and buyer gets exactly 1 token.",
     ["InlineDatum", "SaleDatum", "token_policy", "assets.quantity_of", "spend("]),

    # Crowdfund
    ("Write an Aiken v3 spend validator `crowdfund` with FundDatum "
     "(goal: Int, deadline: Int, creator: ByteArray) via InlineDatum. "
     "Allow withdrawal by creator only if goal is met after deadline.",
     ["InlineDatum", "FundDatum", "goal", "deadline", "validity_range", "spend("]),

    # DAO vote execution
    ("Write an Aiken v3 spend validator `dao_execute` with ProposalDatum "
     "(proposal_id: ByteArray, executor: ByteArray, quorum_met: Bool) via InlineDatum. "
     "Allow execution only if quorum_met is True and executor signed.",
     ["InlineDatum", "ProposalDatum", "quorum_met", "executor", "spend("]),

    # Whitelist
    ("Write an Aiken v3 spend validator `whitelist_sale` with WhitelistDatum "
     "(whitelist: List<ByteArray>, price: Int, max_per_wallet: Int) via InlineDatum. "
     "Allow purchase only if buyer is in whitelist.",
     ["InlineDatum", "WhitelistDatum", "whitelist", "list.has", "spend("]),

    # Parametric vault
    ("Write an Aiken v3 spend validator `parametric_vault` taking a policy_id: ByteArray "
     "parameter, with VaultDatum (owner: ByteArray, asset_name: ByteArray, min_tokens: Int) "
     "via InlineDatum. Verify owner signed and that at least one output contains "
     ">= min_tokens of (policy_id, asset_name) using assets.quantity_of. "
     "Use list.any(self.outputs, fn(o) { assets.quantity_of(o.value, policy_id, d.asset_name) >= d.min_tokens }). "
     "No helper functions needed.",
     ["InlineDatum", "VaultDatum", "policy_id", "assets.quantity_of", "spend("]),

    # Insurance
    ("Write an Aiken v3 spend validator `insurance_claim` with PolicyDatum "
     "(insured: ByteArray, coverage: Int, event_id: ByteArray) via InlineDatum. "
     "Allow claim if insured signed and event matches datum event_id.",
     ["InlineDatum", "PolicyDatum", "insured", "coverage", "spend("]),

    # Batch operation
    ("Write an Aiken v3 spend validator `batch_transfer` with BatchDatum "
     "(recipients: List<ByteArray>, amounts: List<Int>, sender: ByteArray) via InlineDatum. "
     "Verify sender signed and at least one output matches each recipient/amount pair.",
     ["InlineDatum", "BatchDatum", "recipients", "sender", "spend("]),

    # Recurring payment
    ("Write an Aiken v3 spend validator `recurring_payment` with RecurringDatum "
     "(payer: ByteArray, payee: ByteArray, amount: Int, period_secs: Int, last_paid: Int) "
     "via InlineDatum. Allow payment if period_secs has elapsed since last_paid. "
     "Use interval.is_entirely_after(self.validity_range, last_paid + period_secs).",
     ["InlineDatum", "RecurringDatum", "period_secs", "last_paid", "validity_range", "spend("]),
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


def generate_variation(client, original_prompt: str, original_code: str) -> tuple[str, str] | None:
    """Generate a variation of a verified example with different names/constraints."""
    instruction = (
        "Here is a verified Aiken v3 spend validator with its prompt and correct implementation.\n\n"
        f"ORIGINAL PROMPT:\n{original_prompt}\n\n"
        f"VERIFIED IMPLEMENTATION:\n{original_code}\n\n"
        "Write a VARIATION of this validator. Rules:\n"
        "- Use a different validator name (descriptive, snake_case)\n"
        "- Use different datum type name and field names\n"
        "- Keep the same structural pattern (InlineDatum unwrap + same kind of check)\n"
        "- Vary at least one condition or constraint\n"
        "- The new prompt description should accurately describe your new validator\n\n"
        "SYNTAX RULES — violations cause compile failure:\n"
        "1. ALL `use` statements go at the very TOP of the file, before any type or validator.\n"
        "   NEVER place `use` inside a function body, closure, or after any definition.\n"
        "2. The `/` character ONLY appears in `use` statements. NEVER elsewhere — not in types, not in patterns, not in expressions.\n"
        "   WRONG: fn f(a: cardano/address.Address)      — slash in type annotation\n"
        "   WRONG: fn f(v: cardano/assets.Value)         — slash in type annotation\n"
        "   WRONG: cardano/address.VerificationKey(pkh)  — slash in expression\n"
        "   WRONG: cardano/assets.lovelace_of(v)         — slash in expression\n"
        "   RIGHT: use cardano/address.{Address, VerificationKey} at top, then use bare 'Address' and 'VerificationKey'\n"
        "   RIGHT: use cardano/assets at top, then use 'assets.lovelace_of(v)' (dot notation, no slash)\n"
        "3. Helper functions that take address parameters: use 'Address' (after importing it), never 'cardano/address.Address'.\n"
        "   If you want to avoid importing Address, pass ByteArray instead and compare inline.\n"
        "4. Never shadow stdlib function names (e.g. do not define your own 'lovelace_of' — use assets.lovelace_of directly).\n\n"
        "Return TWO sections separated by exactly '---PROMPT---' and '---CODE---':\n"
        "---PROMPT---\n"
        "<one paragraph describing the new validator>\n"
        "---CODE---\n"
        "<complete Aiken source file, no markdown>\n"
    )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=2500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": instruction}],
        )
        text = resp.content[0].text.strip()
        if "---PROMPT---" in text and "---CODE---" in text:
            parts = text.split("---CODE---", 1)
            new_prompt = parts[0].replace("---PROMPT---", "").strip()
            new_code = parts[1].strip()
            if new_code.startswith("```"):
                new_code = re.sub(r'^```[a-z]*\n?', '', new_code)
                new_code = re.sub(r'\n?```$', '', new_code)
            return new_prompt, new_code
        return None
    except Exception as e:
        print(f"    API error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=35)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--append", action="store_true", default=True)
    parser.add_argument("--log-failures", action="store_true",
                        help="Save failed code + errors to logs/generate/")
    parser.add_argument("--only-failed", action="store_true",
                        help="Skip prompts whose validator already passed (present in output jsonl)")
    parser.add_argument("--expand-to", type=int, default=None,
                        help="Generate variations of verified examples until reaching this total count")
    args = parser.parse_args()

    client = anthropic.Anthropic()
    prompts = PROMPTS[:args.n]

    # Filter to only failed prompts if requested
    if args.only_failed and OUT_FILE.exists():
        import re as _re
        passed_names = set()
        with OUT_FILE.open(encoding="utf-8") as _f:
            for _line in _f:
                if _line.strip():
                    _obj = json.loads(_line)
                    _m = _re.search(r'validator `(\w+)`', _obj.get("prompt", ""))
                    if _m:
                        passed_names.add(_m.group(1))
        before = len(prompts)
        def _already_passed(p):
            _m = _re.search(r'validator `(\w+)`', p)
            return _m and _m.group(1) in passed_names

        prompts = [(p, mc) for p, mc in prompts if not _already_passed(p)]
        print(f"  [--only-failed] skipping {before - len(prompts)} already-passed, retrying {len(prompts)}")

    print(f"\n{'═'*60}")
    print(f"  generate_datum_inline — {len(prompts)} prompts")
    print(f"  output → {OUT_FILE.relative_to(ROOT)}")
    print(f"{'═'*60}\n")

    if args.dry_run:
        for i, (p, _) in enumerate(prompts, 1):
            print(f"  [{i:2d}] {p[:80]}...")
        return

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    passed, failed = 0, 0
    failures = []

    # Skip base prompt loop if --expand-to and file already has enough examples
    skip_base = False
    if args.expand_to and OUT_FILE.exists():
        current = sum(1 for l in OUT_FILE.open(encoding="utf-8") if l.strip())
        if current >= len(prompts):
            print(f"  [--expand-to] {current} examples exist — skipping base prompt loop, going to expand")
            skip_base = True

    if not skip_base:
        mode = "a" if args.append and OUT_FILE.exists() else "w"
        with OUT_FILE.open(mode, encoding="utf-8") as out_f:
            for i, (prompt_text, must_contain) in enumerate(prompts, 1):
                print(f"  [{i:2d}/{len(prompts)}] generating...", end="", flush=True)
                code = generate_one(client, prompt_text)
                if code is None:
                    print(" ✗ API failed")
                    failed += 1
                    failures.append({"prompt": prompt_text[:80], "reason": "api_failed", "code": "", "error": ""})
                    continue

                print(" compiling...", end="", flush=True)
                ok, output = compile_check(code)
                if ok:
                    print(" ✅")
                    record = {"prompt": prompt_text, "output": code, "category": "spend/datum_inline"}
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    passed += 1
                else:
                    err = next((l.strip() for l in output.splitlines()
                                if l.strip() and any(k in l.lower() for k in ("error","×","unexpected","unknown"))), "")
                    print(f" ❌  {err[:60]}")
                    failed += 1
                    failures.append({"prompt": prompt_text[:80], "reason": "compile_failed",
                                     "error": output[:600], "code": code})
                time.sleep(0.3)

        print(f"\n{'═'*60}")
        print(f"  Passed: {passed}/{len(prompts)}  Failed: {failed}/{len(prompts)}")
        print(f"  Output: {OUT_FILE}")
        print(f"{'═'*60}")

    if failures and args.log_failures:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = LOGS_DIR / f"datum_inline_failures_{ts}.json"
        log_path.write_text(json.dumps({"run_at": ts, "model": MODEL,
            "passed": passed, "failed": failed, "failures": failures},
            indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Failure log → {log_path}")

    # ── Expand to target count via variations ────────────────────────────────
    if args.expand_to and not args.dry_run:
        import hashlib, random
        existing = []
        seen_hashes    = set()
        seen_val_names = set()

        if OUT_FILE.exists():
            with OUT_FILE.open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        obj = json.loads(line)
                        existing.append(obj)
                        seen_hashes.add(hashlib.sha256(obj.get("output","").encode()).hexdigest())
                        m = re.search(r'\bvalidator\s+(\w+)', obj.get("output",""))
                        if m:
                            seen_val_names.add(m.group(1))

        current_count = len(existing)
        target = args.expand_to
        needed = target - current_count

        print(f"\n{'═'*60}")
        print(f"  --expand-to {target}: have {current_count}, need {max(0,needed)} new unique variations")
        print(f"  Dedup: {len(seen_hashes)} output hashes + {len(seen_val_names)} validator names tracked")
        print(f"{'═'*60}\n")

        if needed <= 0:
            print(f"  Already at {current_count} examples — nothing to do.")
            return

        random.seed(42)
        pool = existing.copy()
        var_passed, var_failed, var_dupes = 0, 0, 0

        with OUT_FILE.open("a", encoding="utf-8") as out_f:
            attempts = 0
            while var_passed < needed and attempts < needed * 4:
                seed = random.choice(pool)
                attempts += 1
                print(f"  [{current_count + var_passed + 1}/{target}] varying...", end="", flush=True)
                result = generate_variation(client, seed["prompt"], seed["output"])
                if result is None:
                    print(" ✗ API failed")
                    var_failed += 1
                    continue
                new_prompt, new_code = result

                # Dedup check
                h = hashlib.sha256(new_code.encode()).hexdigest()
                val_m = re.search(r'\bvalidator\s+(\w+)', new_code)
                val_name = val_m.group(1) if val_m else ""
                if h in seen_hashes or (val_name and val_name in seen_val_names):
                    print(f" ⟳ duplicate ({val_name}) — skipping")
                    var_dupes += 1
                    continue

                print(" compiling...", end="", flush=True)
                ok, output = compile_check(new_code)
                if ok:
                    print(f" ✅  ({val_name})")
                    seen_hashes.add(h)
                    if val_name:
                        seen_val_names.add(val_name)
                    record = {"prompt": new_prompt, "output": new_code, "category": "spend/datum_inline"}
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    var_passed += 1
                else:
                    err = next((l.strip() for l in output.splitlines()
                                if l.strip() and any(k in l.lower() for k in ("error","×","unexpected","unknown"))), "")
                    print(f" ❌  {err[:60]}")
                    var_failed += 1
                time.sleep(0.3)

        print(f"\n{'═'*60}")
        print(f"  Variations — Passed: {var_passed}  Dupes skipped: {var_dupes}  Failed: {var_failed}")
        print(f"  Total examples now: {current_count + var_passed}")
        print(f"{'═'*60}")


if __name__ == "__main__":
    main()
