# Cardumen Forge

Fine-tuning dataset + training pipeline to specialize a code LLM in Aiken v3 (Cardano smart contracts).

## Current state
- Dataset: `data/processed/dataset_v23.jsonl` — 4,708 examples · 99.7% compile-verified
- Benchmark: `data/benchmark_v2.json` — 257/257 pass
- Model: cardano-dev v9 (training) · v8 released (15/15 heuristic, 10/15 compile)
- Aiken: stdlib v3.0.0 · Plutus v3

## Scripts → [SCRIPTS.md](scripts/SCRIPTS.md)
Key scripts:
- `audit_dataset_quality.py` — Claude API quality review
- `audit_dataset_compile.py` — `aiken check` on every example
- `patterns_to_dataset.py` — compile-gated pattern ingestion
- `audit_plausible.py` — PLAUSIBLE queue review
- `promote_plausible.py` — PLAUSIBLE → VERIFIED

## Aiken v3 rules (enforced in dataset)
- Imports: `use aiken/crypto` (slash separator, not dot)
- Handler: `fn spend(datum, redeemer, ctx: ScriptContext) -> Bool`
- No `MintedValue` constructor → use `from_minted_value()`
- No `pub type` inside validator blocks
- No `fn` prefix in handler names (`spend`, not `fn spend`)
