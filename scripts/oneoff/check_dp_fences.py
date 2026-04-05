#!/usr/bin/env python3
import json

examples = []
with open('data/processed/dataset_v22.jsonl') as f:
    for line in f:
        ex = json.loads(line.strip())
        if ex.get('source') == 'aiken_design_patterns':
            examples.append(ex)

has_fence  = [e for e in examples if '```' in e['output']]
pure_code  = [e for e in examples if not '```' in e['output'] and
              (e['output'].strip().startswith('use ') or e['output'].strip().startswith('validator '))]
pure_prose = [e for e in examples if e not in has_fence and e not in pure_code]

print(f'has fence:  {len(has_fence)}')
print(f'pure code:  {len(pure_code)}')
print(f'pure prose: {len(pure_prose)}')

aiken_fence = [e for e in has_fence if '```aiken' in e['output']]
rs_fence    = [e for e in has_fence if '```rs' in e['output'] and '```aiken' not in e['output']]
other_fence = [e for e in has_fence if '```aiken' not in e['output'] and '```rs' not in e['output']]

print(f'\nOf fenced:')
print(f'  ```aiken  : {len(aiken_fence)}')
print(f'  ```rs     : {len(rs_fence)}')
print(f'  other     : {len(other_fence)}')

print('\n=== aiken fence sample:')
if aiken_fence:
    print(aiken_fence[0]['instruction'][:80])
    print(aiken_fence[0]['output'][:500])
print('\n=== rs fence sample:')
if rs_fence:
    print(rs_fence[0]['instruction'][:80])
    print(rs_fence[0]['output'][:500])
print('\n=== other fence sample:')
if other_fence:
    print(other_fence[0]['instruction'][:80])
    print(other_fence[0]['output'][:500])
