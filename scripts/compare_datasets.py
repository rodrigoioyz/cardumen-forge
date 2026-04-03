#!/usr/bin/env python3
"""
compare_datasets.py — Cardumen Forge
Compares quality metrics across dataset versions to quantify improvement.
"""

import re
import json
from pathlib import Path
from collections import Counter

DATASETS = [
    ("v14",  "data/processed/dataset_v14_train_split.jsonl"),
    ("v17",  "data/processed/dataset_v17_train_split.jsonl"),
    ("v19",  "data/processed/dataset_v19_dedup.jsonl"),
]

HANDLERS = ["spend(", "mint(", "withdraw(", "publish(", "vote(", "propose("]

def analyze(path):
    with open(path, encoding="utf-8") as f:
        data = [json.loads(l) for l in f if l.strip()]

    outputs = [d.get("output", "") for d in data]
    total   = len(data)

    # Syntax errors
    fn_handlers = sum(1 for o in outputs if re.search(r'\bfn\s+(spend|mint|withdraw|publish|vote|else)\s*\(', o))
    dot_imports = sum(1 for o in outputs if re.search(r'\buse\s+\w+\.', o, re.MULTILINE))
    wrong_cred  = sum(1 for o in outputs if "ScriptCredential" in o or "PubKeyCredential" in o)
    wrong_pid   = sum(1 for o in outputs if "cardano/transaction" in o and "PolicyId" in o)

    # Coverage
    handler_counts = {h: sum(1 for o in outputs if h in o) for h in HANDLERS}

    # Quality signals
    has_validator  = sum(1 for o in outputs if "validator" in o)
    has_else       = sum(1 for o in outputs if "else(_)" in o)
    sig_check      = sum(1 for o in outputs if "extra_signatories" in o)

    # Truncated (simple check)
    truncated = sum(1 for o in outputs
                    if o.strip() and o.strip()[-1] not in '.`})\n"\'')

    # Status distribution
    statuses = Counter(d.get("review_status", "?") for d in data)

    return {
        "total":         total,
        "fn_handlers":   fn_handlers,
        "dot_imports":   dot_imports,
        "wrong_cred":    wrong_cred,
        "wrong_pid":     wrong_pid,
        "handlers":      handler_counts,
        "has_validator": has_validator,
        "has_else":      has_else,
        "sig_check":     sig_check,
        "truncated":     truncated,
        "statuses":      dict(statuses),
    }

def pct(n, total):
    return f"{n:4d} ({100*n/max(1,total):4.1f}%)"

def main():
    results = {}
    for label, path in DATASETS:
        p = Path(path)
        if not p.exists():
            print(f"  SKIP {label} — {path} not found")
            continue
        results[label] = analyze(path)

    labels = list(results.keys())

    print("\n" + "="*70)
    print("  DATASET COMPARISON — Cardumen Forge")
    print("="*70)

    # Total
    print(f"\n  {'Metric':<35}", end="")
    for l in labels: print(f"  {l:>15}", end="")
    print()
    print(f"  {'-'*60}")

    def row(name, key, good="low"):
        print(f"  {name:<35}", end="")
        vals = [results[l][key] for l in labels]
        for i, (l, v) in enumerate(zip(labels, vals)):
            total = results[l]["total"]
            cell  = pct(v, total)
            # Highlight if improved
            if i > 0 and good == "low" and v < vals[0]:
                cell = "✅ " + cell
            elif i > 0 and good == "high" and v > vals[0]:
                cell = "✅ " + cell
            print(f"  {cell:>15}", end="")
        print()

    print(f"\n  {'Total examples':<35}", end="")
    for l in labels: print(f"  {results[l]['total']:>15,}", end="")
    print()

    print(f"\n  ── SYNTAX ERRORS (lower = better) ──")
    row("fn prefix in handlers",      "fn_handlers",  "low")
    row("Dot-style imports",          "dot_imports",  "low")
    row("Wrong Credential names",     "wrong_cred",   "low")
    row("PolicyId wrong module",      "wrong_pid",    "low")
    row("Truncated outputs",          "truncated",    "low")

    print(f"\n  ── COVERAGE (higher = better) ──")
    for h in HANDLERS:
        print(f"  {'Handler: ' + h:<35}", end="")
        for l in labels:
            v     = results[l]["handlers"][h]
            total = results[l]["total"]
            cell  = pct(v, total)
            print(f"  {cell:>15}", end="")
        print()

    print(f"\n  ── QUALITY SIGNALS ──")
    row("Has validator block",        "has_validator", "high")
    row("Has else(_) fallback",       "has_else",      "high")
    row("Uses extra_signatories",     "sig_check",     None)

    print(f"\n  ── STATUS DISTRIBUTION ──")
    all_statuses = set()
    for r in results.values():
        all_statuses.update(r["statuses"].keys())
    for s in sorted(all_statuses):
        print(f"  {s:<35}", end="")
        for l in labels:
            v     = results[l]["statuses"].get(s, 0)
            total = results[l]["total"]
            print(f"  {pct(v, total):>15}", end="")
        print()

    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    main()
