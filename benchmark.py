#!/usr/bin/env python3
"""
benchmark.py — Cardumen Forge
Runs the 15-prompt eval suite across multiple model versions loaded in LM Studio
and produces a comparison table.

Usage:
    python3 benchmark.py
    python3 benchmark.py --url http://192.168.1.x:1234
    python3 benchmark.py --results-dir eval_results/

Each model must be manually loaded in LM Studio before the script proceeds.
Results are saved to eval_results/ and can be re-compared at any time with:
    python3 benchmark.py --compare-only
"""

import os
import sys
import json
import re
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from openai import OpenAI

# ─────────────────────────────────────────────────────────────────────────────
# Models to benchmark — edit names to match exactly what LM Studio shows
# ─────────────────────────────────────────────────────────────────────────────
MODELS = [
    {
        "label":       "qwen2.5-coder-7b (base)",
        "lm_name":     "qwen2.5-coder-7b-instruct",
        "version":     "base",
    },
    {
        "label":       "gemma-4-e4b (base)",
        "lm_name":     "google_gemma-4-e4b-it",
        "version":     "gemma4",
    },
    {
        "label":       "cardano-dev v1",
        "lm_name":     "lmstudio-community/aiken_expert/cardano-dev qwen3.5-4b.q4_k_m.gguf",
        "version":     "v1",
    },
    {
        "label":       "cardano-dev v2 (dataset v13)",
        "lm_name":     "lmstudio-community/aiken_expert/cardano-dev 2.0 qwen3.5-4b.q4_k_m (1).gguf",
        "version":     "v2",
    },
    {
        "label":       "cardano-dev v3 (dataset v13)",
        "lm_name":     "lmstudio-community/aiken_expert/cardano-dev 3.0 qwen3.5-4b.q4_k_m (2).gguf",
        "version":     "v3",
    },
    {
        "label":       "cardano-dev v4 (dataset v14, run 2)",
        "lm_name":     "lmstudio-community/aiken_expert/cardano-dev 4.0 qwen3.5-4b.q4_k_m (3).gguf",
        "version":     "v4",
    },
    {
        "label":       "cardano-dev v5 (dataset v20, wrong ckpt)",
        "lm_name":     "lmstudio-community/aiken_expert/cardano-dev 5.0  qwen3.5-4b.q4_k_m.gguf",
        "version":     "v5",
    },
    {
        "label":       "cardano-dev v6 (dataset v20, best ckpt)",
        "lm_name":     "lmstudio-community/aiken_expert/cardano-dev-6.0-v20-q4_k_m.gguf",
        "version":     "v6",
    },
    {
        "label":       "cardano-dev v7 (dataset v21, best ckpt)",
        "lm_name":     "lmstudio-community/aiken_expert/cardano-dev-7.0-v21-q4_k_m.gguf",
        "version":     "v7",
    },
]

RESULTS_DIR = Path("eval_results")
TEMPERATURE = 0.1

SYSTEM_PROMPT = """\
You are an expert Aiken v3 smart contract engineer for the Cardano blockchain.
You write correct, compilable Aiken v3 validators using only verified APIs.

CRITICAL — handler syntax inside validator blocks (NO fn keyword before handler name):
  validator my_contract {
    spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool { ... }
    mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool { ... }
    withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool { ... }
    publish(redeemer: T, cert: Certificate, self: Transaction) -> Bool { ... }
    vote(redeemer: T, voter: Voter, self: Transaction) -> Bool { ... }
    propose(redeemer: T, proposal: ProposalProcedure, self: Transaction) -> Bool { ... }
    else(_) { fail }
  }

CUSTOM TYPES — commas required after EVERY field (stdlib v3):
  pub type MyDatum {
    owner: VerificationKeyHash,
    deadline: Int,
    amount: Int,
  }

IMPORTS (slash style — never dot, imports must come first):
  use cardano/assets
  use cardano/transaction.{Transaction, OutputReference}
  use cardano/certificate.{Certificate}
  use cardano/governance.{Voter, ProposalProcedure}
  use aiken/collection/list
  use aiken/collection/dict
  use aiken/interval
  use aiken/math/rational

IMPORT RULES — always include these when using the types:
  Transaction, OutputReference → use cardano/transaction.{Transaction, OutputReference}
  InlineDatum                  → add to transaction import: .{Transaction, OutputReference, InlineDatum}
  PolicyId                     → use cardano/assets.{PolicyId}  OR prefix as assets.PolicyId
  Certificate                  → use cardano/certificate.{Certificate}
  Voter, ProposalProcedure     → use cardano/governance.{Voter, ProposalProcedure}

VERIFIED API PATTERNS:
  ADA check  : assets.lovelace_of(output.value) — NEVER output.assets.ada
  Signatures : list.has(self.extra_signatories, key) — NEVER self.signatures
  Time       : self.validity_range — type is Interval (NOT Interval<Int>)
  NFT check  : assets.quantity_of(value, policy_id, asset_name)
  Inputs     : transaction.find_input(self.inputs, ref)
  Ref inputs : transaction.find_input(self.reference_inputs, ref)
  InlineDatum: expect InlineDatum(raw) = output.datum — always import explicitly
  dict       : dict.to_pairs(d) — NEVER dict.to_list
  rational   : rational.new(n, d)

CERTIFICATE constructors (stdlib v3 exact names):
  RegisterCredential, UnregisterCredential, DelegateCredential
  RegisterAndDelegateCredential

REMOVED in stdlib v3 — NEVER generate:
  aiken/time | PosixTime        → use self.validity_range
  MintedValue                   → use Value
  VerificationKeyCredential     → use VerificationKey
  ScriptCredential              → use Script
  DeregisterCredential          → use UnregisterCredential
  Interval<Int>                 → use Interval (not generic)"""

TEST_SUITE = [
    {
        "id": "spend_owner_sig",
        "category": "spend / signature",
        "prompt": "Write an Aiken v3 spend validator that only allows the owner to withdraw funds. The owner's key hash is stored in the datum.",
        "must_contain": ["validator", "spend(", "extra_signatories"],
        "must_not_contain": ["self.signatures", "tx.signatures", "self.time", "use cardano."],
    },
    {
        "id": "spend_ada_payment",
        "category": "spend / ADA",
        "prompt": "Write an Aiken v3 spend validator for a simple escrow: release funds when at least 5 ADA is sent to the beneficiary.",
        "must_contain": ["validator", "spend(", "lovelace_of"],
        "must_not_contain": ["output.assets.ada", "output.value >=", "self.time", "use cardano."],
    },
    {
        "id": "spend_time_lock",
        "category": "spend / time",
        "prompt": "Write an Aiken v3 spend validator that locks funds until a deadline stored in the datum.",
        "must_contain": ["validator", "spend(", "validity_range"],
        "must_not_contain": ["self.time", "block_num", "self.signatures", "use cardano."],
    },
    {
        "id": "spend_nft_gate",
        "category": "spend / NFT",
        "prompt": "Write an Aiken v3 spend validator that only allows spending if the transaction includes a specific NFT.",
        "must_contain": ["validator", "spend(", "has_nft"],
        "must_not_contain": ["self.time", "output.assets.ada", "use cardano."],
    },
    {
        "id": "spend_multisig",
        "category": "spend / multisig",
        "prompt": "Write an Aiken v3 spend validator that requires 2 out of 3 admins to sign the transaction. Admin keys are stored in the datum.",
        "must_contain": ["validator", "spend(", "extra_signatories", "list.count"],
        "must_not_contain": ["MultiSignature", "self.signatures", "use cardano."],
    },
    {
        "id": "mint_nft_one_shot",
        "category": "mint / one-shot",
        "prompt": "Write an Aiken v3 mint validator for a one-shot NFT policy that can only mint once by consuming a specific UTXO.",
        "must_contain": ["validator", "mint(", "policy_id"],
        "must_not_contain": ["self.time", "self.signatures", "use cardano.", "fn spend("],
    },
    {
        "id": "mint_admin_capped",
        "category": "mint / capped supply",
        "prompt": "Write an Aiken v3 mint validator where only an admin can mint, and total supply cannot exceed 1,000,000 tokens.",
        "must_contain": ["validator", "mint(", "extra_signatories", "quantity_of"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "withdraw_staking",
        "category": "withdraw",
        "prompt": "Write an Aiken v3 withdraw validator that allows staking rewards to be claimed only by the registered owner.",
        "must_contain": ["validator", "withdraw(", "extra_signatories"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "spend_combined",
        "category": "spend / combined",
        "prompt": "Write an Aiken v3 spend validator that checks: the owner signed AND the transaction is submitted before a deadline.",
        "must_contain": ["validator", "spend(", "extra_signatories", "validity_range"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "spend_reference_input",
        "category": "spend / reference inputs",
        "prompt": "Write an Aiken v3 spend validator that reads a price from a reference input oracle and checks the payment is at least that price.",
        "must_contain": ["validator", "spend(", "reference_inputs", "find_input"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "vote_governance",
        "category": "vote / governance",
        "prompt": "Write an Aiken v3 vote validator for a DAO that only allows a registered committee member to cast a governance vote.",
        "must_contain": ["validator", "vote(", "Voter"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano.", "fn spend("],
    },
    {
        "id": "publish_cert",
        "category": "publish / certificate",
        "prompt": "Write an Aiken v3 publish validator that only allows the owner to register or deregister a staking credential.",
        "must_contain": ["validator", "publish(", "Certificate"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "multi_handler",
        "category": "multi-handler",
        "prompt": "Write an Aiken v3 validator with both a spend handler and a mint handler. The spend checks the owner signed, the mint checks a capped supply.",
        "must_contain": ["validator", "spend(", "mint(", "extra_signatories"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "import_style",
        "category": "imports",
        "prompt": "Write an Aiken v3 spend validator that checks a signature and an NFT. Show the correct import style.",
        "must_contain": ["use cardano/", "use aiken/", "validator", "spend("],
        "must_not_contain": ["use cardano.", "use aiken.", "self.signatures"],
    },
    {
        "id": "typed_datum",
        "category": "spend / typed datum",
        "prompt": "Write an Aiken v3 spend validator for a vesting contract. Define a custom VestingDatum type with beneficiary and deadline fields.",
        "must_contain": ["validator", "spend(", "VestingDatum", "validity_range"],
        "must_not_contain": ["self.time", "self.signatures", "use cardano."],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Aiken compile sandbox
# ─────────────────────────────────────────────────────────────────────────────

SANDBOX_DIR       = Path(__file__).parent / "eval" / "aiken_sandbox"
SANDBOX_VALIDATOR = SANDBOX_DIR / "validators" / "output.ak"


def compile_check(code: str) -> dict:
    """
    Write code to sandbox validator slot and run `aiken check`.
    Returns {"pass": bool|None, "skipped": bool, "error": str}.

    Prerequisites (one-time setup):
        cd ~/entrenamiento
        aiken new eval/aiken_sandbox
        aiken check --project eval/aiken_sandbox   # downloads stdlib
    """
    if not (SANDBOX_DIR / "aiken.toml").exists():
        return {"pass": None, "skipped": True, "error": "sandbox not found — run: aiken new eval/aiken_sandbox"}

    SANDBOX_VALIDATOR.parent.mkdir(parents=True, exist_ok=True)
    SANDBOX_VALIDATOR.write_text(code, encoding="utf-8")

    try:
        import pty, select, io
        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            ["aiken", "check"],
            cwd=SANDBOX_DIR,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            env={**os.environ, "TERM": "xterm-256color", "COLUMNS": "200"},
        )
        os.close(slave_fd)

        chunks = []
        import time
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                r_list, _, _ = select.select([master_fd], [], [], 0.2)
                if r_list:
                    data = os.read(master_fd, 4096)
                    chunks.append(data)
                elif proc.poll() is not None:
                    # drain remaining
                    try:
                        while True:
                            data = os.read(master_fd, 4096)
                            chunks.append(data)
                    except OSError:
                        pass
                    break
            except OSError:
                break

        proc.wait()
        try:
            os.close(master_fd)
        except OSError:
            pass

        raw = b"".join(chunks).decode("utf-8", errors="replace")
        # Strip ANSI escape sequences
        ansi_escape = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
        text = ansi_escape.sub("", raw).strip()

        return {
            "pass":    proc.returncode == 0,
            "skipped": False,
            "error":   text if proc.returncode != 0 else "",
            "rc":      proc.returncode,
        }
    except FileNotFoundError:
        return {"pass": None, "skipped": True, "error": "aiken not in PATH"}
    except Exception as e:
        return {"pass": None, "skipped": True, "error": f"compile check error: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Checks
# ─────────────────────────────────────────────────────────────────────────────

def strip_markdown(output: str) -> str:
    """Extract code from a markdown fence if present, otherwise return as-is."""
    m = re.search(r'```(?:\w+)?\n(.*?)```', output, re.DOTALL)
    return m.group(1).strip() if m else output


def has_complete_handler(output: str) -> bool:
    m = re.search(r'\bvalidator\b[^{]*\{', output)
    if not m:
        return False
    body = output[m.start():]
    return bool(re.search(r'\b(?:fn\s+)?(spend|mint|withdraw|publish|vote)\s*\(', body))


def run_checks(output: str, must_contain: list, must_not_contain: list) -> dict:
    results = {}
    had_fence = output.strip().startswith("```")
    code = strip_markdown(output)  # check content inside the fence, not the wrapper

    results["has_validator_block"]   = "validator" in code
    results["has_complete_handler"]  = has_complete_handler(code)
    results["has_slash_imports"]     = bool(re.search(r'\buse\s+\w+/', code))
    results["no_dot_imports"]        = not bool(re.search(r'^use\s+\w+\.', code, re.MULTILINE))
    results["wrapped_in_markdown"]   = had_fence  # informational only — not in pass check
    for p in must_contain:
        results[f"contains:{p}"] = p in code
    for p in must_not_contain:
        results[f"absent:{p}"] = p not in code
    results["pass"] = all(v for k, v in results.items() if k not in ("pass", "wrapped_in_markdown"))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Single model eval
# ─────────────────────────────────────────────────────────────────────────────

def eval_model(client, model_name: str, label: str, skip_compile: bool = False, debug_compile: bool = False) -> dict:
    results = []
    passed = 0
    compiled = 0
    compile_skipped = False

    for i, test in enumerate(TEST_SUITE):
        print(f"  [{i+1:02d}/{len(TEST_SUITE)}] {test['id']}...", end=" ", flush=True)
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": test["prompt"]},
                ],
                temperature=TEMPERATURE,
                max_tokens=2048,
            )
            output = resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({**test, "output": "", "checks": {}, "compile": {}, "error": str(e)})
            continue

        checks = run_checks(output, test["must_contain"], test["must_not_contain"])

        compile = {"pass": None, "skipped": True, "error": "skipped"}
        if not skip_compile:
            code = strip_markdown(output)
            compile = compile_check(code)
            if compile["skipped"]:
                compile_skipped = True
            elif compile["pass"]:
                compiled += 1

        status = "✅" if checks["pass"] else "❌"
        compile_tag = ""
        if not skip_compile and not compile["skipped"]:
            compile_tag = " [C:✅]" if compile["pass"] else " [C:❌]"
        print(status + compile_tag)

        if not checks["pass"]:
            failed = [k for k, v in checks.items() if not v and k != "pass"]
            print(f"         ↳ failed: {failed}")
        if not skip_compile and not compile["skipped"] and not compile["pass"]:
            if debug_compile:
                print(f"         ↳ RAW rc={compile.get('rc')} stdout+stderr:")
                print(repr(compile["error"][:800]))
            else:
                lines = [l for l in compile["error"].splitlines() if l.strip()]
                progress_prefixes = ("Compiling", "Resolving", "Fetched", "Collecting", "Downloading")
                signal_lines = [l for l in lines if not any(l.strip().startswith(p) for p in progress_prefixes)]
                shown = signal_lines[:8] if signal_lines else lines[-8:]
                error_snippet = "\n           ".join(shown)
                print(f"         ↳ {error_snippet}")
        if checks["pass"]:
            passed += 1

        results.append({
            "id":       test["id"],
            "category": test["category"],
            "prompt":   test["prompt"],
            "output":   output,
            "checks":   checks,
            "compile":  compile,
        })

    by_category = {}
    for r in results:
        cat = r["category"].split(" / ")[0]
        by_category.setdefault(cat, {"passed": 0, "total": 0})
        by_category[cat]["total"] += 1
        if r.get("checks", {}).get("pass"):
            by_category[cat]["passed"] += 1
    for cat in by_category:
        p = by_category[cat]
        p["pass_rate"] = 100 * p["passed"] / max(1, p["total"])

    pass_rate    = 100 * passed   / max(1, len(TEST_SUITE))
    compile_rate = 100 * compiled / max(1, len(TEST_SUITE))
    return {
        "label":         label,
        "model":         model_name,
        "passed":        passed,
        "total":         len(TEST_SUITE),
        "pass_rate":     pass_rate,
        "compiled":      compiled,
        "compile_rate":  compile_rate,
        "compile_skipped": compile_skipped,
        "by_category":   by_category,
        "results":       results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Detect loaded models from LM Studio API
# ─────────────────────────────────────────────────────────────────────────────

def get_loaded_models(client) -> list[str]:
    try:
        return [m.id for m in client.models.list().data]
    except Exception as e:
        print(f"  ⚠  API error: {e}")
        return []


def match_model(loaded: list[str], lm_name: str) -> str | None:
    """Find the best match for lm_name among loaded model IDs."""
    # Exact match first
    for m in loaded:
        if m == lm_name:
            return m
    # Partial match (LM Studio sometimes truncates)
    for m in loaded:
        if lm_name.lower() in m.lower() or m.lower() in lm_name.lower():
            return m
    return None


def wait_for_model(client, expected_name: str, label: str):
    """If model is already loaded, return immediately. Otherwise prompt."""
    loaded = get_loaded_models(client)
    match  = match_model(loaded, expected_name)

    if match:
        print(f"\n{'─'*60}")
        print(f"  ✅ Auto-detected: {label}")
        print(f"     Model ID: {match}")
        print(f"{'─'*60}")
        return match

    # Not loaded — fall back to manual prompt
    print(f"\n{'─'*60}")
    print(f"  Next: {label}")
    print(f"  Load in LM Studio: \"{expected_name}\"")
    print(f"  Currently loaded: {loaded or 'none'}")
    print(f"{'─'*60}")

    while True:
        input("  Press Enter when the model is loaded and ready... ")
        loaded = get_loaded_models(client)
        match  = match_model(loaded, expected_name)
        if match:
            print(f"  ✅ Detected: {match}")
            return match
        print(f"  ⚠  Model not found. Loaded: {loaded}")
        print(f"     Expected: \"{expected_name}\"")


# ─────────────────────────────────────────────────────────────────────────────
# Comparison table
# ─────────────────────────────────────────────────────────────────────────────

def print_comparison(summaries: list):
    if not summaries:
        return

    print(f"\n{'═'*70}")
    print("  CARDUMEN FORGE — BENCHMARK RESULTS")
    print(f"{'═'*70}\n")

    # Overall pass rate
    print(f"  {'Model':<38} {'Pass':>6}  {'Score':>7}  {'Δ':>6}  {'Compile':>9}")
    print(f"  {'─'*72}")
    prev_rate = None
    for s in summaries:
        bar   = "█" * int(s["pass_rate"] / 7)
        delta = ""
        if prev_rate is not None:
            d = s["pass_rate"] - prev_rate
            delta = f"{'+'if d>=0 else ''}{d:.0f}%"
        if s.get("compile_skipped") or "compiled" not in s:
            compile_col = "—"
        else:
            compile_col = f"{s['compiled']}/{s['total']} ({s['compile_rate']:.0f}%)"
        print(f"  {s['label']:<38} {s['passed']:>3}/{s['total']:<3}  {s['pass_rate']:>5.0f}%  {delta:>6}  {compile_col:>9}  {bar}")
        prev_rate = s["pass_rate"]

    # By category
    all_cats = sorted({cat for s in summaries for cat in s["by_category"]})
    col_w = 12

    print(f"\n  {'Category':<24}", end="")
    for s in summaries:
        short = s["label"].split("(")[0].strip()[-col_w:]
        print(f"  {short:>{col_w}}", end="")
    print()
    print(f"  {'─'*70}")

    for cat in all_cats:
        print(f"  {cat:<24}", end="")
        for s in summaries:
            c = s["by_category"].get(cat, {"passed": 0, "total": 0, "pass_rate": 0})
            cell = f"{c['passed']}/{c['total']} ({c['pass_rate']:.0f}%)"
            print(f"  {cell:>{col_w}}", end="")
        print()

    print(f"\n{'═'*70}")


# ─────────────────────────────────────────────────────────────────────────────
# Save / load
# ─────────────────────────────────────────────────────────────────────────────

def save_result(result: dict, results_dir: Path):
    results_dir.mkdir(exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^\w]+", "_", result["label"])[:30]
    path = results_dir / f"bench_{ts}_{slug}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Saved → {path}")
    return path


def load_all_results(results_dir: Path) -> list:
    files = sorted(results_dir.glob("bench_*.json"))
    summaries = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        summaries.append(data)
    return summaries


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",           default=os.environ.get("LM_STUDIO_URL", "http://192.168.208.1:3005"))
    parser.add_argument("--results-dir",   default="eval_results")
    parser.add_argument("--compare-only",  action="store_true", help="Only show comparison of saved results")
    parser.add_argument("--models",        nargs="*", help="Run only specific version labels (e.g. base v1 v3)")
    parser.add_argument("--skip-compile",   action="store_true", help="Skip aiken compile-check (faster, heuristic only)")
    parser.add_argument("--debug-compile",  action="store_true", help="Print raw aiken output for every compile failure")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)

    if args.compare_only:
        summaries = load_all_results(results_dir)
        if not summaries:
            print(f"No results found in {results_dir}/")
            sys.exit(1)
        print_comparison(summaries)
        return

    client = OpenAI(base_url=f"{args.url}/v1", api_key="not-needed")

    models_to_run = MODELS
    if args.models:
        models_to_run = [m for m in MODELS if m["version"] in args.models]
        if not models_to_run:
            print(f"No matching models. Available versions: {[m['version'] for m in MODELS]}")
            sys.exit(1)

    # Auto-detect what's loaded
    loaded = get_loaded_models(client)
    if not loaded:
        print(f"⚠  No models detected at {args.url}")
        print(f"   Check that LM Studio is running and the URL is correct.")
        sys.exit(1)

    print(f"\nCardumen Forge — Benchmark")
    print(f"LM Studio URL  : {args.url}")
    print(f"Loaded models  : {len(loaded)}")
    for m in loaded:
        print(f"  • {m}")
    print(f"Models to test : {len(models_to_run)}")
    print(f"Prompts each   : {len(TEST_SUITE)}")
    print(f"Mode           : sequential (one at a time)")
    print(f"Compile check  : {'disabled (--skip-compile)' if args.skip_compile else 'enabled (aiken check)'}")
    print(f"Results dir    : {results_dir}/\n")

    if not args.skip_compile and not (SANDBOX_DIR / "aiken.toml").exists():
        print(f"⚠  Compile sandbox not found at {SANDBOX_DIR}")
        print(f"   One-time setup:")
        print(f"     aiken new eval/aiken_sandbox")
        print(f"     aiken check --project eval/aiken_sandbox")
        print(f"   Continuing without compile-check (add --skip-compile to suppress this warning)\n")

    summaries = []

    for model_cfg in models_to_run:
        actual_name = wait_for_model(client, model_cfg["lm_name"], model_cfg["label"])

        print(f"\n  Running {len(TEST_SUITE)} prompts...")
        result = eval_model(client, actual_name, model_cfg["label"], skip_compile=args.skip_compile, debug_compile=args.debug_compile)

        print(f"\n  {result['passed']}/{result['total']} passed ({result['pass_rate']:.0f}%)")
        save_result(result, results_dir)
        summaries.append(result)

        # Incremental comparison after each model
        if len(summaries) > 1:
            print_comparison(summaries)

    print("\nDone. Final comparison:")
    print_comparison(summaries)
    print(f"\nTo re-compare later:")
    print(f"  python3 benchmark.py --compare-only")


if __name__ == "__main__":
    main()
