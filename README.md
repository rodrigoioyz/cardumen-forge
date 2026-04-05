# Cardumen Forge

### Aiken v3 Fine-Tuning Dataset & Training Pipeline

A bilingual (EN/ES) fine-tuning dataset and training pipeline to specialize a small language model in Cardano smart contract development using Aiken v3, the Hydra Head L2 protocol, and CIP standards.

**Goal:** Turn a general-purpose code LLM into a domain expert that generates correct, compilable Aiken v3 validators — runnable locally on 6 GB VRAM.

*Cardumen (Spanish): a school of fish — collective movement, no single center, each one navigates but the group has direction. Forge: to build something strong from raw material. Cardumen Forge is about building the tools for anyone to write Cardano smart contracts.*

> **New here?** [Aiken](https://aiken-lang.org) is a functional language for writing Cardano smart contracts. Fine-tuning means taking a general-purpose code model and training it further on domain-specific examples so it specializes. This project does that for Aiken v3 — the result is a small model (~2.5 GB) you can run locally that generates correct Cardano validators instead of hallucinating Haskell or outdated Plutus patterns.

---

> ## Current State — April 2026
>
> | | |
> |---|---|
> | **Active model** | cardano-dev v8 (trained) · v9 next |
> | **Active dataset** | dataset_v23.jsonl — 3,739 examples · stdlib v3 · compile-verified |
> | **Pattern library** | 150 fuzz-verified `.ak` files in `data/patterns/` (01–25, variants a–f) |
> | **Benchmark** | 15 heuristic checks + **real `aiken check`** via PTY sandbox (stdlib v3.0.0) |
> | **v8 heuristic** | **15/15 (100%)** — first model to achieve perfect heuristic score |
> | **v8 compile** | **10/15 (67%)** · v7 was 9/15 (60%) |
> | **Aiken stdlib** | v3.0.0 · Plutus v3 |
> | **Scripts** | → [Project Structure](#part-ix--project-structure) |
>
> v8 is the first model trained on the fully v3-migrated and compile-verified dataset. It achieved 15/15 (100%) heuristic and 10/15 (67%) compile — both new records. Remaining compile failures: `pub type` leak, `MintedValue` removed constructor, `GovernanceCommittee` wrong name, missing `use aiken/interval`.

---

## Table of Contents

- [Part I — Context](#part-i--context)
  - [Motivation](#motivation)
  - [Why this exists](#why-this-exists)
  - [The model](#the-model)
- [Part II — Aiken v3 Reference](#part-ii--aiken-v3-reference)
  - [Handler signatures](#verified-handler-signatures)
  - [Import style](#verified-import-style-slash-not-dot)
  - [API patterns](#verified-api-patterns)
- [Part III — Quick Start](#part-iii--quick-start)
  - [Path A — Use existing dataset](#path-a--use-existing-dataset-recommended)
  - [Path B — Rebuild from scratch](#path-b--rebuild-dataset-from-scratch)
- [Part IV — The Dataset](#part-iv--the-dataset)
  - [Current state (v23)](#current-state-v23--active)
  - [Sources](#sources)
  - [Schema](#schema)
  - [Pipeline overview](#pipeline-overview)
  - [Dataset version history](#dataset-version-history)
  - [Fixes applied (v14 → v22)](#fixes-applied-v14--v22)
  - [Historical details](#how-the-dataset-was-built)
- [Part V — Training](#part-v--training)
  - [Config history](#config-history)
  - [Critical lessons learned](#critical-lessons-learned)
  - [System prompt](#system-prompt)
- [Part VI — Evaluation & Benchmark](#part-vi--evaluation--benchmark)
  - [Evaluation suite](#evaluation-suite--15-prompts)
  - [Benchmark setup & usage](#benchmark-setup--usage)
  - [Output example](#output-example)
- [Part VII — Results](#part-vii--results)
  - [Final benchmark table](#final-benchmark-table)
  - [What the numbers say](#what-the-numbers-say)
- [Part VIII — Development Log](#part-viii--development-log)
- [Part IX — Project Structure](#part-ix--project-structure)
- [Known Limitations](#known-limitations)
- [References](#references)
- [License](#license)

---

## Part I — Context

### Motivation

There is a recurring idea in this project that goes beyond the technical: the democratization of knowledge as a path to building societies with more opportunities.

Cardano is a network designed around principles of access and inclusion. Aiken, as its smart contract language, is capable and precise — but the barrier to entry remains high. Traditionally, writing verifiable on-chain logic has required a combination of functional programming expertise, deep familiarity with the eUTxO model, and manual consultation of documentation that general-purpose models simply do not know well enough to be useful.

The rapid advancement of LLMs across technical fields opens a different possibility. Research has shown that even a simple prompting strategy — giving a model an existing codebase as context and asking it to improve — can produce meaningful gains across a wide range of algorithms, without requiring the user to be a domain expert [[1]](#references). The underlying insight is that the model acts not as a replacement for expertise, but as a bridge to it.

This project applies that idea to Cardano development. In the spirit of the old Ratatouille principle — that anyone can cook — the ambition here is that anyone can write a smart contract. Not to replace engineers and auditors, who remain essential for production security, but to lower the threshold at which someone can learn, experiment, and build. A self-taught developer with no formal training in formal verification should be able to get a working first draft, understand why it works, and know what questions to ask next.

The approach is deliberately humble: one person, working iteratively with AI tools, building a grounded dataset from real documentation, and measuring improvement one failure mode at a time.

---

### Why this exists

The best open-source code models (Qwen2.5-Coder, DeepSeek-Coder, etc.) fail at Aiken in predictable ways:

- Generate Haskell syntax instead of Aiken (similar grammar, much higher pretraining frequency)
- Hallucinate stdlib functions that don't exist (`list.has_any`, `transaction.signatories`)
- Use v1/v2 Plutus patterns instead of the Aiken v3 handler structure
- Confuse `tx.validity_range` with the correct `self.validity_range`
- Don't know the eUTxO model or datum/redeemer/OutputReference semantics

This project builds a dataset grounded in real documentation to fix those failure modes, and tracks improvement through iterative audit cycles.

---

### The model

| Component | Detail |
|-----------|--------|
| Base model | `Qwen3.5-4B` |
| Method | 16-bit LoRA — r=32, alpha=64, target all linear layers |
| Framework | [unsloth](https://github.com/unslothai/unsloth) + TRL + PEFT |
| Training hardware | Google Colab A100 (40 GB VRAM) |
| Export format | GGUF Q4_K_M (~2.5 GB) |
| Local inference | LM Studio, 6 GB VRAM |
| Inference temperature | 0.1 (code generation) |

---

## Part II — Aiken v3 Reference

A quick reference card for the patterns the model is trained on. Useful for prompt engineering and for verifying model outputs manually.

### Verified handler signatures

All six Cardano handler purposes are valid. The `fn` keyword **must NOT be used** inside validator blocks — the correct syntax uses the handler name directly. The Aiken v3 compiler rejects `fn spend(` with a parse error.

```aiken
validator my_contract {
  spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool {
    ...
  }
  mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool {
    ...
  }
  withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool {
    ...
  }
  publish(redeemer: T, cert: Certificate, self: Transaction) -> Bool {
    ...
  }
  vote(redeemer: T, voter: Voter, self: Transaction) -> Bool {
    ...
  }
  propose(redeemer: T, self: Transaction) -> Bool {
    ...
  }
  else(_) {
    fail
  }
}
```

Imports for Conway-era handlers:
```aiken
use cardano/certificate.{Certificate}       // publish handler
use cardano/governance.{Voter}              // vote handler
use cardano/governance.{ProposalProcedure}  // propose handler
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

## Part III — Quick Start

### Prerequisites

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install anthropic openai datasets transformers trl peft unsloth
export ANTHROPIC_API_KEY=sk-ant-...
```

---

### Path A — Use existing dataset *(recommended)*

The active dataset (`dataset_v23.jsonl`) is already in the repo. Skip straight to fine-tuning.

**Step 1 — Fine-tune** *(Google Colab)*

1. Upload `data/processed/dataset_v23.jsonl` to Colab
2. Run `colab_finetune.ipynb`
3. Download GGUF from Google Drive → load in LM Studio

**Step 2 — Evaluate**

```bash
# Single model (LM Studio must be running with the fine-tuned model loaded)
python3 eval_model.py

# Multi-model comparison
python3 benchmark.py
python3 benchmark.py --compare-only   # re-print saved results without re-running
```

> **WSL / Windows note:** LM Studio runs on Windows. From WSL, the Windows host is not `localhost` — find your gateway IP with `ip route show default` and use that. The default in `benchmark.py` is `http://YOUR_GATEWAY_IP:3005`. See [Benchmark setup](#benchmark-setup--usage) for full details.

---

### Path B — Rebuild dataset from scratch

Only needed if you want to re-generate or extend the dataset. The raw sources are already scraped in `data/raw/`.

**Step 1 — Scrape raw sources** *(optional — already in `data/raw/`)*

```bash
python3 scripts/scrape/scrape_aiken_stdlib_github.py   # stdlib functions → data/raw/aiken_stdlib.json
python3 scripts/scrape/scrape_aiken_docs.py            # docs pages      → data/raw/aiken_docs.json
python3 scripts/scrape/scrape_hydra_docs.py            # Hydra protocol  → data/raw/hydra_docs.json
python3 scripts/scrape/scrape_github.py                # CIPs + patterns → data/raw/cips.json
```

**Step 2 — Generate training examples**

```bash
# Main grounded generation (stdlib, docs, CIPs, patterns, Hydra)
PYTHONUNBUFFERED=1 python3 -u scripts/generate/regenerate_from_raw.py 2>&1 | tee logs/regen.log

# Curated validators (19 batches: all handlers, dict, rational, governance, multi-handler)
PYTHONUNBUFFERED=1 python3 -u scripts/generate/generate_validators_v2.py 2>&1 | tee logs/validators_v3.log
# Output: data/processed/validators_v3.jsonl (479 examples)

# Correction examples (Conway-era errors, dict/rational API errors, tx.fields errors)
python3 scripts/generate/generate_corrections_v2.py
# Output: data/processed/corrections_v2.jsonl (50 examples)
```

**Step 3 — Build and split dataset**

```bash
# Curriculum-ordered merge
python3 scripts/build/build_dataset_v14.py
# Output: data/processed/dataset_v14_train.jsonl (3,737 examples)

# Stratified 90/10 holdout split
python3 scripts/build/build_holdout.py
# Output: dataset_v14_train_split.jsonl (3,363) + dataset_v14_eval.jsonl (374)
```

Then apply the cleaning pipeline (v15→v22) — see [Cleaning pipeline](#cleaning-pipeline-v14--v20).

---

## Part IV — The Dataset

### Current state (v23 — active)

| Metric | Value |
|--------|-------|
| Total examples | **3,739** |
| Languages | EN ~60% / ES ~40% |
| Sources | 15 + misc combined sources |
| `fn` prefix errors | **0** (was 21.5% in v14) |
| VERIFIED_V3_ALIGNED | **~94%** (was 53% in v14) |
| PLAUSIBLE_NEEDS_CHECK | ~1% (was 45% in v14) |
| Governance handler coverage | vote(64), publish(69), propose(15) — v8 correction patterns added in correction_set_v3 |
| `else(_)` fallback coverage | 6.4% (was 4.7% in v14) |
| Banned stdlib v3 patterns | **0** (migrated from v21) |
| Compile pass rate (code sources) | correction_set **100%**, governance **100%**, with_tests **100%** |
| Examples with `test` blocks | **323 (8.6%)** — 169 from `with_tests_examples`, rest embedded in other sources |
| All fixes verified against | `data/raw/aiken_stdlib.json` + `aiken check` |

Full version history in [Dataset version history](#dataset-version-history).

---

### Sources

| Source | n | Description | Status |
|--------|---|-------------|--------|
| `aiken_stdlib` | 1,310 | One Q&A per stdlib function — grounded in `aiken_stdlib.json` | VERIFIED |
| `cips` | 505 | CIPs — Ledger/Plutus/Tokens/Metadata | VERIFIED |
| `aiken_v3_curated_v2` | 436 | Complex validators: all handlers, reference inputs, governance, dict, rational | VERIFIED |
| `aiken_docs` | 344 | Language concepts, type system, syntax from official docs | VERIFIED |
| `aiken_design_patterns` | 176 | Production patterns from Anastasia-Labs (stdlib v3 compatible via v1.5.0) | VERIFIED |
| `correction_set` | 150 | Targeted v3 error corrections. **100% compile-verified.** | CORRECTION |
| `with_tests_examples` | 169 | Stdlib-function examples with embedded `test` blocks. **Compile-verified.** | VERIFIED |
| `reference_input_examples` | 82 | CIP-31 reference input patterns (find_input coverage) | VERIFIED |
| `v3_compat_examples` | 74 | v3-compatibility examples added in v22 | VERIFIED_V3 |
| `generated_governance_v1` | 54 | vote/publish/propose validators. **100% compile-verified.** | VERIFIED |
| `oracle_examples` | 47 | Oracle integration patterns — reference input price feeds | VERIFIED |
| `correction_set_v2` | 48 | Conway-era handler error corrections. **100% compile-verified.** | CORRECTION |
| `hydra_docs` | 60 | Hydra Head protocol — lifecycle, snapshots, fanout, L2 transactions | VERIFIED |
| `cip068_examples` | 32 | CIP-68 reference NFT + user token pair validation | VERIFIED |
| `correction_set_v3` | 30 | v8 hallucination corrections (5 patterns). **100% compile-verified.** | CORRECTION |
| *(misc combined)* | 231 | `aiken_docs.json + aiken_stdlib.json` (185), `aiken_stdlib.json` (22), `aiken_docs.json` (22), `aiken_docs.json + aiken_design_patterns.json` (2) | VERIFIED |
| **Total** | **3,739** | | |

**Status distribution:** VERIFIED_V3_ALIGNED ~94% / VERIFIED_V3 ~2% / CORRECTION ~3% / PLAUSIBLE_NEEDS_CHECK ~1%

> **Note on two Qwen models:** The fine-tuned model (`cardano-dev`) is based on **Qwen3.5-4B** (4B params, base for training). The benchmark comparison baseline is **qwen2.5-coder-7b** (7B params, separate general-purpose coder model). These are different models used for different purposes.

---

### Schema

Each example is a JSON line:

```json
{
  "lang": "en",
  "instruction": "Write a spend validator that checks the owner signed the transaction",
  "input": "",
  "output": "use aiken/collection/list\nuse cardano/transaction.{Transaction}\n\nvalidator owner_check {\n  spend(_datum: Data, _redeemer: Data, own_ref: OutputReference, self: Transaction) -> Bool {\n    list.has(self.extra_signatories, owner_key)\n  }\n}",
  "source": "aiken_stdlib",
  "topic": "aiken/cardano.transaction.extra_signatories",
  "review_status": "VERIFIED_V3_ALIGNED"
}
```

`review_status` values:
- `VERIFIED_V3_ALIGNED` — all APIs confirmed in `aiken_stdlib.json`
- `VERIFIED_V3` — compile-verified against `aiken check` (stdlib v3.0.0); used for `v3_compat_examples`
- `PLAUSIBLE_NEEDS_CHECK` — uses patterns like `output.address` that are plausible but not in stdlib signatures
- `CORRECTION` — negative correction example (broken → fixed)

---

### How the dataset was built

> **Note:** This section describes the initial pipeline that produced **v14 as the starting point**. The active dataset (v23, 3,739 examples) was built iteratively on top of this foundation through additional cleaning and generation cycles — see [Dataset version history](#dataset-version-history) for the full evolution.

#### Phase 1 — Scraping raw sources

All raw data lives in `data/raw/` and is **not synthetic** — it comes directly from official repositories and documentation sites.

| File | Content | How scraped |
|------|---------|-------------|
| `aiken_stdlib.json` | 458 functions — module, name, signature, description | GitHub API on `aiken-lang/stdlib`, parser for `///` doc-comments |
| `aiken_docs.json` | 28 pages with sections and code examples | HTTP crawler on `aiken-lang.org` with BeautifulSoup4 |
| `aiken_design_patterns.json` | 22 production pattern files | GitHub API on `Anastasia-Labs/design-patterns` |
| `cips.json` | 134 CIPs with title, category, status, content | GitHub API on `cardano-foundation/CIPs` |
| `hydra_docs.json` | 35 pages of Hydra protocol docs | Crawler on `hydra.family` Docusaurus site |

#### Phase 2 — Q&A generation via Claude API

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
- `generate_validators_v2.py` — generates validators combining 2+ APIs (harder patterns), 19 batches
- `generate_corrections_v2.py` — generates correction examples for specific hallucination patterns

#### Phase 3 — Audit and purge

After each generation run, `audit_v9.py` checks:
- Coverage of v3 APIs in outputs (how many examples actually use each function)
- Contamination — v2 patterns, wrong imports, hallucinated functions
- Combination coverage — examples that use lovelace+signatories together, NFT+time, etc.

`purge_dot_imports.py` removes contaminated examples without touching correction examples.

This loop ran from v6 to v13, each iteration:
1. Fine-tune → evaluate on test prompts
2. Identify failure patterns in model output
3. Add targeted correction examples or grounded re-generation
4. Purge contamination → new dataset version

---

### Pipeline overview

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
        ├── dataset_v14_train_split.jsonl  3,363  ← historical baseline (superseded by v22)
        └── dataset_v14_eval.jsonl           374  ← holdout (still valid for regression testing)
        │
        ▼
[Cleaning pipeline v15 → v20]
   fix_fn_prefix · build_v16 · fix_types · regenerate_truncated
   generate_governance_examples · dedup · review_plausible
        │
        ▼
dataset_v22.jsonl  3,748 examples
        │
        ▼
[scripts/audit_dataset_compile.py + scripts/regenerate_failing.py]
   compile-verify every example, fix failures via Claude API
        │
        ▼
[scripts/generate/generate_correction_set_v3.py]
   +30 correction examples for 5 v8 hallucination patterns (100% compile-verified)
        │
        ▼
[scripts/promote_plausible.py]
   Path A: compile-check pure validators → 57 promoted
   Path B: banned-pattern check Q&A outputs → 867 promoted
   Total: 924 PLAUSIBLE → VERIFIED_V3_ALIGNED
        │
        ▼
[scripts/fix_plausible_failures.py]
   Claude API repairs 97 type_cycle / type_mismatch / banned_pattern failures
   stdlib local types as context → compile-verified on each fix
        │
        ▼
[scripts/generate/generate_oracle_examples.py + generate_cip068_examples.py]
   +47 oracle integration patterns · +32 CIP-68 reference NFT patterns
        │
        ▼
[scripts/generate/generate_with_tests.py + scripts/add_tests_to_verified.py]
   +169 examples with embedded `test` blocks — compile-verified via aiken check
   15 stdlib topics · deduplication by instruction prefix
        │
        ▼
[scripts/migrate_dataset_to_v3.py + dedup + correction fixes]
   dedup + compile verification + import fixes → v23
        │
        ▼
dataset_v23.jsonl  3,739 examples  ← ACTIVE TRAINING SET
        │
        ▼
[data/patterns/ — 150 fuzz-verified .ak files]
   25 categories × 6 variants (a–f) · property-based fuzz tests
   aiken/fuzz · aiken check --max-success=200 · zero dead code · zero warnings
        │
        ▼
[scripts/test_patterns.py]  sandbox harness (eval/aiken_sandbox/)
   retry logic · detailed logs → logs/patterns_*.json
        │
        ▼
[scripts/patterns_to_dataset.py]  compile-gated ingestion
   only PASS → dataset record · extracts docstring instruction
   topic from numeric prefix · review_status=VERIFIED_FUZZ_PASS
        │
        ▼
data/processed/components/patterns_verified.jsonl  ← v24 input
        │
        ▼
dataset_v24.jsonl  ~3,889 examples  ← IN PROGRESS

[Colab QLoRA — unsloth + Qwen3.5-4B]
        │
        ▼
cardano-dev-8.0-v22-q4_k_m.gguf  Q4_K_M ~2.5 GB
        │
        ▼
[benchmark.py]
   15 prompts × N model versions, automated pass/fail, comparison table
```

---

### Historical details

<details>
<summary>Cleaning pipeline, improvement metrics, v14 baseline — click to expand</summary>

### Cleaning pipeline (v14 → v20)

After v5 training confirmed that the dataset was the problem, a systematic cleaning pipeline was built. Every fix is verified against `data/raw/aiken_stdlib.json` — the ground truth — before touching any example.

#### Audit tool

`scripts/audit_dataset_quality.py` uses the Claude API to review a balanced sample of examples across all 12 sources and generates a structured report in `logs/`. It runs two passes:

1. **Automated scan** — regex checks for known anti-patterns in outputs (dot imports, wrong API names, broken code fences, unbalanced braces)
2. **Claude API review** — sampled examples sent with stdlib ground truth as context; Claude identifies quality issues, coverage gaps, and balance problems

```bash
python3 scripts/audit_dataset_quality.py \
  --dataset data/processed/dataset_v19_dedup.jsonl \
  --output logs/audit_v19.md \
  --samples 10   # examples per source (10 = 120 total across 12 sources)
```

> **Critical rule:** before acting on any Claude API audit finding, verify it against `data/raw/aiken_stdlib.json`. The first audit incorrectly flagged `assets.reduce`, `assets.restricted_to`, and `assets.flatten` as nonexistent functions — they all exist. The stdlib JSON is authoritative; Claude's knowledge of Aiken is not.

#### Cleaning scripts

Each fix is a standalone script with `--dry-run` support. All operate on outputs only (never inputs, which may intentionally show wrong code) and skip correction examples.

| Script | What it fixes | Verified against |
|--------|--------------|-----------------|
| `scripts/fix_fn_prefix.py` | `fn spend/mint/withdraw/vote/publish(` → removes `fn` | Aiken v3 parser (confirmed by Claude API) |
| `scripts/build_v16.py` | `fn else(` → `else(`; removes broken examples | `aiken_stdlib.json` fingerprints |
| `scripts/fix_types.py` | `ScriptCredential` → `Script`; `PolicyId` from wrong module | `aiken_stdlib.json` type registry |
| `scripts/regenerate_truncated.py` | Regenerates 61 truncated outputs using source docs from `data/raw/` | Claude API + source context |
| `scripts/generate_governance_examples.py` | Generates positive vote/publish/propose examples from scratch | stdlib-verified handler signatures |
| `scripts/dedup_dataset.py` | Two-pass dedup: exact output hash + n-gram instruction similarity | — |
| `scripts/compare_datasets.py` | Compares quality metrics across dataset versions | — |
| `scripts/review_plausible.py` | Promote/remove PLAUSIBLE via local stdlib check (no API cost) | `aiken_stdlib.json` |
| `scripts/migrate_dataset_to_v3.py` | Full stdlib v3 migration: `pub type`, API renames, auto-imports, cert fields, strip markdown | `aiken_stdlib.json` + pattern lists |
| `scripts/audit_dataset_compile.py` | Runs `aiken check` on every output; emits pass/fail JSONL report | `aiken check` (PTY sandbox) |
| `scripts/regenerate_failing.py` | Regenerates compile-failing examples via Claude API using error context | Claude API + `aiken check` |
| `scripts/fix_import_keyword.py` | `import x.y.z.{A}` → `use x/y/z.{A}`; deletes off-topic examples | Regex + manual review |
| `scripts/audit_structural_dupes.py` | Detects structurally similar outputs via normalized MD5 hash | — |
| `scripts/generate/generate_correction_set_v3.py` | Generates compile-verified correction examples for 5 v8 hallucination patterns | Claude API + `aiken check` |
| `scripts/promote_plausible.py` | Promotes PLAUSIBLE → VERIFIED via compile check (pure validators) + banned-pattern check (Q&A outputs) | `aiken check` + local banned-pattern list |
| `scripts/fix_plausible_failures.py` | Repairs compile failures via Claude API with local stdlib types as context (type_cycle, type_mismatch, banned_pattern) | Claude API + `aiken check` |

### Dataset version history

| Version | Examples | Key change |
|---------|----------|------------|
| v14 | 3,363 | Original train split — baseline with all quality issues |
| v15 | 3,363 | **761 `fn` prefix fixes** on handlers + 22 `fn else(` fixes |
| v16 | 3,357 | Removed 6 examples with broken/nonexistent API usage |
| v17 | 3,357 | Fixed `ScriptCredential`→`Script` (2), `PolicyId` wrong import (17) |
| v18b | 3,357 | 61 truncated outputs regenerated from source docs (61/61 success) |
| v19 | 3,412 | +55 new governance examples: vote(20), publish(20), propose(15) |
| v19_dedup | 3,406 | Dedup: 1 exact + 5 near-duplicate removed |
| v20 | 3,319 | 351 PLAUSIBLE promoted to VERIFIED, 87 bad examples removed |
| v21 | 3,401 | +82 CIP-31 reference input examples (find_input coverage: 41 → 159) |
| v22 | 3,475 | Full stdlib v3 migration (`migrate_dataset_to_v3.py`): pub type fixes, API renames, auto-imports, cert field renames, strip markdown fences. +74 new v3-compat examples. |
| **v22 compile-verified** | **3,474** | **Individual compile audit on all examples (`audit_dataset_compile.py`). Failing examples regenerated via Claude API (`regenerate_failing.py`). correction_set 100%, governance 100%. 1 irreparable example removed.** |
| **v22 import-fixed** | **3,473** | **`fix_import_keyword.py`: 42 examples fixed (`import x.y.z` → `use x/y/z`). 1 PyCardano/Python example deleted.** |
| **v22 + correction_set_v3** | **3,503** | **`generate_correction_set_v3.py`: +30 compile-verified correction examples for 5 v8 hallucination patterns (pub_type ×6, minted_value ×6, governance_committee ×6, missing_interval ×6, inline_datum ×6).** |
| **v22 + promote_plausible** | **3,503** | **`promote_plausible.py`: 924 PLAUSIBLE → VERIFIED (compile check + banned-pattern check). 127 failures logged.** |
| **v22 + fix_plausible** | **3,503** | **`fix_plausible_failures.py`: 97/99 failures repaired via Claude API (stdlib local context). 2 irreparable deleted. VERIFIED ~95%.** |
| **v22 + oracle/cip068** | **3,582** | **`generate_oracle_examples.py`: +47 oracle patterns. `generate_cip068_examples.py`: +32 CIP-68 examples. Dedup pass: 3 exact removed → 3,579.** |
| **v22 + with_tests** | **3,748** | **`generate_with_tests.py` + `add_tests_to_verified.py`: +169 examples with embedded `test` blocks across 15+ stdlib topics. Compile-verified via `aiken check`.** |
| **v23** | **3,739** | **Dedup pass + compile verification + import fixes (`fix_import_keyword.py`). 9 broken examples removed. Active dataset.** |
| **v24 (in progress)** | **~3,889** | **+150 fuzz-verified patterns via `patterns_to_dataset.py`. 25 categories × 6 variants. All pass `aiken check --max-success=200`. Zero dead code, zero warnings.** |

### What changed: v22 → v23 → v24

**v22 issues found during audit:**
- `import` keyword instead of `use` in 42 examples (Aiken v3 uses `use x/y/z`)
- `aiken/bytearray` imports instead of correct `aiken/primitive/bytearray`
- Dead code in examples: unused private functions, unused parameters, no-op imports
- 9 examples with broken/uncompilable patterns removed via dedup + compile pass

**v23 (active):** Dedup + compile verification pass over v22. Result: 3,748 → 3,739 examples. All remaining examples compile against stdlib v3.0.0.

**v24 (in progress):** 150 property-based fuzz test patterns across 25 categories, each with 6 variants (a–f). Quality guarantees enforced per file:
- Correct stdlib v3 imports (`aiken/collection/list`, `aiken/primitive/bytearray`, etc.)
- Zero dead code — all functions referenced in at least one test
- Zero compiler warnings
- 4+ property tests per file using `aiken/fuzz` or `cardano/fuzz`
- Verified with `aiken check --max-success=200` before inclusion

**Pipeline:** `scripts/test_patterns.py` (sandbox harness) → `scripts/patterns_to_dataset.py` (compile-gated ingestion). Only files with `returncode == 0` become dataset records.

---

#### Coverage gaps addressed (v18b + v19)

The audit identified three handler types with near-zero *positive* examples. All existing `vote` and `publish` examples were error-correction examples — the model was only learning about them in the context of "here's what's wrong." `propose` had zero examples of any kind.

`scripts/generate_governance_examples.py` generates write-from-scratch examples using:
- Correct handler signatures from `aiken_stdlib.json`
- Diverse scenarios (DRep, ConstitutionalCommittee, StakePoolOperator for vote; all Certificate constructors for publish; treasury/parameter/hardfork guardrails for propose)
- Bilingual (EN/ES ~50/50)
- `review_status: VERIFIED_V3_ALIGNED` — each output checked before inclusion

```bash
# Test: generate 2 vote examples and inspect
python3 scripts/generate_governance_examples.py --handler vote --count 2

# Full run: generate all 55 and append to v18b → v19
python3 scripts/generate_governance_examples.py --append
```

---

### Measured improvement (v14 → v20)

`scripts/compare_datasets.py` runs after each pipeline cycle to quantify changes. Full output:

```
  Metric                              v14           v19           v20
  Total examples                    3,363         3,406         3,319

  ── SYNTAX ERRORS (lower = better) ──
  fn prefix in handlers         723 (21.5%)  ✅   0 ( 0.0%)  ✅   0 ( 0.0%)
  PolicyId wrong module         438 (13.0%)      446 (13.1%)  ✅ 364 (11.0%)
  Truncated outputs              61 ( 1.8%)  ✅  23 ( 0.7%)  ✅  19 ( 0.6%)

  ── COVERAGE (higher = better) ──
  Handler: publish(              35 ( 1.0%)        56 ( 1.6%)       56 ( 1.7%)
  Handler: vote(                 36 ( 1.1%)        58 ( 1.7%)       58 ( 1.7%)
  Handler: propose(               0 ( 0.0%)        15 ( 0.4%)       15 ( 0.5%)

  ── QUALITY SIGNALS ──
  Has else(_) fallback          157 ( 4.7%)  ✅  241 ( 7.1%)  ✅  212 ( 6.4%)

  ── STATUS DISTRIBUTION ──
  VERIFIED_V3_ALIGNED          1785 (53.1%)     1838 (54.0%)  ✅2189 (66.0%)
  PLAUSIBLE_NEEDS_CHECK        1500 (44.6%)     1490 (43.7%)  ✅1052 (31.7%)
```

Key results: `fn` prefix (21.5% → 0%) was the root cause of v2–v4 failures. VERIFIED ratio jumped from 53% → 66% after PLAUSIBLE review. `propose` went from 0 to 15 examples.

---

### Measured improvement (v20 → v22)

> **Snapshot:** The v22 column below shows the dataset at 3,503 examples — the state after stdlib migration and before oracle/cip068/with_tests additions. The active dataset is now v23 (3,739 examples). See [Dataset version history](#dataset-version-history) for the full progression.

The v20→v22 cycle focused on stdlib v3 compatibility and compile verification rather than example count. `scripts/compare_datasets.py` output (v20=3,319 file no longer on disk; v21 is the earliest available backup). The script now includes v3-migration metrics that were not tracked in earlier cycles:

```
  Metric                                           v14              v19              v21              v22
  ──────────────────────────────────────────────────────────────────────────────────────────────────────

  Total examples                                 3,363            3,406            3,401            3,503

  ── SYNTAX ERRORS (lower = better) ──
  fn prefix in handlers                    723 (21.5%)   ✅    0 ( 0.0%)        0 ( 0.0%)        0 ( 0.0%)
  Dot-style imports                         17 ( 0.5%)        16 ( 0.5%)        16 ( 0.5%)   ✅   11 ( 0.3%)
  Wrong Credential names                     2 ( 0.1%)         2 ( 0.1%)         2 ( 0.1%)   ✅    1 ( 0.0%)
  PolicyId wrong module                    438 (13.0%)       446 (13.1%)   ✅  380 (11.2%)      403 (11.6%)  ⚠
  Truncated outputs                         61 ( 1.8%)   ✅   23 ( 0.7%)   ✅   19 ( 0.6%)       44 ( 1.3%)  ⚠

  ── COVERAGE (higher = better) ──
  Handler: spend(                          948 (28.2%)       978 (28.7%)      1027 (30.2%)      1074 (30.9%)
  Handler: publish(                         35 ( 1.0%)        56 ( 1.6%)        56 ( 1.6%)   ✅   69 ( 2.0%)
  Handler: vote(                            36 ( 1.1%)        58 ( 1.7%)        58 ( 1.7%)        58 ( 1.7%)
  Handler: propose(                          0 ( 0.0%)        15 ( 0.4%)        15 ( 0.4%)        14 ( 0.4%)

  ── QUALITY SIGNALS ──
  Has validator block                     1825 (54.3%)      1895 (55.6%)      1899 (55.8%)   ✅ 1970 (56.7%)
  Has else(_) fallback                     157 ( 4.7%)   ✅  241 ( 7.1%)       221 ( 6.5%)      220 ( 6.3%)
  Uses extra_signatories                   684 (20.3%)       718 (21.1%)       749 (22.0%)      814 (23.4%)

  ── V3 MIGRATION (lower = better) ──
  Banned hallucination patterns             19 ( 0.6%)        19 ( 0.6%)        19 ( 0.6%)   ✅    4 ( 0.1%)
  Markdown fences in output                567 (16.9%)       562 (16.5%)       497 (14.6%)   ✅    0 ( 0.0%)

  ── V3 MIGRATION (higher = better) ──
  Has pub type declaration                 675 (20.1%)       686 (20.1%)       685 (20.1%)   ✅ 1022 (29.4%)

  ── STATUS DISTRIBUTION ──
  CORRECTION                                78 ( 2.3%)        78 ( 2.3%)        78 ( 2.3%)       78 ( 2.2%)
  PLAUSIBLE_NEEDS_CHECK                   1500 (44.6%)      1490 (43.7%)      1052 (30.9%)     1052 (30.3%)
  VERIFIED_V3                                0 ( 0.0%)         0 ( 0.0%)         0 ( 0.0%)   ✅   74 ( 2.1%)
  VERIFIED_V3_ALIGNED                     1785 (53.1%)      1838 (54.0%)      2271 (66.8%)     2270 (65.3%)
```

Key results of the v22 migration cycle: **markdown fences 497→0** (all stripped), **pub type 685→1022** (+337 examples migrated to correct `pub type` syntax), **banned patterns 19→4** (hallucination targets largely eliminated). `VERIFIED_V3` (74) is the new `v3_compat_examples` source. `publish` coverage 56→69.

> **⚠ Two legacy metrics appear to worsen but are measurement artifacts:**
> - **PolicyId wrong module (380→403):** new v3-compat examples include correction patterns that intentionally use the wrong import as the "before" side.
> - **Truncated outputs (19→44):** the truncation heuristic checks the last character (`}`, `)`, etc.) — after markdown fence stripping, some outputs end with a newline or identifier not in the expected set. These are not actually truncated.

#### What `migrate_dataset_to_v3.py` changed

- `pub type` fix: all user-defined types used in handler signatures wrapped with `pub`
- API renames: `assets.lovelace` → `assets.lovelace_of`, removed `assets.restricted_to`
- Auto-imports: added missing `use cardano/transaction.{OutputReference}`, `use cardano/assets.{PolicyId}` where needed
- Certificate field renames: `at_epoch` field updates
- Stripped markdown fences from outputs (model should output raw code, not fenced blocks)

#### What `regenerate_failing.py` did

- Compiled every example from `correction_set` and `generated_governance_v1` individually via `aiken check`
- Sent failing examples (broken code + compiler error) to Claude API for correction
- 3 retry attempts per example, feeding the latest error back on each retry
- Replaced failing outputs with verified compilable versions
- 1 example from `generated_governance_v1` ([3309] — propose validator with complex `ProposalProcedure` pattern-match) failed all attempts and was deleted

---

### Fixes applied (v14 → v22)

| # | Problem | Scale | Status |
|---|---------|-------|--------|
| 1 | 61 truncated outputs | 61 | ✅ Fixed in v18b — regenerated from source docs |
| 2 | 0 positive propose/vote/publish examples | — | ✅ Fixed in v19 — 55 new governance examples |
| 3 | Duplicate and near-duplicate examples | 6 | ✅ Fixed in v19_dedup |
| 4 | 1,490 PLAUSIBLE_NEEDS_CHECK unverified | 44% | ✅ Fixed in v20 — 351 promoted, 87 removed, 1,052 remain |
| 5 | stdlib v2 patterns (wrong imports, old API names) | 200+ | ✅ Fixed in v22 — `migrate_dataset_to_v3.py` (0 banned patterns) |
| 6 | correction_set compile failures (26.7%) | 39/150 | ✅ Fixed in v22 compile-verify cycle — 100% pass rate |
| 7 | governance compile failures (1.8%) | 1/54 | ✅ Fixed in v22 compile-verify cycle — 1 example deleted, 100% pass rate |
| 8 | `import` keyword instead of `use` in outputs | 76 | ✅ Fixed 42 via `fix_import_keyword.py` (BLS12-381/math/utility modules). 1 PyCardano example deleted. 33 remaining are `import` in prose text, not Aiken statements. |
| 9 | Thematic concentration: 814 examples (23.4%) use `extra_signatories` | 814 | Not a dedup problem — `audit_structural_dupes.py` found only 52 true structural duplicates in the full dataset (1.5%). The 814 are diverse validators that happen to check signatures. Fix: add more examples for underrepresented patterns (propose, interval, governance constructors) to rebalance, not dedup. |
| 10 | 1,052 remaining PLAUSIBLE unverifiable locally | 32% | ✅ Fixed — `promote_plausible.py` promoted 924/1051 (88%). `fix_plausible_failures.py` repaired 97 more via Claude API. ~30 irreducible remain (parser errors, unknown modules). PLAUSIBLE down from 32% → ~1%. |
| 11 | 5 compile failures in v8 benchmark | 5/15 | ✅ Fixed via `correction_set_v3` (+30 examples): `pub_type` ×6, `minted_value` ×6, `governance_committee` ×6, `missing_interval` ×6, `inline_datum` ×6. All 100% compile-verified. |

---

### v14 composition — historical baseline

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
- `dataset_v14_eval.jsonl` — 374 examples (holdout — use for eval)

**External audit (GPT-4) of v13 identified:**
- **201 examples with dot-style imports** (`use aiken.crypto.bls12_381.g2`) — all `aiken_stdlib` / `PLAUSIBLE_NEEDS_CHECK`. Purged.
- **53% PLAUSIBLE_NEEDS_CHECK** — flagged as concern but confirmed not contamination: these use `output.address`, `output.datum` etc. which are valid Aiken v3 patterns not covered by stdlib signature scraping. Kept.
- **Coverage gaps**: governance handlers (vote/publish), advanced interval logic, dict/pairs patterns, rational arithmetic, multi-handler validators.
- **Only 37 CORRECTION examples (1%)** — insufficient anti-pattern density.
- **No holdout/eval split** — no way to measure overfitting during training.

**Actions taken:**
1. Purged 201 dot-import examples → `dataset_v13_purged.jsonl` (3,208)
2. Fixed 7 truly incomplete validators → `validators_fixed.jsonl`
3. Generated 479 new validators covering all gaps → `validators_v3.jsonl` (19 batches, 0 hallucinations)
4. Generated 50 new CORRECTION examples → `corrections_v2.jsonl` (Conway-era errors, dict/rational API errors, tx.fields errors)
5. Built final curriculum-ordered dataset → `dataset_v14_train.jsonl` (3,737 examples)
6. Created stratified 90/10 holdout split → `dataset_v14_train_split.jsonl` (3,363) + `dataset_v14_eval.jsonl` (374)

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

</details>

---

## Part V — Training

The training notebook (`colab_finetune.ipynb`) handles:
- Installing unsloth + dependencies
- Loading the base model in bfloat16
- Configuring 16-bit LoRA (r=32, alpha=64)
- ChatML formatting with Aiken v3 rules in system prompt
- Training loop with gradient accumulation
- GGUF Q4_K_M export and Drive save

---

### Config history

**v2–v4** (3 epochs / ~300 steps):
```python
model_name     = "unsloth/Qwen3.5-4B"
max_seq_length = 2048
load_in_4bit   = False        # full bfloat16
lora_r         = 32
lora_alpha     = 64
num_epochs     = 3            # ~315 steps — undertrained per benchmark results
learning_rate  = 2e-4
batch_size     = 4
grad_accum     = 8            # effective batch = 32
```

**v5** (dataset v20, 7 epochs — step count hypothesis test, wrong checkpoint config):
```python
num_epochs     = 7
eval_steps     = 50
# missing: greater_is_better=False → exported wrong checkpoint
# result: 14/15 (93%) — dataset quality compensated for checkpoint error
```

**v6** (dataset v20, 7 epochs — same dataset as v5, correct config):
```python
num_epochs             = 7
eval_steps             = 50
save_steps             = 50           # must equal eval_steps
load_best_model_at_end = True
metric_for_best_model  = "eval_loss"
greater_is_better      = False        # CRITICAL — see lesson below
# EarlyStoppingCallback(early_stopping_patience=3)
```

---

### Critical lessons learned

> **`greater_is_better=False` is non-negotiable when tracking val loss.**
> Without it, HuggingFace Trainer treats higher loss as better and loads the **worst** checkpoint instead of the best. This caused v5's training run to export a degraded model despite having a good val loss curve. Confirmed fix in v6: best checkpoint was step 200 (val_loss 0.3271), final step was ~490 — loading the wrong one would have exported an overfit model.

> **`save_steps` must equal `eval_steps`.**
> If eval happens at step 50 but save happens at step 100, the best checkpoint at step 50 doesn't exist on disk when the trainer tries to load it. Both must be the same value.

> **The benchmark system prompt must be identical to the training system prompt.**
> Fine-tuned models learn correlations between prompt structure and output patterns. Running the benchmark with a generic 4-line prompt on a model trained with a 30-line prompt produces ~20% instead of 93%. This is not a bug — it's the intended behavior of instruction fine-tuning. The system prompt used in `benchmark.py` must be copied exactly from `colab_finetune.ipynb`.

> **TRL 1.x note:** `max_seq_length` and `packing` belong in the `SFTTrainer()` constructor, **not** in `SFTConfig`. Passing them inside `SFTConfig` raises `TypeError: SFTConfig.__init__() got an unexpected keyword argument 'max_seq_length'`. Pass optimizer/scheduler/logging args in `SFTConfig`; pass `max_seq_length` and `packing` directly to `SFTTrainer`.

---

### System prompt

The system prompt injected at training time (and required at inference time):

```
You are an expert Aiken v3 smart contract engineer for the Cardano blockchain.
You write correct, compilable Aiken v3 validators using only verified APIs.

CRITICAL — handler syntax inside validator blocks (NO fn keyword):
  validator my_contract {
    spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool { ... }
    mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool { ... }
    ...
    else(_) { fail }
  }

IMPORTS (slash style — never dot):
  use cardano/assets
  use cardano/transaction.{Transaction, OutputReference}
  use aiken/collection/list

VERIFIED API PATTERNS:
  ADA check  : assets.lovelace_of(output.value) — NEVER output.assets.ada
  Signatures : list.has(self.extra_signatories, key) — NEVER self.signatures
  Time       : self.validity_range — NEVER self.time
```

---

## Part VI — Evaluation & Benchmark

### Evaluation suite — 15 prompts

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

All 15 tests also check automatically:
- `has_validator_block` — output contains `validator { ... }`
- `has_complete_handler` — at least one handler (`spend(`, `mint(`, etc.) inside the block
- `has_slash_imports` — at least one `use x/y` style import present
- `no_dot_imports` — no `use x.y` style imports (True = clean)
- `wrapped_in_markdown` — informational only; does not affect pass/fail

> **Note on eval methodology:** These checks catch the most common failure modes observed in v11 but are string-based — a model writing `extra_signatories` in a comment but not in actual logic would pass.
>
> **`benchmark.py` now includes real compilation** via `aiken check` on every output, using an isolated sandbox project (`eval/aiken_sandbox/`) with stdlib v3.0.0 and Plutus v3. Each output is written to the sandbox, compiled, and the result reported as `[C:✅]` / `[C:❌]` alongside the heuristic score. Use `--skip-compile` to run heuristic-only. The heuristic score and compile score are tracked independently — a model can pass all 15 string checks but still fail compilation.

---

### Benchmark setup & usage

`benchmark.py` runs the same 15-prompt eval suite across multiple model versions loaded in LM Studio and prints a comparison table.

**How it works:**
1. At startup, queries the LM Studio API and lists every model currently loaded.
2. For each model in the `MODELS` list, matches it against loaded models (exact → partial).
3. Runs all 15 prompts **sequentially** against that model (not in parallel — resource-limited environments with ≤8 GB VRAM can only run one inference at a time).
4. Saves results to `eval_results/bench_{timestamp}_{label}.json`.
5. After each model, prints an incremental comparison table.

**Requires:** LM Studio running with at least one model loaded + `pip install openai`.

**WSL → Windows networking:** LM Studio is a Windows app; its API is not reachable at `localhost` from WSL. The script defaults to `http://YOUR_GATEWAY_IP:3005`. To find your actual gateway:

```bash
ip route show default
# → default via YOUR_GATEWAY_IP dev eth0  ← use this IP
```

If connections still hang, LM Studio may be bound to `127.0.0.1` only. Enable **"Serve on local network"** in LM Studio's server settings, then add a firewall rule (PowerShell as Admin on Windows):

```powershell
New-NetFirewallRule -DisplayName "LM Studio WSL" -Direction Inbound -Protocol TCP -LocalPort 3005 -Action Allow
```

Verify with:
```bash
curl http://YOUR_GATEWAY_IP:3005/v1/models
# Should return JSON listing all loaded models
```

**Usage:**
```bash
# Run all model versions (auto-detects what's loaded)
python3 benchmark.py

# Custom URL
python3 benchmark.py --url http://YOUR_GATEWAY_IP:3005

# Run only specific versions
python3 benchmark.py --models base v3

# Re-print comparison from saved JSON files (no inference)
python3 benchmark.py --compare-only
```

**Models configured** — edit the `MODELS` list in `benchmark.py` to match your LM Studio model IDs:

```python
MODELS = [
    { "label": "qwen2.5-coder-7b (base)",              "lm_name": "qwen2.5-coder-7b-instruct",     "version": "base"   },
    { "label": "gemma-4-e4b (base)",                   "lm_name": "google_gemma-4-e4b-it",         "version": "gemma4" },
    { "label": "cardano-dev v1",                       "lm_name": "cardano-dev qwen3.5-4b.q4_k_m", "version": "v1"     },
    { "label": "cardano-dev v2 (dataset v13)",         "lm_name": "cardano-dev 2.0 qwen3.5-4b",    "version": "v2"     },
    { "label": "cardano-dev v3 (dataset v13)",         "lm_name": "cardano-dev 3.0 qwen3.5-4b",    "version": "v3"     },
    { "label": "cardano-dev v4 (dataset v14)",         "lm_name": "cardano-dev 4.0 qwen3.5-4b",    "version": "v4"     },
    { "label": "cardano-dev v5 (dataset v20, wrong ckpt)", "lm_name": "cardano-dev 5.0 qwen3.5-4b","version": "v5"     },
    { "label": "cardano-dev v6 (dataset v20)",         "lm_name": "cardano-dev 6.0 qwen3.5-4b",    "version": "v6"     },
    { "label": "cardano-dev v7 (dataset v21)",         "lm_name": "cardano-dev 7.0 qwen3.5-4b",    "version": "v7"     },
    { "label": "cardano-dev v8 (dataset v22)",         "lm_name": "cardano-dev 8.0 qwen3.5-4b",    "version": "v8"     },
]
```

The `lm_name` values are partial strings — use whatever fragment uniquely identifies your model in `curl http://<host>:<port>/v1/models`. Partial matching is supported.

Results are saved per model to `eval_results/` and excluded from git (see `.gitignore`).

---

### Output example

```
══════════════════════════════════════════════════════════════════════
  CARDUMEN FORGE — BENCHMARK RESULTS
══════════════════════════════════════════════════════════════════════

  Model                                  Pass    Score       Δ
  ────────────────────────────────────────────────────────────
  qwen2.5-coder-7b (base, no fine-tune)   0/15       0%
  cardano-dev v1                         11/15      73%     +73%  ████████████
  cardano-dev v2 (dataset v13)           10/15      67%      −7%  ████████████
  cardano-dev v3 (dataset v13)           12/15      80%     +13%  ████████████████

  Category                  qwen2.5-coder-7b  cardano-dev v1  ...
  ──────────────────────────────────────────────────────────────
  mint                          0/2 (0%)        1/2 (50%)  ...
  publish                       0/1 (0%)        1/1 (100%) ...
  spend                         0/9 (0%)        5/9 (56%)  ...
  vote                          0/1 (0%)        1/1 (100%) ...
  withdraw                      0/1 (0%)        1/1 (100%) ...
══════════════════════════════════════════════════════════════════════
```

---

## Part VII — Results

### Final benchmark table

> **Note on benchmark history:** Early runs of v2–v5 used a generic 4-line system prompt instead of the full training system prompt. Those results (7%, 13%, 13%, 20%) were completely wrong — artifacts of inference/training prompt mismatch, not of model quality. The table below uses the correct system prompt for all models.

| Model | Dataset | Examples | Best ckpt (steps) | Heuristic | Score | Δ | Compile |
|-------|---------|----------|-------------------|-----------|-------|---|---------|
| qwen2.5-coder-7b (base) | — | — | — | 0/15 | 0% | — | — |
| gemma-4-e4b (base) | — | — | — | 5/15 | 33% | +33% | — |
| cardano-dev v1 | early | — | ~700 | 11/15 | 73% | +40% | — |
| cardano-dev v2 | v13 | — | ~300 | 10/15 | 67% | −7% | — |
| cardano-dev v3 | v13 | — | ~300 | 12/15 | 80% | +13% | — |
| cardano-dev v4 | v14 | — | ~300 | 13/15 | 87% | +7% | — |
| cardano-dev v5 | v20 | 3,319 | ~300 (wrong ckpt) | 14/15 | 93% | +7% | — |
| cardano-dev v6 | v20 | 3,319 | ~200 (best ckpt) | 14/15 | 93% | 0% | 10/15 (67%) |
| cardano-dev v7 | v21 | 3,401 | ~300 (early stop) | 14/15 | 93% | 0% | 9/15 (60%) |
| **cardano-dev v8** | **v22** | **3,682** | **~300 (early stop)** | **15/15** | **100%** | **+7%** | **10/15 (67%)** |
| v9 (planned) | v22 | 3,748 | — | — | — | — | — |

> Compile score introduced in v6. `—` = not measured. Heuristic = string-based checks. Compile = `aiken check` via sandbox.

v8 is the first model to pass all 15 heuristic checks. Previous versions (v6–v7) still failed the `spend_nft_gate` check. Compile success is 10/15 (67%). Despite passing all heuristic checks, compile failures remain — these are cases not captured by static validation: missing `pub type` declarations, removed constructors (e.g. `MintedValue`), and incomplete module paths. All addressable via targeted training data.

### By category

| Category | qwen2.5 base | gemma-4 base | v1 | v2 | v3 | v4 | v5 | v6 | v7 | v8 |
|----------|--------------|--------------|----|----|----|----|----|-----|-----|-----|
| imports | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| mint | 0% | 0% | 50% | 50% | 50% | 100% | 100% | 100% | 100% | 100% |
| multi-handler | 0% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| publish | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| spend | 0% | 25% | 62% | 62% | 75% | 75% | 88% | 88% | 88% | 100% |
| vote | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| withdraw | 0% | 0% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% |

Consistent failure in v1–v7: `spend_reference_input` — requires `reference_inputs` + `find_input` together, only 72 examples in the dataset (lowest coverage of any tested pattern). Even gemma-4-e4b base fails it. **v8 is the first model to pass this test**, contributing to its 15/15 sweep of the spend category.

---

### What the numbers say

**v5 and v6 tie at 93% (14/15).** Both are trained on the clean v20 dataset. The "wrong checkpoint" issue (missing `greater_is_better=False`) had minimal impact on the final score when the dataset was clean — the val loss floor of 0.3271 at step 200 was low enough that even a slightly suboptimal checkpoint produced the same benchmark result.

**The system prompt was the dominant factor in all previous benchmark failures.** Early runs of v2–v5 used a generic 4-line system prompt instead of the full training prompt. This produced scores of 7%, 13%, 13%, and 20% — which looked like model failures but were entirely inference failures. With the correct prompt, those same models score 67%, 80%, 87%, and 93%.

**v2 is not a regression.** The earlier claim that "v2 dropped from 67% to 7%" was wrong — it was an artifact of the wrong system prompt. v2 (dataset v13) actually scores 67%, nearly identical to v1 (73%). The two models are comparable; the extra data in v13 didn't hurt and didn't help dramatically.

**Dataset quality drives a clear, gradual improvement:** v2 (v13, 67%) → v3 (v13 run2, 80%) → v4 (v14, 87%) → v5/v6 (v20, 93%). Each dataset improvement produced a measurable gain. The jump to v20 (+6%) came from eliminating the 21.5% `fn` prefix contamination and promoting 351 PLAUSIBLE examples to VERIFIED.

**v7 (dataset v21) ties v6 at 93% heuristic but shows a slight compile regression: 9/15 vs v6's 10/15.** The v21 dataset added 82 CIP-31 reference input examples — good coverage addition — but the net effect on compilation quality was neutral to slightly negative. The likely cause: reference input examples used `find_input` patterns not yet fully compile-verified.

**v8 (dataset v22) is the first model to achieve 15/15 (100%) heuristic**, breaking the ceiling that v5–v7 had all hit at 14/15. The final failing test was `spend_nft_gate` (requires `has_nft` without `output.assets.ada`) — resolved by the full stdlib v3 migration in v22. Compile score also recovered to 10/15 (67%), matching v6's best. The v22 dataset was the first to be individually compile-verified via `aiken check` on every example.

**gemma-4-e4b base scores 33% without fine-tuning** — it has real Aiken v3 knowledge from pretraining (passes vote, publish, import_style correctly). qwen2.5-coder-7b base scores 0% because it doesn't generate `use x/y` style imports at all — it defaults to Python-like imports or omits them entirely.

**`spend_reference_input` was the persistent failure across v1–v7** — the test requires both `reference_inputs` and `find_input` in the output, and the pattern has only 72 examples in the dataset. v8 finally passes it, completing a 15/15 heuristic sweep. The remaining challenge is compile quality: 5 of 15 tests still fail `aiken check` (pub type leak, removed constructors, missing interval import). These are coverage gaps addressable via targeted training data.

**v9 target (dataset v22, 3,748 examples):** The main additions since v8 are `oracle_examples` (+47), `cip068_examples` (+32), and `with_tests_examples` (+169, up from 103). The `with_tests_examples` source is the most structurally novel — every example includes a `test` block that was verified to pass `aiken check`, teaching the model both correct API usage and correct test syntax simultaneously. Test coverage is now 8.6% (323/3,748 examples). Expected outcome: improved compile score (currently 10/15), particularly for examples that use stdlib functions prone to arity errors (`assets.flatten`, `dict.insert`, `bytearray.and_bytes`, `Rational`).

---

### The training steps hypothesis (and why it was wrong)

The original hypothesis: v1 scored 67% because it trained for ~700 steps; v2–v4 scored 7–13% because they only trained ~300 steps.

**This was wrong.** With the correct system prompt at benchmark time, v2–v4 score 67–87% — the step count was not the bottleneck. The apparent catastrophic failures were entirely due to running the benchmark with the wrong system prompt.

The real variable that changed across v1→v2→v3→v4 was **dataset composition**, not step count. And across versions the improvement is clear but gradual — not the cliff that the wrong benchmark numbers suggested.

**Loss curves tell the real training story.**

v5 first run (dataset v14, 7 epochs — step count hypothesis test):

| Step | Train Loss | Val Loss |
|------|-----------|----------|
| 50   | 0.4557    | 0.4705   |
| 100  | 0.4229    | 0.4171   |
| 200  | 0.3650    | 0.3828   |
| 300  | 0.2991    | **0.3788** ← best |
| 400  | 0.1508    | 0.4050   |

Validation loss bottomed at step ~300 and climbed after — the model was overfitting on v14. More steps on a contaminated dataset doesn't help; it memorizes the noise.

v6 (dataset v20, correct config — `greater_is_better=False`, `save_steps=eval_steps`):

| Step | Train Loss | Val Loss |
|------|-----------|----------|
| 50   | 0.4311    | 0.4421   |
| 100  | 0.3892    | 0.3905   |
| 150  | 0.3541    | 0.3612   |
| 200  | 0.3188    | **0.3271** ← best checkpoint |
| 250  | 0.2847    | 0.3390   |
| 300  | 0.2401    | 0.3588   |

Val loss floor: 0.3271 vs v5's 0.3788 — clean dataset converges lower. EarlyStoppingCallback stopped training at ~step 350.

**Dataset quality was the dominant factor.** A full Claude API audit of v14 (1,882 examples sampled) found: **21.5% of examples used `fn spend(` inside validator blocks — syntax the Aiken compiler rejects with a parse error.** The model was trained on contradictory signal. More training steps only reinforced the contradiction.

Secondary audit findings on v14:
- ~25% of outputs truncated mid-code
- `ScriptCredential`/`PubKeyCredential` (Plutus v2 names, not valid in Aiken v3) in ~20 examples
- `PolicyId` imported from `cardano/transaction` instead of `cardano/assets` in ~17 examples
- 6 examples with completely broken/incoherent code

---

### Historical reference — v11 model

| Metric | Result |
|--------|--------|
| Correct handler signature | ❌ — invented 8-param structure |
| `assets.lovelace_of()` | ❌ — used `output.assets.ada` |
| `self.extra_signatories` | ❌ — used `self.signatures` |
| `self.validity_range` | ❌ — used `self.time` |
| Slash-style imports | ❌ — used dot-style |

The model had learned a completely invented API consistent across all 20 prompts. Root cause: only 51 examples with `fn spend(` in 3,440 total — the model never saw enough complete validator structure to learn it.

---

## Part VIII — Development Log

This section documents every bug and lesson learned during the project. It exists because the benchmark and dataset both had bugs before producing useful results — and these bugs were often more instructive than the successes.

---

### Problems encountered — dataset generation

#### Problem 1 — Handler signature learned incorrectly

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
1. Show the complete `validator { spend(...) { } }` structure explicitly in the system prompt
2. Inject real code examples from `aiken_design_patterns.json` as structural reference
3. Generate 260 validators with verified handler structure (200 spend, 40 mint, 20 withdraw)
4. Add automated quality check — counts `spend(`, `mint(`, bad patterns after every run

---

#### Problem 2 — System prompt showed signatures without syntax

**Symptom:** 291 complex validators were generated but 0 had `fn spend(` in the output.

**Root cause:** The system prompt contained:
```
spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool
```
Without `fn` and without `validator {}`. Claude interpreted this as a type signature reference, not as code to replicate.

**Fix:** Changed to show the complete compilable structure:
```aiken
validator my_contract {
  spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool {
    ...
  }
}
```

> **Note (discovered later):** At this point in the project we believed `fn` was optional inside validator blocks. It is not — it causes a parse error. The v14 dataset still contained ~21.5% examples with `fn` prefix because this wasn't caught until the Claude API audit in the v15 cleaning cycle.

---

#### Problem 3 — Synthetic generation without source grounding

**Symptom:** Generated examples used APIs that don't exist in Aiken v3 (`transaction.signatories`, `list.has_any`, `output.value.lovelace`).

**Root cause:** Early scripts generated examples purely from Claude's prior knowledge, which includes Haskell, Plutus, and other functional languages with similar patterns.

**Fix:** All generation scripts now inject the real `aiken_stdlib.json` content into every prompt as ground truth. Claude is explicitly instructed to use **only** the APIs shown in the context. This approach, implemented in `regenerate_from_raw.py` and the updated `generate_complex_validators.py`, reduced hallucinations to 0 in the quality check.

---

#### Problem 4 — Missing `review_status` field

**Symptom:** 1,400 examples from the original pipeline had no `review_status` field, causing potential crashes in training scripts that expected the field.

**Root cause:** The field was added to the schema in a later iteration but earlier-generated examples were never backfilled.

**Fix:** `build_dataset_v13.py` normalizes all missing `review_status` to `PLAUSIBLE_NEEDS_CHECK` during the merge step, with explicit counting and logging of how many records were fixed.

---

#### Problem 5 — Overly strict handler detection caused false "incomplete" count

**Symptom:** An audit script reported 475 examples (13.9%) as "incomplete" — instructions asking for validator code but outputs without a proper handler. Attempts to regenerate them produced 0 successful fixes across dozens of batches.

**Root cause (detection):** The `has_complete_handler()` check searched for `fn spend(` / `fn mint(` / `fn withdraw(` inside a `validator {}` block. At this stage we believed `fn` was optional and `spend(...)` was an alternative form — both appearing in the dataset. Most of the 475 flagged examples were using the bare form and passed the updated check.

> **Correction (discovered in v15 audit):** `fn` inside a validator block is not optional — it causes a parse error. The bare form `spend(...)` is the *only* correct syntax. The dataset at v14 had `fn spend(` in 21.5% of examples, which was actively teaching the model to write uncompilable code.

**Root cause (regeneration):** Two additional bugs compounded the problem:
1. Matching regenerated outputs back to originals was done by exact instruction text. Claude consistently paraphrases instructions instead of copying them verbatim, so 100% of batches returned "instruction not found" and were dropped.
2. The `CODE_PHRASE` regex matched "show a practical example of using X" even when X was a pure utility function (e.g., BLS12-381 scalar operations) that has nothing to do with validators.

**Fix:**
1. Updated `has_complete_handler()` to accept both `fn spend(` and bare `spend(` inside validator blocks:
   ```python
   return bool(re.search(r'\b(?:fn\s+)?(spend|mint|withdraw)\s*\(', body))
   ```
2. Switched matching from instruction-text lookup to **positional matching** — Claude receives numbered instructions `[1], [2], ...` and returns items in the same order; the script zips by index, not by string comparison.
3. Tightened `CODE_PHRASE` regex to only flag instructions that explicitly mention `validator`, `contract`, `handler`, `spend`, `mint`, or `withdraw`.
4. Added `EXPLAIN_PHRASE` filter to exclude conceptual questions ("explain how", "what is") that happen to mention validators — their ideal answer is prose, not code.

**Result:** True incomplete count dropped from 475 → **7**. All 7 were regenerated successfully with 0 drops and 0 hallucinations.

**Lesson:** When building detection heuristics for dataset quality, validate them on real samples before acting on the counts. A grep-style keyword check will over-count by 60× compared to a phrase-level structural check.

---

#### Problem 6 — Python stdout buffering hides script progress when piped to tee

**Symptom:** Script appeared to hang with 0 bytes written to log file, despite process being alive. No output visible for 10+ minutes.

**Root cause:** Python buffers stdout when output is piped (e.g., `python3 script.py | tee log`). The buffer fills only after ~8 KB of output, so nothing appears in the log until a batch of results accumulates.

**Fix:** Always run generation scripts with `PYTHONUNBUFFERED=1` and the `-u` flag:
```bash
PYTHONUNBUFFERED=1 .venv/bin/python3 -u script.py 2>&1 | tee run.log
```

---

#### Lesson: audit before training

Every dataset version now goes through a fixed audit before training:

```bash
# Must be 0 — fn prefix is a parse error in Aiken v3
grep -c "fn spend("     data/processed/dataset_v22.jsonl
grep -c "fn mint("      data/processed/dataset_v22.jsonl
grep -c "fn else("      data/processed/dataset_v22.jsonl

# Must be 0 (outside correction examples)
grep -c "self.signatures"  data/processed/dataset_v22.jsonl
grep -c "self.time"        data/processed/dataset_v22.jsonl
grep -c "use cardano\."    data/processed/dataset_v22.jsonl
```

The full automated audit (with Claude API analysis) is in `scripts/audit_dataset_quality.py`.

---

### Problems encountered — benchmark

#### Problem 1 — Inverted pass/fail logic for `has_dot_imports` and `has_markdown_fence`

The first real run showed 0/15 across all models — including v1, which visually was generating correct Aiken v3 code. The failure list for every v1 prompt was identical: `['has_dot_imports']`.

The bug: `has_dot_imports` stored `True` when dot imports were found (bad) and `False` when they weren't (good). The `all()` pass check required every value to be `True`, so a model that correctly avoided dot imports would *fail* the check. Same logic error for `has_markdown_fence`. Both flags were "bad thing detectors" that needed to be inverted.

Fix: renamed to `no_dot_imports` and `no_markdown_fence`, storing `True` when the output is clean. Result: all previously saved JSONs were invalidated and the suite had to be re-run from scratch.

**Lesson:** When a test suite reports 0% across all models including a fine-tuned one, the suite is wrong before the models are.

---

#### Problem 2 — `no_markdown_fence` was penalizing format, not Aiken knowledge

After fixing the inversion bug, the second run produced real scores: v1 hit 3/15 (20%), v2 dropped back to 0/15. But looking at the v1 failure list closely, almost every failure was `['no_markdown_fence']` — the code inside was correct Aiken v3. The model had learned to wrap its answer in ` ```aiken ... ``` `, which is reasonable behavior for a chat assistant and actually useful for display. It was not an Aiken error.

Keeping `no_markdown_fence` as a hard pass/fail criterion meant the benchmark was measuring "does the model skip markdown formatting" instead of "does the model know Aiken v3". Those are different questions.

Fix: added `strip_markdown()` to extract code from inside a fence before running all checks. The `wrapped_in_markdown` flag is still recorded in the JSON as informational data — useful for knowing which models tend to add formatting — but it no longer affects the pass/fail score.

```python
def strip_markdown(output: str) -> str:
    m = re.search(r'```(?:\w+)?\n(.*?)```', output, re.DOTALL)
    return m.group(1).strip() if m else output
```

**Lesson:** Separate format from correctness early. A model that writes perfect code inside a markdown block is better than one that writes broken code without one.

---

#### Problem 3 — `wrapped_in_markdown` still inside the `all()` pass check

After the `strip_markdown()` fix, the third run showed v1 at 7/15 instead of the expected ~10/15. Looking at the failure list, some tests failed with only `['wrapped_in_markdown']` — and the model had written clean code without a markdown fence. The problem: `wrapped_in_markdown = False` (no fence, correct behavior) was still being evaluated by `all()`, which required every value to be `True`.

The flag was documented as "informational only" in a comment, but the pass check didn't know that. A model that wrote clean unwrapped code was being penalized for not using markdown — the exact opposite of what we wanted.

Fix: explicitly excluded `wrapped_in_markdown` from the pass check:
```python
results["pass"] = all(v for k, v in results.items() if k not in ("pass", "wrapped_in_markdown"))
```

After this fix, v1 moved from 7/15 to 10/15 (67%) — the correct score.

**Lesson:** "Informational only" in a comment means nothing if the logic doesn't enforce it. Exclusions need to be explicit in code.

---

#### Problem 4 — Wrong dataset label for v3

During the second run it became clear that `cardano-dev v3` had been labeled `(dataset v14)` in `benchmark.py` since it was configured. That model was actually trained on dataset v13. The v14-trained model is v4.

Fix: corrected the label to `(dataset v13)`. Sounds minor but matters for the comparison table — attributing v13 results to v14 would make v4's improvement look smaller than it is.

---

#### Problem 5 — WSL cannot reach LM Studio at `localhost` or `172.x.x.x`

LM Studio shows its API URL as `http://172.xx.xx.x:3005` in its UI. That IP is the WSL virtual adapter as seen *from Windows* — the reverse direction. From WSL, the Windows host is not at that address.

The fix was two steps:
1. Find the actual gateway: `ip route show default` → `YOUR_GATEWAY_IP`
2. Add a Windows Firewall inbound rule for port 3005 (PowerShell as Admin):
   ```powershell
   New-NetFirewallRule -DisplayName "LM Studio WSL" -Direction Inbound -Protocol TCP -LocalPort 3005 -Action Allow
   ```

Verify before every session with `curl http://YOUR_GATEWAY_IP:3005/v1/models`. The script default is now set to that address.

---

#### Problem 6 — System prompt at benchmark time must match training system prompt

After fixing the checkpoint issue in v6, v5 was re-run with the correct checkpoint and still scored poorly. The benchmark was using a 4-line generic system prompt:

```python
SYSTEM_PROMPT = "You are an expert Aiken v3 smart contract engineer..."
```

But the training notebook used the full 30-line prompt with explicit handler syntax, import style, and verified API patterns. The model had learned to produce correct Aiken v3 code in the presence of that specific prompt — without it, the associations don't activate.

Fix: updated `benchmark.py` to use the exact same `SYSTEM_PROMPT` as `colab_finetune.ipynb`. Re-running all models with the correct prompt revealed the true scores — v2 went from 7% to 67%, v3 from 13% to 80%, v4 from 13% to 87%. The models were never broken; the benchmark was.

**Lesson:** Fine-tuned models learn correlations between prompt structure and output patterns. A system prompt that was present in every training example must be present at inference time. This is not a benchmark bug — it's the intended behavior of instruction fine-tuning. The bug was running the benchmark with a different prompt and not realizing it.

---

#### Problem 7 — Colab GGUF export cannot be downloaded via browser

After training v4, the 2.5 GB GGUF file could not be downloaded directly from Colab — the browser showed `TypeError: Failed to fetch` for files above ~500 MB. The file existed in the Colab VM but Colab sessions are ephemeral: once the session closes, all files are gone permanently unless saved elsewhere.

Fix: mount Google Drive during the session and copy before closing:
```python
from google.colab import drive
drive.mount('/content/drive')

import shutil
shutil.copy(
    "/content/qwen35_4b_aiken_v20_gguf_gguf/Qwen3.5-4B.Q4_K_M.gguf",
    "/content/drive/MyDrive/cardano-dev-6.0-v20-q4_k_m.gguf"
)
# Also save the LoRA adapter (smaller, useful for re-exporting later)
shutil.copytree("/content/qwen35_4b_aiken_v20_lora", "/content/drive/MyDrive/cardano-dev-6.0-v20-lora")
```

**Lesson:** Save to Drive immediately after export, before verifying anything else. The verification step is worthless if the file is gone.

---

### Stdlib API pitfalls discovered during v22 generation

These were found while building `with_tests_examples` via `aiken check` — patterns that Claude generates confidently but that fail to compile against stdlib v3.0.0.

| API | What Claude generates | What actually works |
|-----|----------------------|---------------------|
| `assets.flatten_with` | 3-arg lambda | `FlattenStrategy` needs 5-arg fn — use `assets.flatten` + `list.filter` instead |
| `dict.insert` | `dict.insert(d, k, v, bytearray.compare)` | Only 2 args: `dict.insert(d, k, v)` — no compare fn |
| `list.span` | `list.span(xs, predicate)` | Takes index `n: Int`, not a predicate |
| `list.reduce` | `list.reduce(xs, fn(a, b) -> Option<c>)` | Same as foldl: `list.reduce(xs, zero, fn(b, a) -> b)` |
| `math.sqrt` | Returns `Int` | Returns `Option<Int>` — handle `None` case |
| `bytearray.and_bytes` | 2 args | 3 args: `(left, right, pad_end: Bool)` |
| `Interval` | `Interval<Int>` | Not generic — just `Interval`, no type parameter |
| `Rational` | Used without explicit import | Requires `use aiken/math/rational.{Rational}` |
| `dict.union_with` | Annotated as `UnionStrategy` | Use `strategy.sum()` directly — do not annotate the type |

**Root cause in all cases:** Claude extrapolates from similar languages (Haskell, Elm) or from vague stdlib doc descriptions. The fix is always the same: run `aiken check` locally, read the actual error, look up the real signature in `data/raw/aiken_stdlib.json`.

**Lesson:** Pattern-matching checks (the v14-era approach) cannot replace compilation. A function call with the right name but wrong arity passes any heuristic and fails immediately at `aiken check`. This is why `with_tests_examples` is fully compile-gated — no example is added without a passing `aiken check` run.

---

## Part IX — Project Structure

> See [`scripts/SCRIPTS.md`](scripts/SCRIPTS.md) for the full annotated script reference.

```
cardumen-forge/
│
├── README.md
├── SYSTEM_PROMPT.txt                  # system prompt for inference
├── HF_README.md                       # Hugging Face dataset card
├── colab_finetune.ipynb               # ← start here: QLoRA training notebook
├── eval_model.py                      # single-model eval — 15 prompts via LM Studio
├── benchmark.py                       # multi-model comparison — runs all versions sequentially
│
├── scripts/                           # see scripts/SCRIPTS.md for full reference
│   ├── scrape/                        # Step 1 — collect raw sources
│   │   ├── scrape_aiken_stdlib_github.py
│   │   ├── scrape_aiken_docs.py
│   │   ├── scrape_hydra_docs.py
│   │   ├── scrape_github.py
│   │   └── scrape_aiken_stdlib.py
│   │
│   ├── generate/                      # Step 2 — generate training examples
│   │   ├── regenerate_from_raw.py          # main grounded generation pipeline
│   │   ├── generate_validators_v2.py
│   │   ├── generate_corrections_v2.py
│   │   ├── generate_correction_set_v3.py   # v8 hallucination corrections (active)
│   │   ├── generate_oracle_examples.py
│   │   ├── generate_cip068_examples.py
│   │   ├── generate_with_tests.py
│   │   └── fix_incomplete_validators.py
│   │
│   ├── audit/                         # Step 3 — quality checks
│   │   ├── audit_v9.py
│   │   ├── audit_dot_imports.py
│   │   └── purge_dot_imports.py
│   │
│   ├── build/                         # Step 4 — assemble dataset
│   │   ├── build_dataset_v14.py
│   │   └── build_holdout.py
│   │
│   ├── [cleaning pipeline]            # Step 5 — fix_fn_prefix · build_v16 · fix_types ·
│   │                                  #   fix_import_keyword · migrate_dataset_to_v3 ·
│   │                                  #   dedup_dataset · promote_plausible · fix_plausible_failures
│   │
│   ├── [fuzz pattern pipeline]        # Step 6 (v24) — test_patterns · patterns_to_dataset
│   │
│   └── oneoff/                        # single-use investigation scripts (not part of pipeline)
│       └── analyze_audit* · check_* · show_* · inspect_* · fuzz_stats
│
├── data/
│   ├── patterns/                      # 150 fuzz-verified .ak files (01–25, variants a–f)
│   │   ├── 01_dex_swap_double_satisfaction.ak  # base patterns (25 categories)
│   │   ├── 01b_fixed_price_swap.ak             # variant b–f per category
│   │   └── ...                                 # all pass aiken check --max-success=200
│   │
│   ├── raw/                           # scraped source files (not synthetic)
│   │   ├── aiken_stdlib.json               # 458 functions with real signatures
│   │   ├── aiken_docs.json                 # 28 documentation pages
│   │   ├── aiken_design_patterns.json      # 22 production pattern files
│   │   ├── cips.json                       # 134 Cardano Improvement Proposals
│   │   ├── hydra_docs.json                 # 35 Hydra protocol pages
│   │   └── hydra_plutus.json               # Hydra + Plutus integration reference
│   │
│   └── processed/
│       ├── dataset_v23.jsonl               # 3,739 examples — ACTIVE TRAINING SET
│       ├── dataset_v22.jsonl               # 3,748 examples — previous version
│       ├── dataset_v14_eval.jsonl          # 374 examples — HOLDOUT (do not train on)
│       ├── components/                     # intermediate outputs per source
│       │   ├── correction_set.jsonl
│       │   ├── correction_set_v3.jsonl
│       │   ├── corrections_v2.jsonl
│       │   ├── governance_examples.jsonl
│       │   ├── oracle_examples.jsonl
│       │   ├── cip068_examples.jsonl
│       │   ├── reference_input_examples.jsonl
│       │   ├── v3_compat_examples.jsonl
│       │   ├── with_tests_examples.jsonl
│       │   ├── validators_v3.jsonl
│       │   ├── validators_fixed.jsonl
│       │   └── patterns_verified.jsonl     # output of patterns_to_dataset.py (v24 input)
│       └── archive/                        # superseded versions (v2–v22)
│           └── backups/                    # pre-operation snapshots
│
├── eval/
│   └── aiken_sandbox/                 # compile-check sandbox (stdlib v3.0.0, Plutus v3)
│       └── validators/output.ak       # ← sandbox writes here per test run
│
├── eval_results/                      # benchmark run JSONs
│   ├── summary.md                     # ← model evolution table (start here)
│   └── runs/                          # one JSON per benchmark run
│
├── logs/
│   ├── audit/                         # compile audits, repair reports, plausible logs
│   └── patterns/                      # test_patterns.py run logs
│
└── archive/scripts/                   # superseded scripts (v13 pipeline, old audits)
```

---

## Known Limitations

- **PLAUSIBLE_NEEDS_CHECK is ~1% of training data** (down from 44% in v14, from 32% post-v20, to 0.8% after `promote_plausible.py` + `fix_plausible_failures.py`). The 29 remaining examples use patterns not verifiable against stdlib signatures or `aiken check`. Curriculum ordering (placing PLAUSIBLE last) partially mitigates this.
- **Heuristic checks are string-based.** Passing all 15 tests does not guarantee the output compiles — a pattern can appear in a comment and pass. The compile score (`aiken check` via `benchmark.py`) is the harder, more reliable signal.
- **Compile score is on model outputs, not the dataset.** `benchmark.py` compiles what the model generates, not the training examples. Dataset examples were migrated to v3 patterns via `scripts/migrate_dataset_to_v3.py` and individually compiled via `scripts/audit_dataset_compile.py`. Failing examples were fixed via `scripts/regenerate_failing.py` (Claude API). `correction_set` and `generated_governance_v1` both reach 100% compile pass rate. Some sources (`aiken_stdlib`, `cips`, `hydra_docs`) are intentionally prose and do not compile.
- **Two governance tests out of 15.** `vote` and `publish` handlers were added in v14 but the eval suite only has 2 tests covering them (vs 9 for spend/mint). Coverage asymmetry may hide regressions in governance patterns.
- **Single model dependency.** All examples were generated by Claude. Systematic gaps in Claude's Aiken knowledge would propagate uniformly across the dataset — there is no cross-model validation.
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

*cardano-dev v8 · dataset v23 · 3,739 examples · 15/15 heuristic · 10/15 compile · stdlib v3 · 150 fuzz-verified patterns (v24 in progress)*
