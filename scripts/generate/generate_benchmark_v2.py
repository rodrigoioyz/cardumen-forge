#!/usr/bin/env python3
"""
generate_benchmark_v2.py — Cardumen Forge
Generates benchmark prompts with compile-verified reference solutions.
Every prompt is grounded in real aiken_stdlib.json signatures.
Only prompts whose reference solution passes `aiken check` are saved.

Usage:
    python3 scripts/generate/generate_benchmark_v2.py --n 20
    python3 scripts/generate/generate_benchmark_v2.py --n 200
    python3 scripts/generate/generate_benchmark_v2.py --n 20 --dry-run
    python3 scripts/generate/generate_benchmark_v2.py --n 20 --categories spend/signature spend/time
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

ROOT         = Path(__file__).parent.parent.parent
STDLIB_FILE  = ROOT / "data" / "raw" / "aiken_stdlib.json"
BENCHMARK_PY = ROOT / "benchmark.py"
OUT_FILE     = ROOT / "eval" / "benchmark_v2.json"
LOGS_DIR     = ROOT / "logs" / "benchmarks"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 45
MODEL        = "claude-sonnet-4-6"

# ── Category definitions ──────────────────────────────────────────────────────
# Each category has: id prefix, description, stdlib modules to inject as context

CATEGORIES = [
    {
        "id": "spend/signature",
        "description": "spend validator that checks transaction signatories",
        "modules": ["cardano/transaction"],
        "hint": "Use self.extra_signatories (field on Transaction, not a function). list.has to check membership.",
        "n": 2,
    },
    {
        "id": "spend/ada_payment",
        "description": "spend validator that checks minimum ADA payment to an address",
        "modules": ["cardano/assets", "cardano/transaction"],
        "hint": "Use assets.lovelace_of(output.value) to get lovelace. Iterate self.outputs with list.any or list.find.",
        "n": 2,
    },
    {
        "id": "spend/time",
        "description": "spend validator that enforces a deadline or time window using validity_range",
        "modules": ["aiken/interval", "cardano/transaction"],
        "hint": "Use interval.is_entirely_after(self.validity_range, deadline) — first arg is the Interval, second is the Int point. Or interval.is_entirely_before(self.validity_range, deadline). Import: use aiken/interval.",
        "n": 2,
    },
    {
        "id": "spend/nft_gate",
        "description": "spend validator that requires an NFT to be present in inputs or outputs",
        "modules": ["cardano/assets", "cardano/transaction"],
        "hint": "Use assets.quantity_of(value, policy_id, asset_name) > 0 or assets.has_nft. Check input.output.value.",
        "n": 2,
    },
    {
        "id": "spend/datum_inline",
        "description": "spend validator that reads an InlineDatum from an output",
        "modules": ["cardano/transaction"],
        "hint": "The spend handler datum parameter `datum: Option<MyDatum>` is already decoded by Aiken — use `expect Some(d) = datum` to access it. Do NOT manually extract InlineDatum from outputs; the runtime handles that. Keep the handler logic simple and flat — avoid complex pipe expressions with anonymous functions.",
        "n": 2,
    },
    {
        "id": "mint/one_shot",
        "description": "mint validator that uses a specific UTxO as a one-shot nonce to prevent double-minting",
        "modules": ["cardano/transaction", "cardano/assets"],
        "hint": "Check that a specific OutputReference is consumed in self.inputs. list.any(self.inputs, fn(i) { i.output_reference == nonce_ref }).",
        "n": 2,
    },
    {
        "id": "mint/burn",
        "description": "mint validator that only allows burning (negative quantity)",
        "modules": ["cardano/assets", "cardano/transaction"],
        "hint": "In a mint handler, self.mint contains the minted/burned values. assets.quantity_of(self.mint, policy_id, name) < 0 means burn.",
        "n": 2,
    },
    {
        "id": "governance/vote",
        "description": "vote validator for Conway-era governance",
        "modules": ["cardano/transaction", "cardano/governance"],
        "hint": "Handler signature: vote(redeemer: MyRedeemer, voter: Voter, self: Transaction) — exactly 3 args. Import Voter from cardano/governance. Do NOT add GovernanceActionId as a parameter.",
        "n": 2,
    },
    {
        "id": "spend/reference_input",
        "description": "spend validator that reads a reference input for oracle data",
        "modules": ["cardano/transaction"],
        "hint": "Use transaction.find_input(self, ref) or list.find on self.reference_inputs. Read output.datum from the reference input.",
        "n": 2,
    },
    {
        "id": "spend/multisig_threshold",
        "description": "spend validator that requires M-of-N signatures",
        "modules": ["cardano/transaction", "aiken/collection/list"],
        "hint": "Use list.count(required_signers, fn(s) { list.has(self.extra_signatories, s) }) >= threshold.",
        "n": 2,
    },
]

# ── Stdlib grounding ──────────────────────────────────────────────────────────

def load_stdlib_signatures(modules: list[str]) -> str:
    """Load real function signatures from aiken_stdlib.json for the given modules."""
    try:
        stdlib = json.loads(STDLIB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        return f"(stdlib load error: {e})"

    lines = []
    for entry in stdlib:
        mod = entry.get("module", "")
        # Match if any requested module is a prefix of this entry's module
        if any(mod == m or mod.startswith(m) for m in modules):
            name = entry.get("name", "")
            sig  = entry.get("signature", "")
            doc  = (entry.get("doc") or "").split("\n")[0][:80]
            lines.append(f"  {mod}.{name}: {sig}")
            if doc:
                lines.append(f"    // {doc}")
    return "\n".join(lines) if lines else "(no signatures found for these modules)"


def load_existing_prompt_ids() -> set[str]:
    """Extract prompt IDs from the existing TEST_SUITE in benchmark.py."""
    try:
        text = BENCHMARK_PY.read_text(encoding="utf-8")
        return set(re.findall(r'"id":\s*"([^"]+)"', text))
    except Exception:
        return set()


# ── Aiken compile check ───────────────────────────────────────────────────────

def compile_check(code: str) -> tuple[bool, str]:
    SANDBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
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
            try:
                chunks.append(os.read(master_fd, 4096))
            except OSError:
                break
        elif proc.poll() is not None:
            try:
                while True:
                    chunks.append(os.read(master_fd, 4096))
            except OSError:
                break
            break
    proc.wait()
    try:
        os.close(master_fd)
    except Exception:
        pass
    raw  = b"".join(chunks).decode("utf-8", errors="replace")
    text = ANSI.sub("", raw).strip()
    lines = [l for l in text.splitlines()
             if not l.strip().startswith(("Compiling", "Downloading"))]
    return proc.returncode == 0, "\n".join(lines).strip()


# ── Claude generation ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are generating Aiken v3 smart contract benchmark items for a fine-tuning evaluation suite.

You will produce a JSON object with these fields:
{
  "id": "unique_snake_case_id",
  "category": "category/subcategory",
  "prompt": "Natural language instruction for the model being evaluated",
  "reference_solution": "Complete, compilable Aiken v3 code that correctly answers the prompt",
  "must_contain": ["list", "of", "required", "strings"],
  "must_not_contain": ["banned", "patterns"]
}

═══ AIKEN V3 RULES — MANDATORY ═══

1. HANDLER SYNTAX — NO fn keyword before handlers:
   validator my_validator {
     spend(datum: Option<MyDatum>, redeemer: Data, own_ref: OutputReference, self: Transaction) {
       ...
     }
   }

2. IMPORTS — slash style, always first:
   use cardano/transaction.{Transaction, OutputReference}
   use aiken/collection/list
   use cardano/assets
   use aiken/interval

3. NEVER USE (removed in v3):
   - self.signatures  (use self.extra_signatories)
   - self.time        (use self.validity_range)
   - use cardano.     (dot imports removed)
   - import           (use `use` keyword)
   - MintedValue      (removed)
   - Interval<Int>    (not generic — just Interval)
   - transaction.signatories()  (not a function — field access only)
   - PosixTime        (removed)

4. CUSTOM TYPES — must be `pub type`, not `type`:
   pub type MyDatum {
     field: ByteArray,
   }
   Using `type` (without pub) in a validator file causes a private_leak error.
   ALWAYS use `pub type` for any type you define.

5. IMPORT ORDER — ALL `use` statements MUST come before any validator, fn, type, or const.
   WRONG:
     validator foo { ... }
     use aiken/collection/list   ← parser error
   CORRECT:
     use aiken/collection/list
     validator foo { ... }

6. InlineDatum:
   expect InlineDatum(raw) = output.datum
   expect typed_value: MyType = raw
   (Import InlineDatum from cardano/transaction)

7. Governance handlers — CORRECT signatures (ALL handlers take exactly 3 args):
   use cardano/transaction.{Transaction}
   use cardano/governance.{ProposalProcedure, Voter}
   use cardano/certificate.{Certificate}

   vote(redeemer: MyRedeemer, voter: Voter, self: Transaction)
   publish(redeemer: MyRedeemer, cert: Certificate, self: Transaction)
   propose(redeemer: MyRedeemer, proposal: ProposalProcedure, self: Transaction)

   CRITICAL: vote has 3 args — redeemer, voter, transaction. NEVER add GovernanceActionId as a 4th arg.
   Adding a 4th argument causes aiken::check::illegal::validator_arity error.
   NOTE: Voter comes from cardano/GOVERNANCE (NOT cardano/transaction).
   NEVER import Voter from cardano/transaction — it will cause unknown::module_field error.

8. interval functions — correct argument order:
   interval.is_entirely_after(self: Interval, point: Int) -> Bool
   interval.is_entirely_before(self: Interval, point: Int) -> Bool
   CORRECT:   interval.is_entirely_after(self.validity_range, deadline)
   WRONG:     interval.is_entirely_after(deadline, self.validity_range)  ← type_mismatch
   The Interval is ALWAYS the first argument, the Int point is ALWAYS second.

9. must_contain: specific function names or field names that a correct answer MUST use.
   must_not_contain: banned patterns that indicate wrong v2 patterns.

The reference_solution MUST be a complete .ak file that compiles with `aiken check` against stdlib v3.0.0.
Keep the reference_solution focused — no unnecessary complexity. 10-30 lines is ideal.
"""

def generate_one(client: anthropic.Anthropic, category: dict, seq: int) -> dict | None:
    """Generate one benchmark item for the given category."""
    sigs = load_stdlib_signatures(category["modules"])
    user_msg = f"""\
Generate ONE benchmark item for category: {category["id"]}
Description: {category["description"]}
Hint: {category["hint"]}

Real stdlib signatures available (use ONLY these — no hallucination):
{sigs}

The prompt should be a clear, specific natural language instruction.
The reference_solution must compile with aiken check (stdlib v3.0.0).
Make the id unique: {category["id"].replace("/", "_")}_{seq:02d}

Respond with a single valid JSON object only. No markdown fences, no explanation.
"""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"    API error: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n",          type=int, default=20,
                        help="Total number of prompts to generate (default: 20)")
    parser.add_argument("--categories", nargs="*", default=None,
                        help="Limit to specific categories (e.g. spend/signature mint/burn)")
    parser.add_argument("--retry-failures", metavar="LOG",
                        help="Retry only failed items from a previous failure log JSON")
    parser.add_argument("--out",        default=str(OUT_FILE))
    parser.add_argument("--dry-run",    action="store_true",
                        help="Generate but don't write to disk")
    parser.add_argument("--log-failures", action="store_true",
                        help="Save full failure details to logs/benchmarks/")
    args = parser.parse_args()

    client = anthropic.Anthropic()
    existing_ids = load_existing_prompt_ids()

    # ── Retry mode: load failures from a previous log ────────────────────────
    if args.retry_failures:
        log_path = Path(args.retry_failures)
        if not log_path.exists():
            print(f"Failure log not found: {log_path}")
            return
        log_data = json.loads(log_path.read_text(encoding="utf-8"))
        failures = log_data.get("failures", [])
        # Count how many retries needed per category
        from collections import Counter
        retry_counts = Counter(f["category"] for f in failures)
        cat_map = {c["id"]: c for c in CATEGORIES}
        cats = []
        for cat_id, count in retry_counts.items():
            if cat_id in cat_map:
                c = dict(cat_map[cat_id])  # copy to avoid mutating CATEGORIES
                c["n"] = count
                cats.append(c)
            else:
                print(f"  Warning: unknown category '{cat_id}' in failure log — skipping")
        total = sum(c["n"] for c in cats)
        print(f"\n{'═'*65}")
        print(f"  generate_benchmark_v2 — RETRY MODE")
        print(f"  retrying {total} failed items from: {log_path.name}")
        print(f"  model: {MODEL}")
        print(f"  existing ids to avoid: {len(existing_ids)}")
        print(f"{'═'*65}\n")
    else:
        print(f"\n{'═'*65}")
        print(f"  generate_benchmark_v2 — target: {args.n} prompts")
        print(f"  model: {MODEL}")
        print(f"  existing ids to avoid: {len(existing_ids)}")
        print(f"{'═'*65}\n")

        # Filter categories if requested
        cats = CATEGORIES
        if args.categories:
            cats = [c for c in CATEGORIES if c["id"] in args.categories]
            if not cats:
                print(f"No matching categories for: {args.categories}")
                return

        # Distribute --n across categories
        per_cat = max(1, args.n // len(cats))
        remainder = args.n - per_cat * len(cats)
        for i, cat in enumerate(cats):
            cat["n"] = per_cat + (1 if i < remainder else 0)

    passed  = []
    failed  = []
    seq     = 0

    for cat in cats:
        print(f"\n── {cat['id']} ({cat['n']} prompts) ──")
        for _ in range(cat["n"]):
            seq += 1
            print(f"  [{seq:3d}] generating...", end="", flush=True)

            item = generate_one(client, cat, seq)
            if item is None:
                print(" ✗ generation failed")
                failed.append({"seq": seq, "category": cat["id"], "reason": "generation_failed"})
                continue

            item_id = item.get("id", f"item_{seq:03d}")
            solution = item.get("reference_solution", "")

            if not solution:
                print(f" ✗ no reference_solution in response")
                failed.append({"seq": seq, "category": cat["id"], "reason": "no_solution"})
                continue

            # Compile check
            print(f" compiling {item_id}...", end="", flush=True)
            ok, output = compile_check(solution)

            if ok:
                print(f" ✅")
                passed.append(item)
            else:
                # Show first error line
                err = next((l.strip() for l in output.splitlines()
                            if l.strip() and any(k in l.lower()
                                for k in ("error", "×", "unexpected", "unknown", "unbound"))), "")
                print(f" ❌  {err[:80]}")
                failed.append({
                    "seq":      seq,
                    "category": cat["id"],
                    "id":       item_id,
                    "reason":   "compile_failed",
                    "error":    output[:400],
                    "solution": solution,
                })

            time.sleep(0.5)  # gentle rate limit

    # Summary
    print(f"\n{'═'*65}")
    print(f"  Passed : {len(passed)}/{seq}")
    print(f"  Failed : {len(failed)}/{seq}")
    print(f"{'═'*65}")

    if failed:
        print("\nFailed items:")
        for f in failed:
            print(f"  ❌ [{f['seq']:3d}] {f['category']} — {f.get('id','?')} — {f['reason']}")
            if "error" in f:
                for line in f["error"].splitlines()[:2]:
                    if line.strip():
                        print(f"       {line.strip()[:100]}")

    # Save failure log if requested (always useful for agents to read)
    if failed and (args.log_failures or not args.dry_run):
        from datetime import datetime, timezone
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = LOGS_DIR / f"benchmark_v2_failures_{ts}.json"
        log_data = {
            "run_at":   ts,
            "model":    MODEL,
            "target_n": args.n,
            "passed":   len(passed),
            "failed":   len(failed),
            "failures": failed,
        }
        log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Failure log → {log_path}")

    if args.dry_run:
        print("\n  (dry-run — nothing written)")
        return

    if not passed:
        print("\n  Nothing to write.")
        return

    # Load existing benchmark_v2.json if it exists (append, don't overwrite)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing_out_ids = {e.get("id") for e in existing}
    new_items = [p for p in passed if p.get("id") not in existing_out_ids]
    dupes = len(passed) - len(new_items)

    all_items = existing + new_items
    out_path.write_text(json.dumps(all_items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Saved → {out_path}")
    print(f"  Total in file: {len(all_items)} (+{len(new_items)} new, {dupes} dupes skipped)")


if __name__ == "__main__":
    main()
