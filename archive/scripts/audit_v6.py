#!/usr/bin/env python3
import json, re
from collections import Counter

path = 'data/processed/dataset_v6_clean.jsonl'
records = [json.loads(l) for l in open(path)]
n = len(records)

def search(pat, field='output', case=False):
    hits = []
    for r in records:
        text = r.get(field, '')
        if not case:
            if pat.lower() in text.lower():
                hits.append(r)
        else:
            if pat in text:
                hits.append(r)
    return hits

def search_all(pat):
    return [r for r in records if
            pat.lower() in r.get('output','').lower() or
            pat.lower() in r.get('instruction','').lower() or
            pat.lower() in r.get('input','').lower()]

print(f'=== BASIC STATS ===')
sources = Counter(r.get('source','?') for r in records)
langs   = Counter(r.get('lang','?') for r in records)
print(f'Total: {n}')
print(f'Langs: {dict(langs)}')
for src, cnt in sources.most_common():
    topics = set(r.get('topic','') for r in records if r.get('source') == src)
    print(f'  {src}: {cnt} examples / {len(topics)} unique topics')

print()
print('=== V2 CONTAMINATION — FINAL CHECK ===')
v2 = ['ScriptContext', 'ctx.purpose', 'ctx.transaction', 'ctx.info', 'ctx.fee',
      'context.transaction', 'context.purpose', 'scriptContext']
for pat in v2:
    hits = search_all(pat)
    status = '✅ CLEAN' if not hits else f'❌ {len(hits)} HITS'
    print(f'  "{pat}": {status}')
    for h in hits[:1]:
        for field in ('output','instruction'):
            if pat.lower() in h.get(field,'').lower():
                idx = h[field].lower().find(pat.lower())
                print(f'    [{field}] ...{h[field][max(0,idx-30):idx+70]}...')

print()
print('=== PLUTUS/HASKELL LEAKAGE — FINAL CHECK ===')
plutus = ['unstableMakeIsData', 'BuiltinData', 'TxInInfo', 'TxOutRef',
          'mkValidator', ' :: ', 'FromData', 'ToData', 'PlutusTx',
          'Constr ', 'plutus-tx', 'plutusV2']
for pat in plutus:
    hits = search(pat, 'output')
    is_concept = all('CIP' in h.get('source','') or 'cip' in h.get('topic','') for h in hits)
    if hits:
        note = '(CIP context only — acceptable)' if is_concept else '← LEAKAGE'
        print(f'  "{pat}": {len(hits)} hits {note}')
        if not is_concept:
            for h in hits[:1]:
                idx = h['output'].find(pat)
                print(f'    src={h.get("source")} topic={h.get("topic")}')
                print(f'    ...{h["output"][max(0,idx-30):idx+80]}...')
    else:
        print(f'  "{pat}": 0 ✅')

print()
print('=== TOOLING NOISE — FINAL CHECK ===')
tooling = ['yarn', 'npm ', 'node_modules', 'docusaurus', 'webpack',
           'package.json', 'mkdocs', 'nix build', 'typescript',
           'localhost:3000', 'adr-tools', 'prettier']
for kw in tooling:
    hits = search_all(kw)
    if hits:
        print(f'  "{kw}": {len(hits)} hits ← RESIDUAL')
        for h in hits[:1]:
            print(f'    instr={h.get("instruction")[:80]}')
    else:
        print(f'  "{kw}": 0 ✅')

print()
print('=== UNVERIFIED APIs ===')
unverified = [
    ('find_script_outputs', 'stdlib uncertain'),
    ('has_nft_strict', 'stdlib uncertain'),
    ('interval.is_entirely_after', 'stdlib uncertain'),
    ('interval.is_entirely_before', 'stdlib uncertain'),
    ('transaction.resolve_input', 'stdlib — likely OK'),
    ('transaction.find_input', 'stdlib — likely OK'),
]
for pat, label in unverified:
    hits = search(pat, 'output')
    anti = sum(1 for h in hits if 'anti' in h.get('topic','') or 'correction' in h.get('topic',''))
    real = len(hits) - anti
    if real > 0:
        print(f'  "{pat}" [{label}]: {real} real uses ← mark for human review')
    else:
        print(f'  "{pat}": 0 real uses ✅')

print()
print('=== AIKEN V3 POSITIVE SIGNAL ===')
v3_signals = [
    ('assets.lovelace_of(', 'core'),
    ('assets.quantity_of(', 'core'),
    ('assets.has_nft(', 'core'),
    ('_own_ref, self)', 'core — v3 handler sig'),
    ('self.outputs', 'core'),
    ('self.inputs', 'core'),
    ('self.mint', 'core'),
    ('self.validity_range', 'core'),
    ('self.extra_signatories', 'core'),
    ('self.reference_inputs', 'core'),
    ('expect Some(', 'datum pattern'),
    ('Option<', 'datum pattern'),
    ('pub type ', 'custom type'),
    ('use cardano/assets', 'import'),
    ('use cardano/transaction', 'import'),
]
total_v3_positive = set()
for pat, label in v3_signals:
    hits = search(pat, 'output', case=True)
    for h in hits:
        total_v3_positive.add(id(h))
    print(f'  "{pat}" [{label}]: {len(hits)} examples')

print(f'\n  Unique examples with ≥1 v3 signal: {len(total_v3_positive)} / {n} ({100*len(total_v3_positive)/n:.1f}%)')

print()
print('=== CODE GENERATION RATIO ===')
has_validator = sum(1 for r in records if 'validator ' in r.get('output',''))
has_fn        = sum(1 for r in records if re.search(r'\bfn \w+\s*\(', r.get('output','')))
has_code_block= sum(1 for r in records if '```' in r.get('output',''))
pure_text     = sum(1 for r in records if '```' not in r.get('output','') and 'validator ' not in r.get('output','') and 'fn ' not in r.get('output',''))
print(f'  Examples with "validator": {has_validator} ({100*has_validator/n:.1f}%)')
print(f'  Examples with fn block:    {has_fn} ({100*has_fn/n:.1f}%)')
print(f'  Examples with code block:  {has_code_block} ({100*has_code_block/n:.1f}%)')
print(f'  Pure text explanations:    {pure_text} ({100*pure_text/n:.1f}%)')

print()
print('=== SIGNAL DENSITY ===')
high   = [r for r in records if r.get('source') in ('aiken_v3_curated','aiken_docs','aiken_design_patterns')]
medium = [r for r in records if r.get('source') in ('aiken_stdlib','cips')]
low    = [r for r in records if r.get('source') in ('hydra_docs','hydra_plutus')]
print(f'  High signal  (v3 curated + docs + patterns): {len(high)} ({100*len(high)/n:.1f}%)')
print(f'  Medium signal (stdlib + CIPs):               {len(medium)} ({100*len(medium)/n:.1f}%)')
print(f'  Low signal   (hydra):                        {len(low)} ({100*len(low)/n:.1f}%)')

print()
print('=== HYDRA CONTENT POST-CLEANUP ===')
hydra = [r for r in records if 'hydra' in r.get('source','')]
print(f'  Total hydra examples: {len(hydra)}')
topics_hydra = Counter(r.get('topic','') for r in hydra)
print(f'  Unique topics: {len(topics_hydra)}')
print('  Sample instructions:')
for r in hydra[:6]:
    print(f'    {r.get("instruction")[:85]}')

print()
print('=== CIP QUALITY SAMPLE ===')
cips = [r for r in records if r.get('source') == 'cips']
cip_topics = Counter(r.get('topic','') for r in cips)
print(f'  Total CIP examples: {len(cips)}')
print(f'  CIP topics covered: {len(cip_topics)}')
print('  Topics (sample):')
for t, c in list(cip_topics.most_common())[:15]:
    print(f'    {t}: {c}')

print()
print('=== EUXTO SEMANTIC CHECK ===')
eutxo_good = ['datum', 'redeemer', 'utxo', 'output_reference', 'OutputReference',
              'spend', 'mint', 'withdraw', 'eUTxO', 'eUtxO']
for kw in eutxo_good:
    cnt = sum(1 for r in records if kw.lower() in r.get('output','').lower())
    print(f'  "{kw}": {cnt} examples')

print()
print('=== OUTPUT LENGTH POST CLEANUP ===')
out_lens = sorted(len(r.get('output','')) for r in records)
m = len(out_lens)
print(f'  p25:{out_lens[m//4]} p50:{out_lens[m//2]} p75:{out_lens[3*m//4]} p90:{out_lens[int(m*0.9)]} max:{out_lens[-1]}')

print()
print('=== EMPTY INPUT FIELD ===')
empty = sum(1 for r in records if not r.get('input','').strip())
print(f'  Empty input: {empty} / {n} ({100*empty/n:.1f}%)')
