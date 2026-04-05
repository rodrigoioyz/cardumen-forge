#!/usr/bin/env python3
"""
generate_multisig.py — Generate spend/multisig_threshold training examples
Fills the critical gap: 0 training examples vs 25 benchmark prompts.

Usage:
    python3 scripts/generate/generate_multisig.py --n 28
    python3 scripts/generate/generate_multisig.py --dry-run
"""

import os, re, pty, select, shutil, time, json, argparse, subprocess
from pathlib import Path
from datetime import datetime, timezone

import anthropic

ROOT         = Path(__file__).parent.parent.parent
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
OUT_FILE     = ROOT / "data" / "processed" / "components" / "multisig_verified.jsonl"
LOGS_DIR     = ROOT / "logs" / "generate"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30
MODEL        = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are an expert Aiken v3 smart contract developer.
Generate complete, compilable Aiken v3 multisig spend validators.

── Multisig pattern ──
  use aiken/collection/list
  use cardano/transaction.{Transaction, OutputReference}

  let present = list.count(self.extra_signatories, fn(sig) { list.has(required, sig) })
  present >= threshold

── Time / validity_range ──
  use aiken/interval.{Finite}
  use aiken/interval

  // self.validity_range is of type interval.Interval
  interval.is_entirely_after(self.validity_range, deadline)   // -> Bool
  interval.is_entirely_before(self.validity_range, deadline)  // -> Bool

  // If you need to extract the lower bound value:
  when self.validity_range.lower_bound.bound_type is {
    Finite(t) -> t >= unlock_time
    _         -> False
  }

── Asset / value operations ──
  use cardano/assets
  assets.lovelace_of(output.value)                         // -> Int
  assets.quantity_of(output.value, policy_id, asset_name)  // -> Int

── CRITICAL: type/constructor import rules ──
  The `/` character ONLY appears in `use` statements. NEVER elsewhere.

  WRONG:
    cardano/interval.{Finite(t)} -> ...       // ❌ slash in pattern
    transaction.Finite(t)        -> ...       // ❌ wrong module
    cardano/address.VerificationKey(pkh)      // ❌ slash in expression

  CORRECT:
    use aiken/interval.{Finite}               // import Finite at top
    use cardano/address.{VerificationKey}     // import VerificationKey at top

    Finite(t) -> t >= deadline                // ✅ bare name in pattern
    VerificationKey(pkh)                      // ✅ bare name in expression

  Address type is in cardano/address, NOT in cardano/transaction.

── Key functions ──
  list.count(list, predicate) -> Int
  list.has(list, element) -> Bool
  list.any(list, predicate) -> Bool
  list.filter(list, predicate) -> List

File structure: use statements first, then pub types, then fns, then validator.
Output ONLY raw Aiken source code. No markdown, no explanation.
Start with the first line of the file."""

PROMPTS = [
    # Basic M-of-N
    ("Write an Aiken v3 spend validator `multisig_2of3` with a datum containing "
     "required_signers: List<ByteArray> and threshold: Int. Verify that at least "
     "threshold signers from required_signers appear in self.extra_signatories using "
     "list.count and list.has.",
     ["extra_signatories", "list.count", "list.has", "threshold", "required_signers", "spend("]),

    ("Write an Aiken v3 spend validator `multisig_3of5` where the datum stores "
     "signers: List<ByteArray> with hardcoded threshold of 3. Use list.count to verify "
     "at least 3 of the stored signers have signed.",
     ["extra_signatories", "list.count", "list.has", "signers", "spend("]),

    ("Write an Aiken v3 spend validator `multisig_threshold` parametrized with "
     "threshold: Int. The datum stores required_signers: List<ByteArray>. Check that "
     "the count of matching signatories meets or exceeds the threshold.",
     ["extra_signatories", "list.count", "threshold", "required_signers", "spend("]),

    # Percentage quorum
    ("Write an Aiken v3 spend validator `quorum_vote` with QuorumDatum containing "
     "voters: List<ByteArray> and quorum_pct: Int (0-100). Approve if the percentage "
     "of present voters >= quorum_pct. Use list.count and arithmetic.",
     ["extra_signatories", "list.count", "quorum_pct", "voters", "spend("]),

    # Multisig + timelock
    ("Write an Aiken v3 spend validator `timed_multisig` with datum "
     "(required_signers: List<ByteArray>, threshold: Int, unlock_time: Int). "
     "Allow spending only after unlock_time AND if threshold signers are present.",
     ["extra_signatories", "list.count", "threshold", "unlock_time", "interval", "spend("]),

    ("Write an Aiken v3 spend validator `emergency_multisig` with datum "
     "(signers: List<ByteArray>, threshold: Int, emergency_key: ByteArray, deadline: Int). "
     "Allow normal multisig before deadline, or emergency_key alone after deadline.",
     ["extra_signatories", "list.count", "threshold", "emergency_key", "deadline", "spend("]),

    # Roles
    ("Write an Aiken v3 spend validator `role_multisig` with RoleDatum containing "
     "admins: List<ByteArray>, members: List<ByteArray>, admin_threshold: Int, "
     "member_threshold: Int. Require admin_threshold admins AND member_threshold members.",
     ["extra_signatories", "list.count", "admins", "members", "admin_threshold", "spend("]),

    ("Write an Aiken v3 spend validator `board_vote` with BoardDatum "
     "(directors: List<ByteArray>, observers: List<ByteArray>, min_directors: Int). "
     "Require at least min_directors directors; observers can sign but don't count.",
     ["extra_signatories", "list.count", "directors", "min_directors", "spend("]),

    # Weighted multisig
    ("Write an Aiken v3 spend validator `weighted_multisig` with WeightedDatum "
     "(signers: List<ByteArray>, weights: List<Int>, min_weight: Int). "
     "Compute total weight of present signers and verify >= min_weight.",
     ["extra_signatories", "list.any", "weights", "min_weight", "spend("]),

    # Override patterns
    ("Write an Aiken v3 spend validator `override_multisig` with OverrideDatum "
     "(regular_signers: List<ByteArray>, threshold: Int, override_key: ByteArray). "
     "Allow spending if threshold signers approve OR override_key alone approves.",
     ["extra_signatories", "list.count", "threshold", "override_key", "spend("]),

    # DAO treasury
    ("Write an Aiken v3 spend validator `dao_treasury` with TreasuryDatum "
     "(council: List<ByteArray>, required: Int, admin: ByteArray). "
     "Allow withdrawal if required council members signed, or admin signed alone.",
     ["extra_signatories", "list.count", "council", "required", "spend("]),

    # With NFT gate
    ("Write an Aiken v3 spend validator `nft_multisig` with MultiSigDatum "
     "(holders: List<ByteArray>, threshold: Int, nft_policy: ByteArray). "
     "Verify threshold holders signed AND the NFT policy token is in an input.",
     ["extra_signatories", "list.count", "threshold", "nft_policy", "assets", "spend("]),

    # Protocol upgrade
    ("Write an Aiken v3 spend validator `protocol_upgrade` with UpgradeDatum "
     "(governors: List<ByteArray>, supermajority: Int, current_version: Int). "
     "Allow upgrade only if supermajority (e.g. 75%) of governors signed.",
     ["extra_signatories", "list.count", "governors", "supermajority", "spend("]),

    # Escrow with multisig arbitration
    ("Write an Aiken v3 spend validator `arbitration_escrow` with EscrowDatum "
     "(buyer: ByteArray, seller: ByteArray, arbitrators: List<ByteArray>, threshold: Int). "
     "Allow release if buyer+seller both sign, or if threshold arbitrators approve.",
     ["extra_signatories", "list.count", "buyer", "seller", "arbitrators", "spend("]),

    # Veto multisig
    ("Write an Aiken v3 spend validator `veto_multisig` with VetoDatum "
     "(proposers: List<ByteArray>, vetoers: List<ByteArray>, min_proposers: Int). "
     "Allow only if min_proposers signed AND no vetoer signed.",
     ["extra_signatories", "list.count", "proposers", "vetoers", "min_proposers", "spend("]),

    # Cold/hot wallet
    ("Write an Aiken v3 spend validator `cold_hot_wallet` with WalletDatum "
     "(cold_keys: List<ByteArray>, hot_keys: List<ByteArray>, cold_threshold: Int, "
     "hot_threshold: Int, amount_limit: Int). Allow small amounts with hot_threshold, "
     "require cold_threshold for large amounts.",
     ["extra_signatories", "list.count", "cold_keys", "hot_keys", "cold_threshold", "spend("]),

    # Time-decaying threshold
    ("Write an Aiken v3 spend validator `decaying_multisig` with DecayDatum "
     "(signers: List<ByteArray>, initial_threshold: Int, reduced_threshold: Int, "
     "decay_time: Int). Require initial_threshold before decay_time, reduced_threshold after.",
     ["extra_signatories", "list.count", "initial_threshold", "decay_time", "interval", "spend("]),

    # Recovery wallet
    ("Write an Aiken v3 spend validator `recovery_wallet` with RecoveryDatum "
     "(owner: ByteArray, guardians: List<ByteArray>, guardian_threshold: Int, "
     "recovery_delay: Int). Owner can spend anytime; guardians can recover after delay.",
     ["extra_signatories", "list.count", "owner", "guardians", "guardian_threshold", "spend("]),

    # Simple 2-of-2
    ("Write an Aiken v3 spend validator `joint_account` for a simple 2-of-2 multisig. "
     "The datum stores two owners: owner_a: ByteArray and owner_b: ByteArray. "
     "Both must sign every transaction.",
     ["extra_signatories", "list.has", "owner_a", "owner_b", "spend("]),

    # With amount limit
    ("Write an Aiken v3 spend validator `tiered_auth` with TieredDatum "
     "(signers: List<ByteArray>, low_threshold: Int, high_threshold: Int, limit: Int). "
     "Transactions below limit need low_threshold, above need high_threshold.",
     ["extra_signatories", "list.count", "low_threshold", "high_threshold", "limit", "spend("]),

    # Sequential approval
    ("Write an Aiken v3 spend validator `sequential_approve` with ApprovalDatum "
     "(stage: Int, approvers_stage1: List<ByteArray>, approvers_stage2: List<ByteArray>, "
     "threshold: Int). Require stage1 approval in stage 0, stage2 in stage 1.",
     ["extra_signatories", "list.count", "stage", "approvers_stage1", "threshold", "spend("]),

    # Corporate treasury
    ("Write an Aiken v3 spend validator `corporate_treasury` with CorpDatum "
     "(board: List<ByteArray>, officers: List<ByteArray>, board_min: Int, officer_min: Int). "
     "Require both board_min board members and officer_min officers.",
     ["extra_signatories", "list.count", "board", "officers", "board_min", "spend("]),

    # With expiry
    ("Write an Aiken v3 spend validator `expiring_multisig` with ExpiryDatum "
     "(signers: List<ByteArray>, threshold: Int, expiry: Int, fallback: ByteArray). "
     "Use multisig before expiry; only fallback key allowed after.",
     ["extra_signatories", "list.count", "threshold", "expiry", "fallback", "spend("]),

    # Threshold with minimum amount
    ("Write an Aiken v3 spend validator `guarded_multisig` with GuardDatum "
     "(signers: List<ByteArray>, threshold: Int, min_lovelace: Int). "
     "Require threshold signers AND that at least min_lovelace goes to a specific output.",
     ["extra_signatories", "list.count", "threshold", "assets.lovelace_of", "spend("]),

    # Protocol parameter update
    ("Write an Aiken v3 spend validator `param_update` with ParamDatum "
     "(stewards: List<ByteArray>, min_stewards: Int, new_params: Int). "
     "Allow parameter update only if min_stewards of stewards approved.",
     ["extra_signatories", "list.count", "stewards", "min_stewards", "spend("]),

    # Inheritance
    ("Write an Aiken v3 spend validator `inheritance` with InheritanceDatum "
     "(owner: ByteArray, heirs: List<ByteArray>, heir_threshold: Int, inactivity_deadline: Int). "
     "Owner can always spend; heirs can claim after inactivity_deadline.",
     ["extra_signatories", "list.count", "owner", "heirs", "heir_threshold", "spend("]),

    # Simple with helper function
    ("Write an Aiken v3 spend validator `multisig_with_helper` that uses a helper function "
     "`count_present(signatories: List<ByteArray>, required: List<ByteArray>) -> Int` "
     "to count matching signers. The validator uses this helper with the datum's "
     "required_signers and threshold.",
     ["count_present", "extra_signatories", "list.count", "threshold", "spend("]),

    # Audit trail
    ("Write an Aiken v3 spend validator `audited_multisig` with AuditDatum "
     "(signers: List<ByteArray>, threshold: Int, auditor: ByteArray). "
     "Require threshold signers AND auditor's signature for compliance.",
     ["extra_signatories", "list.count", "threshold", "auditor", "spend("]),
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
        "Here is a verified Aiken v3 multisig spend validator with its prompt and correct implementation.\n\n"
        f"ORIGINAL PROMPT:\n{original_prompt}\n\n"
        f"VERIFIED IMPLEMENTATION:\n{original_code}\n\n"
        "Write a VARIATION of this validator. Rules:\n"
        "- Use a different validator name (descriptive, snake_case)\n"
        "- Use different datum type name and field names\n"
        "- Keep the same structural pattern (multisig threshold check)\n"
        "- Vary at least one condition, threshold logic, or role structure\n"
        "- The new prompt description should accurately describe your new validator\n\n"
        "SYNTAX RULES — violations cause compile failure:\n"
        "1. ALL `use` statements go at the very TOP of the file, before any type or validator.\n"
        "   NEVER place `use` inside a function body, closure, or after any definition.\n"
        "2. The `/` character ONLY appears in `use` statements. NEVER in type annotations or patterns.\n"
        "   WRONG: fn f(a: cardano/address.Address)  |  cardano/interval.{Finite(t)} -> ...\n"
        "   RIGHT: import at top with `use cardano/address.{Address, VerificationKey}` then use bare name.\n"
        "   RIGHT: import at top with `use aiken/interval.{Finite}` then use `Finite(t) -> ...`\n"
        "3. Function parameter types use bare names or dot-notation (dict.Dict), never slash-paths.\n\n"
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
    parser.add_argument("--n", type=int, default=28)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--append", action="store_true", default=True)
    parser.add_argument("--log-failures", action="store_true",
                        help="Save failed code + errors to logs/generate/")
    parser.add_argument("--expand-to", type=int, default=None,
                        help="Generate variations of verified examples until reaching this total count")
    parser.add_argument("--only-failed", action="store_true",
                        help="Skip prompts already passed (present in output jsonl)")
    args = parser.parse_args()

    client = anthropic.Anthropic()
    prompts = PROMPTS[:args.n]

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
        def _already_passed(p):
            _m = _re.search(r'validator `(\w+)`', p)
            return _m and _m.group(1) in passed_names
        before = len(prompts)
        prompts = [(p, mc) for p, mc in prompts if not _already_passed(p)]
        print(f"  [--only-failed] skipping {before - len(prompts)} passed, retrying {len(prompts)}")

    print(f"\n{'═'*60}")
    print(f"  generate_multisig — {len(prompts)} prompts")
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
                    record = {"prompt": prompt_text, "output": code, "category": "spend/multisig_threshold"}
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
        log_path = LOGS_DIR / f"multisig_failures_{ts}.json"
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
                    record = {"prompt": new_prompt, "output": new_code, "category": "spend/multisig_threshold"}
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
