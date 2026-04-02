#!/usr/bin/env python3
import json
from collections import Counter

records = [json.loads(l) for l in open('data/processed/dataset_v2_train.jsonl')]

print('=== HALLUCINATED API PATTERNS ===')
bad_patterns = [
    'output.value.lovelace',
    'value.get_ada()',
    'output.assets.contains',
    'list.count(',
    'dict.get_int(',
    'ScriptContext {',
    'ProposeSpend',
    'get_current_time',
    'tx.fee',
    'ctx.purpose',
]
for pat in bad_patterns:
    hits = [r for r in records if pat in r.get('output', '')]
    if hits:
        print(f'  [{len(hits)}x] "{pat}"')
        for h in hits[:1]:
            idx = h['output'].find(pat)
            print(f'    src={h.get("source")} topic={h.get("topic")}')
            print(f'    ...{h["output"][max(0,idx-30):idx+70]}...')

print()
print('=== INSTRUCTION LEN DISTRIBUTION ===')
instr_lens = sorted(len(r.get('instruction', '')) for r in records)
n = len(instr_lens)
print(f'min:{instr_lens[0]} med:{instr_lens[n//2]} p90:{instr_lens[int(n*0.9)]} max:{instr_lens[-1]}')

print()
print('=== OUTPUT LEN DISTRIBUTION ===')
out_lens = sorted(len(r.get('output', '')) for r in records)
print(f'min:{out_lens[0]} med:{out_lens[n//2]} p90:{out_lens[int(n*0.9)]} max:{out_lens[-1]}')

print()
print('=== EMPTY INPUT FIELD ===')
empty_input = sum(1 for r in records if not r.get('input', '').strip())
print(f'Empty input: {empty_input} / {len(records)} ({100*empty_input//len(records)}%)')

print()
print('=== CODE PRESENCE IN OUTPUT ===')
has_code = sum(1 for r in records if '```' in r.get('output', '') or 'validator ' in r.get('output', ''))
print(f'With code: {has_code} / {len(records)} ({100*has_code//len(records)}%)')

print()
print('=== TOPIC COVERAGE BY SOURCE ===')
sources = Counter(r.get('source', '?') for r in records)
for src, cnt in sources.most_common():
    topics = set(r.get('topic', '') for r in records if r.get('source') == src)
    print(f'  {src}: {cnt} examples, {len(topics)} unique topics')

print()
print('=== HYDRA PLUTUS SAMPLE (quality check) ===')
hydra_plutus = [r for r in records if r.get('source') == 'hydra_plutus'][:5]
for r in hydra_plutus:
    print(f'  topic={r.get("topic")}')
    print(f'  instr={r.get("instruction")[:90]}')
    print(f'  out[:120]={r.get("output")[:120]}')
    print()

print()
print('=== CIP SAMPLE (quality check) ===')
cips = [r for r in records if r.get('source') == 'cips'][:5]
for r in cips:
    print(f'  topic={r.get("topic")}')
    print(f'  instr={r.get("instruction")[:90]}')
    print(f'  out[:120]={r.get("output")[:120]}')
    print()

print()
print('=== V3 CURATED SAMPLE ===')
v3 = [r for r in records if r.get('source') == 'aiken_v3_curated'][:5]
for r in v3:
    print(f'  topic={r.get("topic")} status={r.get("review_status")}')
    print(f'  instr={r.get("instruction")[:90]}')
    print(f'  out[:150]={r.get("output")[:150]}')
    print()
