#!/usr/bin/env python3
import json, re
from collections import Counter

records = [json.loads(l) for l in open('data/processed/dataset_v9_train.jsonl')]
n = len(records)

sources = Counter(r.get('source','?') for r in records)
print(f'Total: {n}')
for src, cnt in sources.most_common():
    print(f'  {src}: {cnt} ({100*cnt/n:.1f}%)')

# Patrones v3 positivos — cuántos ejemplos los usan en output
print('\n=== V3 API COVERAGE (examples that USE each API in output) ===')
apis = [
    ('assets.lovelace_of(',    'ADA check'),
    ('assets.quantity_of(',    'token quantity'),
    ('assets.has_nft(',        'NFT check'),
    ('self.extra_signatories', 'signatories'),
    ('self.validity_range',    'time'),
    ('self.inputs',            'inputs'),
    ('self.outputs',           'outputs'),
    ('self.mint',              'mint field'),
    ('self.reference_inputs',  'ref inputs'),
    ('list.has(',              'list.has'),
    ('list.any(',              'list.any'),
    ('list.all(',              'list.all'),
    ('list.count(',            'list.count'),
    ('interval.contains(',     'interval.contains'),
    ('interval.is_entirely',   'interval.is_entirely_*'),
    ('use cardano/assets',     'import cardano/assets'),
    ('use cardano/transaction','import cardano/transaction'),
    ('use aiken/interval',     'import aiken/interval'),
    ('use aiken/collection/list','import aiken/collection/list'),
    ('expect Some(',           'datum unwrap'),
    ('Option<',                'Option datum type'),
    ('own_ref, self)',         'v3 handler signature'),
]
for pat, label in apis:
    hits = sum(1 for r in records if pat in r.get('output',''))
    bar = '█' * (hits // 5)
    print(f'  {label:30s}: {hits:4d}  {bar}')

# Comportamientos del modelo que queremos evitar
print('\n=== HALLUCINATION PATTERNS STILL IN DATASET (as real usage, not corrections) ===')
bad = [
    'transaction.signatories(',
    'list.has_any(',
    'interval.is_after(',
    'output.value.lovelace',
    'tx.validity_range',
    'cardano.transaction.',
    'cardano/governance/transaction',
]
for pat in bad:
    real = [r for r in records
            if pat in r.get('output','')
            and 'correction' not in r.get('source','')
            and 'anti' not in r.get('topic','')
            and 'correction' not in r.get('topic','')]
    if real:
        print(f'  ❌ "{pat}": {len(real)} real uses (not corrections)')
        for h in real[:1]:
            idx = h['output'].find(pat)
            print(f'     src={h.get("source")} topic={h.get("topic")}')
            print(f'     ...{h["output"][max(0,idx-30):idx+60]}...')
    else:
        print(f'  ✅ "{pat}": 0 real uses')

# Validator signature check
print('\n=== HANDLER SIGNATURE CORRECTNESS ===')
correct_sig   = sum(1 for r in records if 'own_ref, self)' in r.get('output',''))
missing_ownref = sum(1 for r in records if
    'fn spend(' in r.get('output','') and
    'own_ref' not in r.get('output','') and
    'correction' not in r.get('source',''))
print(f'  Correct v3 signature (own_ref, self): {correct_sig}')
print(f'  fn spend() WITHOUT own_ref (wrong):   {missing_ownref}')

# ADA/lovelace usage correctness
print('\n=== ADA PAYMENT PATTERN COVERAGE ===')
correct_ada   = sum(1 for r in records if 'assets.lovelace_of(' in r.get('output',''))
wrong_ada     = sum(1 for r in records if
    'output.value.lovelace' in r.get('output','') and
    'correction' not in r.get('source','') and
    'anti' not in r.get('topic',''))
payment_ctx   = sum(1 for r in records if
    any(k in r.get('output','').lower() for k in ['price', 'payment', 'royalt', 'lovelace >= ']))
print(f'  assets.lovelace_of() in output: {correct_ada}')
print(f'  output.value.lovelace (wrong):  {wrong_ada}')
print(f'  Payment context examples:       {payment_ctx}')

# Gap: payment validators combining lovelace + signatories + NFT
print('\n=== COMPLEX VALIDATOR COVERAGE (combinations) ===')
combos = [
    ('lovelace + signatories', 'assets.lovelace_of(', 'self.extra_signatories'),
    ('lovelace + validity',    'assets.lovelace_of(', 'self.validity_range'),
    ('NFT + signatories',      'assets.has_nft(',     'self.extra_signatories'),
    ('NFT + lovelace',         'assets.has_nft(',     'assets.lovelace_of('),
    ('quantity + lovelace',    'assets.quantity_of(', 'assets.lovelace_of('),
    ('mint + signatories',     'self.mint',           'self.extra_signatories'),
]
for label, p1, p2 in combos:
    hits = sum(1 for r in records if p1 in r.get('output','') and p2 in r.get('output',''))
    print(f'  {label:30s}: {hits}')

# Correction set coverage
print('\n=== CORRECTION SET STATS ===')
correction = [r for r in records if r.get('source') == 'correction_set']
print(f'  correction_set examples: {len(correction)}')
topics_c = Counter(r.get('topic','') for r in correction)
for t, c in topics_c.most_common():
    print(f'    {t}: {c}')
