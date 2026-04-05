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
- plutus
- defi
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
    - type: benchmark_v2_selftest
      value: 1.0
      name: Benchmark v2 Self-test (257/257)
---

# cardumen-forge-aiken · cardano-dev v9

**The first fine-tuned LLM for Aiken v3 smart contract development on Cardano.**

Runs locally on 6 GB VRAM · Bilingual EN/ES · 4,655 compile-verified training examples · Aiken stdlib v3.0.0

[![Model](https://img.shields.io/badge/model-Qwen3.5--4B-blue)](https://huggingface.co/unsloth/Qwen3.5-4B)
[![Dataset](https://img.shields.io/badge/dataset-4%2C655%20examples-green)](https://huggingface.co/CardumenCorps/cardumen-forge-aiken)
[![Stdlib](https://img.shields.io/badge/aiken--stdlib-v3.0.0-orange)](https://aiken-lang.org)
[![GGUF](https://img.shields.io/badge/GGUF-Q4__K__M%20%C2%B72.5GB-purple)](https://huggingface.co/CardumenCorps/cardumen-forge-aiken/tree/main)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

---

## What is this?

[Aiken](https://aiken-lang.org) is the primary smart contract language for Cardano. It has its own type system, module paths, and a stdlib that changed significantly in v3. General-purpose LLMs — including GPT-4, Claude, and Qwen-Coder — fail at it consistently: wrong imports, removed constructors, hallucinated functions, broken handler syntax.

**cardumen-forge-aiken** is a 4B-parameter model fine-tuned specifically on Aiken v3 validators, stdlib docs, CIP standards, design patterns, oracle feeds, governance, and fuzz-tested contracts. It writes correct, compilable Aiken code out of the box.

---

## Quick example

**Input**
```
Write a time-lock spend validator that allows spending only after a deadline stored in the datum.
```

**Output — compiles with `aiken check` against stdlib v3.0.0**
```aiken
use aiken/interval.{Finite}
use cardano/transaction.{OutputReference, Transaction}

pub type Datum {
  deadline: Int,
}

validator time_lock {
  spend(
    datum: Option<Datum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    expect Finite(now) = self.validity_range.lower_bound.bound_type
    now >= d.deadline
  }

  else(_) {
    fail
  }
}
```

---

## Why this model exists

If you have tried to use an LLM for Cardano smart contract development, you have hit these walls:

- `output.assets.ada` — does not exist. The correct call is `assets.lovelace_of(output.value)`.
- `self.signatures` — does not exist. It is `self.extra_signatories`.
- `MintedValue` — removed in stdlib v3. Use `Value`.
- `VerificationKeyCredential(pkh)` — removed. Use `VerificationKey(pkh)`.
- `Interval<Int>` — wrong. The type is just `Interval`.
- Handler syntax: the model writes `fn spend(...)` inside a validator block — that is invalid. There is no `fn` keyword before handler names.

These are not edge cases. They are what every general-purpose LLM produces on its first attempt at Aiken. This model was trained to eliminate them.

---

## Benchmark

### Benchmark v2 — 257 reference solutions

We built a new benchmark with 257 reference solutions across 11 validator categories, each verified to compile and pass `aiken check` in an isolated sandbox. The suite covers the full range of real-world patterns:

| Category | Description |
|---|---|
| `spend/signature` | Owner signature check |
| `spend/ada_payment` | ADA payment to address |
| `spend/time` | Deadline / time-lock |
| `spend/nft_gate` | NFT presence gate |
| `spend/datum_inline` | InlineDatum reference input |
| `mint/one_shot` | One-shot minting policy |
| `mint/burn` | Burn-only policy |
| `spend/reference_input` | Oracle via reference input |
| `spend/multisig_threshold` | M-of-N multisig |
| `governance/vote` | Governance vote handler |
| `withdraw` | Withdrawal validator |

All 257 reference solutions pass `--self-test` (the suite validates itself before scoring any model).

### Results by version

| | cardano-dev v9 | cardano-dev v8 | cardano-dev v7 | qwen2.5-coder-7b (baseline) |
|---|---|---|---|---|
| **Heuristic** — structure, imports, API names | pending | **15/15 · 100%** | 14/15 · 93% | 0/15 · 0% |
| **Compile** — real `aiken check` in sandbox | pending | **10/15 · 67%** | 9/15 · 60% | — |
| **Benchmark v2 self-test** | 257/257 | — | — | — |

v8 was the first version to pass all 15 heuristic checks — the ceiling that v5, v6, and v7 hit at 93%. v9 was trained on 4,655 examples (vs 3,748 in v8), with targeted additions in oracle, CIP-68, governance, fuzz patterns, and expanded DeFi families. Results pending.

---

## How to use

### Option 1 — LM Studio / Ollama (recommended for local use)

1. Download `cardano-dev-9.0-v23-q4_k_m.gguf` (~2.5 GB) from the **Files** tab
2. Load it in [LM Studio](https://lmstudio.ai) or Ollama
3. Copy the contents of `SYSTEM_PROMPT.txt` (also in Files) into the system prompt field
4. Set temperature to **0.2**
5. Ask your question

```
# Ollama example
ollama run cardumen-forge-aiken "Write a one-shot mint validator."
```

### Option 2 — Transformers (Python)

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

model_id = "CardumenCorps/cardumen-forge-aiken"

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)

# SYSTEM_PROMPT.txt is in the Files tab of this repo — always load it
with open("SYSTEM_PROMPT.txt") as f:
    system_prompt = f.read()

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user",   "content": "Write a mint validator that allows minting only if signed by a specific key."},
]

input_ids = tokenizer.apply_chat_template(
    messages,
    return_tensors="pt",
    add_generation_prompt=True,
).to(model.device)

output = model.generate(
    input_ids,
    max_new_tokens=1024,
    temperature=0.2,
    do_sample=True,
)

print(tokenizer.decode(output[0][input_ids.shape[-1]:], skip_special_tokens=True))
```

---

## Evaluation suite

The `eval/` directory in the [GitHub repo](https://github.com/rodrigoioyz/cardumen-forge) contains `eval_benchmark.py`, which runs all 257 prompts through the model, then compiles each output against a real Aiken sandbox.

```bash
# Verify the reference solutions compile (sanity check)
python eval_benchmark.py --self-test

# Run the full benchmark against a loaded model
python eval_benchmark.py --model CardumenCorps/cardumen-forge-aiken
```

The benchmark scores two tiers independently:

- **Heuristic** — regex checks on structure, import paths, API names, removed symbols
- **Compile** — actual `aiken check` in an isolated project with stdlib v3.0.0

This separation matters: a model can score 100% heuristic while still failing to compile on edge cases. We report both.

---

## Training

| | |
|---|---|
| Base model | `unsloth/Qwen3.5-4B` |
| Method | QLoRA · r=32, alpha=64 · `LOAD_IN_4BIT=True` · via [Unsloth](https://github.com/unslothai/unsloth) |
| Dataset | 4,655 examples · dataset_v23 · stdlib v3.0.0 |
| Compile verification | `aiken check` in isolated sandbox on all correction, fuzz, and test examples |
| Epochs | ~3 (EarlyStopping, patience=3, `greater_is_better=False`) |
| Eval steps | Synced with save steps |
| Hardware | NVIDIA A100 · Google Colab |
| Export | GGUF Q4_K_M · ~2.5 GB |

---

## Dataset

**4,655 examples · 15+ sources · 84% VERIFIED_V3_ALIGNED · 11% VERIFIED_FUZZ_PASS · 2% CORRECTION**

| Source | n | Description |
|---|---|---|
| `aiken_stdlib` | 1,310 | One example per stdlib function — all modules |
| `cips` | 505 | CIP-1, CIP-20, CIP-31, CIP-68 in full |
| `aiken_v3_curated_v2` | 436 | Complex validators — all 6 handlers, governance, dict, rational |
| `aiken_docs` | 344 | Official docs — language concepts, type system, let/expect |
| `aiken_design_patterns` | 176 | Production patterns from [Anastasia-Labs](https://github.com/Anastasia-Labs) |
| `with_tests_examples` | 169 | Stdlib examples with `test` blocks · compile-verified |
| `correction_set` + v2/v3 | 228 | Targeted corrections for hallucinations · 100% compile-verified |
| `fuzz_patterns_v3` | 150 | 150 `.ak` files compiled with `--max-success 200` |
| `expand_patterns_v1` | 300 | 5 prompt variants per DeFi pattern (families 16–25) |
| `generated_governance_v1` | 54 | `vote` / `publish` / `propose` handlers · 100% compile-verified |
| `hydra_docs` | 60 | Hydra Head L2 — lifecycle, snapshots, fanout |
| `oracle_examples` | 47 | Oracle price feeds — reference input + InlineDatum + staleness |
| `cip068_examples` | 32 | CIP-68 NFT label validation (label 100 / 222 / 333) |
| `others` | ~344 | v3-compat fixes, reference inputs, address patterns, misc |

### Pattern library

150 `.ak` files organized into 25 DeFi/NFT families — all compile-verified:

DEX swap · NFT marketplace · CDP collateral · AMM liquidity · stablecoin mint · order book · thread NFT · vesting schedule · liquidation · Merkle whitelist · CIP-68 reference NFT · oracle feed · multisig treasury · one-shot policy · burn-only policy · governance vote · Hydra fanout · ADA locker · time-lock · datum inline · signature gate · NFT gate · withdrawal staking · certificate delegation · reference input oracle

### Quality methodology

All examples in `correction_set`, `with_tests_examples`, `fuzz_patterns_v3`, and governance sources were verified by running `aiken check` in an isolated sandbox with stdlib v3.0.0 before inclusion. Zero `PLAUSIBLE_NEEDS_CHECK` remain in v23.

---

## System prompt

> **Always load `SYSTEM_PROMPT.txt` as your system prompt.** The model was fine-tuned against it — without it, output quality drops significantly.

The system prompt does three things the model cannot reliably do alone:

**1. Suppresses hallucinated APIs.** It enumerates every removed symbol (`MintedValue`, `PosixTime`, `VerificationKeyCredential`, `Interval<Int>`) and their correct replacements. This acts as a hard constraint at inference time.

**2. Grounds import syntax.** Aiken uses slash-style module paths (`use cardano/transaction.{Transaction}`) with strict rules about which type comes from which module. The `IMPORT RULES` section ensures the model includes every required import for every type it uses — including `VerificationKeyHash`, `InlineDatum`, `PolicyId`, and `Pairs`.

**3. Enforces type correctness.** The most common compile failure in generated contracts is using `ByteArray` for `owner` fields that must be `VerificationKeyHash` (because `extra_signatories` is `List<VerificationKeyHash>`). The `DATUM FIELD TYPES` section prevents this class of error.

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
  use aiken/collection/pairs
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
  Pairs (for withdrawals)      → use aiken/collection/pairs

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
  dict values  : dict.values(d) — returns List<v>
  dict empty   : dict.empty / dict.is_empty(d) / dict.insert(d, k, v)
  dict fold    : dict.foldl(d, seed, fn(k, v, acc) { ... })
  rational     : rational.new(n, d)
  bytearray    : bytearray.take(b, n) / bytearray.drop(b, n) / bytearray.concat(a, b)
  bytearray    : bytearray.from_int_big_endian(n, size) / bytearray.compare(a, b) -> Ordering
  list         : list.foldl(list, seed, fn(elem, acc) { ... }) / list.any(list, pred)
  list         : list.find(list, pred) -> Option<a> / list.repeat(value, count)
  list         : list.count(list, pred) -> Int / list.filter(list, pred) -> List<a>
  assets merge : assets.merge(v1, v2)
  address      : addr.payment_credential — field of type Credential
  address      : address.from_verification_key(vk_hash) -> Address

WITHDRAWALS (Aiken v3 — CRITICAL):
  self.withdrawals : Pairs<Credential, Lovelace> — NOT Dict
  use aiken/collection/pairs
  pairs.get_first(self.withdrawals, account) -> Option<Lovelace>
  NEVER dict.get(self.withdrawals, ...) — type_mismatch

DATUM UNWRAP PATTERN:
  expect Some(d) = datum  -- fails tx if datum is None

CREDENTIAL PATTERN MATCH:
  use cardano/address.{Address, VerificationKey, Script}
  when output.address.payment_credential is {
    VerificationKey(pkh) -> list.has(self.extra_signatories, pkh)
    Script(_)            -> False
  }

INTERVAL PATTERNS:
  interval.is_entirely_after(self.validity_range, deadline) -> Bool
  interval.before(point) -> Interval / interval.after(point) -> Interval
  use aiken/interval.{Finite}
  when self.validity_range.lower_bound.bound_type is {
    Finite(t) -> t >= unlock_time
    _         -> False
  }

ORACLE PATTERN (reference input + InlineDatum + staleness):
  fn get_oracle_input(inputs: List<Input>, policy: PolicyId, asset: AssetName) -> Input {
    expect Some(oracle_input) = list.find(
      inputs,
      fn(i) { assets.quantity_of(i.output.value, policy, asset) == 1 },
    )
    oracle_input
  }

CIP-68 LABEL PREFIXES:
  Label 100 — reference NFT : #"000643b0"
  Label 222 — user NFT      : #"000de140"
  Label 333 — fungible token: #"0014df10"

CIP-68 PATTERN (mint validator):
  let tokens = assets.tokens(self.mint, policy_id)
  let pairs  = dict.to_pairs(tokens)
  -- Check label:   bytearray.take(name, 4) == #"000de140"
  -- Strip prefix:  bytearray.drop(name, 4)

CERTIFICATE constructors (stdlib v3 exact names):
  RegisterCredential, UnregisterCredential, DelegateCredential
  RegisterAndDelegateCredential

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

## Limitations

> Always run `aiken check` on generated output before using it in production.

- Targets **Aiken stdlib v3.0.0 only** — output will not compile against v2 or earlier
- Compile pass rate is 67% on the v8 benchmark (15-prompt suite) — structural correctness is high, some stdlib edge cases still fail; v9 results pending
- Complex novel patterns that combine multiple advanced features may need manual adjustment
- The model does not know your on-chain context (datum shapes, policy IDs, addresses) — you need to supply those
- This is not an auditing tool — generated contracts have not been security-reviewed

---

## Version history

<details>
<summary>Show all versions (v1 → v9)</summary>

| Version | Training examples | Heuristic (15 prompts) | Compile (15 prompts) | Key change |
|---|---|---|---|---|
| cardano-dev v1 | — | 11/15 · 73% | — | Initial prototype |
| cardano-dev v2 | — | 10/15 · 67% | — | Dataset quality regression |
| cardano-dev v3 | — | 12/15 · 80% | — | Import fixes |
| cardano-dev v4 | — | 13/15 · 87% | — | Handler syntax corrections |
| cardano-dev v5 | 3,319 | 14/15 · 93% | — | Correction set added |
| cardano-dev v6 | 3,319 | 14/15 · 93% | 10/15 · 67% | First compile benchmark |
| cardano-dev v7 | 3,401 | 14/15 · 93% | 9/15 · 60% | Governance + oracle added |
| cardano-dev v8 | 3,682 | **15/15 · 100%** | **10/15 · 67%** | First to hit 100% heuristic |
| **cardano-dev v9** | **4,655** | **pending** | **pending** | dataset_v23 · fuzz · expand_patterns |

Dataset quality has been the dominant driver across all versions — not model size or step count. The jump from v7 to v8 (93% → 100% heuristic) came entirely from targeted correction examples, not architectural changes.

</details>

---

Full training pipeline, dataset scripts, evaluation suite, and changelog:
**[github.com/rodrigoioyz/cardumen-forge](https://github.com/rodrigoioyz/cardumen-forge)**

---

*cardano-dev v9 · dataset v23 · 4,655 examples · Aiken stdlib v3.0.0 · based on Qwen3.5-4B · QLoRA Q4_K_M*
