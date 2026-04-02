#!/usr/bin/env python3
import json
import re
from pathlib import Path

INPUT = Path("dataset_v2_train.jsonl")
OUTPUT = Path("dataset_v4_clean.jsonl")
REPORT = Path("dataset_v4_clean_report.json")

# --- REGLAS ---

HYDRA_TOOLING_RE = re.compile(r"(yarn|docusaurus|nix|mkdocs|adr|architecture decision record|build docs|site docs)", re.I)

# v2 contamination (ahora en TODO el texto)
V2_RE = re.compile(r"\bScriptContext\b|\bctx\.purpose\b")

# Haskell / Plutus
HASKELL_RE = re.compile(r"::|TxInInfo|TxOutRef|ScriptContext\s*->|validate\s*::", re.I)

# sospechoso
LIST_COUNT_RE = re.compile(r"\blist\.count\s*\(")

# CIPs irrelevantes
LOW_SIGNAL_CIP_RE = re.compile(r'^cardano/cip/cip-00(0[1-9]|1[0-5])$')

# --- HELPERS ---

def full_text(rec):
    return "\n".join([
        str(rec.get("instruction", "")),
        str(rec.get("input", "")),
        str(rec.get("output", "")),
        str(rec.get("topic", "")),
        str(rec.get("source", "")),
    ])

def is_hydra_tooling(rec):
    txt = full_text(rec)
    topic = str(rec.get("topic", "")).lower()
    return "hydra" in topic and HYDRA_TOOLING_RE.search(txt)

def is_v2(rec):
    return bool(V2_RE.search(full_text(rec)))

def is_haskell(rec):
    return bool(HASKELL_RE.search(full_text(rec)))

def is_bad_count(rec):
    return bool(LIST_COUNT_RE.search(rec.get("output", "")))

def is_low_cip(rec):
    return bool(LOW_SIGNAL_CIP_RE.match(str(rec.get("topic", ""))))

# --- MAIN ---

def main():
    stats = {
        "input": 0,
        "kept": 0,
        "removed_v2": 0,
        "removed_haskell": 0,
        "removed_hydra_tooling": 0,
        "removed_list_count": 0,
        "removed_low_cip": 0,
    }

    kept = []

    with INPUT.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            stats["input"] += 1

            try:
                rec = json.loads(line)
            except:
                continue

            if is_hydra_tooling(rec):
                stats["removed_hydra_tooling"] += 1
                continue

            if is_v2(rec):
                stats["removed_v2"] += 1
                continue

            if is_haskell(rec):
                stats["removed_haskell"] += 1
                continue

            if is_bad_count(rec):
                stats["removed_list_count"] += 1
                continue

            if is_low_cip(rec):
                stats["removed_low_cip"] += 1
                continue

            kept.append(rec)

    with OUTPUT.open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats["kept"] = len(kept)

    with REPORT.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print("DONE")
    for k, v in stats.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
