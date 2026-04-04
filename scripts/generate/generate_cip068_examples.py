#!/usr/bin/env python3
"""
generate_cip068_examples.py — Cardumen Forge

Generates CIP-0067/CIP-0068 mint validator examples grounded in the local CIP corpus.

CIP-0067: Asset Name Label Registry
  Asset names prefixed with 4 bytes: [0000 | 16-bit label | 8-bit CRC-8 | 0000]
  Key prefixes:
    label 100 → 000643b0 (reference NFT)
    label 222 → 000de140 (user token / NFT)
    label 333 → 0014df10 (fungible token)

CIP-0068: Datum Metadata Standard
  Two tokens per asset under same policy:
    - Reference NFT: 000643b0 + <name_content> — locked at script with datum
    - User token:    000de140 + <name_content> — lives in user wallet
  Pairing rule: for every user token there MUST be exactly one reference NFT
    with the same name content (bytes after the 4-byte prefix).

Usage:
    python3 scripts/generate/generate_cip068_examples.py --dry-run --count 4
    python3 scripts/generate/generate_cip068_examples.py --apply --count 8
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
OUT_FILE     = ROOT / "data" / "processed" / "components" / "cip068_examples.jsonl"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
STDLIB_LIB   = SANDBOX_DIR / "build" / "packages" / "aiken-lang-stdlib" / "lib"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30

# ── Load CIP-0067/CIP-0068 content from local corpus ─────────────────────────

def load_cip_content() -> str:
    cip_file = ROOT / "data" / "raw" / "cips.json"
    data     = json.loads(cip_file.read_text(encoding="utf-8"))
    result   = {}
    for cip in data:
        if cip.get("id") in ("CIP-0067", "CIP-0068"):
            result[cip["id"]] = cip.get("content", "")[:3000]
    return result


# ── Load bytearray stdlib ─────────────────────────────────────────────────────

def load_bytearray_api() -> str:
    path = STDLIB_LIB / "aiken" / "primitive" / "bytearray.ak"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    # Extract pub fn signatures only
    fns = re.findall(r'pub fn \w+\([^)]*\)[^{]*', text)
    return "\n".join(fns[:20])


CIP_CONTENT   = load_cip_content()
BYTEARRAY_API = load_bytearray_api()

SYSTEM_PROMPT = f"""\
You are an expert Aiken v3 smart contract developer generating training examples for CIP-0067 and CIP-0068 validators.

=== CIP-0067: Asset Name Label Registry (from local corpus) ===
{CIP_CONTENT.get('CIP-0067', '')[:1500]}

=== CIP-0068: Datum Metadata Standard (from local corpus) ===
{CIP_CONTENT.get('CIP-0068', '')[:2000]}

=== KEY PREFIXES (hex, 4 bytes each) ===
  000643b0 = label 100 = reference NFT  (locked at script with datum)
  000de140 = label 222 = user token NFT (lives in user wallet)
  0014df10 = label 333 = fungible token
  In Aiken: #"000643b0"  #"000de140"  #"0014df10"

=== AIKEN v3 IMPORT RULES ===
  use aiken/collection/list
  use aiken/collection/dict
  use aiken/primitive/bytearray        -- for bytearray.length, bytearray.take, bytearray.drop
  use cardano/assets.{{PolicyId, AssetName}}
  use cardano/transaction.{{Transaction}}

=== BYTEARRAY API (from local stdlib) ===
{BYTEARRAY_API}

=== HANDLER SIGNATURE ===
  mint(_redeemer: Data, policy_id: PolicyId, self: Transaction) -> Bool
  -- NOT: redeemer: Void  (Void does not exist in Aiken v3)
  -- Use _redeemer: Data for unused redeemers

=== ASSETS API ===
  assets.tokens(self.mint, policy_id) -> Dict<AssetName, Int>
  dict.to_pairs(tokens_dict)          -> Pairs<AssetName, Int>  (= List<Pair<AssetName, Int>>)
  -- Pair(name, qty) to destructure each entry

=== CIP-0068 PAIRING LOGIC ===
  For every user token (prefix 000de140), there MUST be a reference NFT (prefix 000643b0)
  with the same name content (bytes after the 4-byte prefix):
    let user_content = bytearray.drop(name, 4)
    -- verify 000643b0 ++ user_content also exists in minted tokens with qty 1

Output format: JSON array of objects, each with:
  "lang": "en" or "es"
  "instruction": short description of what the validator does
  "input": ""
  "output": the complete Aiken v3 validator code as a string
  "topic": "cip/cip-0068"
  "review_status": "VERIFIED_V3_ALIGNED"

Rules:
  - Output ONLY the JSON array, no explanation, no markdown fences
  - Each example must be a complete, compilable Aiken v3 validator
  - Use pub type for all types in handler signatures
  - Vary complexity: basic prefix check, pairing validation, burn handling, FT variant
"""

PATTERNS = [
    {
        "id": "basic_prefix",
        "description": "mint validator enforcing CIP-0067 4-byte prefix on all minted assets",
        "prompt": """\
Generate {{count}} mint validator examples that enforce the CIP-0067 4-byte prefix rule:
  - Every minted asset name under this policy must start with a valid 4-byte label prefix
  - bytearray.length(name) >= 4
  - Quantity must be exactly 1 for NFTs (label 222 or 100)

Vary the validators: some check only label 222 (user tokens), some check label 100 (reference NFTs),
some check that ALL minted tokens have the prefix.
Half in English, half in Spanish.
""",
    },
    {
        "id": "pairing_validation",
        "description": "mint validator enforcing CIP-0068 pairing: reference NFT (000643b0) paired with user token (000de140)",
        "prompt": """\
Generate {{count}} mint validator examples that enforce the CIP-0068 pairing rule:
  - When minting a user token (prefix 000de140 = label 222), the corresponding reference NFT
    (prefix 000643b0 = label 100) with the same name content MUST also be minted.
  - Both must have quantity = 1
  - Name content = bytearray.drop(name, 4) (bytes after the 4-byte prefix)

The pairing check: for each token with prefix 000de140, verify that a token
000643b0 ++ bytearray.drop(name, 4) is also being minted.

Half in English, half in Spanish.
""",
    },
    {
        "id": "burn_handling",
        "description": "mint validator that allows burning CIP-0068 tokens (negative quantities) while enforcing minting rules",
        "prompt": """\
Generate {{count}} mint validator examples that handle both minting and burning of CIP-0068 tokens:
  - When minting (qty > 0): enforce prefix and pairing rules
  - When burning (qty < 0): allow it (just verify qty == -1 for NFTs, or qty < 0 for FTs)
  - Use when qty > 0 is {{ ... }} else {{ ... }} or list.all with condition check

Half in English, half in Spanish.
""",
    },
    {
        "id": "ft_variant",
        "description": "mint validator for CIP-0068 fungible tokens (label 333, prefix 0014df10)",
        "prompt": """\
Generate {{count}} mint validator examples for CIP-0068 fungible tokens (FT):
  - FT prefix: 0014df10 (label 333)
  - FT can be minted in quantities > 1 (unlike NFTs which must be qty = 1)
  - Still requires the reference NFT (000643b0) with matching name content
  - May add a max_supply check using the datum from the reference NFT output

Half in English, half in Spanish.
""",
    },
]


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
    prompt = pattern["prompt"].replace("{{count}}", str(count))
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
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

    print(f"CIP-0067 content: {len(CIP_CONTENT.get('CIP-0067', ''))} chars")
    print(f"CIP-0068 content: {len(CIP_CONTENT.get('CIP-0068', ''))} chars")
    print(f"bytearray API   : {len(BYTEARRAY_API)} chars")
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
            passed, err = compile_check(code)
            if passed:
                verified.append({
                    "lang":          ex.get("lang", "en"),
                    "instruction":   ex.get("instruction", ""),
                    "input":         ex.get("input", ""),
                    "output":        code,
                    "source":        "cip068_examples",
                    "topic":         f"cip/cip-0068/{p['id']}",
                    "review_status": "VERIFIED_V3_ALIGNED",
                })
                print(f"  ✅ {ex.get('instruction','')[:65]}")
            else:
                err_short = next((l.strip() for l in err.splitlines() if "Error" in l), err[:80])
                print(f"  ❌ {err_short}")
                print(f"     {ex.get('output','')[:200]}")

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
