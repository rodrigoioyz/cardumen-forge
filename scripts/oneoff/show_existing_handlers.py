import json

with open('/home/rodrigo/entrenamiento/data/processed/dataset_v17_train_split.jsonl') as f:
    data = [json.loads(l) for l in f]

for handler in ['vote(', 'publish(', 'propose(']:
    examples = [d for d in data if handler in d.get('output', '')]
    print("=" * 60)
    print(f"Handler: {handler}  —  {len(examples)} examples in v17")
    print("=" * 60)
    for ex in examples[:2]:
        print(f"instruction: {ex.get('instruction','')[:100]}")
        print(f"source: {ex.get('source')}  topic: {ex.get('topic')}")
        print(f"output:\n{ex.get('output','')[:600]}")
        print()
