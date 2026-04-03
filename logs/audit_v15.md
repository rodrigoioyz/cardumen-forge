# Dataset v14 Quality Audit

**Total examples:** 3,363

---

## 1. Distribution Statistics

### By Source
| Source | Count |
|--------|-------|
| `aiken_stdlib` | 1361 |
| `cips` | 525 |
| `aiken_v3_curated_v2` | 436 |
| `aiken_docs` | 359 |
| `aiken_design_patterns` | 193 |
| `aiken_docs.json + aiken_stdlib.json` | 185 |
| `correction_set` | 150 |
| `hydra_docs` | 60 |
| `correction_set_v2` | 48 |
| `aiken_stdlib.json` | 22 |
| `aiken_docs.json` | 22 |
| `aiken_docs.json + aiken_design_patterns.json` | 2 |

### By Review Status
| Status | Count |
|--------|-------|
| `VERIFIED_V3_ALIGNED` | 1785 |
| `PLAUSIBLE_NEEDS_CHECK` | 1500 |
| `CORRECTION` | 78 |

### Code Quality Signals
- Examples with input code: **1256** / 3363
- Outputs with code fences: **1717** / 3363
- Outputs containing `validator`: **1825** / 3363
- Outputs with slash imports (`use cardano/`): **1670**
- ⚠️  Outputs with DOT imports (`use cardano.`): **4** ← should be 0
- Average output length: **892 chars**
- Short outputs (<100 chars): **0**

---

## 2. Anti-Pattern Scan (automated)

**Issues found:**
- `no_validator`: 922 examples
- `dot_import`: 4 examples

**First 10 flagged examples:**

- **[no_validator]** `correction_set` / `correction/type_c_negative`
  - Instruction: Fix this Aiken v3 error: list.has_any used in helper function
  - Output snippet: ``list.has_any` does not exist in Aiken v3; use `list.any(signers, fn(x) { list.has(authorized, x) })`

- **[dot_import]** `correction_set` / `correction/type_c_negative`
  - Instruction: Fix this Aiken v3 error: dot-style import for Transaction
  - Output snippet: `Aiken v3 uses slash-style module paths, not dot-style; replace `use cardano.transaction.{Transaction`

- **[dot_import]** `correction_set` / `correction/type_c_negative`
  - Instruction: Fix this Aiken v3 error: dot-style cardano.transaction import in a spend validator
  - Output snippet: `Aiken v3 requires slash-style module paths, so `use cardano.transaction.{Transaction}` must be repla`

- **[dot_import]** `correction_set` / `correction/type_c_negative`
  - Instruction: Fix this Aiken v3 error: dot-style import and tx.validity_range used together
  - Output snippet: ``use cardano.transaction.{Transaction}` uses invalid dot-style syntax and `tx.validity_range` is not`

- **[dot_import]** `correction_set` / `correction/type_c_negative`
  - Instruction: Fix this Aiken v3 error: assets.quantity_of missing asset_name combined with dot import
  - Output snippet: ``use cardano.transaction.{Transaction}` uses invalid dot-style syntax and `assets.quantity_of` is mi`

- **[no_validator]** `aiken_stdlib` / `aiken/aiken.collection.list.push`
  - Instruction: ¿Cuál es la diferencia entre usar `list.push` y el operador spread `[elem, ..lista]` en Aiken?
  - Output snippet: `Funcionalmente son **equivalentes**: ambos agregan un elemento al frente de la lista.

```aiken
use `

- **[no_validator]** `aiken_stdlib` / `aiken/aiken.collection.list.push`
  - Instruction: Cómo usar `list.push` dentro de un `list.foldl` para construir una lista invertida en Aiken?
  - Output snippet: `Puedes combinar `list.foldl` con `list.push` para invertir una lista: en cada paso, el elemento actu`

- **[no_validator]** `aiken_stdlib` / `aiken/aiken.collection.list.push`
  - Instruction: Refactor the following Aiken snippet to use `list.push` instead of the spread syntax for prepending elements.
  - Output snippet: ````aiken
use aiken/collection/list

let step1 = list.push([2, 3], 1)
let step2 = list.push(step1, 0)`

- **[no_validator]** `aiken_stdlib` / `aiken/aiken.collection.list.range`
  - Instruction: What does `list.range(from, to)` return in Aiken, and can you show a few examples of its output?
  - Output snippet: ``list.range(from, to)` constructs a list of consecutive integers starting at `from` and ending at `t`

- **[no_validator]** `aiken_stdlib` / `aiken/aiken.collection.list.range`
  - Instruction: How do I generate a list of slot indices from slot 10 to slot 20 using Aiken's standard library?
  - Output snippet: `Use `list.range/2` from `aiken/collection/list` to generate the slot indices:

```aiken
use aiken/co`

---

## 3. Claude API Quality Analysis

# Comprehensive Quality Audit of Aiken v3 Fine-Tuning Dataset

## 1. Data Quality Issues

### 1.1 Incorrect Aiken v3 Syntax

**Dot-style imports still present (4 flagged in stats):**
The stats show 4 examples with dot imports. While I can't pinpoint all 4, several examples contain suspicious import patterns:

- **Example 236** (vote handler): Uses `type VerificationKeyHash = ByteArray` instead of importing from `aiken/crypto`. Also defines `Voter` import path inconsistently and mixes `cardano/governance.{Voter}` with `cardano/address.{Credential}`. The handler signature uses `voter: Voter` but the import is from a non-standard location.

- **Example 294** (hot/cold vote): Same issue — `type VerificationKeyHash = ByteArray` is a dangerous anti-pattern that teaches the model to alias types incorrectly instead of using `aiken/crypto.{VerificationKeyHash}`.

- **Example 350** (mint validator): The output is garbled/incoherent — it tries multiple approaches in a single validator with broken logic: `assets.tokens(self.mint, policy_id) |> assets.flatten(assets.from_asset_list([]))`. This is not valid Aiken and would confuse the model badly.

- **Example 756** (string module): Uses `import aiken/primitive/string` — Aiken uses `use`, not `import`.

**Wrong `fn` keyword in handler definitions:**
- **Example 1048** (vote validator): `fn else(_) -> Bool { fail }` — the `else` handler should not use `fn` prefix. This appears in several vote validators.
- **Example 1064** (vote validator): Same `fn else(_) -> Bool { fail }` pattern.
- **Example 1065** (vote validator): Same issue.

**Incorrect handler signatures:**
- **Example 236**: The vote handler output wraps code in a validator that also has a `spend` handler returning `False` — this is pedagogically confusing and the spend handler is gratuitous.

- **Example 438** (burn_only_policy): The output code is deeply nested, incoherent, and uses `assets.reduce` which doesn't exist as shown. The lambda structure is broken.

- **Example 446** (capped_mint): Uses `dict.get(minted_tokens, "my_token") |> option.or_else(0)` — but `option.or_else` requires a direct value, and the piping may not resolve correctly since `dict.get` returns `Option`. The bigger issue: `minted_tokens` is already a Dict but then the code calls `dict.get` on it which assumes keys are ByteArray asset names, not string literals.

**`self` parameter naming violations:**
The correction set (Examples 1775-1822) documents these well, but several non-correction examples still use `tx` or `ctx`:
- **Example 294**: Uses `self` correctly but defines the validator body loosely.

### 1.2 Truncated/Incomplete Outputs

A significant number of examples are cut off mid-code or mid-sentence. These are harmful because the model learns to produce incomplete outputs:

- **Example 1** (validate_mint): Cut at `**`va`
- **Example 2** (validate_mint): Cut at `ordena`
- **Example 3**: Cut at `sobrecargaría aún más la API`
- **Example 5** (normalize_time_range): Cut at `let time`
- **Example 6** (validate_mint): Cut at `the transa`
- Many examples from the `aiken_design_patterns` source (Examples 1-193) are systematically truncated.

This is a pervasive issue across the entire dataset. I estimate **300-400 examples** suffer from meaningful truncation that prevents the model from learning complete code patterns.

### 1.3 Questionable API Usage

- **Example 234** (capped supply): Uses `assets.flatten(self.mint)` then tries to destructure triples and filter — the code is muddled and mixes patterns.

- **Example 364** (nft_mint): The output is broken — `dict_size(d)` doesn't exist as a function; the code tries multiple approaches and none are clean.

- **Example 670** (NFT collection mint): Uses `assets.from_asset_list` and `assets.flatten()` in a way that's likely incorrect — `assets.tokens(policy_id)` returns `Dict<AssetName, Int>`, not something you can pass to `from_asset_list`.

- **Example 877** (ada check): Uses `value.to_dict(val)` — there's no `cardano/value` module in Aiken v3; the correct module is `cardano/assets`.

- **Example 518** (config-based spend): Uses `pub type NftConfigDatum { required_policy: ByteArray required_asset: ByteArray }` — missing commas between fields.

- **Example 537** (oracle check): Same missing-comma pattern in type definitions.

### 1.4 Inconsistent Type Definitions

Many examples define `type VerificationKeyHash = ByteArray` instead of importing from `aiken/crypto`:
- Examples 236, 294, and others in the `aiken_docs.json` source group.

This is dangerous because it teaches the model an anti-pattern that bypasses Aiken's type system.

### 1.5 Missing `else` Handlers

Many validators in the curated examples lack `else(_) { fail }` handlers. While technically optional in some cases, the documentation strongly recommends them for security. The dataset is inconsistent about including them — some examples include them, many don't. This inconsistency will confuse the model.

### 1.6 Credential Import Issues

- **Example 116** (withdraw zero trick): Imports `cardano/credential.{Credential, ScriptCredential}` — but in Aiken v3, `Credential` constructors are `VerificationKey` and `Script`, not `ScriptCredential`.

- **Example 244** (forwarding spend): Same issue with `ScriptCredential`.

### 1.7 Specific Broken Examples to Flag

| Example | Issue |
|---------|-------|
| 350 | Completely incoherent output, broken Aiken code |
| 438 | Broken nested lambda structure, nonexistent API usage |
| 446 | Incorrect dict/option chaining |
| 670 | Wrong `assets.flatten()` usage |
| 756 | Uses `import` keyword instead of `use` |
| 877 | References nonexistent `cardano/value` module |
| 1048 | `fn else(_)` pattern |
| 1064 | `fn else(_)` pattern |
| 1065 | `fn else(_)` pattern |

---

## 2. Coverage Gaps

### 2.1 Missing Aiken v3 Concepts

**`else(_)` handler patterns:**
While present in some examples, there's no dedicated explanation of when and why to use `else(_) { fail }` vs omitting it. Need 10-15 examples explicitly teaching this.

**Backpassing syntax (`<-`):**
Only covered in design pattern examples (tx_level_minter, merkelized_validator). Need 10-15 standalone examples showing backpassing in general validator logic.

**`expect` vs `when` for pattern matching:**
The dataset uses both but never explicitly teaches when to prefer one over the other. Need 10-15 examples contrasting `expect Some(d) = datum` vs `when datum is { Some(d) -> ... None -> ... }`.

**Opaque types and type aliases:**
No examples teaching how to define and use opaque types, or how type aliases work in Aiken.

**Generic/polymorphic functions:**
Very few examples of generic helper functions used in validators.

**`trace` and debugging:**
Examples 219, 325 mention trace but there are no concrete validator examples using `trace` for debugging.

**`test` keyword and property-based testing:**
Only covered in the design patterns source (fuzz testing). Need standalone examples of writing unit tests and property-based tests for validators.

**Multi-validator blocks:**
Examples exist (e.g., spend+mint) but the concept of sharing state/parameters between handlers in the same validator block needs more explicit teaching — maybe 10 examples.

**`Pairs` type usage:**
Used extensively in design patterns but not well-taught as a standalone concept. The model needs examples showing `Pairs<K, V>` construction, iteration, and pattern matching.

**`and { }` syntax for multiple condition checking:**
Mentioned once (Example 101) but not demonstrated in validator examples.

### 2.2 Underrepresented Validator Types

**`publish` validators:** Only 16 examples (Examples 1044, 1070, 1075, 1120, 1125, 1153, 1167, 1171, 1189, 1252, 1291, 1296, 1314, 1317, correction set). Need 15-20 more covering all certificate types.

**`vote` validators:** About 20 examples, mostly with simple signature checks. Need more diverse voting logic — weighted votes, delegation patterns, proposal-specific logic.

**`propose` validators (constitution guardrails):** **Zero examples.** This is a significant gap for Conway-era governance.

### 2.3 Missing Error Correction Scenarios

The correction set is excellent but misses:

- **Wrong `expect` usage**: No examples showing `expect` used where `when` is safer (potential runtime crash on None).
- **Missing `PolicyId` import**: Examples that forget to import `PolicyId` from `cardano/assets`.
- **Incorrect `OutputReference` construction**: No correction for manually constructing OutputReferences wrong.
- **Double satisfaction vulnerability**: Only Example 367/404/442 cover this; need correction examples showing the vulnerable pattern and the fix.
- **Missing `else(_) { fail }`**: No corrections teaching why omitting it is dangerous.
- **Wrong `Credential` constructor names**: Using `ScriptCredential` instead of `Script`, `PubKeyCredential` instead of `VerificationKey`.

### 2.4 Missing Real-World Contract Patterns

- **State machine / continuing output pattern**: The most common DeFi pattern on Cardano — ensuring the script output is recreated with updated datum. Present in a few examples but not systematically taught.
- **Forwarding mint policy**: A spend validator that delegates to a minting policy by checking the mint field. Present in design patterns but not in standalone examples.
- **Reference script deployment patterns**: How to create and use reference scripts.
- **CIP-68 reference NFT + user token pair validation**: Only 2 examples (1423, 1456). This is the dominant NFT standard on Cardano.
- **Merkle proof verification on-chain**: Zero examples.
- **Oracle patterns with datum freshness checks**: A few examples check oracle data but none verify oracle freshness (e.g., checking the oracle UTxO was updated recently).

---

## 3. Balance Issues

### 3.1 Overrepresented Topics (Overfitting Risk)

**Signature checking (`list.has(self.extra_signatories, key)`):**
This single pattern appears in approximately **800+ examples** across the dataset. While fundamental, the sheer volume means the model will overwhelmingly default to signature checks regardless of the actual question. This is the most serious balance issue.

**Multisig N-of-M patterns:**
Approximately 150-200 examples implement some form of N-of-M multisig, many nearly identical (2-of-3, 3-of-5, 4-of-7 variations). The model will learn this thoroughly but at the cost of other patterns. Recommend capping at ~50 total multisig examples.

**Time-lock / deadline patterns:**
Approximately 200+ examples use `interval.is_entirely_before` or `interval.is_entirely_after`. Again, well-represented but crowding out other patterns.

**`aiken_design_patterns` source (193 examples):**
While high quality, many are explanation-heavy and truncated. The model gets many partial explanations of the same patterns (stake validator trick, tx-level minter) without enough complete code.

**`hydra_docs` source (60 examples):**
All 60 are conceptual/explanatory with zero Aiken code. They explain Hydra protocol concepts in natural language. These contribute to general Cardano knowledge but are tangential to the model's core purpose of writing Aiken validators. Consider whether 60 is justified vs the opportunity cost.

### 3.2 Critically Underrepresented Topics

| Topic | Approximate Count | Needed |
|-------|-------------------|--------|
| `propose` validators | 0 | 15-20 |
| CIP-68 datum NFT validation | 2 | 15-20 |
| State machine / continuing output | ~5 | 20-30 |
| `expect` vs `when` teaching | 0 explicit | 15 |
| Backpassing syntax (`<-`) | ~10 (all in design patterns) | 15-20 standalone |
| `and { }` multi-condition | ~1 | 10 |
| Test/benchmark writing | ~5 | 20 |
| Error messages/`fail @"..."` | scattered | 15 dedicated |
| `Dict` operations beyond `get`/`has_key` | ~15 | 20 |
| `assets.from_asset`/`from_asset_list` construction | ~5 | 15 |
| Double satisfaction prevention | ~3 | 10 |
| Script credential matching | ~10 | 15 |
| `reference_inputs` usage patterns | ~20 | 10 more |

### 3.3 Language Balance

The dataset has a roughly 55/45 English/Spanish split, which is good for bilingual capability. However:
- Almost all correction examples are in English
- Almost all CIP-related conceptual explanations are in English
- Spanish examples tend to be concentrated in validators, not in conceptual explanations of v3 API details

---

## 4. Concrete Recommendations

### 4.1 Top 5 Specific Example Types to Add (Priority Order)

**1. `propose` (Constitution Guardrails) Validators — 15 examples**
This is a complete zero in the dataset. Conway governance is live. Examples should cover:
- Basic guardrails checking protocol parameter bounds
- Checking that treasury withdrawals don't exceed a cap
- Verifying governance action metadata hashes
- Rejecting specific governance action types
- Pattern matching on `ProposalProcedure` fields

```aiken
validator constitution_guardrails {
  propose(redeemer: Void, self: Transaction) -> Bool {
    // Validate all proposal procedures
    list.all(self.proposal_procedures, fn(proposal) {
      // Check treasury withdrawal limits, parameter bounds, etc.
      ...
    })
  }
}
```

**2. State Machine / Continuing Output Pattern — 20 examples**
The most critical DeFi pattern. Examples should show:
- Finding own input via `own_ref`
- Extracting own script hash from payment credential
- Finding continuing output at the same script address
- Verifying datum is correctly updated (counter increment, state transition)
- Verifying value is preserved or correctly modified
- Combining with token checks (state thread token)

**3. `expect` vs `when` Decision Teaching — 15 examples**
Pairs showing:
- When `expect` is appropriate (you want to crash on unexpected state)
- When `when` with explicit `None -> False` is safer
- Common gotcha: `expect Some(d) = datum` crashes when datum is None
- Refactoring examples from unsafe `expect` to safe `when`

**4. CIP-68 Token Standard Validators — 15 examples**
- Minting paired reference NFT (label 100) + user token (label 222)
- Validating asset name prefix structure
- Updating metadata via reference NFT datum updates
- Checking CRC-8 checksum of label prefix
- Complete CIP-68 multivalidator with mint + spend

**5. Complete Backpassing and `and { }` Syntax — 15 examples**
- Using `let result <- some_function(args)` in validators
- Using `and { condition1, condition2, condition3 }` for readable multi-condition checks
- Combining both patterns in realistic validators

### 4.2 Examples to Remove or Correct

**Remove (low signal, high noise):**
- **Example 350**: Completely broken output, would teach wrong patterns
- **Example 438**: Incoherent burn policy with broken nested lambdas

**Correct (fixable but currently harmful):**
- **Example 236**: Fix imports, remove gratuitous spend handler, use proper `VerificationKeyHash` import
- **Example 294**: Same fixes as 236
- **Example 446**: Fix dict/option chaining to use correct API
- **Example 670**: Fix

---
_Generated by `scripts/audit_dataset_quality.py`_