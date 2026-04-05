#!/usr/bin/env python3
"""
patterns_to_dataset.py — Cardumen Forge
Runs aiken check on every .ak in data/patterns/.
Files that compile + pass all fuzz tests are converted to dataset examples
and written to data/processed/components/patterns_verified.jsonl.

Usage:
    python3 scripts/patterns_to_dataset.py
    python3 scripts/patterns_to_dataset.py --dry-run
    python3 scripts/patterns_to_dataset.py --pattern 16b_lp_min_deposit.ak
    python3 scripts/patterns_to_dataset.py --max-success 300
    python3 scripts/patterns_to_dataset.py --append-to data/processed/dataset_v23.jsonl
"""

import os
import re
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT         = Path(__file__).parent.parent
PATTERNS_DIR = ROOT / "data" / "patterns"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
OUT_DEFAULT  = ROOT / "data" / "processed" / "components" / "patterns_verified.jsonl"
LOGS_DIR     = ROOT / "logs"
AIKEN_BIN    = os.path.expanduser("~/.aiken/bin/aiken")
AIKEN_CMD    = AIKEN_BIN if os.path.exists(AIKEN_BIN) else "aiken"
TIMEOUT_SECS = 120

# ── Numeric prefix → topic category ──────────────────────────────────────────

CATEGORY_MAP = {
    "1":  "cardano/basics",
    "2":  "cardano/assets",
    "3":  "cardano/transaction",
    "4":  "cardano/validators",
    "5":  "aiken/collection/list",
    "6":  "aiken/collection/dict",
    "7":  "aiken/arithmetic",
    "8":  "aiken/crypto",
    "9":  "aiken/interval",
    "10": "cardano/address",
    "11": "cardano/certificates",
    "12": "cardano/governance",
    "13": "design_pattern/state_machine",
    "14": "design_pattern/cip68",
    "15": "design_pattern/reference_inputs",
    "16": "design_pattern/amm_lp",
    "17": "design_pattern/auction",
    "18": "design_pattern/vault",
    "19": "design_pattern/parameterized_vault",
    "20": "design_pattern/stablecoin",
    "21": "design_pattern/order_book",
    "22": "design_pattern/thread_nft",
    "23": "design_pattern/batch_swap",
    "24": "design_pattern/vesting",
    "25": "design_pattern/liquidation",
}

def topic_for(stem: str) -> str:
    """Derive topic string from file stem like '16b_lp_min_deposit'."""
    m = re.match(r'^(\d+)', stem)
    if m:
        cat = CATEGORY_MAP.get(m.group(1), "aiken/property_test")
        return f"property_test/{cat}"
    return "property_test/aiken"


# ── Instruction extraction ────────────────────────────────────────────────────

def extract_instruction(code: str, stem: str) -> str:
    """
    Use the first /// doc-comment block as the instruction base.
    Fall back to a generated description from the filename.
    """
    lines = code.splitlines()
    doc_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("///"):
            doc_lines.append(stripped[3:].strip())
        elif doc_lines:
            break  # stop at first non-doc line after we started collecting

    if doc_lines:
        text = " ".join(doc_lines).strip()
        if not text.endswith((".", "?", "!")):
            text += "."
        return f"Write an Aiken v3 property-based test module: {text}"

    # Fallback: humanize the stem
    # "16b_lp_min_deposit" → "lp min deposit"
    label = re.sub(r'^\d+[a-z]?_', '', stem).replace('_', ' ')
    return f"Write an Aiken v3 property-based test module for: {label}."


# ── Aiken sandbox runner ──────────────────────────────────────────────────────

def run_aiken_check(code: str, max_success: int) -> dict:
    SANDBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    start = time.time()
    try:
        result = subprocess.run(
            [AIKEN_CMD, "check", f"--max-success={max_success}"],
            cwd=SANDBOX_DIR,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECS,
        )
        elapsed = time.time() - start
        output = (result.stdout + result.stderr).strip()
        lines = [l for l in output.splitlines()
                 if not l.strip().startswith(("Compiling", "Downloading"))]
        return {
            "ok":      result.returncode == 0,
            "output":  "\n".join(lines).strip(),
            "elapsed": round(elapsed, 2),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"TIMEOUT after {TIMEOUT_SECS}s", "elapsed": TIMEOUT_SECS}
    except FileNotFoundError:
        return {"ok": False, "output": "aiken not found — check PATH", "elapsed": 0}


# ── Build one dataset record ──────────────────────────────────────────────────

def build_record(path: Path) -> dict:
    code = path.read_text(encoding="utf-8")
    return {
        "instruction":   extract_instruction(code, path.stem),
        "input":         "",
        "output":        code,
        "source":        "fuzz_patterns_v3",
        "topic":         topic_for(path.stem),
        "review_status": "VERIFIED_FUZZ_PASS",
        "lang":          "en",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patterns",    default=str(PATTERNS_DIR))
    parser.add_argument("--pattern",     default=None, help="Test only this file")
    parser.add_argument("--max-success", type=int, default=200)
    parser.add_argument("--out",         default=str(OUT_DEFAULT))
    parser.add_argument("--append-to",   default=None,
                        help="Append passing examples directly to this dataset file")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Run checks but don't write anything")
    args = parser.parse_args()

    patterns_dir = Path(args.patterns)
    if not patterns_dir.exists():
        print(f"Patterns dir not found: {patterns_dir}")
        sys.exit(1)

    if args.pattern:
        files = [patterns_dir / args.pattern]
    else:
        files = sorted(patterns_dir.glob("*.ak"))

    if not files:
        print(f"No .ak files in {patterns_dir}")
        sys.exit(1)

    print(f"\n{'═'*65}")
    print(f"  patterns_to_dataset — {len(files)} files")
    print(f"  max-success={args.max_success}  dry-run={args.dry_run}")
    print(f"{'═'*65}\n")

    passing  = []
    failing  = []

    for i, path in enumerate(files, 1):
        if not path.exists():
            print(f"[{i:3d}/{len(files)}] ⚠️  {path.name} — not found, skipped")
            continue

        print(f"[{i:3d}/{len(files)}] ⏳  {path.stem:<50}", end="", flush=True)
        res = run_aiken_check(path.read_text(encoding="utf-8"), args.max_success)

        symbol = "✅" if res["ok"] else "❌"
        print(f"\r[{i:3d}/{len(files)}] {symbol}  {path.stem:<50} {res['elapsed']:5.1f}s")

        if res["ok"]:
            passing.append(build_record(path))
        else:
            failing.append({"file": path.name, "error": res["output"][:300]})
            for line in res["output"].splitlines():
                s = line.strip()
                if s and any(kw in s.lower() for kw in ("error", "×", "unexpected", "unknown")):
                    print(f"        ↳ {s[:110]}")
                    break

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*65}")
    print(f"  Passed : {len(passing)}/{len(files)}")
    print(f"  Failed : {len(failing)}/{len(files)}")
    print(f"{'═'*65}")

    if failing:
        print("\nFailed files:")
        for f in failing:
            print(f"  ❌ {f['file']}")

    if args.dry_run:
        print("\n  (dry-run — nothing written)")
        return

    if not passing:
        print("\n  Nothing to write.")
        return

    # ── Write component file ──────────────────────────────────────────────────
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in passing:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\n  Component → {out_path} ({len(passing)} examples)")

    # ── Optionally append to a dataset ───────────────────────────────────────
    if args.append_to:
        dest = Path(args.append_to)
        if not dest.exists():
            print(f"  ⚠️  --append-to target not found: {dest}")
        else:
            # Dedup: collect existing outputs to avoid exact duplicates
            existing_outputs = set()
            with open(dest, encoding="utf-8") as f:
                for line in f:
                    try:
                        existing_outputs.add(json.loads(line)["output"])
                    except Exception:
                        pass

            new_records = [r for r in passing if r["output"] not in existing_outputs]
            dupes = len(passing) - len(new_records)

            if new_records:
                with open(dest, "a", encoding="utf-8") as f:
                    for rec in new_records:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"  Appended → {dest} (+{len(new_records)} new, {dupes} dupes skipped)")
            else:
                print(f"  All {len(passing)} examples already present in {dest.name} — nothing appended")

    # ── Save failure log ──────────────────────────────────────────────────────
    if failing:
        LOGS_DIR.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = LOGS_DIR / f"patterns_to_dataset_failures_{ts}.json"
        log_path.write_text(json.dumps({"run_at": ts, "failures": failing}, indent=2), encoding="utf-8")
        print(f"  Failure log → {log_path}")


if __name__ == "__main__":
    main()
