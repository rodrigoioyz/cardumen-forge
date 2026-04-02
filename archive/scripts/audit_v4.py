#!/usr/bin/env python3
import json
from collections import Counter

path = 'data/processed/dataset_v4_clean.jsonl'
records = [json.loads(l) for l in open(path)]

print(f'=== BASIC STATS ===')
print(f'Total: {len(records)}')
sources = Counter(r.get('source','?') for r in records)
langs   = Counter(r.get('lang','?') for r in records)
print(f'Langs: {dict(langs)}')
print(f'Sources: {dict(sources)}')

print()
print('=== V2 CONTAMINATION CHECK ===')
v2_patterns = ['ScriptContext', 'ctx.purpose', 'ctx.transaction', 'ctx.info']
for pat in v2_patterns:
    hits = [r for r in records if pat in r.get('output','') or pat in r.get('instruction','') or pat in r.get('input','')]
    print(f'  "{pat}": {len(hits)} hits', '← RESIDUAL CONTAMINATION' if hits else '✓ clean')
    for h in hits[:2]:
        idx = (h.get('output','') + h.get('instruction','')).find(pat)
        field = 'output' if pat in h.get('output','') else 'instruction'
        ctx = h[field][max(0,idx-40):idx+80]
        print(f'    [{field}] src={h.get("source")} topic={h.get("topic")}')
        print(f'    ...{ctx}...')

print()
print('=== HASKELL / PLUTUS LEAKAGE CHECK ===')
haskell_patterns = [' :: ', 'TxInInfo', 'TxOutRef', 'PubKeyHash', 'ValidatorHash',
                    'fromData', 'toData', 'unstableMakeIsData', 'mkValidator',
                    'BuiltinData', 'ScriptContext']
for pat in haskell_patterns:
    hits = [r for r in records if pat in r.get('output','')]
    if hits:
        print(f'  "{pat}": {len(hits)} hits ← CHECK')
        for h in hits[:1]:
            idx = h['output'].find(pat)
            print(f'    src={h.get("source")} topic={h.get("topic")}')
            print(f'    ...{h["output"][max(0,idx-30):idx+70]}...')
    else:
        print(f'  "{pat}": 0 ✓')

print()
print('=== REMAINING HALLUCINATED API PATTERNS ===')
bad_patterns = [
    ('output.value.lovelace', 'intentional_anti'),
    ('value.get_ada()', 'intentional_anti'),
    ('output.assets.contains', 'intentional_anti'),
    ('list.count(', 'unverified'),
    ('dict.get_int(', 'unverified'),
    ('ctx.fee', 'v2'),
    ('transaction.fee', 'unverified'),
    ('interval.starts_after', 'unverified'),
    ('interval.starts_before', 'unverified'),
    ('find_script_outputs', 'unverified'),
    ('has_nft_strict', 'unverified'),
]
for pat, label in bad_patterns:
    hits = [r for r in records if pat in r.get('output','')]
    anti = sum(1 for h in hits if 'anti' in h.get('topic','') or 'correction' in h.get('topic','') or 'anti' in h.get('source',''))
    real = len(hits) - anti
    if hits:
        marker = '← INTENTIONAL' if real == 0 else f'← {real} REAL OCCURRENCES'
        print(f'  "{pat}" [{label}]: {len(hits)} total, {anti} anti-pattern, {real} real {marker}')
    else:
        print(f'  "{pat}": 0 ✓')

print()
print('=== HYDRA CONTENT QUALITY AFTER CLEANUP ===')
hydra = [r for r in records if 'hydra' in r.get('source','')]
hydra_docs = [r for r in hydra if r.get('source') == 'hydra_docs']
hydra_code = [r for r in hydra if r.get('source') == 'hydra_plutus']
print(f'hydra_docs: {len(hydra_docs)}')
print(f'hydra_plutus: {len(hydra_code)}')

# Check remaining tooling noise
tooling_kw = ['yarn', 'docusaurus', 'nix build', 'mkdocs', 'adr', 'npm', 'webpack', 'localhost:3000']
for kw in tooling_kw:
    hits = [r for r in hydra if kw.lower() in r.get('output','').lower() or kw.lower() in r.get('instruction','').lower()]
    if hits:
        print(f'  TOOLING RESIDUE "{kw}": {len(hits)} hits')
        for h in hits[:1]:
            print(f'    instr={h.get("instruction")[:80]}')

print()
print('=== V3 ALIGNMENT RATIO ===')
v3_curated = [r for r in records if r.get('source') == 'aiken_v3_curated']
verified = [r for r in v3_curated if r.get('review_status') == 'VERIFIED_V3_ALIGNED']
plausible = [r for r in v3_curated if r.get('review_status') == 'PLAUSIBLE_NEEDS_CHECK']
print(f'aiken_v3_curated total: {len(v3_curated)}')
print(f'  VERIFIED_V3_ALIGNED: {len(verified)}')
print(f'  PLAUSIBLE_NEEDS_CHECK: {len(plausible)}')
print(f'  % of total dataset: {100*len(v3_curated)/len(records):.1f}%')

print()
print('=== AIKEN V3 PATTERN PRESENCE (positive signals) ===')
v3_positive = [
    'assets.lovelace_of(',
    'assets.quantity_of(',
    'assets.has_nft(',
    'list.has(self.extra_signatories',
    '_own_ref, self)',
    'self.outputs',
    'self.inputs',
    'self.mint',
    'self.validity_range',
    'self.extra_signatories',
]
for pat in v3_positive:
    hits = sum(1 for r in records if pat in r.get('output',''))
    print(f'  "{pat}": {hits} examples')

print()
print('=== TOPIC DISTRIBUTION BY SOURCE (uniqueness) ===')
for src, cnt in sources.most_common():
    topics = set(r.get('topic','') for r in records if r.get('source') == src)
    print(f'  {src}: {cnt} examples / {len(topics)} unique topics')

print()
print('=== CODE GENERATION VS EXPLANATION RATIO ===')
has_validator = sum(1 for r in records if 'validator ' in r.get('output',''))
has_fn_block  = sum(1 for r in records if 'fn ' in r.get('output','') and '{' in r.get('output',''))
explanation   = sum(1 for r in records if '```' not in r.get('output','') and 'validator ' not in r.get('output',''))
print(f'  Examples with "validator " keyword: {has_validator}')
print(f'  Examples with fn block code: {has_fn_block}')
print(f'  Pure text explanations (no code): {explanation}')

print()
print('=== OUTPUT LENGTH DISTRIBUTION POST CLEANUP ===')
out_lens = sorted(len(r.get('output','')) for r in records)
n = len(out_lens)
p25 = out_lens[n//4]
p50 = out_lens[n//2]
p75 = out_lens[3*n//4]
p90 = out_lens[int(n*0.9)]
print(f'  p25:{p25} p50:{p50} p75:{p75} p90:{p90} max:{out_lens[-1]}')

print()
print('=== SAMPLE: REMAINING HYDRA PLUTUS (post cleanup) ===')
for r in hydra_code[:6]:
    print(f'  instr={r.get("instruction")[:90]}')
    print(f'  out[:100]={r.get("output")[:100]}')
    print()

print()
print('=== SIGNAL DENSITY ESTIMATE ===')
# High signal = v3 curated + aiken_docs + aiken_stdlib (non-BLS heavy)
high_signal = [r for r in records if r.get('source') in ('aiken_v3_curated', 'aiken_docs', 'aiken_design_patterns')]
medium_signal = [r for r in records if r.get('source') in ('aiken_stdlib', 'cips')]
low_signal = [r for r in records if r.get('source') in ('hydra_docs', 'hydra_plutus')]
print(f'  High signal (v3 curated + docs + patterns): {len(high_signal)} ({100*len(high_signal)/len(records):.1f}%)')
print(f'  Medium signal (stdlib + CIPs): {len(medium_signal)} ({100*len(medium_signal)/len(records):.1f}%)')
print(f'  Low signal (hydra): {len(low_signal)} ({100*len(low_signal)/len(records):.1f}%)')
