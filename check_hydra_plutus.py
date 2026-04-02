#!/usr/bin/env python3
import json
from collections import Counter

records = [json.loads(l) for l in open('data/processed/dataset_v6_clean.jsonl')]
hydra = [r for r in records if r.get('source') == 'hydra_plutus']

print(f'hydra_plutus: {len(hydra)} examples')

# Check for real Plutus/Haskell patterns
dangerous = ['PlutusTx', 'plutus-tx', 'BuiltinData', 'TxInInfo', 'mkValidator',
             'unstableMakeIsData', ' :: ', 'FromData', 'ToData', 'Haskell',
             'ScriptContext', 'ctx.purpose', 'ValidatorHash']

print('\n=== DANGEROUS PATTERNS ===')
for pat in dangerous:
    hits = [r for r in hydra if pat in r.get('output','') or pat in r.get('instruction','')]
    if hits:
        print(f'  "{pat}": {len(hits)} hits')
        for h in hits[:1]:
            field = 'output' if pat in h.get('output','') else 'instruction'
            idx = h[field].find(pat)
            print(f'    ...{h[field][max(0,idx-40):idx+80]}...')
    else:
        print(f'  "{pat}": 0 ✓')

print('\n=== INSTRUCTION SAMPLE (all 143) ===')
for r in hydra:
    print(f'  {r.get("instruction")[:90]}')

print('\n=== CONTENT CATEGORY BREAKDOWN ===')
keywords = {
    'protocol/architecture': ['reactive core', 'head protocol', 'head lifecycle', 'off-chain', 'layer-2', 'layer 2', 'l2'],
    'websocket/api': ['websocket', 'api', 'client', 'server event', 'snapshot'],
    'utxo/cardano': ['utxo', 'fanout', 'commit', 'abort', 'minUTxO', 'ada', 'lovelace'],
    'plutus/haskell_code': ['plutus-tx', 'BuiltinData', 'TxInInfo', 'mkValidator', ':: '],
    'tooling/devops': ['yarn', 'npm', 'nix', 'docusaurus', 'adr', 'build'],
}
for cat, kws in keywords.items():
    count = sum(1 for r in hydra if any(k.lower() in (r.get('output','') + r.get('instruction','')).lower() for k in kws))
    print(f'  {cat}: {count}/{len(hydra)}')
