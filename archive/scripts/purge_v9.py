#!/usr/bin/env python3
"""
purge_v9.py
Elimina ejemplos con patrones contaminantes del dataset_v9_train.jsonl
Produce dataset_v10_train.jsonl sin modificar el original.
"""
import json
from collections import Counter

INPUT  = 'data/processed/dataset_v9_train.jsonl'
OUTPUT = 'data/processed/dataset_v10_train.jsonl'

records = [json.loads(l) for l in open(INPUT)]

# Patrones a purgar — solo en ejemplos que NO son correction_set ni anti-pattern
PURGE_PATTERNS = [
    'cardano.transaction.',   # dot-style import
    'tx.validity_range',      # wrong transaction variable name
]

def is_correction(r):
    return (
        r.get('source') == 'correction_set' or
        'anti' in r.get('topic', '') or
        'correction' in r.get('topic', '') or
        'correction' in r.get('source', '')
    )

kept    = []
removed = []

for r in records:
    if is_correction(r):
        kept.append(r)
        continue

    text = r.get('output', '') + r.get('instruction', '') + r.get('input', '')
    if any(pat in text for pat in PURGE_PATTERNS):
        removed.append(r)
    else:
        kept.append(r)

print(f'Input : {len(records)}')
print(f'Removed: {len(removed)}')
for r in removed:
    print(f'  src={r.get("source")} topic={r.get("topic")}')
    for pat in PURGE_PATTERNS:
        text = r.get('output','') + r.get('instruction','') + r.get('input','')
        if pat in text:
            idx = text.find(pat)
            print(f'    [{pat}] ...{text[max(0,idx-20):idx+50]}...')
print(f'Kept  : {len(kept)}')

with open(OUTPUT, 'w', encoding='utf-8') as f:
    for r in kept:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

print(f'\nEscrito: {OUTPUT}')

# Verify no residual contamination
print('\n=== VERIFICATION ===')
final = [json.loads(l) for l in open(OUTPUT)]
for pat in PURGE_PATTERNS:
    real = [r for r in final if pat in r.get('output','') and not is_correction(r)]
    print(f'  "{pat}" real uses remaining: {len(real)}', '✅' if not real else '❌')
