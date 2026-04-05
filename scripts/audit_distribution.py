#!/usr/bin/env python3
"""
audit_distribution.py — Análisis completo de distribución del dataset v23
Produce 5 reportes en logs/audit_distribution_*.txt
"""
import json, re
from pathlib import Path
from collections import Counter, defaultdict

ROOT         = Path(__file__).parent.parent
DATASET      = ROOT / "data" / "processed" / "dataset_v23.jsonl"
BENCHMARK    = ROOT / "eval" / "benchmark_v2.json"
LOGS         = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

# ── Load ──────────────────────────────────────────────────────────────────────

print("Loading dataset...", end=" ", flush=True)
examples = []
with DATASET.open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            examples.append(json.loads(line))
print(f"{len(examples)} examples")

print("Loading benchmark...", end=" ", flush=True)
with BENCHMARK.open(encoding="utf-8") as f:
    benchmark = json.load(f)
print(f"{len(benchmark)} prompts")

# ── H1: Handler type distribution ─────────────────────────────────────────────

print("\n── H1: Handler types ──")
HANDLERS = ["spend", "mint", "withdraw", "vote", "publish", "propose"]
ds_handler_counts  = Counter()
ds_multi           = 0

for ex in examples:
    code = ex.get("output", "") or ex.get("completion", "") or ex.get("response", "")
    found = set()
    for h in HANDLERS:
        if re.search(rf'\b{h}\s*\(', code):
            found.add(h)
    for h in found:
        ds_handler_counts[h] += 1
    if len(found) > 1:
        ds_multi += 1

bm_cat_counts = Counter(p.get("category","unknown").split("/")[0] for p in benchmark)

lines = ["=" * 60,
         "H1 — Handler Type Distribution",
         "=" * 60,
         "",
         f"{'Handler':<15} {'Dataset':>10} {'%':>7}   {'Benchmark cat':>20}",
         "-" * 60]
for h in HANDLERS:
    ds_n  = ds_handler_counts[h]
    ds_pct = ds_n / len(examples) * 100
    bm_n  = bm_cat_counts.get(h, 0)
    lines.append(f"{h:<15} {ds_n:>10,} {ds_pct:>6.1f}%   {bm_n:>20}")
lines += ["",
          f"Examples with multiple handlers: {ds_multi:,} ({ds_multi/len(examples)*100:.1f}%)",
          "",
          "Benchmark categories:",
          ]
for cat, n in bm_cat_counts.most_common():
    lines.append(f"  {cat:<30} {n:>4}")

report = "\n".join(lines)
print(report)
(LOGS / "audit_distribution_h1_handlers.txt").write_text(report, encoding="utf-8")

# ── H2: Code length distribution ──────────────────────────────────────────────

print("\n── H2: Code length ──")
lengths = []
for ex in examples:
    code = ex.get("output","") or ex.get("completion","") or ex.get("response","")
    n = len([l for l in code.splitlines() if l.strip()])
    lengths.append(n)

lengths.sort()
buckets = [(0,10),(10,20),(20,30),(30,50),(50,100),(100,99999)]
bucket_labels = ["<10","10-20","20-30","30-50","50-100",">100"]

lines = ["=" * 60,
         "H2 — Code Length Distribution (non-empty lines)",
         "=" * 60, ""]
total = len(lengths)
for (lo,hi), label in zip(buckets, bucket_labels):
    cnt = sum(1 for l in lengths if lo <= l < hi)
    lines.append(f"  {label:<10} {cnt:>6,}  ({cnt/total*100:5.1f}%)")

mean   = sum(lengths)/len(lengths)
median = lengths[len(lengths)//2]
p10    = lengths[int(len(lengths)*0.10)]
p90    = lengths[int(len(lengths)*0.90)]

lines += ["",
          f"  Mean:   {mean:.1f} lines",
          f"  Median: {median} lines",
          f"  P10:    {p10} lines",
          f"  P90:    {p90} lines",
          f"  Min:    {lengths[0]} lines",
          f"  Max:    {lengths[-1]} lines",
          ""]

# 5 shortest / longest
def get_prompt(ex):
    return (ex.get("prompt","") or ex.get("instruction","") or "")[:80]

indexed = sorted(enumerate(examples), key=lambda x: lengths[x[0]])
lines.append("5 shortest:")
for i, ex in indexed[:5]:
    lines.append(f"  [{lengths[i]:3d} lines] {get_prompt(ex)}")
lines.append("\n5 longest:")
for i, ex in indexed[-5:]:
    lines.append(f"  [{lengths[i]:3d} lines] {get_prompt(ex)}")

report = "\n".join(lines)
print(report)
(LOGS / "audit_distribution_h2_length.txt").write_text(report, encoding="utf-8")

# ── H3: Stdlib module coverage ────────────────────────────────────────────────

print("\n── H3: Stdlib modules ──")
MODULES = [
    "aiken/collection/list",
    "aiken/collection/dict",
    "aiken/primitive/bytearray",
    "aiken/primitive/string",
    "aiken/interval",
    "aiken/math",
    "aiken/crypto",
    "cardano/assets",
    "cardano/transaction",
    "cardano/address",
    "cardano/governance",
    "aiken/fuzz",
    "cardano/fuzz",
]
CALL_PATTERNS = {
    "aiken/collection/list":      re.compile(r'\blist\.'),
    "aiken/collection/dict":      re.compile(r'\bdict\.'),
    "aiken/primitive/bytearray":  re.compile(r'\bbytearray\.'),
    "aiken/primitive/string":     re.compile(r'\bstring\.'),
    "aiken/interval":             re.compile(r'\binterval\.'),
    "aiken/math":                 re.compile(r'\bmath\.'),
    "aiken/crypto":               re.compile(r'\bcrypto\.'),
    "cardano/assets":             re.compile(r'\bassets\.'),
    "cardano/transaction":        re.compile(r'\btransaction\.|Transaction\b'),
    "cardano/address":            re.compile(r'\baddress\.|Address\b'),
    "cardano/governance":         re.compile(r'\bgovernance\.|Voter\b'),
    "aiken/fuzz":                 re.compile(r'\bfuzz\.'),
    "cardano/fuzz":               re.compile(r'\bcfuzz\.'),
}

import_counts = Counter()
call_counts   = Counter()
for ex in examples:
    code = ex.get("output","") or ex.get("completion","") or ex.get("response","")
    for mod in MODULES:
        if f"use {mod}" in code or f'use {mod}.' in code or f'use {mod}{{' in code:
            import_counts[mod] += 1
        if mod in CALL_PATTERNS and CALL_PATTERNS[mod].search(code):
            call_counts[mod] += 1

lines = ["=" * 60,
         "H3 — Stdlib Module Coverage",
         "=" * 60, "",
         f"{'Module':<35} {'import':>8} {'%':>6}  {'calls':>8} {'%':>6}  Status",
         "-" * 80]
for mod in MODULES:
    imp = import_counts[mod]
    cal = call_counts[mod]
    pct = imp / len(examples) * 100
    status = "✅ well-covered" if pct > 10 else ("⚠️  sparse" if pct > 5 else "❌ GAP")
    lines.append(f"{mod:<35} {imp:>8,} {pct:>5.1f}%  {cal:>8,} {cal/len(examples)*100:>5.1f}%  {status}")

report = "\n".join(lines)
print(report)
(LOGS / "audit_distribution_h3_stdlib.txt").write_text(report, encoding="utf-8")

# ── H4: Structural complexity ──────────────────────────────────────────────────

print("\n── H4: Structural complexity ──")
FEATURES = {
    "custom types":       re.compile(r'\bpub type\b'),
    "helpers (fn)":       re.compile(r'^fn \w+', re.MULTILINE),
    "property tests":     re.compile(r'^test ', re.MULTILINE),
    "fail tests":         re.compile(r'\btest\b[^{]+\bfail\b\s*\{'),
    "else(_) handler":    re.compile(r'\belse\s*\(_\)'),
    "multiple handlers":  None,  # special case
    "reference inputs":   re.compile(r'\breference_inputs\b'),
    "minting":            re.compile(r'\bself\.mint\b|\bctx\.transaction\.mint\b'),
    "typed datum":        re.compile(r'Option<'),
    "expect":             re.compile(r'\bexpect\b'),
}

feature_counts = Counter()
complexity_dist = Counter()

for ex in examples:
    code = ex.get("output","") or ex.get("completion","") or ex.get("response","")
    score = 0
    for feat, pat in FEATURES.items():
        if feat == "multiple handlers":
            n = len(set(re.findall(r'\b(spend|mint|withdraw|vote|publish|propose)\s*\(', code)))
            if n > 1:
                feature_counts[feat] += 1
                score += 1
        elif pat and pat.search(code):
            feature_counts[feat] += 1
            score += 1
    complexity_dist[min(score, 5)] += 1  # cap at 5+

lines = ["=" * 60,
         "H4 — Structural Complexity",
         "=" * 60, "",
         f"{'Feature':<25} {'Count':>8} {'%':>7}",
         "-" * 45]
for feat in FEATURES:
    n = feature_counts[feat]
    lines.append(f"{feat:<25} {n:>8,} {n/len(examples)*100:>6.1f}%")

lines += ["", "Complexity index (# features per example):",
          f"{'Score':<10} {'Count':>8} {'%':>7}"]
for score in range(6):
    label = f"{score}+" if score == 5 else str(score)
    n = complexity_dist[score]
    lines.append(f"{label:<10} {n:>8,} {n/len(examples)*100:>6.1f}%")

report = "\n".join(lines)
print(report)
(LOGS / "audit_distribution_h4_complexity.txt").write_text(report, encoding="utf-8")

# ── H5: Train vs benchmark gap ────────────────────────────────────────────────

print("\n── H5: Train vs benchmark coverage ──")
bm_categories = Counter(p.get("category","unknown") for p in benchmark)

# Keywords per category
CATEGORY_KEYWORDS = {
    "spend/signature":      ["signator","signed by","sign","owner"],
    "spend/ada_payment":    ["lovelace","ada","payment","min_ada","pay"],
    "spend/time":           ["deadline","validity","time","interval","after","before"],
    "spend/nft_gate":       ["nft","token gate","hold","asset"],
    "spend/multi_handler":  ["multi","both","spend.*mint","mint.*spend"],
    "spend/reference_input":["reference input","oracle","ref input"],
    "spend/negative":       ["reject","must fail","should not","deny","prevent"],
    "mint/one_shot":        ["one.shot","utxo","nonce","unique mint"],
    "mint/capped":          ["cap","supply","max","limit.*mint"],
    "mint/cip68":           ["cip.68","reference token","user token","222","100"],
    "withdraw":             ["withdraw","staking","reward","stake"],
    "governance/vote":      ["vote","voter","governance","drep","action"],
    "governance/publish":   ["publish","committee","constitut"],
    "imports_only":         ["import","use "],
    "vesting":              ["vest","cliff","tranche","schedule","unlock"],
}

prompts_lower = [
    (ex.get("prompt","") or ex.get("instruction","")).lower()
    for ex in examples
]

lines = ["=" * 60,
         "H5 — Train vs Benchmark Coverage Gap Analysis",
         "=" * 60, "",
         f"{'Category':<30} {'BM':>4} {'Train~':>8} {'%':>7}  Status",
         "-" * 60]

for cat in sorted(bm_categories):
    bm_n = bm_categories[cat]
    kws  = CATEGORY_KEYWORDS.get(cat, [cat.split("/")[-1]])
    train_n = sum(1 for p in prompts_lower if any(k in p for k in kws))
    pct = train_n / len(examples) * 100
    status = "✅" if pct > 0.5 else "❌ GAP"
    lines.append(f"{cat:<30} {bm_n:>4} {train_n:>8,} {pct:>6.1f}%  {status}")

# must_contain audit
lines += ["", "─" * 60,
          "must_contain / must_not_contain audit (first 20 benchmark prompts):",
          ""]
for p in benchmark[:20]:
    mc  = p.get("must_contain", [])
    mnc = p.get("must_not_contain", [])
    if mc or mnc:
        lines.append(f"  [{p.get('id','?')}] {p.get('prompt','')[:60]}...")
        if mc:  lines.append(f"       must_contain:     {mc}")
        if mnc: lines.append(f"       must_not_contain: {mnc}")

report = "\n".join(lines)
print(report)
(LOGS / "audit_distribution_h5_coverage.txt").write_text(report, encoding="utf-8")

print("\n✅ All reports written to logs/audit_distribution_*.txt")
