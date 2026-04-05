#!/usr/bin/env python3
"""
eval_benchmark.py — Benchmark v2 evaluation tool

Modes:
  --self-test      Compile-verify all reference solutions in benchmark_v2.json
                   using the local aiken sandbox. Reports pass/fail by category.

  (future)         Run prompts against a live model via LM Studio API and
                   score responses against must_contain / must_not_contain rules.

Usage:
    python3 eval_benchmark.py --self-test
    python3 eval_benchmark.py --self-test --category spend/signature
    python3 eval_benchmark.py --self-test --fail-only
"""

import argparse
import json
import os
import pty
import re
import select
import shutil
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT         = Path(__file__).parent
BENCHMARK    = ROOT / "eval" / "benchmark_v2.json"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
LOGS_DIR     = ROOT / "logs"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 20


# ── Compile helper ────────────────────────────────────────────────────────────

def compile_check(code: str) -> tuple[bool, str]:
    """Run `aiken check` on code in the sandbox. Returns (ok, output_text)."""
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    try:
        master_fd, slave_fd = pty.openpty()
        proc = __import__("subprocess").Popen(
            [AIKEN_BIN, "check", "--max-success", "0"],
            cwd=str(SANDBOX_DIR),
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            close_fds=True,
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


def extract_error(log: str) -> str:
    """Pull first meaningful error line from aiken output."""
    for line in log.splitlines():
        s = line.strip()
        if s and any(k in s.lower() for k in ("error", "×", "unexpected", "unknown", "warning")):
            return s[:100]
    return ""


# ── Self-test mode ────────────────────────────────────────────────────────────

def run_self_test(args):
    if not BENCHMARK.exists():
        print(f"  [ERROR] {BENCHMARK} not found")
        return

    prompts = json.loads(BENCHMARK.read_text(encoding="utf-8"))

    # Optional filters
    if args.category:
        prompts = [p for p in prompts if p["category"] == args.category]
        if not prompts:
            print(f"  [WARN] No entries for category '{args.category}'")
            return

    if args.ids:
        id_set  = set(args.ids.split(","))
        prompts = [p for p in prompts if p.get("id") in id_set]
        if not prompts:
            print(f"  [WARN] No entries matched --ids {args.ids}")
            return

    if args.retest_failed:
        # Find latest selftest log and extract failed IDs
        logs = sorted(LOGS_DIR.glob("benchmark_v2_selftest_*.json"), reverse=True)
        if not logs:
            print("  [WARN] No previous selftest log found — run without --retest-failed first")
            return
        prev = json.loads(logs[0].read_text(encoding="utf-8"))
        failed_ids = {r["id"] for r in prev.get("results", []) if r.get("status") in ("fail", "empty")}
        if not failed_ids:
            print(f"  All entries passed in last run ({logs[0].name}). Nothing to retest.")
            return
        prompts = [p for p in prompts if p.get("id") in failed_ids]
        print(f"  Retesting {len(prompts)} failed entries from {logs[0].name}")

    total = len(prompts)
    print(f"\n{'═'*65}")
    print(f"  eval_benchmark --self-test")
    print(f"  Verifying {total} reference solutions  ({BENCHMARK.name})")
    if args.category:
        print(f"  Filter: category = {args.category}")
    if args.ids:
        print(f"  Filter: ids = {args.ids}")
    print(f"  Aiken: {AIKEN_BIN}")
    print(f"{'═'*65}\n")

    results   = []
    by_cat    = defaultdict(lambda: {"pass": 0, "fail": 0})
    passed    = 0
    failed    = 0

    for idx, entry in enumerate(prompts, 1):
        pid      = entry.get("id", f"?{idx}")
        cat      = entry.get("category", "?")
        code     = entry.get("reference_solution", "")
        short_id = pid[:50]

        print(f"  [{idx:3d}/{total}] {short_id:<52}", end=" ", flush=True)

        if not code.strip():
            print("⚠️  empty")
            results.append({"id": pid, "category": cat, "status": "empty"})
            by_cat[cat]["fail"] += 1
            failed += 1
            continue

        ok, log = compile_check(code)

        if ok:
            print("✅")
            results.append({"id": pid, "category": cat, "status": "pass"})
            by_cat[cat]["pass"] += 1
            passed += 1
        else:
            err = extract_error(log)
            print(f"❌  {err[:55]}")
            results.append({"id": pid, "category": cat, "status": "fail", "error": err, "log": log})
            by_cat[cat]["fail"] += 1
            failed += 1

        time.sleep(0.05)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*65}")
    print(f"  TOTAL:  {passed}/{total} pass  ({100*passed//total}%)   {failed} fail")
    print(f"{'═'*65}")

    print(f"\n  By category:")
    for cat in sorted(by_cat):
        p = by_cat[cat]["pass"]
        f = by_cat[cat]["fail"]
        n = p + f
        bar = "✅" * p + "❌" * f
        pct = 100 * p // n if n else 0
        print(f"    {cat:<35}  {p:3d}/{n}  ({pct:3d}%)  {bar}")

    if failed and not args.fail_only:
        print(f"\n  Failed entries:")
        for r in results:
            if r["status"] in ("fail", "empty"):
                print(f"    ❌ [{r['id']}]  {r.get('error', 'empty')[:80]}")

    if args.fail_only:
        print(f"\n  Failed entries:")
        for r in results:
            if r["status"] in ("fail", "empty"):
                print(f"    ❌ [{r['id']}]")
                if r.get("error"):
                    print(f"       {r['error']}")

    # ── Save log ──────────────────────────────────────────────────────────────
    LOGS_DIR.mkdir(exist_ok=True)
    ts       = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOGS_DIR / f"benchmark_v2_selftest_{ts}.json"

    # Omit full 'log' field from summary file to keep it small; keep 'error' only
    slim = [{k: v for k, v in r.items() if k != "log"} for r in results]
    log_path.write_text(json.dumps({
        "run_at":   ts,
        "total":    total,
        "passed":   passed,
        "failed":   failed,
        "by_category": {k: v for k, v in by_cat.items()},
        "results":  slim,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n  Log → {log_path.name}")
    print(f"{'═'*65}\n")

    return passed, failed


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark v2 evaluation — reference solution auditor + model scorer"
    )
    sub = parser.add_subparsers(dest="mode")

    # --self-test as a flag (not subcommand) for convenience
    parser.add_argument("--self-test",   action="store_true",
                        help="Compile-verify all reference solutions")
    parser.add_argument("--category",       type=str, default=None,
                        help="Filter to a single category (e.g. spend/signature)")
    parser.add_argument("--ids",            type=str, default=None,
                        help="Comma-separated list of IDs to test (e.g. withdraw_02,withdraw_09)")
    parser.add_argument("--retest-failed",  action="store_true",
                        help="Read latest selftest log and retest only the failed entries")
    parser.add_argument("--fail-only",      action="store_true",
                        help="Only show failed entries in final report")

    args = parser.parse_args()

    if args.self_test:
        run_self_test(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
