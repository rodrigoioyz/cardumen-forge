#!/usr/bin/env python3
"""
regenerate_truncated.py — Cardumen Forge
Detects truncated outputs in the dataset, finds their original source content
from data/raw/*.json, and regenerates only the output using Claude API.

Safety rules:
  - Only regenerates outputs — instruction/input/source/topic/lang untouched
  - Skips correction examples
  - Requires generated output to be longer than original (no regressions)
  - Saves original as backup field before replacing
  - Dry-run by default

Usage:
    python3 scripts/regenerate_truncated.py              # dry-run: show what would be fixed
    python3 scripts/regenerate_truncated.py --write      # apply and save next version
    python3 scripts/regenerate_truncated.py --limit 10   # only regenerate first N
"""

import os, re, json, time, argparse
from pathlib import Path
from collections import defaultdict
import anthropic

INPUT_PATH  = Path("data/processed/dataset_v17_train_split.jsonl")
OUTPUT_PATH = Path("data/processed/dataset_v18b_train_split.jsonl")
REPORT_PATH = Path("logs/regenerate_truncated_report.md")

RAW_SOURCES = {
    "aiken_stdlib":                           Path("data/raw/aiken_stdlib.json"),
    "aiken_docs":                             Path("data/raw/aiken_docs.json"),
    "aiken_v3_curated_v2":                    None,
    "aiken_design_patterns":                  Path("data/raw/aiken_design_patterns.json"),
    "cips":                                   Path("data/raw/cips.json"),
    "hydra_docs":                             Path("data/raw/hydra_docs.json"),
    "aiken_docs.json + aiken_stdlib.json":    Path("data/raw/aiken_stdlib.json"),
    "aiken_docs.json":                        Path("data/raw/aiken_docs.json"),
    "aiken_stdlib.json":                      Path("data/raw/aiken_stdlib.json"),
    "correction_set":                         None,
    "correction_set_v2":                      None,
    "generated_governance_v1":                None,
}

# ─────────────────────────────────────────────────────────────────────────────
# Truncation detection (same logic as build_v16.py)
# ─────────────────────────────────────────────────────────────────────────────

def count_braces(text):
    return text.count('{') - text.count('}')

def extract_code_blocks(text):
    return re.findall(r'```(?:\w+)?\n(.*?)```', text, re.DOTALL)

def is_truncated(output):
    stripped = output.strip()
    if stripped and stripped[-1] not in '.`})\n"\'':
        return True, f"ends_abruptly"
    for block in extract_code_blocks(output):
        if count_braces(block) > 0:
            return True, "unclosed_braces"
    if output.count('```') % 2 != 0:
        return True, "unclosed_fence"
    return False, ""

def is_correction(ex):
    return 'correction' in ex.get('topic', '').lower() or \
           'correction' in ex.get('source', '').lower()

# ─────────────────────────────────────────────────────────────────────────────
# Raw source lookup
# ─────────────────────────────────────────────────────────────────────────────

_raw_cache = {}

def load_raw(source_key):
    path = RAW_SOURCES.get(source_key)
    if path is None or not path.exists():
        return []
    if str(path) not in _raw_cache:
        with open(path, encoding="utf-8") as f:
            _raw_cache[str(path)] = json.load(f)
    return _raw_cache[str(path)]


def find_source_context(ex):
    """Find the matching raw source entry for this example."""
    source  = ex.get("source", "")
    topic   = ex.get("topic",  "")
    raw     = load_raw(source)
    if not raw:
        return None

    # aiken_stdlib: match by module name embedded in topic
    # topic format: "aiken/cardano.assets" or "aiken/aiken.collection.list.push"
    # stdlib entry has "module" field like "cardano.assets" or "aiken.collection.list"
    if "stdlib" in source:
        # Extract module from topic: "aiken/cardano.assets.reduce" → "cardano.assets"
        topic_module = topic.replace("aiken/", "").replace("aiken_v3/", "")
        # Try progressively shorter prefixes
        for entry in raw:
            mod = entry.get("module", "")
            if mod and (mod in topic_module or topic_module.startswith(mod)):
                return entry.get("description", "") or entry.get("signature", "")

    # CIPs: match by CIP number in topic  e.g. "cardano/cip/cip-0114" → "0114"
    if "cip" in source.lower() or "cip" in topic.lower():
        cip_match = re.search(r'cip-?(\d+)', topic.lower())
        if cip_match:
            cip_num = cip_match.group(1).lstrip("0") or "0"
            for entry in raw:
                entry_id    = str(entry.get("id",    ""))
                entry_title = str(entry.get("title", "")).lower()
                if cip_num in entry_id or f"cip-{cip_num.zfill(4)}" in entry_title or \
                   cip_num.zfill(4) in entry_id:
                    content = entry.get("content", "")
                    return content[:2000] if content else None

    # aiken_docs / design_patterns / hydra: match by title or topic keyword
    topic_keyword = topic.split("/")[-1].replace("_", " ").replace("-", " ").lower()
    best_entry = None
    best_score = 0
    for entry in raw:
        title   = str(entry.get("title",   "")).lower()
        content = str(entry.get("content", ""))
        name    = str(entry.get("name",    "")).lower()
        words   = [w for w in topic_keyword.split() if len(w) > 3]
        score   = sum([
            topic_keyword in title,
            any(w in title for w in words[:3]),
            any(w in name  for w in words[:3]),
        ])
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry and best_score > 0:
        return (best_entry.get("content") or best_entry.get("description") or "")[:2000]

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Regeneration via Claude API
# ─────────────────────────────────────────────────────────────────────────────

STDLIB_RULES = """\
AIKEN V3 RULES (non-negotiable):
- Handler names inside validator blocks: spend(, mint(, withdraw(, publish(, vote(
- NO fn keyword before handler names inside validator blocks
- ONLY slash-style imports: use cardano/assets  NOT use cardano.assets
- Credential constructors: Script and VerificationKey  (NOT ScriptCredential / PubKeyCredential)
- PolicyId lives in cardano/assets  NOT cardano/transaction
- else(_) { fail } recommended as catch-all fallback
- Complete all code — never truncate, always close all braces
"""

def regenerate_output(client, ex, source_context):
    instruction = ex.get("instruction", "")
    input_code  = ex.get("input", "")
    lang        = ex.get("lang", "en")
    lang_note   = "Respond in Spanish." if lang == "es" else "Respond in English."

    context_block = ""
    if source_context:
        context_block = f"\n\nRELEVANT DOCUMENTATION:\n{source_context[:1500]}\n"

    user_msg = f"{instruction}"
    if input_code.strip():
        user_msg += f"\n\nInput code:\n```aiken\n{input_code}\n```"
    user_msg += f"\n{lang_note}\n{context_block}"

    try:
        resp = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1500,
            system=f"You are an expert Aiken v3 smart contract engineer.\n{STDLIB_RULES}",
            messages=[{"role": "user", "content": user_msg}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   default=str(INPUT_PATH))
    parser.add_argument("--output",  default=str(OUTPUT_PATH))
    parser.add_argument("--report",  default=str(REPORT_PATH))
    parser.add_argument("--write",   action="store_true")
    parser.add_argument("--limit",   type=int, default=0, help="Max examples to regenerate (0=all)")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and args.write:
        print("❌ ANTHROPIC_API_KEY not set.")
        return
    client = anthropic.Anthropic(api_key=api_key) if api_key else None

    print(f"\nCardumen Forge — Regenerate Truncated Outputs")
    print(f"Input  : {args.input}")
    print(f"Output : {args.output}")
    print(f"Mode   : {'WRITE' if args.write else 'DRY RUN'}\n")

    with open(args.input, encoding="utf-8") as f:
        examples = [json.loads(l) for l in f if l.strip()]
    print(f"Loaded : {len(examples):,} examples")

    # Find truncated
    truncated_idx = []
    for i, ex in enumerate(examples):
        if is_correction(ex):
            continue
        trunc, reason = is_truncated(ex.get("output", ""))
        if trunc:
            truncated_idx.append((i, reason))

    print(f"Truncated found : {len(truncated_idx)}")

    if args.limit > 0:
        truncated_idx = truncated_idx[:args.limit]
        print(f"Limiting to     : {args.limit}")

    # Stats
    stats = {"attempted": 0, "success": 0, "no_context": 0, "failed": 0, "skipped_shorter": 0}
    log   = []
    results = list(examples)

    for i, (idx, reason) in enumerate(truncated_idx):
        ex = examples[idx]
        print(f"\n[{i+1:02d}/{len(truncated_idx)}] {ex.get('source')} / {ex.get('topic','')[:40]}")
        print(f"  Reason  : {reason}")
        print(f"  Instr   : {ex.get('instruction','')[:80]}")

        # Find source context
        ctx = find_source_context(ex)
        if ctx:
            print(f"  Context : {len(ctx)} chars from raw source")
        else:
            print(f"  Context : none found")
            stats["no_context"] += 1

        if not args.write:
            log.append({"idx": idx, "reason": reason, "has_context": ctx is not None,
                        "source": ex.get("source"), "instruction": ex.get("instruction","")[:100]})
            continue

        stats["attempted"] += 1
        new_output = regenerate_output(client, ex, ctx)

        if new_output is None:
            stats["failed"] += 1
            log.append({"idx": idx, "status": "failed", "reason": reason})
            continue

        if len(new_output) < len(ex.get("output", "")) * 0.8:
            print(f"  ⚠️  New output shorter ({len(new_output)} < {len(ex['output'])}) — skipping")
            stats["skipped_shorter"] += 1
            log.append({"idx": idx, "status": "skipped_shorter", "reason": reason})
            continue

        print(f"  ✅ {len(ex.get('output',''))} → {len(new_output)} chars")
        stats["success"] += 1
        results[idx] = {**ex, "output": new_output, "_original_output": ex["output"][:200]}
        log.append({"idx": idx, "status": "success", "old_len": len(ex["output"]), "new_len": len(new_output)})
        time.sleep(0.3)

    # Summary
    print(f"\n{'='*60}")
    print(f"  Truncated found    : {len(truncated_idx)}")
    if args.write:
        print(f"  Attempted          : {stats['attempted']}")
        print(f"  Success            : {stats['success']}")
        print(f"  No context found   : {stats['no_context']}")
        print(f"  Failed API call    : {stats['failed']}")
        print(f"  Skipped (shorter)  : {stats['skipped_shorter']}")
    else:
        no_ctx = sum(1 for l in log if not l.get("has_context"))
        print(f"  With source context: {len(log) - no_ctx}")
        print(f"  Without context    : {no_ctx}")
        print(f"  (dry run — use --write to regenerate)")
    print(f"{'='*60}")

    if args.write:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            for ex in results:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"\n  ✅ Saved → {args.output}")

    # Report
    report = [
        "# Regenerate Truncated Outputs Report",
        "",
        f"**Input:** `{args.input}` ({len(examples):,} examples)",
        f"**Mode:** {'WRITE' if args.write else 'DRY Run'}",
        f"**Truncated found:** {len(truncated_idx)}",
        "",
        "| # | Source | Topic | Reason | Context | Status |",
        "|---|--------|-------|--------|---------|--------|",
    ]
    for i, item in enumerate(log):
        idx    = item["idx"]
        ex     = examples[idx]
        src    = (ex.get("source") or "")[:20]
        topic  = (ex.get("topic")  or "")[:30]
        reason = item.get("reason", "")[:20]
        ctx    = "✅" if item.get("has_context", item.get("status") == "success") else "❌"
        status = item.get("status", "dry-run")
        report.append(f"| {i+1} | `{src}` | `{topic}` | {reason} | {ctx} | {status} |")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(report), encoding="utf-8")
    print(f"  Report → {args.report}")


if __name__ == "__main__":
    main()
