#!/usr/bin/env python3
"""
build_holdout.py
Divide dataset_v14_train.jsonl en train (90%) + eval (10%) con split estratificado
por review_status, preservando el orden curriculum en el train set.

Uso:
    python3 build_holdout.py --dry-run
    python3 build_holdout.py
    python3 build_holdout.py --eval-ratio 0.1 --seed 42
"""

import json, sys, argparse, random
from pathlib import Path
from collections import defaultdict

INPUT   = "data/processed/dataset_v14_train.jsonl"
TRAIN   = "data/processed/dataset_v14_train_split.jsonl"
EVAL    = "data/processed/dataset_v14_eval.jsonl"


def load_jsonl(path: str) -> list:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: str, records: list):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def stratified_split(records: list, eval_ratio: float, seed: int):
    """
    Split estratificado por review_status.
    Preserva el orden curriculum en train: los registros no seleccionados para eval
    mantienen su posición relativa original.
    """
    rng = random.Random(seed)

    # Agrupar índices por status
    by_status = defaultdict(list)
    for i, r in enumerate(records):
        status = r.get("review_status", "UNKNOWN")
        by_status[status].append(i)

    eval_indices = set()
    for status, indices in by_status.items():
        n_eval = max(1, round(len(indices) * eval_ratio))
        selected = rng.sample(indices, n_eval)
        eval_indices.update(selected)

    train_records = [r for i, r in enumerate(records) if i not in eval_indices]
    eval_records  = [r for i, r in enumerate(records) if i in eval_indices]

    return train_records, eval_records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",      default=INPUT)
    parser.add_argument("--train-out",  default=TRAIN)
    parser.add_argument("--eval-out",   default=EVAL)
    parser.add_argument("--eval-ratio", type=float, default=0.10)
    parser.add_argument("--seed",       type=int,   default=42)
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--overwrite",  action="store_true")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"ERROR: {args.input} no existe. Corre build_dataset_v14.py primero.")
        sys.exit(1)

    if not args.dry_run and not args.overwrite:
        for path in [args.train_out, args.eval_out]:
            if Path(path).exists():
                print(f"ERROR: {path} ya existe. Usa --overwrite.")
                sys.exit(1)

    print(f"Cargando {args.input}...")
    records = load_jsonl(args.input)
    print(f"  Total: {len(records)} registros")

    # Distribución de entrada
    from collections import Counter
    in_status = Counter(r.get("review_status","?") for r in records)
    print(f"  Por status: {dict(in_status)}")

    train, eval_set = stratified_split(records, args.eval_ratio, args.seed)

    # Estadísticas del split
    train_status = Counter(r.get("review_status","?") for r in train)
    eval_status  = Counter(r.get("review_status","?") for r in eval_set)

    print(f"\nSplit (eval_ratio={args.eval_ratio}, seed={args.seed}):")
    print(f"  Train : {len(train):>5} ejemplos")
    print(f"  Eval  : {len(eval_set):>5} ejemplos")
    print(f"\n  {'Status':<25} {'Train':>7} {'Eval':>7} {'Eval%':>7}")
    print(f"  {'-'*50}")
    all_statuses = sorted(set(list(train_status) + list(eval_status)))
    for s in all_statuses:
        t = train_status.get(s, 0)
        e = eval_status.get(s, 0)
        total = t + e
        pct = 100 * e / max(1, total)
        print(f"  {s:<25} {t:>7} {e:>7} {pct:>6.1f}%")

    if args.dry_run:
        print(f"\n[DRY RUN] No se escribió nada.")
        return

    write_jsonl(args.train_out, train)
    write_jsonl(args.eval_out,  eval_set)

    train_written = sum(1 for _ in open(args.train_out, encoding="utf-8"))
    eval_written  = sum(1 for _ in open(args.eval_out,  encoding="utf-8"))

    print(f"\n  Train : {args.train_out} ({train_written} líneas)")
    print(f"  Eval  : {args.eval_out} ({eval_written} líneas)")
    print(f"\nPara fine-tuning usa: {args.train_out}")
    print(f"Para eval usa:        {args.eval_out}")


if __name__ == "__main__":
    main()
