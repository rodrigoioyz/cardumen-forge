#!/usr/bin/env python3
import json, re

examples = []
with open('data/processed/dataset_v22.jsonl') as f:
    for line in f:
        ex = json.loads(line.strip())
        if ex.get('source') == 'aiken_design_patterns':
            examples.append(ex)

aiken_fence = [e for e in examples if '```aiken' in e['output']]

# Extract the code inside ```aiken ... ``` blocks
fence_re = re.compile(r'```aiken\n(.*?)```', re.DOTALL)

standalone = []  # has 'validator' or starts with 'use' — likely compilable
fragment   = []  # just a type def, fn, snippet

for ex in aiken_fence:
    blocks = fence_re.findall(ex['output'])
    code = '\n'.join(blocks).strip()
    if 'validator' in code or code.startswith('use '):
        standalone.append(ex)
    else:
        fragment.append(ex)

print(f'aiken fence total: {len(aiken_fence)}')
print(f'  standalone (validator/use): {len(standalone)}')
print(f'  fragment only:              {len(fragment)}')

print('\n=== standalone sample:')
for ex in standalone[:2]:
    blocks = fence_re.findall(ex['output'])
    print('INST:', ex['instruction'][:70])
    print('CODE:', '\n'.join(blocks)[:300])
    print()

print('\n=== fragment sample:')
for ex in fragment[:2]:
    blocks = fence_re.findall(ex['output'])
    print('INST:', ex['instruction'][:70])
    print('CODE:', '\n'.join(blocks)[:300])
    print()
