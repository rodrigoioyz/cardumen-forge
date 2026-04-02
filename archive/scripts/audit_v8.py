#!/usr/bin/env python3
import json, re
from collections import Counter

records = [json.loads(l) for l in open('data/processed/dataset_v8_train.jsonl')]
n = len(records)

sources = Counter(r.get('source','?') for r in records)
langs   = Counter(r.get('lang','?') for r in records)

print(f'=== STATS ===')
print(f'Total: {n}')
print(f'Langs: {dict(langs)} ({100*langs["en"]/n:.0f}% EN / {100*langs["es"]/n:.0f}% ES)')
for src, cnt in sources.most_common():
    topics = set(r.get('topic','') for r in records if r.get('source') == src)
    print(f'  {src}: {cnt} ({100*cnt/n:.1f}%) / {len(topics)} topics')

print()
print('=== CONTAMINATION FINAL CHECK ===')
checks = ['ScriptContext','ctx.purpose','ctx.transaction','PlutusTx','plutus-tx',
          'unstableMakeIsData','BuiltinData','TxInInfo',' :: ','hydra_plutus']
for pat in checks:
    hits = [r for r in records if pat in r.get('output','') or pat in r.get('instruction','')]
    print(f'  "{pat}": {len(hits)}', '✅' if not hits else '⚠️')

print()
print('=== V3 SIGNAL ===')
v3_signals = ['assets.lovelace_of(','assets.quantity_of(','assets.has_nft(',
              '_own_ref, self)','self.inputs','self.outputs','self.mint',
              'self.validity_range','self.extra_signatories','self.reference_inputs',
              'expect Some(','use cardano/assets','use cardano/transaction']
unique_v3 = set()
for pat in v3_signals:
    hits = [r for r in records if pat in r.get('output','')]
    for h in hits: unique_v3.add(id(h))
    print(f'  "{pat}": {len(hits)}')
print(f'\n  Ejemplos con ≥1 señal v3: {len(unique_v3)} / {n} ({100*len(unique_v3)/n:.1f}%)')

print()
print('=== CODE VS EXPLANATION ===')
has_validator = sum(1 for r in records if 'validator ' in r.get('output',''))
has_code      = sum(1 for r in records if '```' in r.get('output',''))
pure_text     = sum(1 for r in records if '```' not in r.get('output','') and 'validator ' not in r.get('output','') and 'fn ' not in r.get('output',''))
print(f'  validator keyword : {has_validator} ({100*has_validator/n:.1f}%)')
print(f'  code blocks       : {has_code} ({100*has_code/n:.1f}%)')
print(f'  pure text         : {pure_text} ({100*pure_text/n:.1f}%)')

print()
print('=== SIGNAL DENSITY ===')
high   = [r for r in records if r.get('source') in ('aiken_v3_curated','aiken_docs','aiken_design_patterns')]
medium = [r for r in records if r.get('source') in ('aiken_stdlib','cips')]
low    = [r for r in records if r.get('source') in ('hydra_docs',)]
print(f'  High   (v3 curated + docs + patterns): {len(high)} ({100*len(high)/n:.1f}%)')
print(f'  Medium (stdlib + CIPs):                {len(medium)} ({100*len(medium)/n:.1f}%)')
print(f'  Low    (hydra_docs):                   {len(low)} ({100*len(low)/n:.1f}%)')

print()
print('=== OUTPUT LENGTH ===')
lens = sorted(len(r.get('output','')) for r in records)
print(f'  p25:{lens[n//4]} p50:{lens[n//2]} p75:{lens[3*n//4]} p90:{lens[int(n*0.9)]}')
