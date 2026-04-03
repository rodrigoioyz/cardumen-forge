#!/usr/bin/env python3
"""
audit_structural_dupes.py — Cardumen Forge

Identifies structurally similar examples by computing a normalized hash of
each output. Normalization strips variable names, type names, and validator
names so that two validators doing the same thing with different names hash
to the same value.

Usage:
    python3 scripts/audit_structural_dupes.py
    python3 scripts/audit_structural_dupes.py --source aiken_stdlib
    python3 scripts/audit_structural_dupes.py --source aiken_stdlib --show-clusters 5
    python3 scripts/audit_structural_dupes.py --tag-field  # adds struct_hash to dataset (dry-run)
    python3 scripts/audit_structural_dupes.py --tag-field --apply  # writes hashes to dataset
"""

import re
import json
import hashlib
import argparse
from pathlib import Path
from collections import defaultdict

ROOT    = Path(__file__).parent.parent
DATASET = ROOT / "data" / "processed" / "dataset_v22.jsonl"


def normalize(code: str) -> str:
    """
    Structural normalization — strips away names, keeps skeleton.
    Steps:
      1. Remove comments
      2. Collapse string literals
      3. Replace identifiers that look like user-defined names with placeholders
         (validator names, type names, variable names in let bindings)
      4. Normalize whitespace
    """
    # Remove line comments
    code = re.sub(r'//[^\n]*', '', code)

    # Collapse string literals
    code = re.sub(r'"[^"]*"', '"S"', code)

    # Normalize validator name:  validator foo_bar {  →  validator V {
    code = re.sub(r'\bvalidator\s+\w+\s*\{', 'validator V {', code)

    # Normalize pub type declarations:  pub type FooDatum  →  pub type T
    code = re.sub(r'\bpub\s+type\s+\w+', 'pub type T', code)
    code = re.sub(r'\btype\s+\w+', 'type T', code)

    # Normalize constructor names inside type bodies (UpperCase identifiers)
    # Only inside braces after type T — too aggressive globally, skip

    # Normalize let bindings:  let owner_key =  →  let v =
    code = re.sub(r'\blet\s+\w+\s*=', 'let v =', code)

    # Normalize function parameter names (lower_snake_case that aren't keywords)
    KEYWORDS = {
        'use', 'validator', 'fn', 'let', 'if', 'else', 'when', 'is',
        'type', 'pub', 'opaque', 'test', 'todo', 'fail', 'and', 'or',
        'true', 'false', 'expect', 'trace', 'as', 'in',
        # handler names
        'spend', 'mint', 'withdraw', 'publish', 'vote', 'propose',
        # common stdlib names we want to KEEP
        'list', 'assets', 'transaction', 'interval', 'dict', 'pairs',
        'extra_signatories', 'validity_range', 'inputs', 'outputs',
        'reference_inputs', 'mint', 'withdrawals', 'certificates',
        'lovelace_of', 'quantity_of', 'has_nft', 'policies', 'tokens',
        'flatten', 'any', 'all', 'has', 'filter', 'map', 'foldl',
        'length', 'find', 'count',
        'is_entirely_after', 'is_entirely_before',
        'find_input', 'find_script_outputs',
        'Finite', 'NegativeInfinity', 'PositiveInfinity',
        'Transaction', 'OutputReference', 'Input', 'Output',
        'PolicyId', 'AssetName', 'Value', 'Lovelace',
        'VerificationKeyHash', 'ScriptHash', 'Credential',
        'Voter', 'Certificate', 'ProposalProcedure',
        'Option', 'Some', 'None', 'Bool', 'Int', 'ByteArray', 'Data',
        'True', 'False',
        'self', 'own_ref', 'policy_id', 'account', 'voter', 'cert',
        'datum', 'redeemer',
    }

    def replace_ident(m):
        word = m.group(0)
        if word in KEYWORDS:
            return word
        # Keep ALL_CAPS (constants) and module-path segments
        if word.isupper():
            return word
        # Keep single letters (common in generic types)
        if len(word) == 1:
            return word
        return 'x'

    code = re.sub(r'\b[a-z][a-z0-9_]*\b', replace_ident, code)

    # Normalize whitespace
    code = re.sub(r'\s+', ' ', code).strip()

    return code


def struct_hash(code: str) -> str:
    normalized = normalize(code)
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source",        default=None,  help="Filter by source (e.g. aiken_stdlib)")
    parser.add_argument("--show-clusters", type=int, default=3, help="Show N largest clusters with examples")
    parser.add_argument("--tag-field",     action="store_true", help="Add struct_hash field to examples")
    parser.add_argument("--apply",         action="store_true", help="Write changes (only with --tag-field)")
    parser.add_argument("--min-cluster",   type=int, default=3, help="Min cluster size to report")
    args = parser.parse_args()

    examples = []
    with DATASET.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    # Filter subset
    subset = [
        (i, e) for i, e in enumerate(examples)
        if (args.source is None or e.get("source") == args.source)
        and e.get("output", "").strip()
    ]

    print(f"\nDataset : {len(examples)} total examples")
    print(f"Subset  : {len(subset)} examples" + (f" (source={args.source})" if args.source else ""))

    # Compute hashes
    clusters = defaultdict(list)  # hash → list of (idx, example)
    for i, e in subset:
        h = struct_hash(e["output"])
        clusters[h].append((i, e))

    # Stats
    sizes = sorted([len(v) for v in clusters.values()], reverse=True)
    unique      = sum(1 for s in sizes if s == 1)
    dupes       = sum(1 for s in sizes if s > 1)
    dupe_examples = sum(s - 1 for s in sizes if s > 1)  # extras beyond first

    print(f"\nStructural clusters  : {len(clusters)}")
    print(f"  Unique (size=1)    : {unique}")
    print(f"  Duplicate clusters : {dupes}  (clusters with 2+ structurally identical examples)")
    print(f"  Redundant examples : {dupe_examples}  (could be removed without losing coverage)")
    print(f"\nCluster size distribution:")
    from collections import Counter
    size_dist = Counter(sizes)
    for sz in sorted(size_dist.keys(), reverse=True)[:15]:
        bar = "█" * min(sz, 40)
        print(f"  size {sz:3d}: {size_dist[sz]:4d} clusters  {bar}")

    # Show largest clusters
    if args.show_clusters > 0:
        print(f"\nTop {args.show_clusters} largest clusters:")
        top = sorted(clusters.values(), key=len, reverse=True)[:args.show_clusters]
        for cluster in top:
            sz = len(cluster)
            first_idx, first_ex = cluster[0]
            print(f"\n  [{sz} examples] hash={struct_hash(first_ex['output'])}")
            print(f"  Source    : {first_ex.get('source','?')}")
            print(f"  Status    : {first_ex.get('review_status','?')}")
            print(f"  Instruction: {first_ex['instruction'][:80]}")
            print(f"  Normalized : {normalize(first_ex['output'])[:120]}...")
            if sz > 1:
                print(f"  Others:")
                for _, ex in cluster[1:min(4, sz)]:
                    print(f"    - {ex['instruction'][:70]}")

    # Tag field
    if args.tag_field:
        print(f"\n{'--apply mode' if args.apply else 'DRY RUN'}: adding struct_hash field...")
        changed = 0
        for i, e in subset:
            h = struct_hash(e["output"])
            if examples[i].get("struct_hash") != h:
                examples[i]["struct_hash"] = h
                changed += 1
        print(f"  Would tag {changed} examples")
        if args.apply:
            with DATASET.open("w", encoding="utf-8") as f:
                for ex in examples:
                    f.write(json.dumps(ex, ensure_ascii=False) + "\n")
            print(f"  Written to {DATASET}")


if __name__ == "__main__":
    main()
