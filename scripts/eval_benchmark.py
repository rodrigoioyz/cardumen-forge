#!/usr/bin/env python3
"""
eval_benchmark.py — Evaluate model outputs against benchmark_v2.json

Usage:
  python scripts/eval_benchmark.py --self-test
  python scripts/eval_benchmark.py --results path/to/outputs.jsonl
  python scripts/eval_benchmark.py --self-test --category spend/signature --n 20
"""

import argparse
import json
import os
import pty
import re
import select
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT      = Path(__file__).resolve().parent.parent
BENCHMARK      = REPO_ROOT / "eval" / "benchmark_v2.json"
SANDBOX_DIR    = REPO_ROOT / "eval" / "aiken_sandbox"
VALIDATOR_FILE = SANDBOX_DIR / "validators" / "output.ak"
LOGS_DIR       = REPO_ROOT / "logs"
ANSI           = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN      = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")


def compile_check(code: str, timeout: int = 30) -> tuple[bool, str]:
    VALIDATOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    VALIDATOR_FILE.write_text(code, encoding="utf-8")
    import subprocess
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        [AIKEN_BIN, "check", "--max-success", "0"],
        cwd=str(SANDBOX_DIR),
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)
    buf = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        r, _, _ = select.select([master_fd], [], [], 0.5)
        if r:
            try:
                chunk = os.read(master_fd, 4096).decode("utf-8", errors="replace")
                buf.append(chunk)
            except OSError:
                break
        if proc.poll() is not None:
            break
    proc.wait(timeout=5)
    os.close(master_fd)
    clean = ANSI.sub("", "".join(buf))
    return proc.returncode == 0, clean


def string_match_check(output: str, must_contain: list, must_not_contain: list) -> tuple[bool, list]:
    failures = []
    for s in must_contain:
        if s not in output:
            failures.append(f"missing: {s!r}")
    for s in must_not_contain:
        if s in output:
            failures.append(f"forbidden: {s!r}")
    return len(failures) == 0, failures


def extract_code(output: str) -> str:
    for pattern in [r"```aiken\s*\n(.*?)```", r"```\s*\n(.*?)```"]:
        m = re.search(pattern, output, re.DOTALL)
        if m:
            return m.group(1).strip()
    return output.strip()


def load_benchmark(category=None, n=None):
    with open(BENCHMARK, encoding="utf-8") as f:
        data = json.load(f)
    if category:
        data = [ex for ex in data if ex.get("category", "") == category]
    if n:
        data = data[:n]
    return data


def load_results(path: str) -> dict:
    results = {}
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "id" in obj:
                    results[obj["id"]] = obj.get("output", "")
            except json.JSONDecodeError as e:
                print(f"  [WARN] line {i}: {e}", file=sys.stderr)
    return results


def run_eval(benchmark, results_map, self_test, verbose=True):
    all_results = []
    cat_stats   = {}
    total       = len(benchmark)

    for idx, ex in enumerate(benchmark, 1):
        ex_id    = ex["id"]
        cat      = ex.get("category", "unknown")
        must     = ex.get("must_contain", [])
        must_not = ex.get("must_not_contain", [])

        raw = ex.get("reference_solution", "") if self_test else results_map.get(ex_id, "")
        code = extract_code(raw)

        str_ok, str_failures = string_match_check(raw, must, must_not)
        cmp_ok, cmp_log = compile_check(code) if code else (False, "[no code]")
        score = 2 if (str_ok and cmp_ok) else (1 if (str_ok or cmp_ok) else 0)

        if cat not in cat_stats:
            cat_stats[cat] = {"string": 0, "compile": 0, "score_sum": 0, "total": 0}
        cat_stats[cat]["total"]     += 1
        cat_stats[cat]["string"]    += int(str_ok)
        cat_stats[cat]["compile"]   += int(cmp_ok)
        cat_stats[cat]["score_sum"] += score

        all_results.append({
            "id": ex_id, "category": cat,
            "string_ok": str_ok, "compile_ok": cmp_ok, "score": score,
            "string_failures": str_failures,
            "compile_log": cmp_log if not cmp_ok else "",
        })

        if verbose:
            ss = "✅" if str_ok else "❌"
            cs = "✅" if cmp_ok else "❌"
            print(f"  [{idx:>3}/{total}] {ex_id:<35} string={ss}  compile={cs}  score={score}")
            for f in str_failures:
                print(f"              string fail: {f}")
            if not cmp_ok and cmp_log not in ("[no code]", "[timeout]", ""):
                for line in cmp_log.splitlines():
                    if line.strip() and "error" in line.lower():
                        print(f"              compile: {line.strip()[:120]}")
                        break

    return all_results, cat_stats


def print_report(all_results, cat_stats, total):
    str_total = sum(1 for r in all_results if r["string_ok"])
    cmp_total = sum(1 for r in all_results if r["compile_ok"])
    score_sum = sum(r["score"] for r in all_results)
    max_score = total * 2

    print()
    print("=" * 72)
    print("RESULTS BY CATEGORY")
    print(f"  {'Category':<30} {'N':>4}  {'String':>12}  {'Compile':>12}  {'Avg':>6}")
    print("  " + "-" * 68)
    for cat in sorted(cat_stats):
        s  = cat_stats[cat]
        n  = s["total"]
        sp = 100 * s["string"]    / n
        cp = 100 * s["compile"]   / n
        av = s["score_sum"] / n
        print(f"  {cat:<30} {n:>4}  {s['string']:>3}/{n:<3}({sp:>5.1f}%)  {s['compile']:>3}/{n:<3}({cp:>5.1f}%)  {av:.2f}")
    print("  " + "-" * 68)
    sp = 100 * str_total / total
    cp = 100 * cmp_total / total
    av = score_sum / total
    print(f"  {'TOTAL':<30} {total:>4}  {str_total:>3}/{total:<3}({sp:>5.1f}%)  {cmp_total:>3}/{total:<3}({cp:>5.1f}%)  {av:.2f}")
    print()
    print(f"string={str_total}/{total} ({sp:.1f}%)  compile={cmp_total}/{total} ({cp:.1f}%)  score={score_sum}/{max_score} ({100*score_sum/max_score:.1f}%)")
    print("=" * 72)


def save_results(all_results, cat_stats, args):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = LOGS_DIR / f"eval_results_{ts}.json"
    total     = len(all_results)
    str_total = sum(1 for r in all_results if r["string_ok"])
    cmp_total = sum(1 for r in all_results if r["compile_ok"])
    score_sum = sum(r["score"] for r in all_results)
    payload = {
        "meta": {
            "timestamp": ts, "self_test": getattr(args, "self_test", False),
            "results_file": getattr(args, "results", None),
            "category_filter": getattr(args, "category", None),
            "n_filter": getattr(args, "n", None),
            "total": total, "string_pass": str_total,
            "compile_pass": cmp_total, "score_sum": score_sum, "max_score": total * 2,
        },
        "by_category": cat_stats,
        "examples": all_results,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--results",   metavar="PATH")
    mode.add_argument("--self-test", action="store_true")
    parser.add_argument("--category", default=None)
    parser.add_argument("--n",        type=int, default=None)
    parser.add_argument("--quiet",    action="store_true")
    parser.add_argument("--no-save",  action="store_true")
    args = parser.parse_args()

    benchmark = load_benchmark(category=args.category, n=args.n)
    if not benchmark:
        sys.exit("[ERROR] No examples loaded")

    print(f"\n{'═'*60}")
    print(f"  eval_benchmark — {len(benchmark)} prompts")
    if args.self_test: print(f"  mode: self-test (reference_solution)")
    else:              print(f"  mode: --results {args.results}")
    print(f"{'═'*60}\n")

    results_map = {} if args.self_test else load_results(args.results)

    all_results, cat_stats = run_eval(benchmark, results_map, args.self_test, not args.quiet)
    print_report(all_results, cat_stats, len(benchmark))

    if not args.no_save:
        out = save_results(all_results, cat_stats, args)
        print(f"\nResults → {out}")


if __name__ == "__main__":
    main()
