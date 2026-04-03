#!/usr/bin/env python3
"""
audit_dataset_quality.py — Cardumen Forge
Uses Claude API to analyze dataset_v14 quality and identify gaps.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 scripts/audit_dataset_quality.py
    python3 scripts/audit_dataset_quality.py --samples 50 --output audit_v14.md
"""

import os
import sys
import json
import random
import argparse
from pathlib import Path
from collections import Counter, defaultdict

import anthropic

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

DATASET_PATH = Path("data/processed/dataset_v14_train_split.jsonl")
DEFAULT_SAMPLES = 60   # examples sent to Claude for quality review
DEFAULT_OUTPUT  = "logs/audit_v14.md"

# How many samples per source to include (balanced sampling)
SAMPLES_PER_SOURCE = 10

# ─────────────────────────────────────────────────────────────────────────────
# Load dataset
# ─────────────────────────────────────────────────────────────────────────────

def load_dataset(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def balanced_sample(data: list[dict], n_per_source: int, seed: int = 42) -> list[dict]:
    """Take n examples per source to get a balanced view."""
    rng = random.Random(seed)
    by_source = defaultdict(list)
    for d in data:
        by_source[d.get("source", "unknown")].append(d)

    sampled = []
    for source, examples in sorted(by_source.items()):
        take = min(n_per_source, len(examples))
        sampled.extend(rng.sample(examples, take))

    return sampled


# ─────────────────────────────────────────────────────────────────────────────
# Stats (no API needed)
# ─────────────────────────────────────────────────────────────────────────────

def compute_stats(data: list[dict]) -> dict:
    sources       = Counter(d.get("source", "?") for d in data)
    topics        = Counter(d.get("topic",  "?") for d in data)
    statuses      = Counter(d.get("review_status", "?") for d in data)
    has_input     = sum(1 for d in data if d.get("input", "").strip())
    has_code_out  = sum(1 for d in data if "```" in d.get("output", ""))
    has_validator = sum(1 for d in data if "validator" in d.get("output", ""))
    has_dot_import = sum(1 for d in data if "use cardano." in d.get("output", ""))
    has_slash_import = sum(1 for d in data if "use cardano/" in d.get("output", ""))

    output_lens = [len(d.get("output", "")) for d in data]
    avg_out_len = sum(output_lens) / max(1, len(output_lens))
    short_outputs = sum(1 for l in output_lens if l < 100)

    return {
        "total": len(data),
        "sources": dict(sources.most_common()),
        "top_topics": dict(topics.most_common(20)),
        "review_status": dict(statuses.most_common()),
        "has_input": has_input,
        "has_code_output": has_code_out,
        "has_validator_in_output": has_validator,
        "dot_imports_in_output": has_dot_import,    # BAD — should be 0
        "slash_imports_in_output": has_slash_import,
        "avg_output_len_chars": round(avg_out_len),
        "short_outputs_under_100_chars": short_outputs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Claude quality review
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert in Aiken v3 smart contract development on Cardano and in machine learning dataset quality.
You will analyze a sample of fine-tuning examples for a model that should:
1. Write correct Aiken v3 validators (spend, mint, withdraw, publish, vote)
2. Use slash-style imports: `use cardano/assets` NOT `use cardano.assets`
3. Always wrap handlers in a `validator { }` block
4. Use correct v3 API: `self.extra_signatories`, `validity_range`, `lovelace_of`, etc.

For each issue you find, be specific. For coverage gaps, suggest concrete example types to add.
"""

def format_samples_for_review(samples: list[dict]) -> str:
    lines = []
    for i, s in enumerate(samples, 1):
        lines.append(f"=== Example {i} | source={s.get('source','?')} | topic={s.get('topic','?')} | status={s.get('review_status','?')} ===")
        lines.append(f"INSTRUCTION: {s.get('instruction','')[:200]}")
        if s.get("input", "").strip():
            lines.append(f"INPUT CODE:\n{s['input'][:400]}")
        lines.append(f"OUTPUT:\n{s.get('output','')[:600]}")
        lines.append("")
    return "\n".join(lines)


def ask_claude_quality_review(client: anthropic.Anthropic, samples: list[dict], stats: dict) -> str:
    stats_summary = json.dumps(stats, indent=2)
    sample_text   = format_samples_for_review(samples)

    user_message = f"""Here are the overall statistics for the dataset (3,363 training examples):

```json
{stats_summary}
```

And here is a balanced sample of {len(samples)} examples across all sources:

{sample_text}

Please provide a thorough quality audit covering:

## 1. Data Quality Issues
- Examples with incorrect Aiken v3 syntax (dot imports, wrong API calls, missing validator block)
- Examples that are too short or too generic to be useful
- Inconsistencies between instruction, input, and output
- Any other quality red flags

## 2. Coverage Gaps
- What Aiken v3 concepts are underrepresented or missing entirely?
- What validator types/patterns should have more examples?
- What error correction scenarios are missing?
- What real-world contract patterns are absent?

## 3. Balance Issues
- Is there a topic overrepresented that could cause the model to overfit?
- Is there a critical topic with too few examples?

## 4. Concrete Recommendations
- Top 5 specific example types to add for dataset v15
- Any examples that should be removed or corrected
- Estimated how many examples of each type would meaningfully improve coverage

Be specific, cite example numbers when you spot issues, and prioritize by impact.
"""

    print("  Sending to Claude API...", flush=True)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


# ─────────────────────────────────────────────────────────────────────────────
# Anti-pattern scan (fast, no API)
# ─────────────────────────────────────────────────────────────────────────────

def scan_antipatterns(data: list[dict]) -> list[dict]:
    """Find examples with known Aiken v3 anti-patterns in their outputs."""
    issues = []
    checks = [
        ("dot_import",      lambda o: "use cardano." in o or "use aiken." in o),
        ("self.signatures", lambda o: "self.signatures" in o),
        ("self.time",       lambda o: "self.time" in o),
        ("tx.signatures",   lambda o: "tx.signatures" in o),
        ("output.value >=", lambda o: "output.value >=" in o),
        ("no_validator",    lambda o: "validator" not in o and "```" in o),
        ("empty_output",    lambda o: len(o.strip()) < 50),
    ]
    for d in data:
        out = d.get("output", "")
        for name, check_fn in checks:
            if check_fn(out):
                issues.append({
                    "issue": name,
                    "source": d.get("source"),
                    "topic": d.get("topic"),
                    "instruction": d.get("instruction", "")[:120],
                    "output_snippet": out[:200],
                })
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────

def build_report(stats: dict, antipattern_issues: list, claude_analysis: str) -> str:
    lines = [
        "# Dataset v14 Quality Audit",
        "",
        f"**Total examples:** {stats['total']:,}",
        "",
        "---",
        "",
        "## 1. Distribution Statistics",
        "",
        "### By Source",
        "| Source | Count |",
        "|--------|-------|",
    ]
    for src, cnt in stats["sources"].items():
        lines.append(f"| `{src}` | {cnt} |")

    lines += [
        "",
        "### By Review Status",
        "| Status | Count |",
        "|--------|-------|",
    ]
    for status, cnt in stats["review_status"].items():
        lines.append(f"| `{status}` | {cnt} |")

    lines += [
        "",
        "### Code Quality Signals",
        f"- Examples with input code: **{stats['has_input']}** / {stats['total']}",
        f"- Outputs with code fences: **{stats['has_code_output']}** / {stats['total']}",
        f"- Outputs containing `validator`: **{stats['has_validator_in_output']}** / {stats['total']}",
        f"- Outputs with slash imports (`use cardano/`): **{stats['slash_imports_in_output']}**",
        f"- ⚠️  Outputs with DOT imports (`use cardano.`): **{stats['dot_imports_in_output']}** ← should be 0",
        f"- Average output length: **{stats['avg_output_len_chars']} chars**",
        f"- Short outputs (<100 chars): **{stats['short_outputs_under_100_chars']}**",
        "",
    ]

    # Anti-pattern scan
    lines += [
        "---",
        "",
        "## 2. Anti-Pattern Scan (automated)",
        "",
    ]
    if antipattern_issues:
        issue_counts = Counter(i["issue"] for i in antipattern_issues)
        lines.append("**Issues found:**")
        for issue, cnt in issue_counts.most_common():
            lines.append(f"- `{issue}`: {cnt} examples")
        lines.append("")
        lines.append("**First 10 flagged examples:**")
        lines.append("")
        for item in antipattern_issues[:10]:
            lines.append(f"- **[{item['issue']}]** `{item['source']}` / `{item['topic']}`")
            lines.append(f"  - Instruction: {item['instruction']}")
            lines.append(f"  - Output snippet: `{item['output_snippet'][:100]}`")
            lines.append("")
    else:
        lines.append("✅ No anti-patterns detected in automated scan.")

    # Claude analysis
    lines += [
        "---",
        "",
        "## 3. Claude API Quality Analysis",
        "",
        claude_analysis,
        "",
        "---",
        "_Generated by `scripts/audit_dataset_quality.py`_",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset",    default=str(DATASET_PATH))
    parser.add_argument("--samples",    type=int, default=SAMPLES_PER_SOURCE,
                        help="Examples per source for Claude review (default 10)")
    parser.add_argument("--output",     default=DEFAULT_OUTPUT)
    parser.add_argument("--no-api",     action="store_true",
                        help="Skip Claude API call, only run automated checks")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.no_api:
        print("❌ ANTHROPIC_API_KEY not set.")
        print("   export ANTHROPIC_API_KEY=sk-ant-...")
        print("   Or run with --no-api for automated checks only.")
        sys.exit(1)

    print(f"\nCardumen Forge — Dataset Quality Audit")
    print(f"Dataset : {args.dataset}")
    print(f"Output  : {args.output}\n")

    # Load
    print("Loading dataset...", flush=True)
    data = load_dataset(Path(args.dataset))
    print(f"  {len(data):,} examples loaded")

    # Stats
    print("Computing statistics...", flush=True)
    stats = compute_stats(data)
    print(f"  ✅ Stats done — {stats['dot_imports_in_output']} dot-import issues found")

    # Anti-pattern scan
    print("Scanning for anti-patterns...", flush=True)
    issues = scan_antipatterns(data)
    print(f"  ✅ Scan done — {len(issues)} issues flagged")

    # Claude review
    claude_analysis = ""
    if not args.no_api:
        print("Sampling for Claude review...", flush=True)
        samples = balanced_sample(data, args.samples)
        print(f"  {len(samples)} examples sampled across {len(set(s['source'] for s in samples))} sources")
        claude_analysis = ask_claude_quality_review(anthropic.Anthropic(api_key=api_key), samples, stats)
        print("  ✅ Claude analysis done")
    else:
        claude_analysis = "_Skipped (--no-api flag set)_"

    # Report
    print("Building report...", flush=True)
    report = build_report(stats, issues, claude_analysis)
    out_path = Path(args.output)
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n✅ Report saved → {out_path}")
    print(f"   Open with: cat {out_path}\n")

    # Quick summary to terminal
    print("=== QUICK SUMMARY ===")
    print(f"Total examples    : {stats['total']:,}")
    print(f"VERIFIED_V3_ALIGNED: {stats['review_status'].get('VERIFIED_V3_ALIGNED', 0):,}")
    print(f"PLAUSIBLE_NEEDS_CHECK: {stats['review_status'].get('PLAUSIBLE_NEEDS_CHECK', 0):,}")
    print(f"DOT IMPORT ISSUES : {stats['dot_imports_in_output']} (should be 0)")
    print(f"Anti-patterns     : {len(issues)}")
    print(f"Largest source    : {max(stats['sources'], key=stats['sources'].get)} ({max(stats['sources'].values())})")


if __name__ == "__main__":
    main()
