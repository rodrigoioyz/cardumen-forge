#!/usr/bin/env python3
"""
generate_dict_examples.py — Generate aiken/collection/dict training examples
Fills coverage gap: dict at 4.4% vs well-covered list at 43%.

Usage:
    python3 scripts/generate/generate_dict_examples.py
    python3 scripts/generate/generate_dict_examples.py --n 40
    python3 scripts/generate/generate_dict_examples.py --dry-run
"""

import os, re, pty, select, shutil, time, json, argparse, subprocess
from pathlib import Path
from datetime import datetime, timezone

import anthropic

ROOT         = Path(__file__).parent.parent.parent
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
OUT_FILE     = ROOT / "data" / "processed" / "components" / "dict_examples.jsonl"
LOGS_DIR     = ROOT / "logs" / "generate"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30
MODEL        = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are an expert Aiken v3 smart contract developer.
Generate complete, compilable Aiken v3 validators that use aiken/collection/dict.

── dict import and usage ──
  use aiken/collection/dict

  dict.empty                                         // Dict<key, value>
  dict.insert(d, key: ByteArray, value)              // -> Dict<key, value>
  dict.get(d, key: ByteArray)                        // -> Option<value>
  dict.has_key(d, key: ByteArray)                    // -> Bool
  dict.delete(d, key: ByteArray)                     // -> Dict<key, value>
  dict.size(d)                                       // -> Int
  dict.is_empty(d)                                   // -> Bool
  dict.keys(d)                                       // -> List<ByteArray>
  dict.values(d)                                     // -> List<value>
  dict.to_pairs(d)                                   // -> Pairs<ByteArray, value>  (NEVER dict.to_list)
  dict.from_pairs(xs)                                // -> Dict<key, value>
  dict.filter(d, fn(ByteArray, value) -> Bool)       // -> Dict<key, value>
  dict.map(d, fn(ByteArray, a) -> b)                 // -> Dict<key, b>
  dict.foldl(d, zero, fn(ByteArray, value, acc) -> acc) // left fold
  dict.foldr(d, zero, fn(ByteArray, value, acc) -> acc) // right fold
  dict.union(left, right)                            // left-biased merge
  dict.union_with(left, right, fn(k, v1, v2) -> Option<v>) // merge with strategy

── withdrawals — IMPORTANT: Pairs, NOT Dict ──
  // Transaction.withdrawals is Pairs<Credential, Lovelace>, NOT a Dict!
  // Use the pairs module for withdrawals, NOT the dict module.
  use aiken/collection/pairs
  use cardano/address.{Credential}   // Credential comes from cardano/address

  // Credential variants (from cardano/address):
  //   Script(ScriptHash)              ← use this for script credentials
  //   VerificationKey(VerificationKeyHash)
  // NEVER use ScriptCredential — that does NOT exist!

  pairs.has_key(self.withdrawals, cred)              // Bool — check if withdrew
  pairs.get_first(self.withdrawals, cred)            // Option<Lovelace>

  // For summing withdrawal amounts, use list.foldl on the pairs list:
  use aiken/collection/list
  list.foldl(self.withdrawals, 0, fn(pair, acc) { acc + pair.2nd })

── dict in transaction context ──
  // assets.tokens returns a Dict<ByteArray, Int> (asset_name -> quantity)
  use cardano/assets
  let token_dict = assets.tokens(output.value, policy_id)
  dict.size(token_dict) > 0

── list module — ALWAYS import when using list functions ──
  use aiken/collection/list
  list.has(xs, x) -> Bool          // check membership
  list.any(xs, fn) -> Bool         // any element satisfies predicate
  list.all(xs, fn) -> Bool         // all elements satisfy predicate
  list.foldl(xs, zero, fn) -> acc  // left fold
  list.length(xs) -> Int           // list length
  // self.outputs, self.extra_signatories are List — always import list!

── Import rules — CRITICAL ──
  use statements go at the TOP of the file — NEVER inside functions/validators.
  Slash ONLY in use statements. NEVER in type annotations, patterns, or expressions.

  WRONG: _ref: cardano/transaction.OutputReference   // ❌ slash in type annotation
  WRONG: fn f(d: aiken/collection/dict.Dict<...>)    // ❌ slash in type annotation
  RIGHT: use cardano/transaction.{Transaction, OutputReference}
         then use bare OutputReference in signatures  // ✅

  ALWAYS import OutputReference explicitly:
    use cardano/transaction.{Transaction, OutputReference}

── Handler signatures ──
  validator my_contract {
    spend(datum: Option<MyDatum>, _redeemer: Data, _ref: OutputReference, self: Transaction) -> Bool { ... }
    mint(redeemer: MyRedeemer, policy_id: PolicyId, self: Transaction) -> Bool { ... }
  }

File structure: use statements, pub types, helper fns, validator.
Output ONLY raw Aiken source code. No markdown, no explanation."""

PROMPTS = [
    # Registry / lookup patterns
    ("Write an Aiken v3 spend validator `registry_lookup` with RegistryDatum "
     "(registry: dict.Dict<ByteArray, Int>, required_key: ByteArray, min_value: Int). "
     "Use dict.get to check that required_key exists in registry with value >= min_value.",
     ["dict.get", "registry", "required_key", "spend("]),

    ("Write an Aiken v3 spend validator `whitelist_gate` with WhitelistDatum "
     "(whitelist: dict.Dict<ByteArray, Bool>, authorized_key: ByteArray). "
     "Use dict.has_key to verify authorized_key is in the whitelist.",
     ["dict.has_key", "whitelist", "spend("]),

    ("Write an Aiken v3 spend validator `fee_table_validator` with FeeDatum "
     "(fee_table: dict.Dict<ByteArray, Int>, operation: ByteArray, max_fee: Int). "
     "Look up the fee for the given operation and verify it does not exceed max_fee.",
     ["dict.get", "fee_table", "operation", "spend("]),

    # Withdrawal checks (withdrawals is Pairs<Credential, Lovelace> — use pairs module)
    ("Write an Aiken v3 spend validator `withdrawal_check` with WithdrawDatum "
     "(required_script_hash: ByteArray). Build a Script(required_script_hash) Credential "
     "using cardano/address.{Credential} and use pairs.has_key on self.withdrawals "
     "to verify the credential withdrew. Credential variant is Script(hash), NOT ScriptCredential.",
     ["pairs.has_key", "withdrawals", "spend("]),

    ("Write an Aiken v3 spend validator `min_withdrawal_validator` with a WithdrawDatum "
     "(script_hash: ByteArray, min_amount: Int). Build cred = Script(script_hash) using "
     "cardano/address.{Credential}, then use pairs.get_first on self.withdrawals to "
     "get the withdrawn amount, verify >= min_amount. Credential variant is Script(hash).",
     ["pairs.get_first", "withdrawals", "min_amount", "spend("]),

    # Token dict patterns
    ("Write an Aiken v3 spend validator `token_count_gate` with TokenDatum "
     "(policy_id: ByteArray, min_token_types: Int). Use assets.tokens and dict.size "
     "to verify the output contains at least min_token_types different token names "
     "under the given policy.",
     ["dict.size", "assets.tokens", "policy_id", "spend("]),

    ("Write an Aiken v3 mint validator `multi_asset_mint` that uses assets.tokens "
     "and dict.to_pairs to iterate over minted tokens and verify each quantity is "
     "exactly 1 (NFT mint). PolicyId is provided by the handler.",
     ["dict.to_pairs", "assets.tokens", "mint("]),

    # Dict fold patterns
    ("Write an Aiken v3 spend validator `sum_withdrawals` with a SumDatum "
     "(required_total: Int). self.withdrawals is Pairs<Credential, Lovelace>. "
     "Use list.foldl on self.withdrawals to sum all withdrawal amounts "
     "(pair.2nd gives the Lovelace amount) and verify the total >= required_total.",
     ["list.foldl", "withdrawals", "required_total", "spend("]),

    ("Write an Aiken v3 spend validator `all_positive_values` with a CheckDatum "
     "(policy_id: ByteArray). Use assets.tokens and dict.foldl to verify all "
     "token quantities under the policy are positive.",
     ["dict.foldl", "assets.tokens", "spend("]),

    # Dict filter/map patterns
    ("Write an Aiken v3 spend validator `filtered_registry` with FilterDatum "
     "(registry: dict.Dict<ByteArray, Int>, min_threshold: Int). "
     "Use dict.filter to get entries >= min_threshold and verify the filtered "
     "dict is non-empty using dict.is_empty.",
     ["dict.filter", "dict.is_empty", "registry", "spend("]),

    ("Write an Aiken v3 spend validator `scaled_values` with ScaleDatum "
     "(scores: dict.Dict<ByteArray, Int>, multiplier: Int, min_total: Int). "
     "Use dict.map to multiply each score by multiplier, then dict.foldl to sum "
     "and verify sum >= min_total.",
     ["dict.map", "dict.foldl", "scores", "spend("]),

    # Union patterns
    ("Write an Aiken v3 spend validator `merged_registry` with MergeDatum "
     "(base: dict.Dict<ByteArray, Int>, override_data: dict.Dict<ByteArray, Int>, "
     "required_key: ByteArray). Use dict.union (override_data left-biased) and "
     "dict.get to verify required_key is present in the merged result.",
     ["dict.union", "dict.get", "spend("]),

    # from_pairs / to_pairs
    ("Write an Aiken v3 spend validator `pairs_validator` with PairsDatum "
     "(entries: Pairs<ByteArray, Int>, required_key: ByteArray). "
     "Use dict.from_pairs to build a dict, then dict.get to look up required_key.",
     ["dict.from_pairs", "dict.get", "entries", "spend("]),

    ("Write an Aiken v3 spend validator `keys_check` with KeysDatum "
     "(registry: dict.Dict<ByteArray, Int>, signer: ByteArray). "
     "Use dict.keys to get all keys and verify signer is in the key list using list.has.",
     ["dict.keys", "list.has", "spend("]),

    ("Write an Aiken v3 spend validator `values_sum_check` with SumDatum "
     "(balances: dict.Dict<ByteArray, Int>, min_sum: Int). "
     "Use dict.values and list.foldl to sum all values and verify sum >= min_sum.",
     ["dict.values", "list.foldl", "min_sum", "spend("]),

    # get_or_else
    ("Write an Aiken v3 spend validator `default_fee_validator` with FeeDatum "
     "(fee_table: dict.Dict<ByteArray, Int>, operation: ByteArray, default_fee: Int, "
     "max_allowed: Int). Use dict.get to look up the operation fee, defaulting to "
     "default_fee if not found, and verify fee <= max_allowed.",
     ["dict.get", "fee_table", "default_fee", "spend("]),

    # Parametric validator
    ("Write a parametric Aiken v3 spend validator `config_registry(admin: ByteArray)` "
     "with ConfigDatum (config: dict.Dict<ByteArray, Int>, key: ByteArray, min_val: Int). "
     "Verify admin signed and dict.get(config, key) returns Some(v) with v >= min_val.",
     ["dict.get", "extra_signatories", "list.has", "spend("]),

    # pop / delete
    ("Write an Aiken v3 spend validator `entry_removal` with RemovalDatum "
     "(registry: dict.Dict<ByteArray, Int>, remove_key: ByteArray, owner: ByteArray). "
     "Verify owner signed. Use dict.delete and verify the resulting dict no longer "
     "has_key the removed key.",
     ["dict.delete", "dict.has_key", "owner", "spend("]),

    # size checks
    ("Write an Aiken v3 spend validator `bounded_registry` with BoundedDatum "
     "(registry: dict.Dict<ByteArray, Int>, max_entries: Int). "
     "Verify dict.size(registry) <= max_entries.",
     ["dict.size", "registry", "max_entries", "spend("]),

    # mint with dict
    ("Write an Aiken v3 mint validator `batch_nft_mint` that uses dict.to_pairs "
     "on assets.tokens(self.mint, policy_id) to iterate minted tokens and verify "
     "each has quantity == 1 using list.all.",
     ["dict.to_pairs", "assets.tokens", "list.all", "mint("]),
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

    # Skip already-verified prompts
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

        # must_contain check
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
                "source": "generate/dict_examples",
                "topic": "aiken/collection/dict",
                "review_status": "VERIFIED",
                "lang": "en",
            }
            with OUT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            passed += 1
        else:
            print(f"  ✗ compile error")
            failed_list.append({"prompt": prompt, "error": output[:500], "code": code})

    # save failures log
    if failed_list:
        log_path = LOGS_DIR / f"dict_failures_{ts}.json"
        log_path.write_text(json.dumps({"run_at": ts, "failures": failed_list}, indent=2))
        print(f"\nFailures saved to {log_path}")

    print(f"\nDone: {passed}/{len(prompts)} verified → {OUT_FILE}")


if __name__ == "__main__":
    main()
