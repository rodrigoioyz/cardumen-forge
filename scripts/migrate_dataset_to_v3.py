#!/usr/bin/env python3
"""
migrate_dataset_to_v3.py — Cardumen Forge
Migrates dataset to stdlib v3.0.0 patterns. Output: dataset_v22.jsonl

Changes applied:
  1. Record field commas   — adds comma after every field in pub type blocks
  2. Constructor renames   — DeregisterCredential, VerificationKeyCredential, etc.
  3. Interval<T>           — removes generic parameter
  4. aiken/time / PosixTime — removes or replaces
  5. MintedValue           — replaces with Value

Usage:
    python3 scripts/migrate_dataset_to_v3.py --dry-run         # report only
    python3 scripts/migrate_dataset_to_v3.py --apply           # write in-place
    python3 scripts/migrate_dataset_to_v3.py --apply --out data/processed/dataset_v22.jsonl
"""

import re
import json
import argparse
import shutil
from pathlib import Path
from collections import defaultdict

ROOT       = Path(__file__).parent.parent
INPUT_FILE = ROOT / "data" / "processed" / "dataset_v22.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# Fix 1 — Record field commas
# ─────────────────────────────────────────────────────────────────────────────

def fix_record_commas(code: str) -> tuple[str, int]:
    """
    Add commas after record fields that are missing them.
    Targets: pub type Foo { field: Type\n  field2: Type2 }
    Returns (fixed_code, number_of_commas_added).
    """
    added = 0

    def fix_type_block(m: re.Match) -> str:
        nonlocal added
        block_start = m.group(0)  # "pub type Name {"
        rest_start  = m.end()
        return block_start  # we process inside separately

    # Find all pub type blocks and fix fields inside them
    def process_type_block(match: re.Match) -> str:
        nonlocal added
        header = match.group(1)   # "pub type Name "
        body   = match.group(2)   # content between { }

        lines = body.split('\n')
        new_lines = []

        for i, line in enumerate(lines):
            stripped = line.rstrip()

            # Is this a field line? Pattern: optional spaces + name: Type
            # Ends without comma, not a comment, not empty, not closing brace
            if (re.match(r'^\s+\w+\s*:', stripped)
                    and not stripped.rstrip().endswith(',')
                    and not stripped.rstrip().endswith('{')
                    and '//' not in stripped):
                stripped += ','
                added += 1

            new_lines.append(stripped)

        return f"{header}{{{'\n'.join(new_lines)}}}"

    # Match: pub type Name { ... } (single-level, non-nested)
    pattern = re.compile(
        r'(pub\s+type\s+\w+(?:\s*\([^)]*\))?\s*)\{([^{}]*)\}',
        re.DOTALL
    )
    fixed = pattern.sub(process_type_block, code)
    return fixed, added


# ─────────────────────────────────────────────────────────────────────────────
# Fix 2 — Constructor / module renames
# ─────────────────────────────────────────────────────────────────────────────

RENAMES = [
    # ── stdlib v3 breaking changes ────────────────────────────────────────────
    # Ref: https://github.com/aiken-lang/stdlib/blob/main/CHANGELOG.md
    (r'\bDeregisterCredential\b',      'UnregisterCredential',   'DeregisterCredential→UnregisterCredential'),
    (r'\bVerificationKeyCredential\b', 'VerificationKey',        'VerificationKeyCredential→VerificationKey'),
    (r'\bScriptCredential\b',          'Script',                 'ScriptCredential→Script'),
    (r'\bMintedValue\b',               'Value',                  'MintedValue→Value'),
    # Interval<X> → Interval (remove generic parameter)
    (r'\bInterval\s*<[^>]+>',          'Interval',               'Interval<T>→Interval'),

    # ── Voter constructors — correct names per stdlib v3 ─────────────────────
    # Ref: https://github.com/aiken-lang/stdlib/blob/main/lib/cardano/governance.ak
    # pub type Voter {
    #   ConstitutionalCommitteeMember(Credential)  ← was ConstitutionalCommittee(
    #   DelegateRepresentative(Credential)
    #   StakePool(VerificationKeyHash)             ← was StakePoolOperator(
    # }
    #
    # NOTE: negative lookahead (?!\s*\{) avoids touching the GovernanceAction
    # constructor `ConstitutionalCommittee { ... }` which is correct as-is.
    # Covers both usage `ConstitutionalCommittee(` AND imports `ConstitutionalCommittee,`
    (r'\bConstitutionalCommittee\b(?!\s*\{)', 'ConstitutionalCommitteeMember', 'ConstitutionalCommittee→ConstitutionalCommitteeMember'),
    # Global rename covers both imports and usage (StakePoolOperator was never valid in v3)
    (r'\bStakePoolOperator\b',               'StakePool',                     'StakePoolOperator→StakePool'),

    # ── GovernanceAction constructor names — correct per stdlib v3 ────────────
    # Ref: https://github.com/aiken-lang/stdlib/blob/main/lib/cardano/governance.ak
    # pub type GovernanceAction {
    #   ProtocolParameters { ... }   ← LLMs hallucinate as ParameterChange
    #   HardFork { ... }
    #   TreasuryWithdrawal { ... }   ← LLMs hallucinate as TreasuryWithdrawals (plural)
    #   NoConfidence { ... }
    #   ConstitutionalCommittee { ... }
    #   NewConstitution { ... }
    #   NicePoll                     ← LLMs hallucinate as InfoAction
    # }
    (r'\bParameterChange\b',      'ProtocolParameters', 'ParameterChange→ProtocolParameters'),
    (r'\bTreasuryWithdrawals\b',  'TreasuryWithdrawal', 'TreasuryWithdrawals→TreasuryWithdrawal'),
    (r'\bInfoAction\b',           'NicePoll',           'InfoAction→NicePoll'),

    # ── ProposalProcedure field name ──────────────────────────────────────────
    # Ref: pub type ProposalProcedure { deposit, return_address, governance_action }
    # LLMs hallucinate `.value` as the GovernanceAction field name.
    (r'\bproposal\.value\b', 'proposal.governance_action', 'proposal.value→proposal.governance_action'),

    # ── transaction.Finite / transaction.ValidityRange ────────────────────────
    # These belong to aiken/interval, not cardano/transaction.
    # `Finite` is a constructor of IntervalBoundType; `ValidityRange` is `Interval`.
    (r'\btransaction\.Finite\b',        'Finite',    'transaction.Finite→Finite'),
    (r'\btransaction\.ValidityRange\b', 'Interval',  'transaction.ValidityRange→Interval'),

    # ── RetireStakePool field names ───────────────────────────────────────────
    # Ref: RetireStakePool { stake_pool: StakePoolId, at_epoch: Int }
    # LLMs hallucinate `id` for the pool id field.
    (r'\bRetireStakePool\s*\{\s*id\b',  'RetireStakePool { stake_pool', 'RetireStakePool.id→stake_pool'),
]


def fix_renames(code: str) -> tuple[str, dict]:
    counts = defaultdict(int)
    for pattern, replacement, desc in RENAMES:
        new_code, n = re.subn(pattern, replacement, code)
        if n:
            counts[desc] += n
        code = new_code
    return code, dict(counts)


# ─────────────────────────────────────────────────────────────────────────────
# Fix 3 — aiken/time and PosixTime
# ─────────────────────────────────────────────────────────────────────────────

def fix_time_module(code: str) -> tuple[str, int]:
    """
    Remove 'use aiken/time' import lines.
    Replace PosixTime type annotations with Int.
    """
    removed = 0

    # Remove import line
    new_code, n = re.subn(r'^\s*use\s+aiken/time[^\n]*\n?', '', code, flags=re.MULTILINE)
    removed += n
    code = new_code

    # Replace PosixTime with Int in type annotations
    new_code, n = re.subn(r'\bPosixTime\b', 'Int', code)
    removed += n
    code = new_code

    return code, removed


# ─────────────────────────────────────────────────────────────────────────────
# Fix 4 — Make top-level custom types pub
# ─────────────────────────────────────────────────────────────────────────────

def fix_private_type_leak(code: str) -> tuple[str, int]:
    """
    Add 'pub' to top-level type definitions that lack it.

    Validators in Aiken v3 are public, so any type used in a handler signature
    must also be pub. Lines like:
        type Foo {          →  pub type Foo {
        type Bar = Baz      →  pub type Bar = Baz

    Pattern: lines that start exactly with 'type ' (no leading spaces, no
    preceding 'pub' or 'opaque') are made public. Already-public ('pub type')
    and opaque types ('opaque type') are left unchanged.
    """
    new_code, n = re.subn(r'^type\b', 'pub type', code, flags=re.MULTILINE)
    return new_code, n


# ─────────────────────────────────────────────────────────────────────────────
# Fix 5 — Certificate record field renames (context-specific)
# ─────────────────────────────────────────────────────────────────────────────

# Constructors where the credential field is NOT named `credential`:
#   Ref: https://github.com/aiken-lang/stdlib/blob/main/lib/cardano/certificate.ak
#
#   DRep certs → `delegate_representative`
#   CC certs   → `constitutional_committee_member`
#
# Note: RegisterCredential / UnregisterCredential / DelegateCredential /
#       RegisterAndDelegateCredential all correctly use `credential` — leave them alone.
_CERT_FIELD_RENAMES = [
    # (constructor, wrong_field, correct_field)
    ("RegisterDelegateRepresentative",    "credential", "delegate_representative"),
    ("UnregisterDelegateRepresentative",  "credential", "delegate_representative"),
    ("UpdateDelegateRepresentative",      "credential", "delegate_representative"),
    ("AuthorizeConstitutionalCommitteeProxy", "credential", "constitutional_committee_member"),
    ("RetireFromConstitutionalCommittee", "credential", "constitutional_committee_member"),
]

def fix_certificate_fields(code: str) -> tuple[str, int]:
    """
    For DRep and CC Certificate constructors, rename the `credential` field
    to its correct name. Uses re.sub with a callback to locate each
    constructor's record body and rename only within it.
    """
    count = 0
    for constructor, wrong, correct in _CERT_FIELD_RENAMES:
        # Match the constructor + its record body: Foo { ... }
        # The body can span multiple lines and contain nested braces up to
        # depth 1 (record fields don't nest further in these constructors).
        pat = re.compile(
            r'\b' + re.escape(constructor) + r'\s*\{([^{}]*)\}',
            re.DOTALL,
        )

        def replacer(m, wrong=wrong, correct=correct):
            body = m.group(1)
            new_body, n = re.subn(r'\b' + re.escape(wrong) + r'\b', correct, body)
            replacer.n += n
            return m.group(0)[:m.group(0).index('{')+1] + new_body + '}'

        replacer.n = 0
        code = pat.sub(replacer, code)
        count += replacer.n

    return code, count


# ─────────────────────────────────────────────────────────────────────────────
# Apply all fixes to one example
# ─────────────────────────────────────────────────────────────────────────────

def migrate_example(ex: dict) -> tuple[dict, dict]:
    """Returns (migrated_example, change_report)."""
    output = ex.get("output", "")
    if not output:
        return ex, {}

    report = {}

    output, n_commas    = fix_record_commas(output)
    output, rename_map  = fix_renames(output)
    output, n_time      = fix_time_module(output)
    output, n_pub       = fix_private_type_leak(output)
    output, n_cert      = fix_certificate_fields(output)

    if n_commas:
        report["commas_added"] = n_commas
    if rename_map:
        report.update(rename_map)
    if n_time:
        report["time_module_removed"] = n_time
    if n_pub:
        report["type_made_pub"] = n_pub
    if n_cert:
        report["cert_field_renamed"] = n_cert

    new_ex = {**ex, "output": output}
    return new_ex, report


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    parser.add_argument("--apply",   action="store_true", help="Apply changes")
    parser.add_argument("--out",     default=None,        help="Output path (default: overwrite input)")
    parser.add_argument("--input",   default=str(INPUT_FILE), help="Input JSONL file")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    input_path  = Path(args.input)
    output_path = Path(args.out) if args.out else input_path

    examples = []
    with input_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    print(f"Loaded  : {len(examples)} examples from {input_path.name}")

    # Migrate all
    migrated      = []
    total_changes = defaultdict(int)
    changed_count = 0

    for ex in examples:
        new_ex, report = migrate_example(ex)
        migrated.append(new_ex)
        if report:
            changed_count += 1
            for k, v in report.items():
                total_changes[k] += v

    # Report
    print(f"\nExamples changed : {changed_count}/{len(examples)}")
    print("\nChanges by type:")
    for k, v in sorted(total_changes.items(), key=lambda x: -x[1]):
        print(f"  {v:5d}  {k}")

    if args.dry_run:
        # Show a few examples of what changed
        print("\n── Sample diffs (first 5 changed examples) ──")
        shown = 0
        for orig, new_ex in zip(examples, migrated):
            if orig["output"] != new_ex["output"]:
                orig_lines = set(orig["output"].splitlines())
                new_lines  = set(new_ex["output"].splitlines())
                added   = [l for l in new_ex["output"].splitlines() if l not in orig_lines][:3]
                removed = [l for l in orig["output"].splitlines() if l not in new_lines][:3]
                print(f"\n  instruction: {orig.get('instruction','')[:70]}")
                for l in removed:
                    print(f"  - {l.rstrip()}")
                for l in added:
                    print(f"  + {l.rstrip()}")
                shown += 1
                if shown >= 5:
                    break
        print("\nRe-run with --apply to write changes.")
        return

    # Write
    if output_path == input_path:
        backup = input_path.with_suffix(".jsonl.v21_backup")
        if not backup.exists():
            shutil.copy2(input_path, backup)
            print(f"\nBackup  : {backup}")
        else:
            print(f"\nBackup already exists: {backup} (not overwriting)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for ex in migrated:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    written = sum(1 for _ in output_path.open(encoding="utf-8"))
    print(f"\nWritten : {written} examples → {output_path}")
    print("\nDataset is now v22-ready. Next step:")
    print("  python3 scripts/generate_v3_compat_examples.py --write --append-to-v21")


if __name__ == "__main__":
    main()
