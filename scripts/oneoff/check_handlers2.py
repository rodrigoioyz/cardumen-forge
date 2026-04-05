import json

# Get full signatures for the types we need to generate examples
with open('/home/rodrigo/entrenamiento/data/raw/aiken_stdlib.json') as f:
    stdlib = json.load(f)

# Get all governance and certificate related entries in full
targets = ['Certificate', 'Voter', 'ProposalProcedure', 'GovernanceAction',
           'Vote', 'DRep', 'Credential', 'cardano.governance', 'cardano.certificate']

for target in targets:
    matches = [d for d in stdlib if
               target.lower() in str(d.get('name', '')).lower() or
               target.lower() in str(d.get('module', '')).lower()]
    if matches:
        print("=== " + target + " ===")
        for m in matches[:4]:
            print("  module: " + str(m.get('module', '')))
            print("  name  : " + str(m.get('name', '')))
            print("  sig   : " + str(m.get('signature', ''))[:300])
            print()
