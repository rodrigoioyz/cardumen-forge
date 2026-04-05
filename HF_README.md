---
license: mit
language:
- en
- es
tags:
- cardano
- aiken
- aiken-v3
- code-generation
- smart-contracts
- llm
- finetuned
- qlora
base_model: unsloth/Qwen3.5-4B
datasets:
- CardumenCorps/cardumen-forge-aiken-dataset
pipeline_tag: text-generation
library_name: transformers
model-index:
- name: cardano-dev-v9
  results:
  - task:
      type: text-generation
    metrics:
    - type: heuristic_pass_rate
      value: 1.0
      name: Heuristic Pass Rate (15/15, v8 baseline)
    - type: compile_pass_rate
      value: 0.667
      name: Compile Pass Rate (10/15, v8 baseline)
---

# cardumen-forge-aiken · cardano-dev v9

**Qwen3.5-4B fine-tuned for Cardano smart contract development in Aiken v3.**

Runs locally on 6 GB VRAM · Bilingual EN/ES · 3,748 compile-verified training examples · stdlib v3.0.0

> [Aiken](https://aiken-lang.org) is the main smart contract language for Cardano. General-purpose LLMs fail at it consistently — wrong imports, removed types, hallucinated functions. This model was trained specifically to fix those failures.

**Sections:** Quick example · Benchmark · How to use · System prompt · Training · Dataset · Limitations · Version history

---

## Quick example

**Input**
```
Write a time-lock spend validator that allows spending only after a deadline.
```

**Output**
```aiken
use cardano/transaction.{Transaction, OutputReference}
use aiken/interval.{Finite}

pub type Datum {
  deadline: Int,
}

validator time_lock {
  spend(datum: Option<Datum>, _redeemer: Data, _own_ref: OutputReference, self: Transaction) -> Bool {
    expect Some(d) = datum
    expect Finite(now) = self.validity_range.lower_bound.bound_type
    now >= d.deadline
  }
}
```

---

## Benchmark

15 held-out prompts across spend, mint, withdraw, governance, and oracle patterns. Two independent evaluation tiers. v9 benchmarking in progress — v8 results shown as baseline:

| | cardano-dev v9 | cardano-dev v8 | cardano-dev v7 | qwen2.5-coder-7b |
|---|---|---|---|---|
| **Heuristic** — structure, imports, API names | pending | **15/15 · 100%** | 14/15 · 93% | 0/15 · 0% |
| **Compile** — `aiken check` vs stdlib v3.0.0 | pending | **10/15 · 67%** | 9/15 · 60% | — |

v8 was the first model to pass all 15 heuristic checks — the ceiling that v5–v7 all hit at 93%. v9 adds 66 new compile-verified examples (oracle, CIP-68, with_tests) targeting the 5 remaining compile failures: `pub type` visibility leak, `MintedValue` removed constructor, `GovernanceCommittee` wrong name, missing `use aiken/interval`.

---

## How to use

### LM Studio / Ollama

1. Download `cardano-dev-9.0-v22-q4_k_m.gguf` from the **Files** tab
2. Load it in LM Studio or Ollama
3. Copy `SYSTEM_PROMPT.txt` (also in Files) into the system prompt field
4. Temperature: 0.2

### Transformers

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

model_id = "CardumenCorps/cardumen-forge-aiken"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.bfloat16)

# SYSTEM_PROMPT.txt is in the Files tab of this repo
system_prompt = open("SYSTEM_PROMPT.txt").read()

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user",   "content": "Write a mint validator that allows minting only if signed by a specific key."}
]

input_ids = tokenizer.apply_chat_template(messages, return_tensors="pt", add_generation_prompt=True)
output = model.generate(input_ids, max_new_tokens=1024, temperature=0.2, do_sample=True)
print(tokenizer.decode(output[0][input_ids.shape[-1]:], skip_special_tokens=True))
```

---

## System prompt

> ⚠️ **Always load `SYSTEM_PROMPT.txt` as your system prompt.** The model was fine-tuned against it — without it output quality drops significantly.

### Why the system prompt matters

This model was trained on ~3,700 examples, all formatted with this exact system prompt as the instruction prefix. It is not optional documentation — it is part of the model's input distribution.

The system prompt does three things that the model alone cannot reliably do:

**1. Constrains hallucinated APIs.** General-purpose LLMs invent functions like `output.assets.ada`, `self.signatures`, or `Interval<Int>` that do not exist in stdlib v3. The `VERIFIED API PATTERNS` and `REMOVED in stdlib v3` sections act as a hard constraint layer that suppresses these hallucinations at inference time.

**2. Fixes import syntax.** Aiken uses slash-style module paths (`use cardano/transaction.{Transaction}`) which differ from most languages. The `IMPORTS` and `IMPORT RULES` sections ground the model to the correct syntax and ensure it includes all required imports for the types it uses — including `VerificationKeyHash`, `InlineDatum`, `PolicyId`, and others that are commonly missed.

**3. Enforces correct type usage.** The `DATUM FIELD TYPES` section prevents the most common type error in generated contracts: using `ByteArray` for fields like `owner` or `signer` that must be `VerificationKeyHash` because `extra_signatories` is `List<VerificationKeyHash>`. Without this constraint, the model generates code that looks correct but fails to compile.

Skipping the system prompt degrades all three — heuristic scores drop and compile pass rate falls substantially. Always include it.

<details>
<summary>Show full system prompt</summary>

```
You are an expert Aiken v3 smart contract engineer for the Cardano blockchain.
You write correct, compilable Aiken v3 validators using only verified APIs.

CRITICAL — handler syntax inside validator blocks (NO fn keyword before handler name):
  validator my_contract {
    spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool { ... }
    mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool { ... }
    withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool { ... }
    publish(redeemer: T, cert: Certificate, self: Transaction) -> Bool { ... }
    vote(redeemer: T, voter: Voter, self: Transaction) -> Bool { ... }
    propose(redeemer: T, proposal: ProposalProcedure, self: Transaction) -> Bool { ... }
    else(_) { fail }
  }

CUSTOM TYPES — commas required after EVERY field (stdlib v3):
  pub type MyDatum {
    owner: VerificationKeyHash,
    deadline: Int,
    amount: Int,
  }

IMPORTS (slash style — never dot, imports must come first):
  use cardano/assets
  use cardano/transaction.{Transaction, OutputReference}
  use cardano/address.{Address, Script, Credential}
  use cardano/certificate.{Certificate}
  use cardano/governance.{Voter, ProposalProcedure}
  use aiken/collection/list
  use aiken/collection/dict
  use aiken/interval
  use aiken/interval.{Finite, IntervalBound}
  use aiken/math/rational
  use aiken/primitive/bytearray

IMPORT RULES — always include these when using the types:
  Transaction, OutputReference → use cardano/transaction.{Transaction, OutputReference}
  Input, Output                → add to transaction import: .{Transaction, Input, Output, ...}
  InlineDatum                  → add to transaction import: .{Transaction, OutputReference, InlineDatum}
  PolicyId, AssetName          → use cardano/assets.{PolicyId, AssetName}
  Address, Script, Credential  → use cardano/address.{Address, Script, Credential}
  Certificate                  → use cardano/certificate.{Certificate}
  Voter, ProposalProcedure     → use cardano/governance.{Voter, ProposalProcedure}
  Finite, IntervalBound        → use aiken/interval.{Finite, IntervalBound}
  VerificationKeyHash          → use aiken/crypto.{VerificationKeyHash}

DATUM FIELD TYPES — use exact types, never substitute ByteArray:
  owner / signer fields : VerificationKeyHash — NEVER ByteArray
                          list.has(self.extra_signatories, d.owner) requires VerificationKeyHash
  asset name fields     : AssetName (from cardano/assets) — only use ByteArray for raw bytes
  policy id fields      : PolicyId (from cardano/assets) — NEVER ByteArray

VERIFIED API PATTERNS:
  ADA check    : assets.lovelace_of(output.value) — NEVER output.assets.ada
  Signatures   : list.has(self.extra_signatories, key) — NEVER self.signatures
  Time         : self.validity_range — type is Interval (NOT Interval<Int>)
  NFT check    : assets.quantity_of(value, policy_id, asset_name)
  Token map    : assets.tokens(value, policy_id) — returns Dict<AssetName, Int>
  Inputs       : transaction.find_input(self.inputs, ref)
  Ref inputs   : transaction.find_input(self.reference_inputs, ref)
  InlineDatum  : expect InlineDatum(raw) = output.datum — always import explicitly
  dict         : dict.to_pairs(d) — NEVER dict.to_list
  dict lookup  : dict.get(d, key) — returns Option<value>
  rational     : rational.new(n, d)
  bytearray    : bytearray.take(b, n) / bytearray.drop(b, n) / bytearray.concat(a, b)

CIP-68 LABEL PREFIXES:
  Label 100 — reference NFT : #"000643b0"
  Label 222 — user NFT      : #"000de140"
  Label 333 — fungible token: #"0014df10"

SYNTAX RULES:
  Lambda body requires braces: fn(x) { x }  — NEVER fn(x) x
  Withdraw is NOT in cardano/certificate — use Credential for withdraw handler account param

REMOVED in stdlib v3 — NEVER generate:
  aiken/time | PosixTime        → use self.validity_range
  MintedValue                   → use Value
  VerificationKeyCredential     → use VerificationKey
  ScriptCredential              → use Script
  DeregisterCredential          → use UnregisterCredential
  Interval<Int>                 → use Interval (not generic)
```

</details>

---

## Training

| | |
|---|---|
| Base model | `unsloth/Qwen3.5-4B` |
| Method | 16-bit LoRA · r=32, alpha=64 · via [Unsloth](https://github.com/unslothai/unsloth) |
| Dataset | 3,748 examples — stdlib docs, CIPs, design patterns, oracle, CIP-68, corrections |
| Stdlib target | Aiken stdlib v3.0.0 / Plutus v3 |
| Compile verification | `aiken check` via isolated sandbox on all correction + test examples |
| Epochs | ~3 (early stopping, patience=3) |
| Hardware | NVIDIA A100 · Google Colab |
| Export | GGUF Q4_K_M · ~2.5 GB |

---

## Dataset

3,748 examples · 15 sources · ~94% `VERIFIED_V3_ALIGNED` · EN 60% / ES 40%

| Source | n | Description |
|---|---|---|
| `aiken_stdlib` | 1,310 | One example per stdlib function |
| `cips` | 505 | CIP standards — CIP-1, CIP-20, CIP-31, CIP-68 |
| `aiken_v3_curated_v2` | 436 | Complex validators — all handlers, governance, dict, rational |
| `aiken_docs` | 344 | Official docs — language concepts, type system |
| `aiken_design_patterns` | 176 | Production patterns from Anastasia-Labs |
| `with_tests_examples` | 169 | Stdlib examples with `test` blocks · compile-verified |
| `correction_set` + v2/v3 | 228 | Hallucination corrections · 100% compile-verified |
| `generated_governance_v1` | 54 | vote / publish / propose · 100% compile-verified |
| `hydra_docs` | 60 | Hydra Head L2 — lifecycle, snapshots, fanout |
| `oracle_examples` | 47 | Oracle price feeds — reference input + InlineDatum + staleness |
| `cip068_examples` | 32 | CIP-68 NFT label validation (label 100 / 222 / 333) |
| others | 187 | Reference inputs, v3-compat, misc combined sources |

---

## Limitations

> ⚠️ Always run `aiken check` on generated output before using it in production.

- Targets **Aiken stdlib v3.0.0 only**
- Compile pass rate is 67% (v8 baseline) — structural correctness is high, some stdlib calls still fail
- Complex novel patterns may need manual adjustment

---

## Version history

<details>
<summary>Show all versions (v1 → v9)</summary>

| Model | Examples | Heuristic | Compile |
|---|---|---|---|
| cardano-dev v1 | — | 11/15 · 73% | — |
| cardano-dev v2 | — | 10/15 · 67% | — |
| cardano-dev v3 | — | 12/15 · 80% | — |
| cardano-dev v4 | — | 13/15 · 87% | — |
| cardano-dev v5 | 3,319 | 14/15 · 93% | — |
| cardano-dev v6 | 3,319 | 14/15 · 93% | 10/15 · 67% |
| cardano-dev v7 | 3,401 | 14/15 · 93% | 9/15 · 60% |
| cardano-dev v8 | 3,682 | **15/15 · 100%** | **10/15 · 67%** |
| **cardano-dev v9** | **3,748** | **pending** | **pending** |

Dataset quality has been the dominant driver across all versions — not model size or step count.

</details>

---

Full training pipeline, dataset, evaluation suite, and changelog:
**[github.com/rodrigoioyz/cardumen-forge](https://github.com/rodrigoioyz/cardumen-forge)**

---

*cardano-dev v9 · dataset v22 · 3,748 examples · Aiken stdlib v3 · based on Qwen3.5-4B*
