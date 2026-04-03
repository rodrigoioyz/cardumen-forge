#!/usr/bin/env python3
"""
audit_dataset_compile.py — Cardumen Forge
Compiles a sample of dataset examples through the aiken sandbox and reports
how many pass `aiken check`. Reuses the PTY compile_check logic from benchmark.py.

Usage:
    python3 scripts/audit_dataset_compile.py                     # 300 random examples
    python3 scripts/audit_dataset_compile.py --sample 100        # smaller sample
    python3 scripts/audit_dataset_compile.py --all               # full dataset (slow)
    python3 scripts/audit_dataset_compile.py --source aiken_stdlib  # filter by source
    python3 scripts/audit_dataset_compile.py --sample 300 --out logs/compile_audit.json
"""

import os
import re
import sys
import json
import time
import argparse
import random
import subprocess
from pathlib import Path
from collections import defaultdict

ROOT             = Path(__file__).parent.parent
DATASET_PATH     = ROOT / "data" / "processed" / "dataset_v22.jsonl"
SANDBOX_DIR      = ROOT / "eval" / "aiken_sandbox"
SANDBOX_VALIDATOR = SANDBOX_DIR / "validators" / "output.ak"
DEFAULT_SAMPLE   = 300
TIMEOUT_SECS     = 30


# ─────────────────────────────────────────────────────────────────────────────
# PTY compile_check — copied from benchmark.py
# ─────────────────────────────────────────────────────────────────────────────

def compile_check(code: str) -> dict:
    """Run aiken check on code via PTY sandbox. Returns {pass, skipped, error}."""
    if not (SANDBOX_DIR / "aiken.toml").exists():
        return {"pass": None, "skipped": True, "error": "sandbox not found"}

    SANDBOX_VALIDATOR.parent.mkdir(parents=True, exist_ok=True)
    SANDBOX_VALIDATOR.write_text(code, encoding="utf-8")

    try:
        import pty, select

        master_fd, slave_fd = pty.openpty()
        aiken_bin = os.path.expanduser("~/.aiken/bin/aiken")
        aiken_cmd = aiken_bin if os.path.exists(aiken_bin) else "aiken"
        proc = subprocess.Popen(
            [aiken_cmd, "check"],
            cwd=SANDBOX_DIR,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            env={**os.environ, "TERM": "xterm-256color", "COLUMNS": "200"},
        )
        os.close(slave_fd)

        chunks = []
        deadline = time.time() + TIMEOUT_SECS
        while time.time() < deadline:
            try:
                r_list, _, _ = select.select([master_fd], [], [], 0.2)
                if r_list:
                    data = os.read(master_fd, 4096)
                    chunks.append(data)
                elif proc.poll() is not None:
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
# Load dataset
# ─────────────────────────────────────────────────────────────────────────────

def load_dataset(path: Path, source_filter: str = None) -> list:
    examples = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ex = json.loads(line)
            if source_filter and ex.get("source") != source_filter:
                continue
            if ex.get("output", "").strip():
                examples.append(ex)
    return examples


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(DATASET_PATH), help="Path to JSONL dataset")
    parser.add_argument("--sample",  type=int, default=DEFAULT_SAMPLE, help="Number of examples to sample")
    parser.add_argument("--all",     action="store_true", help="Run on full dataset (slow)")
    parser.add_argument("--source",  default=None, help="Filter by source field")
    parser.add_argument("--seed",    type=int, default=42, help="Random seed for sampling")
    parser.add_argument("--out",     default=None, help="Save results to JSON file")
    parser.add_argument("--verbose", action="store_true", help="Print errors for failing examples")
    args = parser.parse_args()

    # Validate sandbox
    if not (SANDBOX_DIR / "aiken.toml").exists():
        print(f"❌ Sandbox not found at {SANDBOX_DIR}")
        print("   Run: aiken new eval/aiken_sandbox && aiken check eval/aiken_sandbox")
        sys.exit(1)

    # Load
    dataset_path = Path(args.dataset)
    examples = load_dataset(dataset_path, source_filter=args.source)
    print(f"Loaded  : {len(examples)} examples from {dataset_path.name}"
          + (f" (source={args.source})" if args.source else ""))

    # Sample
    if args.all:
        sample = examples
    else:
        n = min(args.sample, len(examples))
        random.seed(args.seed)
        sample = random.sample(examples, n)

    print(f"Sample  : {len(sample)} examples (seed={args.seed})")
    print(f"Sandbox : {SANDBOX_DIR}")
    print()

    # Audit
    results = []
    passed = 0
    failed = 0
    skipped = 0

    by_source  = defaultdict(lambda: {"pass": 0, "fail": 0})
    by_status  = defaultdict(lambda: {"pass": 0, "fail": 0})

    for i, ex in enumerate(sample, 1):
        code   = ex.get("output", "").strip()
        source = ex.get("source", "unknown")
        status = ex.get("review_status", "unknown")
        instr  = ex.get("instruction", "")[:60]

        result = compile_check(code)

        if result["skipped"]:
            skipped += 1
            symbol = "⚠"
        elif result["pass"]:
            passed += 1
            symbol = "✅"
            by_source[source]["pass"] += 1
            by_status[status]["pass"]  += 1
        else:
            failed += 1
            symbol = "❌"
            by_source[source]["fail"] += 1
            by_status[status]["fail"]  += 1

        total_done = passed + failed + skipped
        pct = 100 * passed / max(1, passed + failed)
        print(f"[{i:4d}/{len(sample)}] {symbol}  {source:<25} | {instr}")

        if args.verbose and not result["pass"] and not result["skipped"]:
            # Show first signal line of error
            error_lines = [l for l in result["error"].splitlines()
                           if any(k in l for k in ["error", "Error", "×", "─"])]
            if error_lines:
                print(f"          {error_lines[0].strip()[:120]}")

        results.append({
            "index":          i,
            "source":         source,
            "review_status":  status,
            "instruction":    ex.get("instruction", "")[:120],
            "compile_pass":   result["pass"],
            "skipped":        result["skipped"],
            "error_summary":  result["error"][:300] if not result["pass"] else "",
        })

    # ── Summary ──────────────────────────────────────────────────────────────
    total_compiled = passed + failed
    print()
    print("═" * 60)
    print(f"  COMPILE AUDIT — {dataset_path.name}")
    print("═" * 60)
    print(f"  Sample     : {len(sample)}")
    print(f"  Compiled   : {total_compiled}  (skipped: {skipped})")
    print(f"  Pass       : {passed}  ({100*passed/max(1,total_compiled):.1f}%)")
    print(f"  Fail       : {failed}  ({100*failed/max(1,total_compiled):.1f}%)")
    print()

    if by_source:
        print("  By source:")
        for src, counts in sorted(by_source.items(), key=lambda x: -(x[1]["pass"]+x[1]["fail"])):
            total = counts["pass"] + counts["fail"]
            pct   = 100 * counts["pass"] / max(1, total)
            bar   = "█" * int(pct / 5)
            print(f"    {src:<30} {counts['pass']:3d}/{total:3d}  ({pct:5.1f}%)  {bar}")

    print()
    if by_status:
        print("  By review_status:")
        for st, counts in sorted(by_status.items(), key=lambda x: -(x[1]["pass"]+x[1]["fail"])):
            total = counts["pass"] + counts["fail"]
            pct   = 100 * counts["pass"] / max(1, total)
            print(f"    {st:<35} {counts['pass']:3d}/{total:3d}  ({pct:5.1f}%)")

    print("═" * 60)

    # ── Save ─────────────────────────────────────────────────────────────────
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "dataset":       str(dataset_path),
            "sample_size":   len(sample),
            "seed":          args.seed,
            "source_filter": args.source,
            "passed":        passed,
            "failed":        failed,
            "skipped":       skipped,
            "pass_rate":     round(passed / max(1, total_compiled), 4),
            "by_source":     {k: v for k, v in by_source.items()},
            "by_status":     {k: v for k, v in by_status.items()},
            "results":       results,
        }
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    main()
