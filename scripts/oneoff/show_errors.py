#!/usr/bin/env python3
import json, subprocess, os, re

examples = []
with open('/home/rodrigo/entrenamiento/data/processed/dataset_v22.jsonl') as f:
    for line in f:
        ex = json.loads(line.strip())
        examples.append(ex)

subset = [e for e in examples if e.get('source') == 'correction_set_v2']

ansi = re.compile(r'\x1b\[[0-9;]*m')

for i in [35, 43]:
    code = subset[i]['output']
    with open('/home/rodrigo/entrenamiento/eval/aiken_sandbox/validators/output.ak', 'w') as f:
        f.write(code)
    r = subprocess.run(
        ['script', '-q', '-c', 'aiken check', '/dev/null'],
        cwd='/home/rodrigo/entrenamiento/eval/aiken_sandbox',
        capture_output=True, text=True, timeout=30)
    out = ansi.sub('', r.stdout + r.stderr)
    lines = [l for l in out.splitlines() if l.strip() and 'Compiling' not in l]
    print(f'=== [{i+1}/48]')
    for l in lines[:20]:
        print(l)
    print()
