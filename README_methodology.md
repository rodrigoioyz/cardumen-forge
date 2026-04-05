# Cardumen Forge

Training pipeline and dataset for **cardumen-forge-aiken** — the first fine-tuned LLM for Aiken v3 smart contract development on Cardano.

[![HuggingFace](https://img.shields.io/badge/model-CardumenCorps%2Fcardumen--forge--aiken-blue)](https://huggingface.co/CardumenCorps/cardumen-forge-aiken)
[![Dataset](https://img.shields.io/badge/dataset-4%2C655%20examples-green)](https://huggingface.co/CardumenCorps/cardumen-forge-aiken)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

> For usage instructions, code examples, training config, and benchmark results, see the **[HuggingFace Model Card](https://huggingface.co/CardumenCorps/cardumen-forge-aiken)**. This document covers the process: how the dataset was built, what broke, what was fixed, and why.

---

## The Problem

[Aiken](https://aiken-lang.org) is the primary smart contract language for Cardano. Every capable open-source code LLM fails at it in the same predictable ways:

**1. Wrong handler syntax — `fn` keyword inside validator blocks**

```aiken
// What every LLM generates (parse error in Aiken v3):
validator my_contract {
  fn spend(datum: Option<Datum>, ...) -> Bool { ... }
}

// Correct:
validator my_contract {
  spend(datum: Option<Datum>, ...) -> Bool { ... }
}
```

**2. Hallucinated field names**

```aiken
self.signatures      // does not exist — use self.extra_signatories
self.time            // does not exist — use self.validity_range
output.assets.ada    // does not exist — use assets.lovelace_of(output.value)
```

**3. Removed stdlib v3 constructors**

```aiken
MintedValue              // removed — use Value
VerificationKeyCredential(pkh)  // removed — use VerificationKey(pkh)
ScriptCredential(h)      // removed — use Script(h)
Interval<Int>            // wrong — type is Interval (not generic)
```

**4. Dot-style imports**

```aiken
use cardano.transaction.{Transaction}   // wrong
use cardano/transaction.{Transaction}   // correct
```

**5. Wrong module paths for types**

```aiken
use cardano/transaction.{PolicyId}  // wrong — PolicyId is in cardano/assets
use aiken/bytearray                 // wrong — use aiken/primitive/bytearray
```

These are not edge cases. They appear on the first prompt to any general-purpose LLM, every time. Qwen2.5-Coder-7B scores 0/15 on the heuristic eval without fine-tuning. The model has Aiken knowledge from pretraining — it just can't activate it reliably without domain grounding.

---

## The Approach

Three principles drove every decision in this project:

**`aiken check` as the oracle of truth.** Heuristic checks (regexes, pattern matching) can verify that a function name appears in an output. They cannot verify that the function is called with the right arity, that all required imports are present, or that the types align. Only the compiler knows. From v22 onward, every example in the correction set, governance set, and fuzz pattern library was individually compiled before inclusion. No example enters those sources with a compile failure.

**Dataset grounded in real documentation.** Every generation script injects the actual `aiken_stdlib.json` content — real function signatures and descriptions scraped from the aiken-lang/stdlib repo — into the generation prompt. Claude is explicitly told which functions exist. Early ungrounded generation produced `transaction.signatories`, `list.has_any`, `output.value.lovelace` — none of which exist. Grounded generation reduced hallucinations to zero in the quality check.

**Iterative audit cycles, not batch generation.** Each dataset version was the result of a specific diagnosis: what is the model failing on, why, and what data fixes it. The jump from 93% to 100% heuristic (v7 → v8) came entirely from 30 targeted correction examples — not from adding 300 more general examples. The smallest targeted fix consistently outperformed the largest blind addition.

There is also a broader motivation. Cardano is a network built around access and inclusion. The barrier to writing smart contracts remains high — it requires functional programming expertise, eUTxO knowledge, and careful manual consultation of documentation that general-purpose models don't know well enough to be useful. In the spirit of the Ratatouille principle — anyone can cook — the ambition here is that anyone can write a smart contract. Not to replace engineers and auditors, who remain essential for production security, but to lower the threshold at which someone can learn, experiment, and build.

---

## Dataset Evolution (v14 → v23)

| Version | Examples | Problem diagnosed | Fix applied |
|---------|----------|-------------------|-------------|
| v14 | 3,363 | 21.5% of examples had `fn spend(` — a parse error the compiler rejects | Baseline: first audit identified this as the root cause of v2–v4 failures |
| v15 | 3,363 | `fn` prefix in handlers | `fix_fn_prefix.py`: 761 handler fixes + 22 `fn else(` fixes |
| v16 | 3,357 | 6 examples with broken/nonexistent API usage | Removed |
| v17 | 3,357 | `ScriptCredential` (v2 name) and `PolicyId` from wrong module | `fix_types.py`: 2 credential + 17 import fixes |
| v18b | 3,357 | 61 truncated outputs | `regenerate_truncated.py`: regenerated from source docs (61/61 success) |
| v19 | 3,412 | Zero positive `propose` examples; only error-correction examples for `vote`/`publish` | +55 governance examples (vote×20, publish×20, propose×15) |
| v19_dedup | 3,406 | 1 exact + 5 near-duplicate examples | Dedup pass |
| v20 | 3,319 | 44.6% PLAUSIBLE_NEEDS_CHECK — unverified examples | 351 promoted to VERIFIED, 87 bad examples removed |
| v21 | 3,401 | Low `reference_inputs` + `find_input` coverage (41 → 159 examples) | +82 CIP-31 reference input examples |
| v22 | 3,475 | stdlib v2 patterns throughout: wrong imports, old API names, markdown fences in outputs | `migrate_dataset_to_v3.py`: `pub type` fixes, API renames, auto-imports, strip fences |
| v22 compile-verified | 3,474 | correction_set had 26.7% compile failures; governance had 1.8% | `audit_dataset_compile.py` + `regenerate_failing.py`: correction_set 100%, governance 100% |
| v22 import-fixed | 3,473 | 42 examples using `import x.y.z` keyword instead of `use x/y/z` | `fix_import_keyword.py` |
| v22 + correction_set_v3 | 3,503 | 5 compile failures in v8 benchmark: pub_type, minted_value, governance_committee, missing_interval, inline_datum | +30 compile-verified correction examples (6 per pattern) |
| v22 + promote_plausible | 3,503 | 30.3% PLAUSIBLE still unverified | `promote_plausible.py`: 924 promoted (compile check + banned-pattern check) |
| v22 + fix_plausible | 3,503 | 127 PLAUSIBLE failures from promotion pass | `fix_plausible_failures.py`: 97/99 repaired via Claude API with local stdlib context |
| v22 + oracle/cip068 | 3,579 | No oracle or CIP-68 coverage | +47 oracle patterns + 32 CIP-68 reference NFT examples |
| v22 + with_tests | 3,748 | No property-based test examples | +169 examples with `test` blocks across 15 stdlib topics, compile-verified |
| v23 | 3,739 | Dedup + compile verification + import fixes | 9 broken examples removed. Active dataset. |
| v23 + patterns | 4,219 | No fuzz-verified production patterns | 150 `.ak` files compiled with `--max-success 200` → +135 net new examples |
| v23 + expand | 4,610 | DeFi coverage thin (~60 examples for families 16–25) | `expand_patterns.py`: 5 task variants × 60 files → +300 DeFi examples |

**Key inflection points:**

- `fn` prefix (21.5% → 0%) was the single largest quality bug. It was teaching the model to write code the compiler rejects.
- The PLAUSIBLE_NEEDS_CHECK queue (44% → 0%) was the longest-running debt. It took three passes: local promote, compile check, Claude API repair.
- The v7→v8 jump (93% → 100% heuristic) came from 30 correction examples, not from the 300+ examples added before them. Targeted beats general.
- `Transaction.withdrawals` is `Pairs<Credential, Lovelace>`, not `Dict`. Caught during benchmark_v2 self-test when `withdraw_02/09/14` failed. `dict.get()` produces a `type_mismatch`; use `pairs.get_first()`.

---

## Pipeline Architecture

```
data/raw/                        scraped from official repos — not synthetic
  aiken_stdlib.json              458 functions with real signatures (ground truth)
  aiken_docs.json                28 documentation pages
  aiken_design_patterns.json     22 production patterns (Anastasia-Labs)
  cips.json                      134 Cardano Improvement Proposals
  hydra_docs.json                35 Hydra protocol pages
        |
        v
[Claude API — grounded generation]
  inject real signatures as context per prompt
  model cannot hallucinate APIs it was not shown
        |
        v
[audit_dataset_compile.py]
  aiken check on every output in correction/governance/fuzz sources
  PTY capture for full ANSI compiler diagnostics
        |
        +-- PASS  --> include in dataset
        +-- FAIL  --> regenerate_failing.py (Claude API + error context, 3 retries)
        |
        v
[promote_plausible.py]
  Path A: compile-check pure validators
  Path B: banned-pattern check on Q&A outputs
  924 PLAUSIBLE -> VERIFIED_V3_ALIGNED
        |
        v
[data/patterns/ — 150 fuzz-verified .ak files]
  25 DeFi/NFT families x 6 variants
  aiken check --max-success=200 (property-based fuzz)
  zero dead code, zero compiler warnings
        |
        v
[patterns_to_dataset.py]       compile-gated ingestion
  only returncode == 0 -> dataset record
        |
        v
[expand_patterns.py]           5 task variants per DeFi file
  implement / complete_from_stub / add_fuzz_tests /
  impl_from_description / complete_from_imports
        |
        v
dataset_v23.jsonl — 4,610 examples — ACTIVE TRAINING SET
        |
        v
[colab_finetune.ipynb — QLoRA, Qwen3.5-4B, unsloth]
        |
        v
cardano-dev-N.gguf (Q4_K_M, ~2.5 GB)
        |
        v
[benchmark.py / eval_benchmark.py]
  15-prompt heuristic eval + aiken check per output
  257-prompt compile-verified reference suite
```

---

## Key Methodological Decisions

**`aiken check` as oracle, not heuristics.** The v14-era approach checked whether a function name appeared in an output. This passes `assets.flatten_with` with the wrong lambda arity, `dict.insert` with an extra comparator argument that doesn't exist, `list.span` called with a predicate instead of an index. Every one of these patterns passes regex checks and fails `aiken check`. The only reliable signal is the compiler. This is why compile-verification became mandatory for all correction and fuzz sources.

**QLoRA over LoRA.** The target inference environment is 6 GB VRAM — consumer hardware, not a cloud endpoint. QLoRA (4-bit quantized base + LoRA adapters) fits comfortably. Full LoRA on Qwen3.5-4B requires ~14 GB for bfloat16. The quality tradeoff is acceptable: v8 reaches 15/15 heuristic and 10/15 compile on QLoRA.

**Qwen3.5-4B over a larger base.** Aiken v3 is a niche language with weak pretraining representation in any base model. A 4B model with strong domain coverage outperforms a 7B model with weak coverage on this specific task — qwen2.5-coder-7b scores 0/15 without fine-tuning; gemma-4-e4b (4B) scores 33% because it has incidental Aiken knowledge from pretraining. The ceiling for a well-trained 4B is higher than the floor of an untrained 7B. VRAM constraints made this an easy decision.

**Benchmark v2: 257 prompts, compile-verified.** The original 15-prompt suite was sufficient for tracking heuristic improvement but too small to catch compile regressions reliably. 15 prompts also meant 2-3 tests per category — not enough to distinguish a model that understands a pattern from one that memorized an example. The 257-prompt suite was built to cover the full range within each of 11 categories, with every reference solution individually compiled. The `--self-test` flag verifies the suite before scoring any model.

**System prompt at inference must match training.** The system prompt was present in every training example. Without it at inference time, the learned associations don't activate. This caused apparent catastrophic failures in early benchmark runs: v2–v5 scored 7–20% with a generic 4-line prompt and 67–93% with the training prompt. The models were never broken; the benchmark was. The `SYSTEM_PROMPT.txt` in this repo is the authoritative copy.

**`greater_is_better=False` is not optional.** Without this flag, HuggingFace Trainer treats higher loss as better and loads the worst checkpoint instead of the best. This caused v5 to export a degraded model despite having a good val loss curve. Always pair it with `save_steps = eval_steps` — if eval runs at step 50 but save runs at step 100, the best checkpoint doesn't exist on disk.

**Pattern library as `.ak` files, not generated examples.** Fuzz-verified `.ak` files are a different quality tier from generated JSONL. Each file has: doc comments that become the instruction, verified imports, helper functions with zero dead code, a validator block, and property-based `test` blocks that exercise the logic under randomized inputs. The format enforces correctness as a precondition of inclusion. `patterns_to_dataset.py` only ingests files that pass `aiken check --max-success 200`.

---

## Results

| Model | Dataset | Examples | Heuristic | Compile |
|-------|---------|----------|-----------|---------|
| qwen2.5-coder-7b (base) | — | — | 0/15 · 0% | — |
| cardano-dev v1 | early | — | 11/15 · 73% | — |
| cardano-dev v2 | v13 | — | 10/15 · 67% | — |
| cardano-dev v3 | v13 | — | 12/15 · 80% | — |
| cardano-dev v4 | v14 | — | 13/15 · 87% | — |
| cardano-dev v5 | v20 | 3,319 | 14/15 · 93% | — |
| cardano-dev v6 | v20 | 3,319 | 14/15 · 93% | 10/15 · 67% |
| cardano-dev v7 | v21 | 3,401 | 14/15 · 93% | 9/15 · 60% |
| **cardano-dev v8** | **v22** | **3,682** | **15/15 · 100%** | **10/15 · 67%** |
| cardano-dev v9 | v23 | 4,655 | pending | pending |

Dataset quality was the dominant driver across all versions. The v7→v8 jump (93% → 100% heuristic) came entirely from 30 targeted correction examples for the 5 patterns that were failing at compile time. v8 is the first model to pass all 15 heuristic checks and to pass `spend_reference_input` — which requires `reference_inputs` + `find_input` together and had been the persistent failure across v1–v7.

For detailed benchmark methodology and per-category breakdowns, see the [HuggingFace Model Card](https://huggingface.co/CardumenCorps/cardumen-forge-aiken).

---

## Quick Start (Extending the Dataset or Pipeline)

This section is for developers who want to extend the dataset or re-run the pipeline. For using the model, see the HuggingFace Model Card.

**Prerequisites**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install anthropic datasets transformers trl peft unsloth
export ANTHROPIC_API_KEY=sk-ant-...
```

**Use the existing dataset (recommended)**

```bash
# The active dataset is already in the repo
ls data/processed/dataset_v23.jsonl   # 4,610 examples

# Run the 15-prompt eval (requires LM Studio running locally)
python3 eval_model.py

# Run the 257-prompt compile-verified benchmark
python3 eval_benchmark.py --self-test          # verify reference solutions
python3 eval_benchmark.py --model CardumenCorps/cardumen-forge-aiken
```

**Add new fuzz pattern files**

```bash
# Place .ak file in data/patterns/, verify it compiles
python3 scripts/test_patterns.py --file data/patterns/26a_my_pattern.ak

# Ingest passing files into the dataset
python3 scripts/patterns_to_dataset.py --append-to data/processed/dataset_v23.jsonl
```

**Extend DeFi coverage with task variants**

```bash
python3 scripts/expand_patterns.py \
  --families 16,17,18 \
  --max-success 200 \
  --append-to data/processed/dataset_v23.jsonl
```

**WSL networking note:** LM Studio runs on Windows; from WSL, the Windows host is not `localhost`. Use `ip route show default` to find the gateway IP. Enable "Serve on local network" in LM Studio and add a firewall rule:
```powershell
New-NetFirewallRule -DisplayName "LM Studio WSL" -Direction Inbound -Protocol TCP -LocalPort 3005 -Action Allow
```

---

## Project Structure

```
cardumen-forge/
|
+-- README.md                       this file — methodology and process
+-- HF_README.md                    HuggingFace model card — usage, benchmarks, training
+-- SYSTEM_PROMPT.txt               system prompt for inference (load at training AND inference)
+-- colab_finetune.ipynb            QLoRA training notebook (start here for training)
+-- eval_model.py                   single-model eval — 15 prompts via LM Studio
+-- eval_benchmark.py               compile-verified benchmark — 257 reference solutions
+-- benchmark.py                    multi-model comparison table
|
+-- scripts/
|   +-- scrape/                     Step 1: collect raw sources from official repos
|   +-- generate/                   Step 2: grounded generation via Claude API
|   +-- audit/                      Step 3: quality checks (coverage, contamination)
|   +-- build/                      Step 4: assemble and split dataset
|   +-- [cleaning pipeline]         fix_fn_prefix, fix_types, migrate_dataset_to_v3,
|   |                               dedup_dataset, promote_plausible, fix_plausible_failures
|   +-- test_patterns.py            fuzz pattern sandbox harness (PTY capture)
|   +-- patterns_to_dataset.py      compile-gated ingestion for .ak files
|   +-- expand_patterns.py          5 task variants per DeFi pattern file
|   +-- audit_dataset_compile.py    compile-verify every dataset example via aiken check
|
+-- data/
|   +-- patterns/                   150 fuzz-verified .ak files (25 families x 6 variants)
|   +-- raw/                        scraped source files — aiken_stdlib.json is ground truth
|   +-- processed/
|       +-- dataset_v23.jsonl       4,610 examples — ACTIVE TRAINING SET
|       +-- dataset_v14_eval.jsonl  374 examples — HOLDOUT (do not train on)
|       +-- components/             intermediate outputs per source
|       +-- archive/                superseded versions v2-v22
|
+-- eval/
|   +-- aiken_sandbox/              compile-check sandbox (stdlib v3.0.0, Plutus v3)
|
+-- logs/                           audit logs, compile reports, repair logs
+-- eval_results/                   benchmark run JSONs — summary.md is the entry point
```

---

## References

[1] Chacón Sartori, C. & Blum, C. (2026). Combinatorial Optimization for All: Using LLMs to Aid Non-Experts in Improving Optimization Algorithms. *Inteligencia Artificial*, 29(77), 108–132. https://doi.org/10.4114/intartif.vol29iss77pp108-132

---

## License

Dataset and scripts: MIT

Raw source content in `data/raw/` is scraped from:
- [aiken-lang/stdlib](https://github.com/aiken-lang/stdlib) — Apache 2.0
- [aiken-lang.org](https://aiken-lang.org) — documentation
- [cardano-foundation/CIPs](https://github.com/cardano-foundation/CIPs) — CC-BY-4.0
- [Anastasia-Labs/design-patterns](https://github.com/Anastasia-Labs/design-patterns) — MIT
- [input-output-hk/hydra](https://github.com/input-output-hk/hydra) — Apache 2.0
