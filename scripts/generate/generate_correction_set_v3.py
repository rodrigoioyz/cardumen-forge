#!/usr/bin/env python3
"""
generate_correction_set_v3.py — Cardumen Forge

Generates correction examples for 5 patterns that cause compile failures in v8:
  1. pub type missing    — model generates `type X` without `pub`
  2. MintedValue         — model uses non-existent MintedValue constructor
  3. GovernanceCommittee — model uses non-existent Voter constructor
  4. missing interval    — model uses interval.is_entirely_after without importing
  5. inline_datum        — model uses InlineDatum without importing it (or wrong module)

Usage:
    python3 scripts/generate/generate_correction_set_v3.py --dry-run
    python3 scripts/generate/generate_correction_set_v3.py --apply
    python3 scripts/generate/generate_correction_set_v3.py --apply --count 8
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
from pathlib import Path

import anthropic

ROOT         = Path(__file__).parent.parent.parent
DATASET      = ROOT / "data" / "processed" / "dataset_v22.jsonl"
OUT_FILE     = ROOT / "data" / "processed" / "components" / "correction_set_v3.jsonl"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')

def _load_stdlib_types() -> str:
    """Load key type definitions directly from the local stdlib source."""
    base = ROOT / "eval" / "aiken_sandbox" / "build" / "packages" / "aiken-lang-stdlib" / "lib"
    snippets = []
    files = {
        "cardano/governance (Voter, GovernanceAction)": base / "cardano" / "governance.ak",
        "cardano/address (Credential)":                 base / "cardano" / "address.ak",
        "cardano/transaction (Transaction)":            base / "cardano" / "transaction.ak",
    }
    for label, path in files.items():
        if path.exists():
            text = path.read_text(encoding="utf-8")
            # Extract pub type blocks only (up to 40 lines each)
            blocks = re.findall(r'pub type \w+.*?(?=\npub |\Z)', text, re.DOTALL)
            if blocks:
                snippet = "\n".join(b[:600] for b in blocks[:6])
                snippets.append(f"-- {label} --\n{snippet}")
    return "\n\n".join(snippets)


_STDLIB_TYPES = _load_stdlib_types()

STDLIB_REF = f"""\
=== IMPORT RULES ===
CORRECT: use aiken/collection/list  |  use aiken/interval  |  use cardano/assets
         use cardano/transaction.{{Transaction, OutputReference}}
         use cardano/governance.{{Voter, ProposalProcedure}}
         use cardano/address.{{Credential}}
         use aiken/crypto.{{VerificationKeyHash}}

=== HANDLER SIGNATURES (v3) ===
  spend(datum: Option<Data>, redeemer: r, own_ref: OutputReference, self: Transaction)
  mint(redeemer: r, policy_id: PolicyId, self: Transaction)
  vote(redeemer: r, voter: Voter, self: Transaction)
  propose(redeemer: r, proposal: ProposalProcedure, self: Transaction)
  -- All top-level types used in handlers MUST be `pub type`, never `type`

=== VOTER CONSTRUCTORS — exact types from local stdlib ===
  pub type Voter {{
    ConstitutionalCommitteeMember(Credential)
    DelegateRepresentative(Credential)
    StakePool(VerificationKeyHash)
  }}
  WRONG names: GovernanceCommittee  GovernanceCouncil  CommitteeMember  (do not exist)

  CRITICAL: constructors are NOT in scope from `use cardano/governance.{{Voter}}` alone.
  You MUST import them explicitly:
    use cardano/governance.{{ConstitutionalCommitteeMember, DelegateRepresentative, StakePool, Voter}}
  This is how the local stdlib itself does it (voter.ak line 4).

=== MINTING (cardano/transaction + cardano/assets) ===
  self.mint : Value   -- directly a Value, NOT wrapped in MintedValue
  CORRECT: assets.quantity_of(self.mint, policy_id, asset_name)
  WRONG:   let MintedValue {{ mint, .. }} = self.mint   -- MintedValue does not exist
  WRONG:   self.mint.value   self.mint.tokens            -- no sub-fields

=== INTERVAL (aiken/interval) ===
  MUST import: use aiken/interval
  CORRECT: interval.is_entirely_after(self.validity_range, deadline)
  WRONG:   using interval functions without `use aiken/interval` import

=== LOCAL STDLIB TYPE DEFINITIONS (reference) ===
{_STDLIB_TYPES}
"""

SYSTEM_PROMPT = f"""\
You are an expert Aiken v3 smart contract developer generating training correction examples.

Each correction example has:
- A broken validator that fails `aiken check` due to ONE specific error
- The corrected validator that compiles correctly

{STDLIB_REF}

Output format — return a JSON array of objects, each with:
  "lang": "en" or "es" (alternate)
  "instruction": "Fix this Aiken v3 error: <short description>"
  "broken": <the broken aiken code as a string>
  "fixed": <the corrected aiken code as a string>

Rules:
- Each example tests EXACTLY ONE error (no combined errors)
- The broken code must have exactly the error described — nothing else wrong
- The fixed code must be a minimal correction of ONLY that error
- Output ONLY the JSON array — no explanation, no markdown fences
"""

PATTERNS = {
    "pub_type": {
        "description": "model uses `type X` without `pub` for types in handler signatures",
        "prompt": """\
Generate {count} correction examples for this Aiken v3 error:
  The model writes `type MyDatum {{ ... }}` without `pub` for types used in handler signatures.
  In Aiken v3, any type used in a handler signature must be declared with `pub type`.

Example broken pattern:
  type VestingDatum {{ beneficiary: ByteArray, deadline: Int }}
  validator v {{ spend(datum: Option<VestingDatum>, ...) -> Bool {{ ... }} }}

Example fixed pattern:
  pub type VestingDatum {{ beneficiary: ByteArray, deadline: Int }}
  validator v {{ spend(datum: Option<VestingDatum>, ...) -> Bool {{ ... }} }}

Generate {count} diverse variations using different handler types (spend, mint, withdraw, vote)
and different datum/redeemer type names. Half in English, half in Spanish.
""",
    },
    "minted_value": {
        "description": "model uses non-existent MintedValue constructor to destructure self.mint",
        "prompt": """\
Generate {count} correction examples for this Aiken v3 error:
  The model writes `let MintedValue {{ mint, .. }} = self.mint` to access minted tokens.
  MintedValue does not exist in Aiken v3. `self.mint` is already a `Value` — use it directly.

Example broken pattern:
  let MintedValue {{ mint, .. }} = self.mint
  let qty = assets.quantity_of(mint, policy_id, asset_name)

Example fixed pattern:
  let qty = assets.quantity_of(self.mint, policy_id, asset_name)

Generate {count} diverse mint validator variations. Half in English, half in Spanish.
""",
    },
    "governance_committee": {
        "description": "model uses non-existent GovernanceCommittee Voter constructor",
        "prompt": """\
Generate {count} correction examples for this Aiken v3 error:
  The model uses a non-existent Voter constructor (GovernanceCommittee, GovernanceCouncil,
  or CommitteeMember) when pattern-matching on a `Voter` in a vote handler.
  These constructors do not exist. The valid Voter constructors are:
    ConstitutionalCommitteeMember(Credential)
    DelegateRepresentative(Credential)
    StakePool(VerificationKeyHash)

IMPORTANT — use ONLY these import/usage patterns (they compile):

  CRITICAL IMPORT RULE:
    In Aiken, type constructors are NOT in scope when you only import the type.
    You MUST import each constructor explicitly alongside the type.
    This is confirmed by the local stdlib (cardano/governance/voter.ak):
      use cardano/governance.{{ConstitutionalCommitteeMember, DelegateRepresentative, StakePool, Voter}}

  Minimal correct imports (always use this exact form):
    use cardano/governance.{{ConstitutionalCommitteeMember, DelegateRepresentative, StakePool, Voter}}
    use cardano/transaction.{{Transaction}}

  CORRECT — check voter type:
    when voter is {{
      ConstitutionalCommitteeMember(_cred) -> True
      _ -> False
    }}

  CORRECT — full match all constructors:
    when voter is {{
      ConstitutionalCommitteeMember(_cred) -> True
      DelegateRepresentative(_cred) -> False
      StakePool(_pkh) -> False
    }}

  CORRECT — StakePool with signatories:
    use aiken/collection/list
    use cardano/governance.{{ConstitutionalCommitteeMember, DelegateRepresentative, StakePool, Voter}}
    use cardano/transaction.{{Transaction}}
    when voter is {{
      StakePool(pkh) -> list.has(self.extra_signatories, pkh)
      _ -> False
    }}

  DO NOT use `use cardano/governance.{{Voter}}` alone — constructors won't be in scope.

Example broken (wrong constructor name GovernanceCommittee):
  use cardano/governance.{{Voter}}
  use cardano/transaction.{{Transaction}}
  validator governance_check {{
    vote(_redeemer: Data, voter: Voter, _self: Transaction) -> Bool {{
      when voter is {{
        GovernanceCommittee(_cred) -> True
        _ -> False
      }}
    }}
  }}

Example fixed (note: imports ConstitutionalCommitteeMember explicitly):
  use cardano/governance.{{ConstitutionalCommitteeMember, DelegateRepresentative, StakePool, Voter}}
  use cardano/transaction.{{Transaction}}
  validator governance_check {{
    vote(_redeemer: Data, voter: Voter, _self: Transaction) -> Bool {{
      when voter is {{
        ConstitutionalCommitteeMember(_cred) -> True
        _ -> False
      }}
    }}
  }}

Generate {count} diverse vote validator variations.
Include wrong names: GovernanceCommittee, GovernanceCouncil, CommitteeMember (mix them).
Half in English, half in Spanish.
""",
    },
    "missing_interval": {
        "description": "model uses interval functions without importing use aiken/interval",
        "prompt": """\
Generate {count} correction examples for this Aiken v3 error:
  The model uses `interval.is_entirely_after` or `interval.is_entirely_before` without
  the required import `use aiken/interval`.

Example broken pattern (missing import):
  use cardano/transaction.{{Transaction, OutputReference}}
  validator v {{
    spend(..., self: Transaction) -> Bool {{
      interval.is_entirely_after(self.validity_range, deadline)
    }}
  }}

Example fixed pattern (import added):
  use aiken/interval
  use cardano/transaction.{{Transaction, OutputReference}}
  validator v {{
    spend(..., self: Transaction) -> Bool {{
      interval.is_entirely_after(self.validity_range, deadline)
    }}
  }}

Generate {count} diverse spend/mint/withdraw validator variations using time checks.
Half in English, half in Spanish.
""",
    },
    "inline_datum": {
        "description": "model uses InlineDatum without importing it, or imports from wrong module",
        "prompt": """\
Generate {count} correction examples for this Aiken v3 error:
  The model uses the `InlineDatum` constructor in pattern matching but either:
  (a) does not import it at all (only imports `Datum` or `Transaction`)
  (b) imports it from a wrong module (e.g. `cardano/outputs`, `cardano/assets`, made-up paths)

`InlineDatum` is defined in `cardano/transaction.ak` as a constructor of `pub type Datum`:
  pub type Datum {{
    NoDatum
    DatumHash(DataHash)
    InlineDatum(Data)
  }}

CRITICAL: In Aiken, constructors must be imported explicitly via `use`.
  CORRECT: use cardano/transaction.{{Transaction, OutputReference, InlineDatum}}
  WRONG:   use cardano/transaction.{{Transaction, OutputReference, Datum}}  -- Datum imported, InlineDatum NOT in scope
  WRONG:   use cardano/transaction.{{Transaction, OutputReference}}          -- InlineDatum not imported
  WRONG:   use cardano/outputs.{{InlineDatum}}                               -- module does not exist
  WRONG:   use cardano/assets.{{InlineDatum}}                                -- wrong module

Typical usage (pattern matching on an output's datum):
  when output.datum is {{
    InlineDatum(data) -> ... -- process inline datum
    _ -> False
  }}

Example broken (InlineDatum used but not imported):
  use cardano/transaction.{{Transaction, OutputReference}}

  pub type MyDatum {{
    amount: Int,
    owner: ByteArray,
  }}

  validator escrow {{
    spend(_datum: Option<MyDatum>, _redeemer: Data, _own_ref: OutputReference, self: Transaction) -> Bool {{
      let outputs = self.outputs
      list.any(outputs, fn(output) {{
        when output.datum is {{
          InlineDatum(_data) -> True
          _ -> False
        }}
      }})
    }}
  }}

Example fixed (InlineDatum explicitly imported):
  use aiken/collection/list
  use cardano/transaction.{{Transaction, OutputReference, InlineDatum}}

  pub type MyDatum {{
    amount: Int,
    owner: ByteArray,
  }}

  validator escrow {{
    spend(_datum: Option<MyDatum>, _redeemer: Data, _own_ref: OutputReference, self: Transaction) -> Bool {{
      let outputs = self.outputs
      list.any(outputs, fn(output) {{
        when output.datum is {{
          InlineDatum(_data) -> True
          _ -> False
        }}
      }})
    }}
  }}

Generate {count} diverse spend validator variations that pattern-match on output datums.
Mix error types: some missing import entirely, some importing wrong module.
Half in English, half in Spanish.
""",
    },
}


AIKEN_BIN = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")


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


def sanitize_json(raw: str) -> str:
    """Replace literal newlines/tabs inside JSON string values with escape sequences."""
    result = []
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == '\\':
            result.append(ch)
            escape_next = True
        elif ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            pass  # drop bare CR
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)
    return ''.join(result)


def generate_examples(client, pattern_key: str, count: int) -> list[dict]:
    p = PATTERNS[pattern_key]
    prompt = p["prompt"].format(count=count)

    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r'^```\w*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)

    def try_parse(text):
        # Pass 1: as-is
        try:
            return json.loads(text), None
        except json.JSONDecodeError:
            pass
        # Pass 2: fix literal newlines/tabs inside strings
        text = sanitize_json(text)
        try:
            return json.loads(text), None
        except json.JSONDecodeError:
            pass
        # Pass 3: strip trailing commas before } or ]
        text = re.sub(r',\s*([}\]])', r'\1', text)
        try:
            return json.loads(text), None
        except json.JSONDecodeError as e:
            return None, (e, text)

    result, err = try_parse(raw)
    if result is not None:
        return result
    e, cleaned = err
    pos = e.pos
    snippet = cleaned[max(0, pos-120):pos+80]
    print(f"  JSON parse error: {e}")
    print(f"  Context around error (char {pos}):\n{snippet!r}")
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply",   action="store_true")
    parser.add_argument("--count",   type=int, default=6, help="Examples per pattern")
    parser.add_argument("--patterns", nargs="+",
                        default=list(PATTERNS.keys()),
                        choices=list(PATTERNS.keys()),
                        help="Which patterns to generate")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    client = anthropic.Anthropic()

    all_examples = []

    for pattern_key in args.patterns:
        p = PATTERNS[pattern_key]
        print(f"\n{'='*60}")
        print(f"Pattern: {pattern_key}")
        print(f"  {p['description']}")
        print(f"  Requesting {args.count} examples...")

        raw_examples = generate_examples(client, pattern_key, args.count)
        print(f"  Got {len(raw_examples)} from Claude")

        if args.dry_run:
            for i, ex in enumerate(raw_examples[:2]):
                print(f"\n  Sample [{i}] ({ex.get('lang','?')}):")
                print(f"    instruction: {ex.get('instruction','')}")
                print(f"    broken snippet: {ex.get('broken','')[:120]}")
                print(f"    fixed snippet:  {ex.get('fixed','')[:120]}")
            continue

        # Compile-verify each fixed output
        verified = []
        for ex in raw_examples:
            fixed_code = ex.get("fixed", "")
            broken_code = ex.get("broken", "")
            if not fixed_code.strip():
                continue

            # Verify fixed compiles
            passed, err = compile_check(fixed_code)
            if not passed:
                err_short = next((l.strip() for l in err.splitlines() if "Error" in l), err[:80])
                print(f"  ❌ fixed fails: {err_short}")
                print(f"     fixed code:\n{fixed_code[:400]}")
                continue

            # Verify broken actually fails (sanity check)
            broken_fails, _ = compile_check(broken_code)
            if broken_fails:
                print(f"  ⚠ broken compiles (should fail) — skipping")
                continue

            print(f"  ✅ {ex.get('instruction','')[:60]}")
            verified.append({
                "lang":          ex.get("lang", "en"),
                "instruction":   ex.get("instruction", f"Fix this Aiken v3 error: {pattern_key}"),
                "input":         broken_code,
                "output":        fixed_code,
                "source":        "correction_set_v3",
                "topic":         f"correction/{pattern_key}",
                "review_status": "CORRECTION",
            })

        print(f"  Verified: {len(verified)}/{len(raw_examples)}")
        all_examples.extend(verified)

    if args.dry_run:
        return

    print(f"\n{'='*60}")
    print(f"Total verified: {len(all_examples)}")

    if not all_examples:
        print("Nothing to save.")
        return

    # Save component file
    OUT_FILE.parent.mkdir(exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Saved: {OUT_FILE}")

    # Append to main dataset
    with DATASET.open("a", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Appended {len(all_examples)} examples to {DATASET}")


if __name__ == "__main__":
    main()
