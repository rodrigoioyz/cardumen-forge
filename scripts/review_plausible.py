#!/usr/bin/env python3
"""
review_plausible.py — Cardumen Forge
Reviews PLAUSIBLE_NEEDS_CHECK examples using local documentation only.
No API calls, no cost.

Pass 1 — Known bad patterns (regex):
  Flags examples with confirmed hallucinations or wrong syntax.
  → review_status: FLAGGED_REMOVE

Pass 2 — Stdlib API verification:
  Extracts function calls from code blocks and checks each against
  data/raw/aiken_stdlib.json.  If all calls are verified → promotes.
  → review_status: VERIFIED_V3_ALIGNED

Examples that use output.*, self.*, or custom types (cannot be verified
locally without runtime type info) stay as PLAUSIBLE_NEEDS_CHECK.

Usage:
    python3 scripts/review_plausible.py                   # dry-run
    python3 scripts/review_plausible.py --write           # apply changes
    python3 scripts/review_plausible.py --input data/processed/dataset_v19_dedup.jsonl
    python3 scripts/review_plausible.py --output-only     # skip Pass 2
"""

import re
import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter

INPUT_PATH  = Path("data/processed/dataset_v19_dedup.jsonl")
OUTPUT_PATH = Path("data/processed/dataset_v20_reviewed.jsonl")
REPORT_PATH = Path("logs/review_plausible_report.md")
STDLIB_PATH = Path("data/raw/aiken_stdlib.json")

# ─────────────────────────────────────────────────────────────────────────────
# Pass 1 — known bad patterns
# Each entry: (label, regex, check_in_code_only)
# check_in_code_only=True → only match inside ```...``` blocks
# ─────────────────────────────────────────────────────────────────────────────

BAD_PATTERNS = [
    # Hallucinated field names
    ("self.signatures",       r'\bself\.signatures\b',                    True),
    ("self.time",             r'\bself\.time\b',                          True),
    ("output.assets.ada",     r'\boutput\.assets\.ada\b',                 True),
    ("tx.validity_range",     r'\btx\.validity_range\b',                  True),
    # Hallucinated functions
    ("list.has_any",          r'\blist\.has_any\s*\(',                    True),
    ("transaction.signatories",r'\btransaction\.signatories\s*\(',        True),
    ("value.to_dict",         r'\bvalue\.to_dict\s*\(',                   True),
    ("assets.from_asset_list",r'\bassets\.from_asset_list\s*\(',          True),
    # Wrong type names (Plutus v2)
    ("ScriptCredential",      r'\bScriptCredential\b',                    True),
    ("PubKeyCredential",      r'\bPubKeyCredential\b',                    True),
    # Wrong import style
    ("dot_import",            r'\buse\s+\w+\.',                           True),
    # fn prefix in handlers (should be 0 after v15, but double-check)
    ("fn_handler",            r'\bfn\s+(spend|mint|withdraw|publish|vote|propose)\s*\(', True),
    # PolicyId from wrong module
    ("policyd_wrong_module",  r'use\s+cardano/transaction[^;]*PolicyId',  True),
]


def extract_code_blocks(text: str) -> list[str]:
    return re.findall(r'```(?:\w+)?\n(.*?)```', text, re.DOTALL)


def check_bad_patterns(output: str) -> list[str]:
    """Return list of bad pattern labels found in output."""
    code_blocks = extract_code_blocks(output)
    code_combined = "\n".join(code_blocks)
    found = []
    for label, pattern, code_only in BAD_PATTERNS:
        text = code_combined if code_only else output
        if re.search(pattern, text):
            found.append(label)
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2 — stdlib API verification
# ─────────────────────────────────────────────────────────────────────────────

# Aliases that are valid but not in stdlib JSON — never flag these
WHITELIST_ALIASES = {
    "builtin",   # Plutus built-in functions (always valid)
    "fuzz",      # Aiken testing framework
    "bench",     # benchmark helpers
    "test",      # test helpers
    "expect",    # trace/expect helpers
}

# Aliases that are struct field accessors, not module function calls
# (e.g. output.address, self.inputs — these appear as word.word but are fields)
FIELD_ALIASES = {
    "output", "input", "self", "tx", "datum", "redeemer",
    "policy_id", "asset_name", "credential", "address",
    "value", "cert", "voter", "proposal", "ctx",
}


def build_stdlib_lookup(stdlib_path: Path) -> dict[str, set]:
    """Returns {alias: {fn_name, ...}} for all function entries in stdlib."""
    with open(stdlib_path, encoding="utf-8") as f:
        entries = json.load(f)
    lookup = defaultdict(set)
    for entry in entries:
        if entry.get("type") != "function":
            continue
        mod   = entry.get("module", "")
        name  = entry.get("name", "")
        alias = mod.split(".")[-1]
        lookup[alias].add(name)
    return dict(lookup)


def check_api_calls(output: str, stdlib_lookup: dict) -> tuple[list, list]:
    """
    Returns (verified_calls, unverified_calls).
    verified_calls   — alias.fn confirmed in stdlib
    unverified_calls — alias.fn where alias is a known stdlib module but fn is not in it
    Calls on whitelist or field aliases are ignored.
    """
    code_blocks = extract_code_blocks(output)
    if not code_blocks:
        return [], []

    verified   = []
    unverified = []

    for block in code_blocks:
        calls = re.findall(r'\b([a-z_]\w*)\.([a-z_]\w*)\s*\(', block)
        for alias, fn in calls:
            if alias in WHITELIST_ALIASES:
                continue
            if alias in FIELD_ALIASES:
                continue
            if alias not in stdlib_lookup:
                continue  # custom type or unknown — skip, don't penalize
            if fn in stdlib_lookup[alias]:
                verified.append(f"{alias}.{fn}")
            else:
                unverified.append(f"{alias}.{fn}")

    return verified, unverified


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",       default=str(INPUT_PATH))
    parser.add_argument("--output",      default=str(OUTPUT_PATH))
    parser.add_argument("--report",      default=str(REPORT_PATH))
    parser.add_argument("--write",       action="store_true")
    parser.add_argument("--output-only", action="store_true", help="Skip Pass 2 API check")
    args = parser.parse_args()

    print(f"\nCardumen Forge — Review PLAUSIBLE_NEEDS_CHECK")
    print(f"Input  : {args.input}")
    print(f"Output : {args.output}")
    print(f"Mode   : {'WRITE' if args.write else 'DRY RUN'}\n")

    stdlib_lookup = build_stdlib_lookup(STDLIB_PATH)
    print(f"Stdlib : {sum(len(v) for v in stdlib_lookup.values())} functions across {len(stdlib_lookup)} modules")

    with open(args.input, encoding="utf-8") as f:
        examples = [json.loads(l) for l in f if l.strip()]
    print(f"Loaded : {len(examples):,} examples\n")

    plausible_idx = [i for i, ex in enumerate(examples)
                     if ex.get("review_status") == "PLAUSIBLE_NEEDS_CHECK"]
    print(f"PLAUSIBLE_NEEDS_CHECK : {len(plausible_idx):,}")

    stats = Counter()
    log   = []   # one entry per PLAUSIBLE example

    for idx in plausible_idx:
        ex     = examples[idx]
        output = ex.get("output", "")

        # Pass 1 — bad patterns
        bad = check_bad_patterns(output)

        # Pass 2 — stdlib API check
        verified, unverified = [], []
        if not args.output_only:
            verified, unverified = check_api_calls(output, stdlib_lookup)

        # Decision
        if bad:
            decision = "FLAGGED_REMOVE"
        elif not unverified and verified:
            decision = "VERIFIED_V3_ALIGNED"
        else:
            decision = "PLAUSIBLE_NEEDS_CHECK"

        stats[decision] += 1
        log.append({
            "idx":        idx,
            "decision":   decision,
            "bad":        bad,
            "verified":   list(set(verified)),
            "unverified": list(set(unverified)),
            "source":     ex.get("source", ""),
            "topic":      ex.get("topic", ""),
            "instruction": ex.get("instruction", "")[:100],
        })

    # ── Summary ──────────────────────────────────────────────────────────────
    total_p = len(plausible_idx)
    print(f"\n{'='*60}")
    print(f"  PLAUSIBLE reviewed    : {total_p:,}")
    print(f"  → VERIFIED_V3_ALIGNED : {stats['VERIFIED_V3_ALIGNED']:,}  "
          f"({100*stats['VERIFIED_V3_ALIGNED']/max(1,total_p):.1f}%)")
    print(f"  → FLAGGED_REMOVE      : {stats['FLAGGED_REMOVE']:,}  "
          f"({100*stats['FLAGGED_REMOVE']/max(1,total_p):.1f}%)")
    print(f"  → stays PLAUSIBLE     : {stats['PLAUSIBLE_NEEDS_CHECK']:,}  "
          f"({100*stats['PLAUSIBLE_NEEDS_CHECK']/max(1,total_p):.1f}%)")
    print(f"{'='*60}")

    # Sample flagged
    flagged = [e for e in log if e["decision"] == "FLAGGED_REMOVE"]
    if flagged:
        print(f"\n  FLAGGED sample (first 5):")
        for e in flagged[:5]:
            print(f"    [{e['source']}] {e['instruction'][:70]}")
            print(f"    bad: {e['bad']}")

    # Most common unverified calls
    all_unverified = []
    for e in log:
        all_unverified.extend(e["unverified"])
    if all_unverified:
        print(f"\n  Most common unverified API calls (top 15):")
        for call, count in Counter(all_unverified).most_common(15):
            print(f"    {count:4d}×  {call}")

    # ── Apply ─────────────────────────────────────────────────────────────────
    results = list(examples)
    if args.write:
        promoted = 0
        removed  = 0
        for entry in log:
            idx      = entry["idx"]
            decision = entry["decision"]
            if decision == "VERIFIED_V3_ALIGNED":
                results[idx] = {**examples[idx], "review_status": "VERIFIED_V3_ALIGNED",
                                "_promoted_from": "PLAUSIBLE_NEEDS_CHECK"}
                promoted += 1
            elif decision == "FLAGGED_REMOVE":
                results[idx] = None   # mark for removal
                removed += 1

        results = [r for r in results if r is not None]
        print(f"\n  Applied: promoted {promoted}, removed {removed}")
        print(f"  Final dataset size: {len(results):,}")

        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            for ex in results:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"  ✅ Saved → {args.output}")
    else:
        print(f"\n  (dry run — use --write to apply)")

    # ── Report ────────────────────────────────────────────────────────────────
    report = [
        "# Review PLAUSIBLE_NEEDS_CHECK Report",
        "",
        f"**Input:** `{args.input}` ({len(examples):,} examples)",
        f"**Mode:** {'WRITE' if args.write else 'DRY RUN'}",
        "",
        "## Summary",
        "",
        f"| Decision | Count | % |",
        f"|----------|-------|---|",
        f"| VERIFIED_V3_ALIGNED | {stats['VERIFIED_V3_ALIGNED']:,} | "
        f"{100*stats['VERIFIED_V3_ALIGNED']/max(1,total_p):.1f}% |",
        f"| FLAGGED_REMOVE | {stats['FLAGGED_REMOVE']:,} | "
        f"{100*stats['FLAGGED_REMOVE']/max(1,total_p):.1f}% |",
        f"| stays PLAUSIBLE | {stats['PLAUSIBLE_NEEDS_CHECK']:,} | "
        f"{100*stats['PLAUSIBLE_NEEDS_CHECK']/max(1,total_p):.1f}% |",
        "",
        "## Flagged for removal",
        "",
        "| Source | Topic | Bad patterns | Instruction |",
        "|--------|-------|-------------|-------------|",
    ]
    for e in [x for x in log if x["decision"] == "FLAGGED_REMOVE"][:100]:
        src   = (e["source"] or "")[:20]
        topic = (e["topic"]  or "")[:30]
        bad   = ", ".join(e["bad"])[:50]
        instr = e["instruction"][:70]
        report.append(f"| `{src}` | `{topic}` | {bad} | {instr} |")

    report += [
        "",
        "## Most common unverified API calls",
        "",
        "| Call | Count |",
        "|------|-------|",
    ]
    for call, count in Counter(all_unverified).most_common(30):
        report.append(f"| `{call}` | {count} |")

    report += ["", "_Generated by `scripts/review_plausible.py`_"]

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(report), encoding="utf-8")
    print(f"  Report → {args.report}")


if __name__ == "__main__":
    main()
