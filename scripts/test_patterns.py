#!/usr/bin/env python3
"""
test_patterns.py
Compila y testea (aiken check) cada archivo .ak en data/patterns/.
Incluye retry, logs detallados y resumen final.

Usage:
    python3 scripts/test_patterns.py
    python3 scripts/test_patterns.py --patterns data/patterns/
    python3 scripts/test_patterns.py --max-success 300 --retries 3
    python3 scripts/test_patterns.py --pattern dex_swap.ak
"""

import os
import re
import sys
import json
import time
import shutil
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT          = Path(__file__).parent.parent
PATTERNS_DIR  = ROOT / "data" / "patterns"
SANDBOX_DIR   = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE  = SANDBOX_DIR / "validators" / "output.ak"
LOGS_DIR      = ROOT / "logs"
AIKEN_BIN     = os.path.expanduser("~/.aiken/bin/aiken")
AIKEN_CMD     = AIKEN_BIN if os.path.exists(AIKEN_BIN) else "aiken"
TIMEOUT_SECS  = 120  # property tests can be slow


# ─────────────────────────────────────────────────────────────────────────────

def run_aiken_check(code: str, max_success: int = 200) -> dict:
    """Write code to sandbox and run aiken check. Returns result dict."""
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
        # Filter out progress lines
        lines = [l for l in output.splitlines()
                 if not l.strip().startswith("Compiling")
                 and not l.strip().startswith("Downloading")]
        clean = "\n".join(lines).strip()
        return {
            "ok":      result.returncode == 0,
            "output":  clean,
            "elapsed": round(elapsed, 2),
            "timeout": False,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {
            "ok":      False,
            "output":  f"TIMEOUT after {elapsed:.0f}s",
            "elapsed": round(elapsed, 2),
            "timeout": True,
        }
    except FileNotFoundError:
        return {
            "ok":      False,
            "output":  "aiken not found — check PATH",
            "elapsed": 0,
            "timeout": False,
        }


def test_pattern(path: Path, max_success: int, retries: int) -> dict:
    """Test a single pattern file with retries. Returns full result record."""
    code = path.read_text(encoding="utf-8")
    name = path.stem

    # Count expected tests
    unit_tests = re.findall(r'^\s*test\s+\w+\s*\(', code, re.MULTILINE)
    prop_tests = re.findall(r'^\s*test\s+prop_\w+', code, re.MULTILINE)

    attempts = []
    ok = False

    for attempt in range(1, retries + 2):  # retries+1 total attempts
        res = run_aiken_check(code, max_success)
        attempts.append({
            "attempt": attempt,
            "ok":      res["ok"],
            "elapsed": res["elapsed"],
            "timeout": res["timeout"],
            "output":  res["output"],
        })
        if res["ok"]:
            ok = True
            break
        if res["timeout"]:
            # Timeout: retry with reduced max-success
            max_success = max(50, max_success // 2)
        if attempt <= retries:
            time.sleep(1)

    return {
        "name":         name,
        "file":         str(path),
        "ok":           ok,
        "unit_tests":   len(unit_tests),
        "prop_tests":   len(prop_tests),
        "attempts":     len(attempts),
        "attempts_log": attempts,
        "final_output": attempts[-1]["output"],
        "total_elapsed": sum(a["elapsed"] for a in attempts),
    }


def extract_test_summary(output: str) -> str:
    """Pull the test summary lines from aiken output."""
    lines = []
    in_summary = False
    for line in output.splitlines():
        if "passed" in line.lower() or "failed" in line.lower() or "test" in line.lower():
            lines.append(line.strip())
        if line.strip().startswith("Summary"):
            in_summary = True
        if in_summary:
            lines.append(line.strip())
    return " | ".join(l for l in lines[:4] if l)


# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patterns",    default=str(PATTERNS_DIR))
    parser.add_argument("--pattern",     default=None, help="Test only this file")
    parser.add_argument("--max-success", type=int, default=200)
    parser.add_argument("--retries",     type=int, default=2)
    parser.add_argument("--out",         default=None)
    args = parser.parse_args()

    patterns_dir = Path(args.patterns)
    if not patterns_dir.exists():
        print(f"Patterns dir not found: {patterns_dir}")
        sys.exit(1)

    # Collect files
    if args.pattern:
        files = [patterns_dir / args.pattern]
    else:
        files = sorted(patterns_dir.glob("*.ak"))

    if not files:
        print(f"No .ak files found in {patterns_dir}")
        sys.exit(1)

    print(f"{'═'*65}")
    print(f"  PATTERN TEST HARNESS — {len(files)} patterns")
    print(f"  max-success={args.max_success}  retries={args.retries}")
    print(f"{'═'*65}")

    results = []
    passed = 0
    failed = 0

    for i, path in enumerate(files, 1):
        if not path.exists():
            print(f"[{i:2d}/{len(files)}] ⚠️  {path.name} — file not found")
            continue

        print(f"[{i:2d}/{len(files)}] ⏳  {path.stem:<45}", end="", flush=True)
        r = test_pattern(path, args.max_success, args.retries)
        results.append(r)

        symbol = "✅" if r["ok"] else "❌"
        retry_note = f" (retry×{r['attempts']-1})" if r["attempts"] > 1 else ""
        tests_note = f"  unit={r['unit_tests']} prop={r['prop_tests']}"
        print(f"\r[{i:2d}/{len(files)}] {symbol}  {path.stem:<45} {r['total_elapsed']:5.1f}s{retry_note}{tests_note}")

        if r["ok"]:
            passed += 1
        else:
            failed += 1
            # Show first error line
            for line in r["final_output"].splitlines():
                line = line.strip()
                if line and ("error" in line.lower() or "×" in line or "unexpected" in line.lower()):
                    print(f"        ↳ {line[:100]}")
                    break

    # Summary
    print(f"\n{'═'*65}")
    print(f"  Passed : {passed}/{len(results)}")
    print(f"  Failed : {failed}/{len(results)}")
    total_unit = sum(r["unit_tests"] for r in results if r["ok"])
    total_prop  = sum(r["prop_tests"] for r in results if r["ok"])
    print(f"  Tests  : {total_unit} unit + {total_prop} property (passing only)")
    print(f"{'═'*65}")

    if failed:
        print("\nFailed patterns:")
        for r in results:
            if not r["ok"]:
                print(f"  ❌ {r['name']}")
                for line in r["final_output"].splitlines()[:3]:
                    if line.strip():
                        print(f"     {line.strip()[:110]}")

    # Save log
    LOGS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else LOGS_DIR / f"patterns_{ts}.json"
    log = {
        "run_at":      ts,
        "patterns_dir": str(patterns_dir),
        "max_success": args.max_success,
        "retries":     args.retries,
        "passed":      passed,
        "failed":      failed,
        "results":     results,
    }
    out_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nLog → {out_path}")


if __name__ == "__main__":
    main()
