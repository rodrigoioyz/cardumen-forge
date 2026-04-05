import json

with open('/home/rodrigo/entrenamiento/data/raw/aiken_stdlib.json') as f:
    data = json.load(f)

keywords = ['reduce', 'to_dict', 'from_asset_list', 'restricted_to', 'flatten', 'lovelace_of', 'tokens']
for kw in keywords:
    matches = [d for d in data if kw in d.get('name', '').lower()]
    print("=== " + kw + " ===")
    for m in matches:
        print("  " + m.get('module', '?') + "." + m.get('name', '?') + "  ->  " + str(m.get('signature', ''))[:120])
    if not matches:
        print("  NOT FOUND in stdlib")
    print()
