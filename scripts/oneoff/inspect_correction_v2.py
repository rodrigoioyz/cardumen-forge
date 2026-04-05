#!/usr/bin/env python3
import json

examples = []
with open('data/processed/dataset_v22.jsonl') as f:
    for line in f:
        ex = json.loads(line.strip())
        examples.append(ex)

subset = [e for e in examples if e.get('source') == 'correction_set_v2']

# Show failing ones by index (1-based from audit: 23,26,29,36,44)
targets = [22, 25, 28, 35, 43]  # 0-based
for i in targets:
    ex = subset[i]
    print(f'=== [{i+1}/48] {ex["instruction"][:80]}')
    print(ex['output'])
    print()
