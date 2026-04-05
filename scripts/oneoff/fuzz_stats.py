import json, re
from collections import Counter

with open('/home/rodrigo/entrenamiento/data/processed/dataset_v23.jsonl') as f:
    examples = [json.loads(l) for l in f if l.strip()]

total = len(examples)
has_fuzz = [ex for ex in examples if 'use aiken/fuzz' in ex.get('output','')]
has_unit = [ex for ex in examples if re.search(r'^\s*test\s+\w+', ex.get('output',''), re.MULTILINE)]
has_prop = [ex for ex in examples if re.search(r'^\s*test\s+prop_\w+', ex.get('output',''), re.MULTILINE)]
is_code  = [ex for ex in examples if '```' not in ex.get('output','')
            and re.search(r'\bvalidator\b|^pub fn|^pub type|^use ', ex.get('output',''), re.MULTILINE)]

print(f"Total ejemplos       : {total}")
print(f"Es codigo Aiken      : {len(is_code)} ({100*len(is_code)/total:.1f}%)")
print(f"Tiene unit tests     : {len(has_unit)} ({100*len(has_unit)/total:.1f}%)")
print(f"Tiene property tests : {len(has_prop)} ({100*len(has_prop)/total:.1f}%)")
print(f"Usa aiken/fuzz       : {len(has_fuzz)} ({100*len(has_fuzz)/total:.1f}%)")
print()
print("Sources con property tests:")
src_prop = Counter(ex['source'] for ex in has_prop)
for src, n in src_prop.most_common():
    total_src = sum(1 for ex in examples if ex['source'] == src)
    print(f"  {src:<35} {n:3d}/{total_src}")
print()

# Count property tests per example
prop_counts = []
for ex in has_prop:
    props = re.findall(r'^\s*test\s+prop_\w+', ex.get('output',''), re.MULTILINE)
    prop_counts.append(len(props))
if prop_counts:
    print(f"Promedio props/ejemplo : {sum(prop_counts)/len(prop_counts):.1f}")
    print(f"Max props en 1 ejemplo : {max(prop_counts)}")
