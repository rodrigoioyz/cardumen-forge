#!/usr/bin/env python3
"""One-shot patch: fix the broken positive_mints example at idx 3082."""
import json
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DATASET = ROOT / "data" / "processed" / "dataset_v22.jsonl"

FIXED_CODE = (
    "use aiken/collection/list\n"
    "use cardano/assets\n"
    "use cardano/assets.{AssetName, PolicyId, Value}\n"
    "use cardano/transaction.{Transaction}\n"
    "\n"
    "/// Keep only entries where quantity > 0.\n"
    "fn positive_mints(v: Value) -> List<(PolicyId, AssetName, Int)> {\n"
    "  list.filter(\n"
    "    assets.flatten(v),\n"
    "    fn(entry) {\n"
    "      let (_, _, qty) = entry\n"
    "      qty > 0\n"
    "    },\n"
    "  )\n"
    "}\n"
    "\n"
    "validator my_policy {\n"
    "  mint(_redeemer: Data, _policy_id: PolicyId, self: Transaction) -> Bool {\n"
    "    let positives = positive_mints(self.mint)\n"
    "    list.all(\n"
    "      positives,\n"
    "      fn(entry) {\n"
    "        let (_, _, qty) = entry\n"
    "        qty > 0\n"
    "      },\n"
    "    )\n"
    "  }\n"
    "}\n"
    "\n"
    "test positive_mints_empty_value() {\n"
    "  list.length(positive_mints(assets.zero)) == 0\n"
    "}\n"
    "\n"
    "test positive_mints_lovelace_only() {\n"
    "  list.length(positive_mints(assets.from_lovelace(1_000_000))) == 1\n"
    "}\n"
)

examples = []
with DATASET.open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            examples.append(json.loads(line))

TARGET_IDX = 3082
ex = examples[TARGET_IDX]
assert "positive_mints" in ex.get("output", ""), f"Wrong example at idx {TARGET_IDX}"

ex["output"] = FIXED_CODE
ex["review_status"] = "VERIFIED_V3_ALIGNED"

with DATASET.open("w", encoding="utf-8") as f:
    for e in examples:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

print(f"Patched idx {TARGET_IDX}: {ex['instruction'][:70]}")
print(f"Written: {DATASET}")
