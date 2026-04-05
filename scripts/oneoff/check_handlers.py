import json

# Load all raw sources
sources = {
    'stdlib':   '/home/rodrigo/entrenamiento/data/raw/aiken_stdlib.json',
    'docs':     '/home/rodrigo/entrenamiento/data/raw/aiken_docs.json',
    'patterns': '/home/rodrigo/entrenamiento/data/raw/aiken_design_patterns.json',
}

for name, path in sources.items():
    with open(path) as f:
        data = json.load(f)

    keywords = ['vote', 'publish', 'propose', 'certificate', 'voter', 'governance',
                'ProposalProcedure', 'Certificate', 'Voter']

    print("=" * 60)
    print("SOURCE: " + name + " (" + str(len(data)) + " entries)")
    print("=" * 60)

    for kw in keywords:
        matches = [d for d in data if
                   kw.lower() in str(d.get('name', '')).lower() or
                   kw.lower() in str(d.get('title', '')).lower() or
                   kw.lower() in str(d.get('module', '')).lower()]
        if matches:
            print("\n  [" + kw + "] " + str(len(matches)) + " entries:")
            for m in matches[:3]:
                label = m.get('name') or m.get('title') or m.get('module') or '?'
                sig   = str(m.get('signature') or m.get('content') or '')[:150]
                print("    • " + str(label)[:60])
                print("      " + sig[:120])
    print()
