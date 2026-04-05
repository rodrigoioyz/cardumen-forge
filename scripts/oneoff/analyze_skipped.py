#!/usr/bin/env python3
"""
Analyze why 735 candidates are skipped in add_property_tests.py.
Reports blocking types and patterns to guide expanding the generator.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import importlib.util
spec = importlib.util.spec_from_file_location('apt', ROOT / 'scripts/add_property_tests.py')
apt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apt)

with open(ROOT / 'data/processed/dataset_v23.jsonl') as f:
    examples = [json.loads(l) for l in f if l.strip()]

def has_helpers(code):
    return bool(re.search(r'^(pub )?fn\s+\w+\s*\(', code, re.MULTILINE))

candidates = [ex for ex in examples
    if (re.search(r'^\s*test\s+\w+', ex.get('output',''), re.MULTILINE)
        or has_helpers(ex.get('output','')))
    and '```' not in ex.get('output','')
    and '**' not in ex.get('output','')]

skipped_type_ctr   = Counter()  # arg types that returned None from type_to_fuzzer
skipped_reason_ctr = Counter()  # why generate_properties_for_example returned None
blocking_examples  = []

for ex in candidates:
    code = ex.get('output','')
    result = apt.generate_properties_for_example(code)
    if result is not None:
        continue  # not skipped

    helpers = apt.parse_helpers(code)
    if not helpers:
        skipped_reason_ctr['no_helpers_parsed'] += 1
        continue

    # Has helpers — why did gen_properties return nothing?
    all_none = True
    for h in helpers:
        args = apt.infer_arg_fuzzers(h['args_raw'], fn_name=h['name'])
        if args is None:
            # Some arg type returned None
            for part in re.split(r',\s*(?![^<>]*>)', h['args_raw']):
                part = part.strip()
                if ':' in part:
                    atype = part.split(':', 1)[1].strip()
                    fuzz = apt.type_to_fuzzer(part.split(':')[0].strip(), atype, h['name'])
                    if fuzz is None:
                        skipped_type_ctr[atype] += 1
            skipped_reason_ctr['unhandled_arg_type'] += 1
        elif len(args) > 4:
            skipped_reason_ctr['too_many_args (>4)'] += 1
        else:
            props = apt.gen_properties(h, apt.get_existing_test_names(code))
            if props:
                all_none = False

    if all_none and helpers:
        skipped_reason_ctr.setdefault('all_helpers_produce_no_props', 0)
        skipped_reason_ctr['all_helpers_produce_no_props'] += 1

print(f"Total candidates : {len(candidates)}")
print(f"Skipped          : {sum(skipped_reason_ctr.values())}")
print()
print("Skip reasons:")
for reason, n in skipped_reason_ctr.most_common():
    print(f"  {n:4d}  {reason}")
print()
print("Blocking arg types (no fuzzer):")
for t, n in skipped_type_ctr.most_common(25):
    print(f"  {n:4d}  {t}")
