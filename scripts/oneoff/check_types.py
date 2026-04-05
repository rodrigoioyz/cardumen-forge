import json

with open('/home/rodrigo/entrenamiento/data/raw/aiken_stdlib.json') as f:
    data = json.load(f)

keywords = ['PolicyId', 'ScriptCredential', 'PubKeyCredential', 'VerificationKeyHash',
            'Credential', 'Script', 'VerificationKey', 'Certificate', 'Voter', 'StakeCredential']

for kw in keywords:
    matches = [d for d in data if kw.lower() in d.get('name', '').lower()]
    print("=== " + kw + " ===")
    for m in matches:
        print("  module: " + m.get('module', '?'))
        print("  name  : " + m.get('name', '?'))
        print("  type  : " + m.get('type', '?'))
        print("  sig   : " + str(m.get('signature', ''))[:200])
        print()
    if not matches:
        print("  NOT FOUND")
    print()
