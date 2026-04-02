# Cardano Aiken Copilot — Fine-Tuning Dataset

A bilingual (EN/ES) fine-tuning dataset and training pipeline to specialize a small language model in Cardano smart contract development using Aiken v3, the Hydra Head L2 protocol, and CIP standards.

**Goal:** Turn a general-purpose code LLM into a domain expert that generates correct, compilable Aiken v3 validators — runnable locally on 6 GB VRAM.

---

> **Context for newcomers:** [Aiken](https://aiken-lang.org) is a functional language for writing Cardano smart contracts. Fine-tuning means taking a general-purpose code model and training it further on domain-specific examples so it specializes. This project does that for Aiken v3 — the result is a small model (~2.5 GB) you can run locally that generates correct Cardano validators instead of hallucinating Haskell or outdated Plutus patterns.

---

## Motivation

There is a recurring idea in this project that goes beyond the technical: the democratization of knowledge as a path to building societies with more opportunities.

Cardano is a network designed around principles of access and inclusion. Aiken, as its smart contract language, is capable and precise — but the barrier to entry remains high. Traditionally, writing verifiable on-chain logic has required a combination of functional programming expertise, deep familiarity with the eUTxO model, and manual consultation of documentation that general-purpose models simply do not know well enough to be useful.

The rapid advancement of LLMs across technical fields opens a different possibility. Research has shown that even a simple prompting strategy — giving a model an existing codebase as context and asking it to improve — can produce meaningful gains across a wide range of algorithms, without requiring the user to be a domain expert [[1]](#references). The underlying insight is that the model acts not as a replacement for expertise, but as a bridge to it.

This project applies that idea to Cardano development. In the spirit of the old Ratatouille principle — that anyone can cook — the ambition here is that anyone can write a smart contract. Not to replace engineers and auditors, who remain essential for production security, but to lower the threshold at which someone can learn, experiment, and build. A self-taught developer with no formal training in formal verification should be able to get a working first draft, understand why it works, and know what questions to ask next.

The approach is deliberately humble: one person, working iteratively with AI tools, building a grounded dataset from real documentation, and measuring improvement one failure mode at a time.

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

### Current state (v14 — final)

| Metric | Value |
|--------|-------|
| Total examples (v14 train) | 3,737 |
| Train split (90%) | 3,363 |
| Eval/holdout split (10%) | 374 |
| Languages | EN 63% / ES 37% |
| Contamination (hallucinated APIs) | 0 |
| Dot-import contamination purged | 201 (all `aiken_stdlib` / `PLAUSIBLE_NEEDS_CHECK`) |
| Truly incomplete outputs (no handler) | 7 (fixed in `validators_fixed.jsonl`) |
| Sources | 8 |

### v14 composition (final)

| Source | Examples | Status |
|--------|----------|--------|
| CORRECTION (v13) | 37 | anti-pattern corrections |
| CORRECTION (v2) | 50 | new: Conway-era, dict, rational, tx.fields errors |
| VERIFIED_V3_ALIGNED (v13) | 1,558 | deduped against fixed |
| `validators_fixed.jsonl` | 7 | regenerated from 7 incompletes |
| `validators_v3.jsonl` | 479 | 19 batches: governance, cert, dict, rational, multi-handler |
| PLAUSIBLE_NEEDS_CHECK (v13) | 1,606 | deduped against fixed |
| **Total** | **3,737** | 0 duplicates |

**Status distribution:** CORRECTION 87 (2.3%) / VERIFIED_V3_ALIGNED 1,983 (53%) / PLAUSIBLE_NEEDS_CHECK 1,667 (44.6%)

**Training order (curriculum):** CORRECTION → VERIFIED_V3_ALIGNED → validators_v3 → PLAUSIBLE_NEEDS_CHECK

**Holdout split:** stratified 90/10 by `review_status`, seed=42
- `dataset_v14_train_split.jsonl` — 3,363 examples (for fine-tuning)
- `dataset_v14_eval.jsonl` — 374 examples (for evaluation)

### Sources

| Source | Examples | Description |
|--------|----------|-------------|
| `aiken_stdlib` | 1,721 | One Q&A per stdlib function — grounded in real signatures from `aiken_stdlib.json` |
| `cips` | 588 | CIPs in Ledger/Plutus/Tokens/Metadata categories |
| `aiken_docs` | 396 | Language concepts, type system, syntax from official docs |
| `aiken_design_patterns` | 209 | Production patterns from Anastasia-Labs |
| `aiken_v3_curated` | 260 | Complex validators with correct handler structure (spend/mint/withdraw) |
| `aiken_v3_curated_v2` | 301+ | New validators: reference inputs, typed datum, interval, governance, dict, rational |
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

## Quick start — reproduce from scratch

### Prerequisites

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install anthropic openai datasets transformers trl peft unsloth
export ANTHROPIC_API_KEY=sk-ant-...
```

### Step 1 — Scrape raw sources (optional, already in `data/raw/`)

```bash
python3 scrape_aiken_stdlib_github.py   # stdlib functions → data/raw/aiken_stdlib.json
python3 scrape_aiken_docs.py            # docs pages      → data/raw/aiken_docs.json
python3 scrape_hydra_docs.py            # Hydra protocol  → data/raw/hydra_docs.json
python3 scrape_github.py                # CIPs + patterns → data/raw/cips.json, aiken_design_patterns.json
```

### Step 2 — Generate training examples

```bash
# Main grounded generation (stdlib, docs, CIPs, patterns, Hydra)
PYTHONUNBUFFERED=1 python3 -u regenerate_from_raw.py 2>&1 | tee logs/regen.log

# Curated validators (19 batches: all handlers, dict, rational, governance, multi-handler)
PYTHONUNBUFFERED=1 python3 -u generate_validators_v2.py 2>&1 | tee logs/validators_v3.log
# Output: data/processed/validators_v3.jsonl (479 examples)

# Correction examples (Conway-era errors, dict/rational API errors, tx.fields errors)
python3 generate_corrections_v2.py
# Output: data/processed/corrections_v2.jsonl (50 examples)
```

### Step 3 — Build and split dataset

```bash
# Curriculum-ordered merge
python3 build_dataset_v14.py
# Output: data/processed/dataset_v14_train.jsonl (3,737 examples)

# Stratified 90/10 holdout split
python3 build_holdout.py
# Output: dataset_v14_train_split.jsonl (3,363) + dataset_v14_eval.jsonl (374)
```

### Step 4 — Fine-tune (Google Colab)

1. Upload `data/processed/dataset_v14_train_split.jsonl` to Colab
2. Run `colab_finetune.ipynb`
3. Download `qwen35_4b_aiken_v14_gguf/` and load in LM Studio

### Step 5 — Evaluate

```bash
# Requires LM Studio running with the fine-tuned model loaded
export LM_STUDIO_URL=http://192.168.x.x:1234
export LM_MODEL_NAME=qwen35_4b_aiken_v14_q4

pip install openai
python3 eval_model.py
# Compare two runs:
python3 eval_model.py --compare
```

---

## Pipeline overview

```
data/raw/                          ← scraped from official repos (not synthetic)
   aiken_stdlib.json  458 functions with real signatures
   aiken_docs.json    28 documentation pages
   aiken_design_patterns.json  22 production pattern files
   cips.json          134 Cardano Improvement Proposals
   hydra_docs.json    35 Hydra protocol pages
        │
        ▼
[Claude API — grounded generation]
   inject real signatures as context → model cannot hallucinate APIs it wasn't shown
        │
        ▼
data/processed/raw outputs
        │
        ▼
[audit_v9.py + audit_dot_imports.py]
   check API coverage, contamination, import style
        │
        ├── contaminated → purge_dot_imports.py → dataset_v13_purged.jsonl
        ├── incomplete   → fix_incomplete_validators.py → validators_fixed.jsonl
        └── gaps covered → generate_validators_v2.py → validators_v3.jsonl (479)
                         → generate_corrections_v2.py → corrections_v2.jsonl (50)
        │
        ▼
[build_dataset_v14.py]  curriculum-ordered merge
   CORRECTION → VERIFIED → new curated → PLAUSIBLE
        │
        ▼
dataset_v14_train.jsonl  3,737 examples
        │
        ▼
[build_holdout.py]  stratified 90/10 split by review_status
        ├── dataset_v14_train_split.jsonl  3,363  ← USE FOR TRAINING
        └── dataset_v14_eval.jsonl           374  ← USE FOR EVAL
        │
        ▼
[Colab QLoRA — unsloth + Qwen3.5-4B]
        │
        ▼
qwen35_4b_aiken_v14_gguf/  Q4_K_M ~2.5 GB
        │
        ▼
[eval_model.py — 15 prompts, automated pass/fail]
```

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

### Problem 5 — Overly strict handler detection caused false "incomplete" count

**Symptom:** An audit script reported 475 examples (13.9%) as "incomplete" — instructions asking for validator code but outputs without a proper handler. Attempts to regenerate them produced 0 successful fixes across dozens of batches.

**Root cause (detection):** The `has_complete_handler()` check searched for `fn spend(` / `fn mint(` / `fn withdraw(` inside a `validator {}` block. However, Aiken v3 allows the `fn` keyword to be omitted inside validator blocks — `spend(...)` is also valid syntax. Most of the 475 flagged examples were using the bare form and were actually correct.

**Root cause (regeneration):** Two additional bugs compounded the problem:
1. Matching regenerated outputs back to originals was done by exact instruction text. Claude consistently paraphrases instructions instead of copying them verbatim, so 100% of batches returned "instruction not found" and were dropped.
2. The `CODE_PHRASE` regex matched "show a practical example of using X" even when X was a pure utility function (e.g., BLS12-381 scalar operations) that has nothing to do with validators.

**Fix:**
1. Updated `has_complete_handler()` to accept both `fn spend(` and bare `spend(` inside validator blocks:
   ```python
   return bool(re.search(r'\b(?:fn\s+)?(spend|mint|withdraw)\s*\(', body))
   ```
2. Switched matching from instruction-text lookup to **positional matching** — Claude receives numbered instructions `[1], [2], ...` and returns items in the same order; the script zips by index, not by string comparison.
3. Tightened `CODE_PHRASE` regex to only flag instructions that explicitly mention `validator`, `contract`, `handler`, `spend`, `mint`, or `withdraw` — not just any "show me an example of X".
4. Added `EXPLAIN_PHRASE` filter to exclude conceptual questions ("explain how", "what is", "how does X work") that happen to mention validators — their ideal answer is prose, not code.

**Result:** True incomplete count dropped from 475 → **7**. All 7 were regenerated successfully with 0 drops and 0 hallucinations.

**Lesson:** When building detection heuristics for dataset quality, validate them on real samples before acting on the counts. A grep-style keyword check ("instruction contains 'write'") will over-count by 60x compared to a phrase-level structural check.

### Problem 6 — Python stdout buffering hides script progress when piped to tee

**Symptom:** Script appeared to hang with 0 bytes written to log file, despite process being alive. No output visible for 10+ minutes.

**Root cause:** Python buffers stdout when output is piped (e.g., `python3 script.py | tee log`). The buffer fills only after ~8 KB of output, so nothing appears in the log until a batch of results accumulates.

**Fix:** Always run generation scripts with `PYTHONUNBUFFERED=1` and the `-u` flag:
```bash
PYTHONUNBUFFERED=1 .venv/bin/python3 -u script.py 2>&1 | tee run.log
```

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

All six Cardano handler purposes are valid. The `fn` keyword is optional inside validator blocks — both `fn spend(` and bare `spend(` compile.

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
  fn publish(redeemer: T, cert: Certificate, self: Transaction) -> Bool {
    ...
  }
  fn vote(redeemer: T, voter: Voter, self: Transaction) -> Bool {
    ...
  }
}
```

Imports for Conway-era handlers:
```aiken
use cardano/certificate.{Certificate}
use cardano/governance.{Voter, ProposalProcedure}
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
│   │   ├── aiken_stdlib.json              # 458 functions with real signatures
│   │   ├── aiken_docs.json                # 28 documentation pages
│   │   ├── aiken_design_patterns.json     # 22 production pattern files
│   │   ├── cips.json                      # 134 Cardano Improvement Proposals
│   │   └── hydra_docs.json                # 35 Hydra protocol pages
│   └── processed/
│       ├── correction_set.jsonl           # 37 corrections (v1 — anti-pattern grounding)
│       ├── corrections_v2.jsonl           # 50 corrections (v2 — Conway-era, dict, rational)
│       ├── dataset_v13_purged.jsonl       # 3,208 examples (dot-imports purged)
│       ├── validators_fixed.jsonl         # 7 regenerated complete validators
│       ├── validators_v3.jsonl            # 479 new validators (19 batches, all handlers)
│       ├── dataset_v14_train.jsonl        # 3,737 examples (full curriculum-ordered dataset)
│       ├── dataset_v14_train_split.jsonl  # 3,363 examples (90% — USE FOR TRAINING)
│       ├── dataset_v14_eval.jsonl         # 374 examples (10% holdout — USE FOR EVAL)
│       └── archive/                       # superseded datasets (v13_train, validators_v2, etc.)
│
├── logs/                                  # generation run logs
│
├── scrape_aiken_stdlib_github.py          # GitHub API scraper for stdlib
├── scrape_aiken_docs.py                   # Crawler for aiken-lang.org
├── scrape_hydra_docs.py                   # Crawler for hydra.family
├── scrape_github.py                       # Scraper for CIPs + design patterns
├── scrape_aiken_stdlib.py                 # Local stdlib scraper (legacy)
│
├── regenerate_from_raw.py                 # Main generation pipeline (grounded)
├── generate_validators_v2.py              # Curated validator generator (19 batches)
├── generate_correction_set.py             # Correction examples v1
├── generate_corrections_v2.py             # Correction examples v2 (Conway-era, dict, rational)
├── fix_incomplete_validators.py           # Regenerate outputs for incomplete examples
│
├── audit_v9.py                            # Dataset quality audit
├── audit_dot_imports.py                   # Detect dot-style import contamination
├── purge_dot_imports.py                   # Purge dot-import contamination
├── build_dataset_v14.py                   # Curriculum-ordered merge pipeline (v14)
├── build_holdout.py                       # Stratified 90/10 train/eval split
├── eval_model.py                          # 15-prompt eval suite via LM Studio API
│
├── colab_finetune.ipynb                   # QLoRA training notebook
│
└── archive/scripts/                       # superseded scripts (v13 pipeline, old audits, etc.)
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

## Evaluation suite

15 prompts designed to reproduce the specific failure modes of the v11 model. Each test has automated checks — `must_contain` (required patterns) and `must_not_contain` (hallucination targets). A test passes only if all checks pass.

Run with `eval_model.py` (requires LM Studio + openai package).

| # | ID | Category | Key checks (must contain) | Hallucination targets (must not contain) |
|---|-----|----------|--------------------------|------------------------------------------|
| 1 | `spend_owner_sig` | spend / signature | `spend(`, `extra_signatories` | `self.signatures`, `self.time`, `use cardano.` |
| 2 | `spend_ada_payment` | spend / ADA | `spend(`, `lovelace_of` | `output.assets.ada`, `self.time` |
| 3 | `spend_time_lock` | spend / time | `spend(`, `validity_range` | `self.time`, `block_num` |
| 4 | `spend_nft_gate` | spend / NFT | `spend(`, `has_nft` | `output.assets.ada`, `self.time` |
| 5 | `spend_multisig` | spend / multisig | `spend(`, `extra_signatories`, `list.count` | `MultiSignature`, `self.signatures` |
| 6 | `mint_nft_one_shot` | mint / one-shot | `mint(`, `policy_id` | `fn spend(`, `self.signatures` |
| 7 | `mint_admin_capped` | mint / capped supply | `mint(`, `extra_signatories`, `quantity_of` | `self.signatures`, `self.time` |
| 8 | `withdraw_staking` | withdraw | `withdraw(`, `extra_signatories` | `self.signatures`, `self.time` |
| 9 | `spend_combined` | spend / combined | `spend(`, `extra_signatories`, `validity_range` | `self.signatures`, `self.time` |
| 10 | `spend_reference_input` | spend / reference inputs | `spend(`, `reference_inputs`, `find_input` | `self.signatures`, `self.time` |
| 11 | `vote_governance` | vote / governance | `vote(`, `Voter` | `fn spend(`, `self.signatures` |
| 12 | `publish_cert` | publish / certificate | `publish(`, `Certificate` | `self.signatures`, `self.time` |
| 13 | `multi_handler` | multi-handler | `spend(`, `mint(`, `extra_signatories` | `self.signatures`, `self.time` |
| 14 | `import_style` | imports | `use cardano/`, `use aiken/`, `spend(` | `use cardano.`, `use aiken.` |
| 15 | `typed_datum` | spend / typed datum | `spend(`, `VestingDatum`, `validity_range` | `self.time`, `self.signatures` |

**Note on eval methodology:** These checks catch the most common failure modes observed in v11 but are string-based — a model writing `extra_signatories` in a comment but not in actual logic would pass. True validation requires compiling the output with `aiken check`. Manual spot-checking is recommended alongside automated scores. This aligns with findings in [[1]](#references) on the practical costs of automated validation loops.

All 15 tests also check automatically:
- `has_validator_block` — output contains `validator { ... }`
- `has_complete_handler` — at least one handler (`spend(`, `mint(`, etc.) inside the block
- `has_slash_imports` — at least one `use x/y` style import present
- `has_dot_imports` (must be false) — no `use x.y` style imports
- `has_markdown_fence` (must be false) — no raw ` ``` ` wrapping the code

---

## Results

### Baseline comparison

| Check | Qwen3.5-4B base (no fine-tune) | v11 fine-tune | v14 fine-tune |
|-------|-------------------------------|---------------|---------------|
| Correct handler signature | ❌ invented 8-param structure | ❌ | pending |
| Slash-style imports | ❌ dot-style | ❌ | pending |
| `extra_signatories` (not `self.signatures`) | ❌ | ❌ | pending |
| `validity_range` (not `self.time`) | ❌ | ❌ | pending |
| `lovelace_of` (not `output.assets.ada`) | ❌ | ❌ | pending |
| `publish` / `vote` handlers | ❌ | ❌ | pending |

*v14 column will be filled after training completes.*

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

### v14 dataset — complete

External audit (GPT-4) of v13 identified:
- **201 examples with dot-style imports** (`use aiken.crypto.bls12_381.g2`) — all `aiken_stdlib` / `PLAUSIBLE_NEEDS_CHECK`. Purged.
- **53% PLAUSIBLE_NEEDS_CHECK** — flagged as concern but confirmed not contamination: these use `output.address`, `output.datum` etc. which are valid Aiken v3 patterns not covered by stdlib signature scraping. Kept.
- **Coverage gaps**: governance handlers (vote/publish), advanced interval logic, dict/pairs patterns, rational arithmetic, multi-handler validators.
- **Only 37 CORRECTION examples (1%)** — insufficient anti-pattern density.
- **No holdout/eval split** — no way to measure overfitting during training.

Actions taken:
1. Purged 201 dot-import examples → `dataset_v13_purged.jsonl` (3,208)
2. Fixed 7 truly incomplete validators → `validators_fixed.jsonl`
3. Generated 479 new validators covering all gaps → `validators_v3.jsonl` (19 batches, 0 hallucinations)
4. Generated 50 new CORRECTION examples → `corrections_v2.jsonl` (Conway-era errors, dict/rational API errors, tx.fields errors)
5. Built final curriculum-ordered dataset → `dataset_v14_train.jsonl` (3,737 examples)
6. Created stratified 90/10 holdout split → `dataset_v14_train_split.jsonl` (3,363) + `dataset_v14_eval.jsonl` (374)

**Training strategy for v14:** curriculum ordering within a single run — CORRECTION first to anchor anti-patterns, VERIFIED next for canonical syntax, new curated validators for coverage, PLAUSIBLE last for diversity.

**Coverage added in v14 vs v13:**

| Handler/Pattern | v13 | v14 |
|----------------|-----|-----|
| `publish` (certificate) | 0 | 25+ |
| `vote` (governance) | 0 | 25+ |
| multi-handler validators | ~10 | 52+ |
| `interval.intersection` / `hull` | ~5 | 30+ |
| `dict.get` / `dict.to_pairs` | ~10 | 35+ |
| `rational.compare` / `rational.new` | ~5 | 30+ |
| complex mint redeemers | ~15 | 40+ |
| CORRECTION examples | 37 | 87 |

---

## Known limitations

- **PLAUSIBLE_NEEDS_CHECK is 44% of training data.** These examples use patterns like `output.address` and `output.datum` that are plausible but not directly verifiable against stdlib signatures. The model may learn some patterns that work in practice but aren't grounded in documentation. Curriculum ordering (placing PLAUSIBLE last) partially mitigates this.
- **Eval checks are string-based.** Passing all 15 tests does not guarantee the output compiles. True validation requires `aiken check`. See the note in the Evaluation suite section.
- **Two governance tests out of 15.** `vote` and `publish` handlers were added in v14 but the eval suite only has 2 tests covering them (vs 9 for spend/mint). Coverage asymmetry may hide regressions in governance patterns.
- **Single model dependency.** All examples were generated by Claude. Systematic gaps in Claude's Aiken knowledge would propagate uniformly across the dataset — there is no cross-model validation.
- **No compilation-based audit.** The audit pipeline checks API patterns and import style via regex, not by running `aiken check` on every output. Some syntactically invalid examples may have passed through.
- **Effectiveness tied to training data representation.** As noted in [[1]](#references), LLM-based improvement strategies work best for problems well-represented in pretraining data. Aiken v3 is a niche language — the base model's prior is weak, which is exactly why fine-tuning helps, but also means the model may struggle on patterns not covered in the dataset.

---

## References

[1] Chacón Sartori, C. & Blum, C. (2026). Combinatorial Optimization for All: Using LLMs to Aid Non-Experts in Improving Optimization Algorithms. *Inteligencia Artificial*, 29(77), 108–132. https://doi.org/10.4114/intartif.vol29iss77pp108-132

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

*Dataset v14 (complete) | 3,737 examples | train: 3,363 / eval: 374 | EN/ES | Aiken v3 + Conway handlers*
