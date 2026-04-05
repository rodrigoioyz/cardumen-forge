#!/usr/bin/env python3
"""
audit_plausible.py — Compile-verify PLAUSIBLE_NEEDS_CHECK examples in dataset_v23.jsonl

For each PLAUSIBLE example, runs `aiken check` on its output field.
Produces a report and optionally updates review_status in-place.

Usage:
    python3 scripts/audit_plausible.py --dry-run     # report only, no changes
    python3 scripts/audit_plausible.py               # report only (safe default)
    python3 scripts/audit_plausible.py --fix         # update status in dataset
"""

import argparse
import json
import os
import pty
import re
import select
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT         = Path(__file__).parent.parent
DATASET      = ROOT / "data" / "processed" / "dataset_v23.jsonl"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
LOGS_DIR     = ROOT / "logs"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 20


def compile_check(code: str) -> tuple[bool, str]:
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    try:
        master_fd, slave_fd = pty.openpty()
        proc = __import__("subprocess").Popen(
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Report only — do not modify dataset")
    parser.add_argument("--fix", action="store_true",
                        help="Update review_status in dataset for passing examples")
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print(f"  audit_plausible — PLAUSIBLE_NEEDS_CHECK examples")
    print(f"  dataset: {DATASET.name}")
    if args.fix:
        print(f"  mode: --fix (will update review_status for passing examples)")
    else:
        print(f"  mode: report only (use --fix to update dataset)")
    print(f"{'═'*60}\n")

    # Load all examples
    examples = []
    with DATASET.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))

    plausible = [(i, ex) for i, ex in enumerate(examples)
                 if ex.get("review_status") == "PLAUSIBLE_NEEDS_CHECK"]

    print(f"  Found {len(plausible)} PLAUSIBLE_NEEDS_CHECK examples\n")

    if not plausible:
        print("  Nothing to audit.")
        return

    results = []
    for idx, (i, ex) in enumerate(plausible, 1):
        code = ex.get("output", "")
        topic = ex.get("topic", "?")[:50]
        print(f"  [{idx:2d}/{len(plausible)}] {topic:<50}", end=" ", flush=True)

        if not code.strip():
            print("⚠️  empty output")
            results.append({"index": i, "topic": ex.get("topic"), "status": "empty"})
            continue

        ok, log = compile_check(code)
        if ok:
            print("✅")
            results.append({"index": i, "topic": ex.get("topic"), "status": "pass"})
            if args.fix:
                examples[i]["review_status"] = "VERIFIED_V3_ALIGNED"
        else:
            err = next((l.strip() for l in log.splitlines()
                        if l.strip() and any(k in l.lower() for k in ("error", "×", "unexpected", "unknown"))), "")
            print(f"❌  {err[:60]}")
            results.append({"index": i, "topic": ex.get("topic"), "status": "fail", "error": err})

        time.sleep(0.1)

    # Summary
    passed  = sum(1 for r in results if r["status"] == "pass")
    failed  = sum(1 for r in results if r["status"] == "fail")
    empty   = sum(1 for r in results if r["status"] == "empty")

    print(f"\n{'═'*60}")
    print(f"  Results: {passed} pass  {failed} fail  {empty} empty")
    print(f"{'═'*60}")

    if failed:
        print(f"\n  Failed examples:")
        for r in results:
            if r["status"] == "fail":
                print(f"    ❌ [{r['index']}] {r['topic']}")
                if r.get("error"):
                    print(f"       {r['error'][:80]}")

    # Write updated dataset if --fix
    if args.fix and passed > 0:
        with DATASET.open("w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"\n  ✅ Updated {passed} examples to VERIFIED_V3_ALIGNED in {DATASET.name}")

    # Save log
    LOGS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOGS_DIR / f"plausible_audit_{ts}.json"
    log_path.write_text(json.dumps({
        "run_at": ts, "total": len(plausible),
        "passed": passed, "failed": failed, "empty": empty,
        "results": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Log → {log_path}")


if __name__ == "__main__":
    main()
