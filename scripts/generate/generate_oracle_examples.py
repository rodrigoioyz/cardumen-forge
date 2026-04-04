#!/usr/bin/env python3
"""
generate_oracle_examples.py — Cardumen Forge

Generates oracle integration examples for Aiken v3, using the generic
Cardano oracle pattern (reference_inputs + InlineDatum).

The pattern is oracle-agnostic: works with Charli3, Orcfax, Pyth, or any
custom oracle that delivers price data via a UTxO with an inline datum.

Architecture:
  - Oracle provider keeps a UTxO at a well-known script address.
  - UTxO carries an InlineDatum: OracleDatum { price, exponent, timestamp }
  - Consumers identify the oracle UTxO by checking for a specific NFT
    (oracle_policy + oracle_asset) in the value of each reference input.
  - real_price = price × 10^exponent  (exponent is usually negative)

Patterns:
  basic_oracle_read  — find oracle UTxO in reference_inputs, extract price
  staleness_check    — validate oracle timestamp against tx validity_range
  price_gated_spend  — spend only allowed if price meets a condition
  collateral_cdp     — CDP mint/burn with collateral ratio + liquidation

Usage:
    python3 scripts/generate/generate_oracle_examples.py --dry-run --count 4
    python3 scripts/generate/generate_oracle_examples.py --apply --count 8
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
DATASET      = ROOT / "data" / "processed" / "dataset_v22.jsonl"
OUT_FILE     = ROOT / "data" / "processed" / "components" / "oracle_examples.jsonl"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
STDLIB_LIB   = SANDBOX_DIR / "build" / "packages" / "aiken-lang-stdlib" / "lib"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30

# ── Reference notes from hackathon production code ────────────────────────────

REFERENCE_NOTES = """\
Reference: synth-dolar.ak (Cardano-Pyth-Hackathon) — production oracle consumer.

Key insight: oracle data arrives via reference_inputs as InlineDatum.
Consumer validates:
  1. Oracle UTxO is present (identified by oracle NFT)
  2. Price/exponent extracted correctly via InlineDatum + expect
  3. Staleness: timestamp within validity window
  4. Business logic: collateral ratio, liquidation threshold

Collateral math (ADA-backed synth):
  synth_amount = ada_lovelaces * raw_price / 10^abs(exponent)
  health_ratio = (ada_locked * raw_price / 10^abs(exp)) * 100 / minted_amount
  collateral_ratio=150 means $1.50 ADA backs $1.00 synth

OracleDatum { price: Int, exponent: Int, timestamp: Int }
  raw_price=70_000_000, exponent=-8 → $0.70 per ADA
  1_000_000 lovelaces * 70_000_000 / 10^8 = 700_000 micro-USD
"""


# ── Load stdlib snippets for context ─────────────────────────────────────────

def load_stdlib_types() -> str:
    """Load critical type definitions from local stdlib — ground truth for pattern matching."""
    parts = []

    # Datum type — 3 constructors, Claude often forgets NoDatum/DatumHash
    tx_path = STDLIB_LIB / "cardano" / "transaction.ak"
    if tx_path.exists():
        text = tx_path.read_text(encoding="utf-8")
        for typedef in re.findall(r'pub type \w+\b[^{]*\{[^}]+\}', text, re.DOTALL):
            name = re.search(r'pub type (\w+)', typedef).group(1)
            if name in ("Datum", "Input", "Output", "Transaction"):
                parts.append(typedef.strip())

    # IntervalBoundType — 3 constructors: NegativeInfinity, Finite(Int), PositiveInfinity
    interval_path = STDLIB_LIB / "aiken" / "interval.ak"
    if interval_path.exists():
        text = interval_path.read_text(encoding="utf-8")
        for typedef in re.findall(r'pub type \w+\b[^{]*\{[^}]+\}', text, re.DOTALL):
            name = re.search(r'pub type (\w+)', typedef).group(1)
            if name in ("Interval", "IntervalBound", "IntervalBoundType"):
                parts.append(typedef.strip())

    # Credential type
    addr_path = STDLIB_LIB / "cardano" / "address.ak"
    if addr_path.exists():
        text = addr_path.read_text(encoding="utf-8")
        for typedef in re.findall(r'pub type \w+\b[^{]*\{[^}]+\}', text, re.DOTALL):
            name = re.search(r'pub type (\w+)', typedef).group(1)
            if name in ("Credential",):
                parts.append(typedef.strip())

    # assets pub fn signatures
    assets_path = STDLIB_LIB / "cardano" / "assets.ak"
    if assets_path.exists():
        text = assets_path.read_text(encoding="utf-8")
        fns  = re.findall(r'pub fn \w+\([^)]*\)[^{]*', text)
        parts.append("// cardano/assets functions:\n" + "\n".join(fns[:15]))

    return "\n\n".join(parts)


STDLIB_SNIPPETS = load_stdlib_types()

SYSTEM_PROMPT = f"""\
You are an expert Aiken v3 smart contract developer generating training examples
for the **Cardano oracle consumption pattern**.

=== ORACLE PATTERN (agnostic — works with Charli3, Orcfax, Pyth, custom) ===

Oracle data is delivered via a UTxO in tx.reference_inputs.
The oracle UTxO is identified by a specific NFT in its value.
The datum contains the price data.

Standard OracleDatum:
  pub type OracleDatum {{
    price: Int       -- raw integer  (e.g. 70_000_000)
    exponent: Int    -- negative scale (e.g. -8  →  real = price × 10^-8 = 0.70)
    timestamp: Int   -- POSIX milliseconds (for staleness check)
  }}

Finding the oracle UTxO in reference_inputs:
  fn get_oracle_datum(
    oracle_policy: PolicyId,
    oracle_asset: AssetName,
    ref_inputs: List<Input>,
  ) -> OracleDatum {{
    expect Some(oracle_input) =
      list.find(ref_inputs, fn(i) {{
        assets.quantity_of(i.output.value, oracle_policy, oracle_asset) == 1
      }})
    expect InlineDatum(raw) = oracle_input.output.datum
    expect datum: OracleDatum = raw
    datum
  }}

Price math helpers (inline — do NOT import external packages):
  fn compute_value(ada_lovelaces: Int, raw_price: Int, exponent: Int) -> Int {{
    let abs_exp = if exponent < 0 {{ -exponent }} else {{ exponent }}
    ada_lovelaces * raw_price / pow(10, abs_exp)
  }}

  fn pow(base: Int, exp: Int) -> Int {{
    if exp == 0 {{ 1 }} else {{ base * pow(base, exp - 1) }}
  }}

Staleness check (use tx.validity_range.upper_bound):
  use aiken/interval.{{Finite, IntervalBound}}
  let IntervalBound {{ bound_type: Finite(upper), .. }} = self.validity_range.upper_bound
  upper - datum.timestamp < max_age_ms

=== AIKEN v3 IMPORT RULES ===
  use aiken/collection/list
  use aiken/collection/dict
  use aiken/interval.{{Finite, IntervalBound}}
  use cardano/assets.{{PolicyId, AssetName}}
  use cardano/transaction.{{Transaction, Input, Output, OutputReference, InlineDatum}}
  use cardano/address.{{Script}}
  -- ONLY stdlib imports — no external packages

=== HANDLER SIGNATURES ===
  mint(_redeemer: Data, policy_id: PolicyId, self: Transaction) -> Bool
  spend(datum: Option<Data>, _redeemer: Data, utxo: OutputReference, self: Transaction) -> Bool
  -- Void does not exist in Aiken v3 — use _redeemer: Data for unused redeemers

=== ASSETS API ===
  assets.quantity_of(value, policy_id, asset_name) -> Int
  assets.tokens(value, policy_id) -> Dict<AssetName, Int>
  assets.lovelace_of(value) -> Int

=== REFERENCE PRODUCTION CODE NOTES ===
{REFERENCE_NOTES}

=== STDLIB SNIPPETS ===
{STDLIB_SNIPPETS}

Output format: JSON array of objects, each with:
  "lang": "en" or "es"
  "instruction": short description of what the validator does
  "input": ""
  "output": the complete Aiken v3 validator code as a string
  "topic": "oracle/cardano"
  "review_status": "VERIFIED_V3_ALIGNED"

=== CRITICAL: PATTERN MATCHING EXHAUSTIVENESS ===
`when` requires ALL constructors covered. Use `expect` for single-constructor patterns.

pub type Datum has 3 constructors: NoDatum | DatumHash(DataHash) | InlineDatum(Data)
  CORRECT: expect InlineDatum(raw) = oracle_input.output.datum
  WRONG:   when oracle_input.output.datum is {{ InlineDatum(raw) -> ... }}  ← non_exhaustive!

pub type IntervalBoundType has 3 constructors: NegativeInfinity | Finite(Int) | PositiveInfinity
  CORRECT: expect IntervalBound {{ bound_type: Finite(upper), .. }} = self.validity_range.upper_bound
  WRONG:   when ... is {{ Finite(x) -> ... }}  ← non_exhaustive!

Option has 2 constructors: Some(a) | None
  CORRECT: expect Some(x) = list.find(...)
  WRONG:   when list.find(...) is {{ Some(x) -> ... }}  ← non_exhaustive!

For custom ADTs with `when redeemer is`, cover ALL constructors you defined:
  pub type Action {{ Mint | Burn | Liquidate }}
  when redeemer is {{
    Mint     -> {{ ... }}
    Burn     -> {{ ... }}
    Liquidate -> {{ ... }}   ← must include ALL three
  }}

=== LOCAL STDLIB TYPES (ground truth) ===
{STDLIB_SNIPPETS}

=== AIKEN TEST BLOCKS (required) ===
Every example MUST include at least 3 test blocks after the validator code.
Tests verify the math helpers with concrete values — they run with `aiken test`.

Syntax:
  test name() {{
    expression == expected_value   -- must evaluate to True
  }}
  test name() fail {{
    expression                     -- must fail/error (for edge cases)
  }}

Required tests for oracle math helpers (use these exact values):
  -- ADA/USD: raw_price=70_000_000, exponent=-8 → $0.70 per ADA
  test compute_value_1_ada() {{
    compute_value(1_000_000, 70_000_000, -8) == 700_000
  }}
  test compute_value_2_ada() {{
    compute_value(2_000_000, 70_000_000, -8) == 1_400_000
  }}
  test pow_zero() {{
    pow(10, 0) == 1
  }}
  test pow_eight() {{
    pow(10, 8) == 100_000_000
  }}

For CDP validators, also include health ratio tests:
  test health_ratio_150pct() {{
    health_ratio(1_500_000, 700_000, 70_000_000, -8) == 150
  }}
  test health_ratio_zero_debt_fails() fail {{
    health_ratio(1_000_000, 0, 70_000_000, -8) == 0
  }}

IMPORTANT: test blocks must be at top level (not inside the validator block).

Rules:
  - Output ONLY the JSON array, no explanation, no markdown fences
  - Each example must be a complete, self-contained, compilable Aiken v3 validator
  - Do NOT import from external packages — stdlib only
  - Inline all helper functions (compute_value, pow, get_oracle_datum)
  - pub type for all custom types used in handler signatures
  - Include at least 3 test blocks per example
  - Half in English, half in Spanish
"""

PATTERNS = [
    {
        "id": "basic_oracle_read",
        "description": "read price from oracle reference input datum and validate basic conditions",
        "prompt": """\
Generate {count} validators that consume oracle price data from a reference input.
Each validator must:
  - Define: pub type OracleDatum {{ price: Int, exponent: Int, timestamp: Int }}
  - Find the oracle UTxO in reference_inputs by checking for an NFT (oracle_policy + oracle_asset)
  - Extract the InlineDatum as OracleDatum using: expect InlineDatum(raw) = ...; expect datum: OracleDatum = raw
  - Apply a simple price condition (e.g. price > min_price, or price < max_price)

Vary: some are spend validators, some are mint validators.
Half in English, half in Spanish.
""",
    },
    {
        "id": "staleness_check",
        "description": "oracle price staleness validation using tx validity_range",
        "prompt": """\
Generate {count} validators that include a price staleness check.
Must use: use aiken/interval.{Finite, IntervalBound}
Staleness pattern:
  expect IntervalBound { bound_type: Finite(upper), .. } = self.validity_range.upper_bound
  let is_fresh = upper - datum.timestamp < max_age_ms

Combine staleness check with a price condition.
Some should enforce max_price (sell order), others min_price (collateral floor).
Half in English, half in Spanish.
""",
    },
    {
        "id": "price_gated_spend",
        "description": "spend validator that gates spending on an oracle price threshold",
        "prompt": """\
Generate {count} spend validators that gate spending on an oracle price condition.
The UTxO datum (SpendDatum) stores: owner, threshold price, oracle_policy, oracle_asset.
On spend: read oracle, check price condition AND owner signature.

Scenarios to vary:
  - Stop-loss: allow only if price drops below threshold
  - Take-profit: allow only if price rises above threshold
  - Collateral release: allow only if position health is above minimum

Half in English, half in Spanish.
""",
    },
    {
        "id": "collateral_cdp",
        "description": "CDP mint/burn validator with collateral ratio, liquidation and oracle price",
        "max_tokens": 16000,
        "prompt": """\
Generate {count} collateral debt position (CDP) validators with oracle price feed.
Parameterized validator: collateral_ratio (e.g. 150), liquidation_threshold (e.g. 120).
Actions: pub type Action { Mint | Burn | Liquidate }

Math (inline all helpers — no external imports):
  fn compute_value(ada_lovelaces: Int, raw_price: Int, exponent: Int) -> Int {
    let abs_exp = if exponent < 0 { -exponent } else { exponent }
    ada_lovelaces * raw_price / pow(10, abs_exp)
  }
  fn pow(base: Int, exp: Int) -> Int {
    if exp == 0 { 1 } else { base * pow(base, exp - 1) }
  }
  fn health_ratio(ada_locked: Int, minted: Int, raw_price: Int, exponent: Int) -> Int {
    let abs_exp = if exponent < 0 { -exponent } else { exponent }
    ada_locked * raw_price / pow(10, abs_exp) * 100 / minted
  }

For Mint: ada_deposited >= 1, minted == compute_value(ada, price, exp) * 100 / collateral_ratio
For Burn: ada_withdrawn via ADA delta, owner must sign
For Liquidate: health_ratio(...) < liquidation_threshold (anyone can liquidate)

Half in English, half in Spanish.
""",
    },
]


def _run_aiken(cmd: str) -> tuple[bool, str]:
    """Run `aiken check` or `aiken test` in the sandbox via PTY."""
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        [AIKEN_BIN, cmd],
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


def compile_and_test(code: str) -> tuple[bool, str, str]:
    """
    Returns (passed, compile_err, test_err).
    `aiken check` type-checks AND runs all test blocks — one call does both.
    Exit code != 0 if compilation fails OR any test fails.
    """
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    ok, output = _run_aiken("check")
    if not ok:
        # Distinguish compile error vs test failure by content
        if any(kw in output for kw in ("FAIL", "failed", "test")):
            return False, "", output
        return False, output, ""
    return True, "", ""


def sanitize_json(raw: str) -> str:
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
            pass
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)
    return ''.join(result)


def parse_json(raw: str) -> list | None:
    for text in [raw, sanitize_json(raw),
                 re.sub(r',\s*([}\]])', r'\1', sanitize_json(raw))]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


def generate_batch(client, pattern: dict, count: int) -> list[dict]:
    prompt = pattern["prompt"].replace("{count}", str(count))
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=pattern.get("max_tokens", 8192),
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r'^```\w*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    result = parse_json(raw)
    if result is None:
        print(f"  JSON parse error — raw[:200]: {raw[:200]}")
        return []
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--apply",    action="store_true")
    parser.add_argument("--count",    type=int, default=4, help="Examples per pattern")
    parser.add_argument("--patterns", nargs="+",
                        default=[p["id"] for p in PATTERNS],
                        choices=[p["id"] for p in PATTERNS])
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    print(f"Stdlib snippets : {len(STDLIB_SNIPPETS)} chars")
    print()

    client = anthropic.Anthropic()
    all_examples = []

    for p in PATTERNS:
        if p["id"] not in args.patterns:
            continue

        print(f"\n{'='*60}")
        print(f"Pattern: {p['id']}")
        print(f"  {p['description']}")
        print(f"  Requesting {args.count} examples...")

        raw_examples = generate_batch(client, p, args.count)
        print(f"  Got {len(raw_examples)} from Claude")

        if args.dry_run:
            for i, ex in enumerate(raw_examples[:2]):
                print(f"\n  Sample [{i}] ({ex.get('lang','?')}):")
                print(f"    instruction: {ex.get('instruction','')}")
                print(f"    output[:150]: {ex.get('output','')[:150]}")
            continue

        verified = []
        for ex in raw_examples:
            code = ex.get("output", "")
            if not code.strip():
                continue
            passed, compile_err, test_err = compile_and_test(code)
            if passed:
                verified.append({
                    "lang":          ex.get("lang", "en"),
                    "instruction":   ex.get("instruction", ""),
                    "input":         ex.get("input", ""),
                    "output":        code,
                    "source":        "oracle_examples",
                    "topic":         f"oracle/cardano/{p['id']}",
                    "review_status": "VERIFIED_V3_ALIGNED",
                })
                print(f"  ✅ {ex.get('instruction','')[:65]}")
            elif compile_err:
                err_short = next((l.strip() for l in compile_err.splitlines() if "Error" in l), compile_err[:80])
                print(f"  ❌ compile: {err_short}")
            else:
                err_short = next((l.strip() for l in test_err.splitlines() if "FAIL" in l or "fail" in l), test_err[:80])
                print(f"  ❌ test:    {err_short}")

        print(f"  Verified: {len(verified)}/{len(raw_examples)}")
        all_examples.extend(verified)

    if args.dry_run:
        return

    print(f"\n{'='*60}")
    print(f"Total verified: {len(all_examples)}")

    if not all_examples:
        print("Nothing to save.")
        return

    OUT_FILE.parent.mkdir(exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Saved component: {OUT_FILE}")

    with DATASET.open("a", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Appended {len(all_examples)} examples to {DATASET}")


if __name__ == "__main__":
    main()
