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
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

ROOT             = Path(__file__).parent.parent
DATASET_PATH     = ROOT / "data" / "processed" / "dataset_v23.jsonl"
SANDBOX_DIR      = ROOT / "eval" / "aiken_sandbox"
SANDBOX_VALIDATOR = SANDBOX_DIR / "validators" / "output.ak"
DEFAULT_SAMPLE   = 300
TIMEOUT_SECS     = 30


# ─────────────────────────────────────────────────────────────────────────────
# PTY compile_check — copied from benchmark.py
# ─────────────────────────────────────────────────────────────────────────────

def has_test_blocks(code: str) -> bool:
    """Retorna True si el código contiene al menos un bloque test."""
    return bool(re.search(r'^\s*test\s+\w+\s*\(', code, re.MULTILINE))


def is_aiken_code(code: str) -> bool:
    """
    Retorna True si el output es código Aiken compilable.
    Filtra ejemplos de documentación en texto o markdown con code fences.
    Un ejemplo es código si tiene validator, fn standalone, o pub type sin markdown.
    """
    if '```' in code:
        return False
    # Markdown bold markers = explanation text, not pure code
    if '**' in code:
        return False
    # First non-empty line must look like Aiken (not prose)
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('//'):
            continue
        # If first meaningful line is not an Aiken top-level construct, it's docs
        if not re.match(r'^(use |pub |fn |validator |test |type )', stripped):
            return False
        break
    return bool(
        re.search(r'^(use |pub fn|pub type|validator )', code, re.MULTILINE)
    )


def _run_aiken(command: str) -> dict:
    """Ejecuta aiken check o aiken test en el sandbox. Retorna {pass, skipped, error}."""
    if not (SANDBOX_DIR / "aiken.toml").exists():
        return {"pass": None, "skipped": True, "error": "sandbox not found"}

    try:
        import pty, select

        master_fd, slave_fd = pty.openpty()
        aiken_bin = os.path.expanduser("~/.aiken/bin/aiken")
        aiken_cmd = aiken_bin if os.path.exists(aiken_bin) else "aiken"
        proc = subprocess.Popen(
            [aiken_cmd, command],
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
        return {"pass": None, "skipped": True, "error": f"aiken {command} error: {e}"}


def compile_check(code: str) -> dict:
    """
    Corre aiken check — en v1.1.21 este comando compila Y ejecuta los bloques test
    en un solo paso. No existe 'aiken test' como subcomando separado.
    El resultado de test_pass se infiere del mismo returncode de check.
    """
    SANDBOX_VALIDATOR.parent.mkdir(parents=True, exist_ok=True)
    SANDBOX_VALIDATOR.write_text(code, encoding="utf-8")

    check_result = _run_aiken("check")
    has_tests = has_test_blocks(code)

    return {
        **check_result,
        "test_run":  has_tests,
        "test_pass": check_result["pass"] if has_tests else None,
    }


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
    results      = []
    check_passed = 0
    check_failed = 0
    skipped      = 0
    not_code     = 0
    test_ran     = 0
    test_passed  = 0
    test_failed  = 0

    by_source = defaultdict(lambda: {"check_pass": 0, "check_fail": 0, "test_pass": 0, "test_fail": 0, "not_code": 0})
    by_status = defaultdict(lambda: {"check_pass": 0, "check_fail": 0})

    for i, ex in enumerate(sample, 1):
        code      = ex.get("output", "").strip()
        source    = ex.get("source", "unknown")
        status    = ex.get("review_status", "unknown")
        instr     = ex.get("instruction", "")[:60]
        has_tests = has_test_blocks(code)

        # Saltar ejemplos de documentación en texto
        if not is_aiken_code(code):
            not_code += 1
            by_source[source]["not_code"] += 1
            print(f"[{i:4d}/{len(sample)}] 📄  {source:<25} | {instr}")
            results.append({
                "index": i, "source": source, "review_status": status,
                "instruction": ex.get("instruction", ""),
                "is_code": False, "check_pass": None, "test_run": False,
                "test_pass": None, "skipped": False, "error": "",
                "output": "",
            })
            continue

        result = compile_check(code)

        if result["skipped"]:
            skipped += 1
            symbol = "⚠ "
        elif result["pass"]:
            check_passed += 1
            by_source[source]["check_pass"] += 1
            by_status[status]["check_pass"]  += 1
            if result["test_run"]:
                test_ran += 1
                if result["test_pass"]:
                    test_passed += 1
                    by_source[source]["test_pass"] += 1
                    symbol = "✅T"
                else:
                    test_failed += 1
                    by_source[source]["test_fail"] += 1
                    symbol = "❌T"
            else:
                symbol = "✅ "
        else:
            check_failed += 1
            by_source[source]["check_fail"] += 1
            by_status[status]["check_fail"]  += 1
            symbol = "❌ "

        print(f"[{i:4d}/{len(sample)}] {symbol}  {source:<25} | {instr}")

        if args.verbose and not result["pass"] and not result["skipped"]:
            error_lines = [l for l in result["error"].splitlines()
                           if any(k in l for k in ["error", "Error", "×", "─", "FAILED"])]
            if error_lines:
                print(f"          {error_lines[0].strip()[:120]}")

        failed = not result["skipped"] and not result["pass"]
        results.append({
            "index":         i,
            "source":        source,
            "review_status": status,
            "instruction":   ex.get("instruction", ""),
            "is_code":       True,
            "has_tests":     has_tests,
            "check_pass":    result["pass"] if not result["skipped"] else None,
            "test_run":      result.get("test_run", False),
            "test_pass":     result.get("test_pass"),
            "skipped":       result["skipped"],
            "error":         result["error"] if failed else "",
            "output":        code if failed else "",
        })

    # ── Summary ──────────────────────────────────────────────────────────────
    total_checked = check_passed + check_failed
    print()
    print("═" * 65)
    print(f"  COMPILE + TEST AUDIT — {dataset_path.name}")
    print("═" * 65)
    print(f"  Sample          : {len(sample)}")
    print(f"  Documentación   : {not_code:4d}  (texto — no se compila)")
    print(f"  Código Aiken    : {total_checked + skipped:4d}  (skipped: {skipped})")
    print(f"  aiken check")
    print(f"    Pass          : {check_passed:4d} / {total_checked}  ({100*check_passed/max(1,total_checked):.1f}%)")
    print(f"    Fail          : {check_failed:4d} / {total_checked}  ({100*check_failed/max(1,total_checked):.1f}%)")
    print(f"  aiken test  (solo ejemplos con bloques test)")
    print(f"    Ran           : {test_ran:4d}")
    print(f"    Pass          : {test_passed:4d} / {test_ran}  ({100*test_passed/max(1,test_ran):.1f}%)")
    print(f"    Fail          : {test_failed:4d} / {test_ran}  ({100*test_failed/max(1,test_ran):.1f}%)")
    print()

    if by_source:
        print("  By source:")
        for src, c in sorted(by_source.items(), key=lambda x: -(x[1]["check_pass"]+x[1]["check_fail"]+x[1]["not_code"])):
            tot      = c["check_pass"] + c["check_fail"]
            doc      = c["not_code"]
            pct      = 100 * c["check_pass"] / max(1, tot)
            bar      = "█" * int(pct / 5)
            t_info   = f"  tests:{c['test_pass']}/{c['test_pass']+c['test_fail']}" if c['test_pass']+c['test_fail'] > 0 else ""
            doc_info = f"  doc:{doc}" if doc > 0 else ""
            print(f"    {src:<30} {c['check_pass']:3d}/{tot:3d} ({pct:5.1f}%) {bar}{t_info}{doc_info}")

    print("═" * 65)

    # ── Save ─────────────────────────────────────────────────────────────────
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Never overwrite: inject timestamp before extension if file already exists
        if out_path.exists():
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out_path = out_path.with_stem(f"{out_path.stem}_{ts}")

        run_ts = datetime.now(timezone.utc).isoformat()
        summary = {
            "run_at":           run_ts,
            "dataset":          str(dataset_path),
            "sample_size":      len(sample),
            "seed":             args.seed,
            "source_filter":    args.source,
            "check_passed":     check_passed,
            "check_failed":     check_failed,
            "skipped":          skipped,
            "check_pass_rate":  round(check_passed / max(1, total_checked), 4),
            "test_ran":         test_ran,
            "test_passed":      test_passed,
            "test_failed":      test_failed,
            "test_pass_rate":   round(test_passed / max(1, test_ran), 4),
            "by_source":        {k: v for k, v in by_source.items()},
            "by_status":        {k: v for k, v in by_status.items()},
            "results":          results,
        }
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    main()
