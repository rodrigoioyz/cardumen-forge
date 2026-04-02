# Cardano Aiken Copilot — Fine-Tuning Dataset

A bilingual (EN/ES) fine-tuning dataset and training pipeline to specialize a small language model in Cardano smart contract development using Aiken v3, the Hydra Head L2 protocol, and CIP standards.

**Goal:** Turn a general-purpose code LLM into a domain expert that generates correct, compilable Aiken v3 validators — runnable locally on 6 GB VRAM.

---

## Why this exists

The best open-source code models (Qwen2.5-Coder, DeepSeek-Coder, etc.) fail at Aiken in predictable ways:

- Generate Haskell syntax instead of Aiken (similar grammar, much higher pretraining frequency)
- Hallucinate stdlib functions that don't exist (`list.has_any`, `transaction.signatories`)
- Use v1/v2 Plutus patterns instead of the Aiken v3 handler structure
- Confuse `tx.validity_range` with the correct `self.validity_range`
- Don't know the eUTxO model or datum/redeemer/OutputReference semantics

This project builds a dataset grounded in real documentation to fix those failure modes, and tracks improvement through iterative audit cycles.

---

## Model

| Component | Detail |
|-----------|--------|
| Base model | `Qwen3.5-4B` |
| Method | 16-bit LoRA — r=32, alpha=64, target all linear layers |
| Framework | [unsloth](https://github.com/unslothai/unsloth) + TRL + PEFT |
| Training hardware | NVIDIA RTX PRO 6000 Blackwell (94 GB VRAM) |
| Export format | GGUF Q4_K_M (~2.5 GB) |
| Local inference | LM Studio, 6 GB VRAM |
| Inference temperature | 0.1 (code generation) |

---

## Dataset

### Current state (v13)

| Metric | Value |
|--------|-------|
| Total examples | 3,409 |
| Languages | EN 63% / ES 37% |
| Contamination (hallucinated APIs) | 0 |
| Sources | 7 |

### Sources

| Source | Examples | Description |
|--------|----------|-------------|
| `aiken_stdlib` | 1,721 | One Q&A per stdlib function — grounded in real signatures from `aiken_stdlib.json` |
| `cips` | 588 | CIPs in Ledger/Plutus/Tokens/Metadata categories |
| `aiken_docs` | 396 | Language concepts, type system, syntax from official docs |
| `aiken_design_patterns` | 209 | Production patterns from Anastasia-Labs |
| `aiken_v3_curated` | 260 | Complex validators with correct handler structure (spend/mint/withdraw) |
| `correction_set` | 167 | Targeted negative examples — broken code in `input`, correct fix in `output` |
| `hydra_docs` | 68 | Hydra Head protocol — lifecycle, snapshots, fanout, L2 transactions |

### Schema

Each example is a JSON line:

```json
{
  "lang": "en",
  "instruction": "Write a spend validator that checks the owner signed the transaction",
  "input": "",
  "output": "use aiken/collection/list\nuse cardano/transaction.{Transaction}\n\nvalidator owner_check {\n  fn spend(_datum: Data, _redeemer: Data, own_ref: OutputReference, self: Transaction) -> Bool {\n    list.has(self.extra_signatories, owner_key)\n  }\n}",
  "source": "aiken_stdlib",
  "topic": "aiken/cardano.transaction.extra_signatories",
  "review_status": "VERIFIED_V3_ALIGNED"
}
```

`review_status` values:
- `VERIFIED_V3_ALIGNED` — all APIs are confirmed in `aiken_stdlib.json`
- `PLAUSIBLE_NEEDS_CHECK` — uses patterns like `output.address` comparison that are plausible but not in the stdlib signatures
- `CORRECTION` — negative correction example (broken → fixed)

---

## How the dataset was built

### Phase 1 — Scraping raw sources

All raw data lives in `data/raw/` and is **not synthetic** — it comes directly from official repositories and documentation sites.

| File | Content | How scraped |
|------|---------|-------------|
| `aiken_stdlib.json` | 458 functions — module, name, signature, description | GitHub API on `aiken-lang/stdlib`, parser for `///` doc-comments |
| `aiken_docs.json` | 28 pages with sections and code examples | HTTP crawler on `aiken-lang.org` with BeautifulSoup4 |
| `aiken_design_patterns.json` | 22 production pattern files | GitHub API on `Anastasia-Labs/design-patterns` |
| `cips.json` | 134 CIPs with title, category, status, content | GitHub API on `cardano-foundation/CIPs` |
| `hydra_docs.json` | 35 pages of Hydra protocol docs | Crawler on `hydra.family` Docusaurus site |

### Phase 2 — Q&A generation via Claude API

Each raw chunk is sent to Claude with the real content as context — the model is instructed to generate examples **only based on what's in the source**, not from prior knowledge. This prevents API hallucination.

```
[real stdlib signature + description]
     ↓
[Claude with tool_use forced]
     ↓
[structured JSON examples]
```

The key design decision: **inject the real stdlib signatures into every prompt as ground truth**. Claude is explicitly told which functions exist and which don't.

Key scripts:
- `regenerate_from_raw.py` — main generation pipeline, one chunk per stdlib function / doc section / pattern file
- `generate_complex_validators.py` — generates validators combining 2+ APIs (harder patterns)
- `generate_correction_type_c.py` — generates correction examples for specific hallucination patterns

### Phase 3 — Audit and purge

After each generation run, `audit_v9.py` checks:
- Coverage of v3 APIs in outputs (how many examples actually use each function)
- Contamination — v2 patterns, wrong imports, hallucinated functions
- Combination coverage — examples that use lovelace+signatories together, NFT+time, etc.

`purge_v9.py` removes contaminated examples without touching correction examples.

This loop ran from v6 to v13, each iteration:
1. Fine-tune → evaluate on test prompts
2. Identify failure patterns in model output
3. Add targeted correction examples or grounded re-generation
4. Purge contamination → new dataset version

---

## Problems encountered with synthetic generation

Generating a fine-tuning dataset synthetically (asking an LLM to invent examples) introduces specific failure modes that took several iterations to identify and fix. This section documents what went wrong and how it was addressed.

### Problem 1 — Handler signature learned incorrectly

**Symptom:** After fine-tuning, the model consistently generated this invented handler structure:

```aiken
spend(
  _redeemer: Void,
  self: Transaction,
  policy_id: Hash,       // ← invented
  _own_vout: Int,        // ← invented
  _own_utxo: Assets,     // ← invented
  _self_vout: Int,       // ← invented
) -> Bool
```

And used `self.signatures`, `self.time`, `self.outputs.all()` — none of which exist in Aiken v3.

**Root cause:** The dataset had 3,149 examples but only **51 with `fn spend(`**. The generation script showed the handler signature as pseudocode reference without `fn` keyword or `validator {}` wrapper, so the generator never produced complete validators. The model learned field names from prose descriptions but never saw the full syntactic structure as a unit.

**Fix:** Rewrote `generate_complex_validators.py` to:
1. Show the complete `validator { fn spend(...) { } }` structure explicitly in the system prompt
2. Inject real code examples from `aiken_design_patterns.json` as structural reference
3. Generate 260 validators with verified handler structure (200 spend, 40 mint, 20 withdraw)
4. Add automated quality check — counts `fn spend(`, `fn mint(`, bad patterns after every run

### Problem 2 — System prompt showed signatures without syntax

**Symptom:** 291 complex validators were generated but 0 had `fn spend(` in the output.

**Root cause:** The system prompt contained:
```
spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
```
Without `fn` and without `validator {}`. Claude interpreted this as a type signature reference, not as code to replicate.

**Fix:** Changed to show the complete compilable structure:
```aiken
validator my_contract {
  fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool {
    ...
  }
}
```

### Problem 3 — Synthetic generation without source grounding

**Symptom:** Generated examples used APIs that don't exist in Aiken v3 (`transaction.signatories`, `list.has_any`, `output.value.lovelace`).

**Root cause:** Early scripts generated examples purely from Claude's prior knowledge, which includes Haskell, Plutus, and other functional languages with similar patterns.

**Fix:** All generation scripts now inject the real `aiken_stdlib.json` content into every prompt as ground truth. Claude is explicitly instructed to use **only** the APIs shown in the context. This approach, implemented in `regenerate_from_raw.py` and the updated `generate_complex_validators.py`, reduced hallucinations to 0 in the quality check.

### Problem 4 — Missing `review_status` field

**Symptom:** 1,400 examples from the original pipeline had no `review_status` field, causing potential crashes in training scripts that expected the field.

**Root cause:** The field was added to the schema in a later iteration but earlier-generated examples were never backfilled.

**Fix:** `build_dataset_v13.py` normalizes all missing `review_status` to `PLAUSIBLE_NEEDS_CHECK` during the merge step, with explicit counting and logging of how many records were fixed.

### Lesson: audit before training

Every dataset version now goes through a fixed audit before training:

```bash
grep -c "fn spend("     dataset_v13_train.jsonl   # must be > 5% of total
grep -c "fn mint("      dataset_v13_train.jsonl
grep -c "fn withdraw("  dataset_v13_train.jsonl
grep -c "self.signatures" dataset_v13_train.jsonl  # must be 0 (outside corrections)
grep -c "self.time"       dataset_v13_train.jsonl  # must be 0
```

The `build_dataset_v13.py` script runs this audit automatically and reports coverage percentages with warnings for patterns below 3%.

---

## Aiken v3 — What the model learns

### Verified handler signatures

```aiken
validator my_contract {
  fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool {
    ...
  }
  fn mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool {
    ...
  }
  fn withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool {
    ...
  }
}
```

### Verified import style (slash, not dot)

```aiken
use cardano/assets
use cardano/transaction
use aiken/interval
use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
```

### Verified API patterns

```aiken
// ADA check
assets.lovelace_of(output.value) >= price

// Signature check
list.has(self.extra_signatories, owner_key)

// N-of-M multisig
list.count(admins, fn(k) { list.has(self.extra_signatories, k) }) >= threshold

// NFT check (3 args required)
assets.has_nft(output.value, policy_id, asset_name)

// Time constraint
interval.is_entirely_after(self.validity_range, deadline)

// Script outputs
transaction.find_script_outputs(self.outputs, script_hash)
```

### What NOT to generate (hallucination targets)

```aiken
// ❌ These do not exist in Aiken v3
transaction.signatories(tx)
list.has_any(a, b)
output.value.lovelace
tx.validity_range
use cardano.transaction.{Transaction}  // dot-style imports
interval.is_after(deadline, range)     // wrong function name
```

---

## Project structure

```
entrenamiento/
├── data/
│   ├── raw/
│   │   ├── aiken_stdlib.json          # 458 functions with real signatures
│   │   ├── aiken_docs.json            # 28 documentation pages
│   │   ├── aiken_design_patterns.json # 22 production pattern files
│   │   ├── cips.json                  # 134 Cardano Improvement Proposals
│   │   └── hydra_docs.json            # 35 Hydra protocol pages
│   └── processed/
│       └── dataset_v13_train.jsonl    # 3,409 clean examples (active)
│
├── scrape_aiken_stdlib_github.py      # GitHub API scraper for stdlib
├── scrape_aiken_docs.py               # Crawler for aiken-lang.org
├── scrape_hydra_docs.py               # Crawler for hydra.family
├── scrape_github.py                   # Scraper for CIPs + design patterns
│
├── regenerate_from_raw.py             # Main generation pipeline (grounded)
├── generate_complex_validators.py     # Complex multi-API validators
├── generate_correction_type_c.py      # Negative correction examples
│
├── audit_v9.py                        # Dataset quality audit
├── purge_v9.py                        # Remove contaminated examples
├── build_dataset_v13.py               # Merge + normalize + audit pipeline
│
└── colab_finetune.ipynb               # QLoRA training notebook
```

---

## Training

The training script handles:
- Installing unsloth + dependencies
- Loading the base model in bfloat16
- Configuring 16-bit LoRA (r=32, alpha=64)
- ChatML formatting with Aiken v3 rules in system prompt
- Training loop with gradient accumulation
- GGUF Q4_K_M export for LM Studio

Config for RTX PRO 6000 (94 GB VRAM):
```python
model_name     = "unsloth/Qwen3.5-4B"
max_seq_length = 2048
load_in_4bit   = False        # full bfloat16
lora_r         = 32
lora_alpha     = 64
num_epochs     = 3
learning_rate  = 2e-4
batch_size     = 4
grad_accum     = 8            # effective batch = 32
```

The system prompt injected at training time reinforces the critical rules:
```
- fn spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
- Always wrap handlers inside validator { } block with fn keyword
- ADA: assets.lovelace_of(output.value) — NEVER output.assets.ada
- Signatures: list.has(self.extra_signatories, key) — NEVER self.signatures
- Time: self.validity_range — NEVER self.time
```

---

## Results

### v11 model (dataset v11, 3440 examples) — evaluated on 20 test prompts

| Metric | Result |
|--------|--------|
| Correct handler signature | ❌ — invented 8-param structure |
| `assets.lovelace_of()` | ❌ — used `output.assets.ada` |
| `self.extra_signatories` | ❌ — used `self.signatures` |
| `self.validity_range` | ❌ — used `self.time` |
| `list.all(outputs, fn)` | ❌ — used `self.outputs.all()` |
| Slash-style imports | ❌ — used dot-style |
| Correct Aiken syntax | partial |

The model had learned a completely invented API that was consistent across all 20 prompts. Root cause: only 51 examples with `fn spend(` in 3,440 total.

### v13 model (dataset v13, 3409 examples) — in progress

Training loss at epoch 2: **0.42 train / 0.46 eval** — significantly lower than v11 (0.75 at epoch 2). Evaluation pending after training completes.

---

## License

Dataset and scripts: MIT

The raw source content in `data/raw/` is scraped from:
- [aiken-lang/stdlib](https://github.com/aiken-lang/stdlib) — Apache 2.0
- [aiken-lang.org](https://aiken-lang.org) — documentation
- [cardano-foundation/CIPs](https://github.com/cardano-foundation/CIPs) — CC-BY-4.0
- [Anastasia-Labs/design-patterns](https://github.com/Anastasia-Labs/design-patterns) — MIT
- [input-output-hk/hydra](https://github.com/input-output-hk/hydra) — Apache 2.0

---

*Dataset v13 | 3,409 examples | EN/ES | Aiken v3*
