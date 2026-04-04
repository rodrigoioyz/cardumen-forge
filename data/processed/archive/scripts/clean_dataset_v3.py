#!/usr/bin/env python3
import json
import re
from pathlib import Path

INPUT = Path("dataset_v2_train.jsonl")
OUTPUT = Path("dataset_v3_clean.jsonl")
REPORT = Path("dataset_v3_clean_report.json")

HYDRA_BAD_RE = re.compile(r"(yarn|docusaurus|nix|mkdocs|adr|architecture decision record|build docs|site docs)", re.I)
V2_BAD_RE_1 = re.compile(r"\bScriptContext\b")
V2_BAD_RE_2 = re.compile(r"\bctx\.purpose\b")
COUNT_BAD_RE = re.compile(r"\blist\.count\s*\(")

# CIPs de bajo valor para este objetivo
LOW_SIGNAL_CIP_RE = re.compile(r'^cardano/cip/cip-00(0[1-9]|1[0-5])$')

def text_of(rec: dict) -> str:
    return "\n".join([
        str(rec.get("instruction", "")),
        str(rec.get("input", "")),
        str(rec.get("output", "")),
        str(rec.get("topic", "")),
        str(rec.get("source", "")),
    ])

def is_hydra_tooling(rec: dict) -> bool:
    txt = text_of(rec)
    topic = str(rec.get("topic", ""))
    src = str(rec.get("source", ""))
    # Conservador: solo eliminar si además del tema Hydra hay señal fuerte de tooling/docs
    return ("hydra" in topic.lower() or "hydra" in src.lower() or "hydra" in txt.lower()) and bool(HYDRA_BAD_RE.search(txt))

def is_v2_contamination(rec: dict) -> bool:
    out = str(rec.get("output", ""))
    return bool(V2_BAD_RE_1.search(out) or V2_BAD_RE_2.search(out))

def is_unverified_list_count(rec: dict) -> bool:
    out = str(rec.get("output", ""))
    return bool(COUNT_BAD_RE.search(out))

def is_low_signal_cip(rec: dict) -> bool:
    topic = str(rec.get("topic", ""))
    return bool(LOW_SIGNAL_CIP_RE.match(topic))

def main():
    kept = []
    stats = {
        "input_lines": 0,
        "kept": 0,
        "removed_hydra_tooling": 0,
        "removed_v2_contamination": 0,
        "removed_list_count": 0,
        "removed_low_signal_cips": 0,
        "invalid_json": 0,
    }

    with INPUT.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            stats["input_lines"] += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                stats["invalid_json"] += 1
                continue

            if is_hydra_tooling(rec):
                stats["removed_hydra_tooling"] += 1
                continue

            if is_v2_contamination(rec):
                stats["removed_v2_contamination"] += 1
                continue

            if is_unverified_list_count(rec):
                stats["removed_list_count"] += 1
                continue

            if is_low_signal_cip(rec):
                stats["removed_low_signal_cips"] += 1
                continue

            kept.append(rec)

    with OUTPUT.open("w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    stats["kept"] = len(kept)

    with REPORT.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"Input:  {INPUT}")
    print(f"Output: {OUTPUT}")
    print(f"Report: {REPORT}")
    for k, v in stats.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
