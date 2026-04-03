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
- Average output length: **893 chars**
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

# Thorough Quality Audit of Aiken v3 Fine-Tuning Dataset

## 1. Data Quality Issues

### 1.1 Critical Syntax Errors: `fn` in Handler Signatures

**This is the single most damaging pattern in the dataset.** Multiple examples use `fn` keyword inside validator handler definitions, which is **incorrect Aiken v3 syntax**. Validator handlers should NOT have `fn` before the handler name.

**Affected examples in sample:**
- **Example 21** (aiken_docs.json): `fn spend(datum: Option<ChannelDatum>, ...)` — should be `spend(datum: Option<ChannelDatum>, ...)`
- **Example 22** (aiken_docs.json): `fn spend(datum: Option<TokenGateDatum>, ...)`
- **Example 23** (aiken_docs.json): `fn mint(_redeemer: Data, policy_id: PolicyId, ...)`
- **Example 24** (aiken_docs.json): `fn spend(datum: Option<DonationDatum>, ...)`
- **Example 25** (aiken_docs.json): `fn spend(datum: Option<TimedSplitDatum>, ...)`
- **Example 26** (aiken_docs.json): `fn spend(datum: Option<MilestoneDatum>, ...)`
- **Example 27** (aiken_docs.json): `fn spend(datum: Option<MultiSigEscrowDatum>, ...)`
- **Example 28** (aiken_docs.json): `fn spend(datum: Option<VestingDatum>, ...)`
- **Example 29** (aiken_docs.json): `fn spend(datum: Option<NftSwapDatum>, ...)`
- **Example 30** (aiken_docs.json): `fn spend(datum: Option<AuctionDatum>, ...)`
- **Example 31** (aiken_docs.json + aiken_design_patterns.json): `fn mint(_redeemer: Data, policy_id: PolicyId, ...)`
- **Example 32** (aiken_docs.json + aiken_design_patterns.json): `fn mint(_redeemer: Data, policy_id: PolicyId, ...)`
- **Example 33** (aiken_docs.json + aiken_stdlib.json): `fn spend(...)`
- **Example 34**: `fn spend(...)`
- **Example 35**: `fn spend(...)`
- **Example 36**: `fn withdraw(...)`
- **Example 37**: `fn spend(...)`
- **Example 38**: `fn mint(...)`
- **Example 39**: `fn spend(...)`
- **Example 40**: `fn spend(...)`
- **Example 41**: `fn spend(...)`
- **Example 42**: `fn spend(...)`
- **Example 53**: `fn mint(...)`
- **Example 54**: `fn spend(...)`
- **Example 55**: `fn mint(...)`
- **Example 56**: `fn mint(...)`
- **Example 57**: `fn mint(...)`
- **Example 58**: `fn spend(...)`
- **Example 59**: `fn mint(...)`
- **Example 60**: `fn mint(...)`
- **Example 61**: `fn mint(...)`
- **Example 62**: `fn spend(...)`
- **Example 63**: `fn spend(...)`
- **Example 64**: `fn spend(...)`
- **Example 65**: `fn spend(...)`

**Impact assessment:** In this 112-example sample, roughly **45 examples** (~40%) use the `fn` prefix in handler definitions. Extrapolating to the full dataset: the `aiken_docs.json`, `aiken_stdlib.json`, `aiken_docs.json + aiken_stdlib.json`, and `aiken_v3_curated_v2` sources collectively have ~665+ examples, many of which likely contain this same error. The sources `aiken_docs.json` (22), `aiken_stdlib.json` (22), `aiken_docs.json + aiken_stdlib.json` (185), and `aiken_docs.json + aiken_design_patterns.json` (2) are particularly suspect — these 231 examples likely all use `fn` syntax consistently. Even many `aiken_v3_curated_v2` examples (436 total) use `fn`.

**Correct syntax:**
```aiken
validator my_validator {
  spend(datum: Option<Data>, redeemer: Data, own_ref: OutputReference, self: Transaction) -> Bool {
    // ...
  }
}
```

**Incorrect syntax found in dataset:**
```aiken
validator my_validator {
  fn spend(datum: Option<Data>, redeemer: Data, own_ref: OutputReference, self: Transaction) -> Bool {
    // ...
  }
}
```

This is arguably the **most critical issue** in the entire dataset. The model will learn to produce `fn` prefixed handlers approximately 40-50% of the time, creating unreliable output.

### 1.2 `self` Naming Convention vs Actual Compiler Requirement

**Example 97** and **Example 100-102** in the correction set teach that the Transaction parameter **must** be named `self`. This is misleading — Aiken v3 does not enforce the parameter name `self`; any name works. The convention is `self`, but `tx` compiles fine. The correction in Example 97 states: "Accessing it as `tx.inputs` will cause a compile error because the parameter name `tx` does not exist in this scope" — this is **factually wrong**. The parameter can be named anything.

However, teaching `self` as convention is reasonable for consistency. The problem is framing it as a compiler error rather than a style convention. Examples 97, 100, 101, and 102 should be revised to say "by convention" not "will cause a compile error."

### 1.3 `StakeCredential` Import Path Error

**Example 101**: `use cardano/assets.{StakeCredential}` — `StakeCredential` is NOT exported from `cardano/assets`. It should be `use cardano/address.{Credential}` or similar. The correction output repeats this wrong import.

### 1.4 Truncated Outputs

Many examples are truncated mid-sentence or mid-code:
- **Example 1**: cuts off at `**`va`
- **Example 2**: cuts off mid-sentence
- **Example 3**: cuts off mid-sentence  
- **Example 5**: cuts off at `let time`
- **Example 6**: cuts off at `tx.mint,                   // the Value from the transa`
- **Example 9**: cuts off at `acc`
- **Example 23**: cuts off mid-code
- **Example 33**: cuts off mid-code
- **Example 34**: cuts off mid-code
- **Example 40**: cuts off mid-code
- **Example 41**: cuts off mid-code
- **Example 48**: garbled/confused code
- **Example 64**: cuts off mid-code
- **Example 65**: cuts off mid-code
- **Example 67**: cuts off mid-code
- **Example 96**: cuts off mid-code

From the stats, `avg_output_len_chars = 893` — many real-world validators would be longer. However, the truncation is a more immediate quality issue. The model will learn to produce incomplete code.

**Quantification:** ~25% of the sample examples appear truncated. At the dataset level, with average output length of 893 characters and no outputs under 100 chars, the truncation likely affects examples in the 700-1200 char range that are cut before completion.

### 1.5 Example 48 — Garbled/Confused Code

```aiken
let invalid_entries =
  list.filter(
    assets.flatten(assets.from_asset("", "", 0) |> fn(_) { self.mint }),
    fn(entry) {
      let (pid, _name, qty) = entry
      pid == policy_id && qty <= 0
    },
  )
```

This is nonsensical — `assets.from_asset("", "", 0) |> fn(_) { self.mint }` is not valid Aiken. This example teaches completely wrong patterns and should be removed or rewritten.

### 1.6 `else(_)` Inconsistency

Some examples include `else(_) { fail }` fallback handlers (Examples 10, 31, 32, 53, 56, 57, 60, 61, 78) while others don't. The `else` handler is recommended practice for production validators. The dataset should be consistent about when to include it or explicitly teach when it's needed vs optional.

### 1.7 `option.unwrap` vs `option.or_else` Inconsistency

**Example 83** uses `datum |> option.unwrap(0)` but doesn't import `aiken/option`. The function is actually `option.or_else` in some contexts. Need to verify the correct API.

### 1.8 Correction Examples with `fn` Prefix

The correction set (Examples 88, 90, 96) that are supposed to fix errors **also contain `fn` in the handler signatures in the INPUT CODE**. This is fine for the input (showing the error), but Examples 88 and 90's corrected OUTPUT also use `fn spend(...)` — meaning the correction doesn't actually fix the `fn` prefix issue. This teaches the model that `fn` prefix is correct.

### 1.9 Missing Import for `option` Module

**Examples 83, 87, 91** use `option.unwrap` or `option.or_else` without importing the option module. The correct import would be `use aiken/option` or similar.

### 1.10 `PolicyId` Without Import

**Examples 53, 55, 56, 57, 59, 60, 61, 67, 70, 72** reference `PolicyId` in function signatures without importing it. In Aiken v3, `PolicyId` should come from `use cardano/assets.{PolicyId}` (as correctly done in Example 13) or be available as `ByteArray`.

---

## 2. Coverage Gaps

### 2.1 Missing Validator Types

| Handler Type | Count in Sample | Estimated in Full Dataset | Assessment |
|---|---|---|---|
| `spend` | ~60 | ~1400+ | Well covered |
| `mint` | ~20 | ~400+ | Adequately covered |
| `withdraw` | ~3 | ~50-70 | **Severely underrepresented** |
| `publish` | ~1 (correction only) | ~30-40 | **Severely underrepresented** |
| `vote` | ~1 (correction only) | ~20-30 | **Severely underrepresented** |
| `propose` | 0 | ~5-10 | **Nearly absent** |
| Multi-handler validators | ~3 | ~30-50 | **Underrepresented** |

The dataset is dominated by `spend` validators. Conway-era governance handlers (`vote`, `publish`, `propose`) are almost exclusively in correction examples, meaning the model only learns about them in error-fixing contexts, not in "write from scratch" contexts.

### 2.2 Missing Aiken v3 Language Concepts

1. **`when/is` exhaustive matching on complex types** — Few examples show deep pattern matching on transaction structure
2. **`expect` with custom error messages** — Only Example 14 touches this
3. **Validator parameters** — Only a few examples show parameterized validators (e.g., Example 13)
4. **`else(_)` fallback handler** — Inconsistently taught, never explicitly explained
5. **Opaque types** — Not covered at all
6. **Generics in custom types** — Not covered
7. **Recursive types and functions** — Not covered in validator contexts
8. **`trace` and `@` string syntax for debugging** — Minimally covered
9. **`Pairs` type (distinct from `Dict`)** — Only covered in corrections
10. **`OutputReference` construction and matching** — Frequently used but rarely explained
11. **`InlineDatum` vs `DatumHash` vs `NoDatum` pattern matching** — Only Example 69 touches `InlineDatum`
12. **Reference inputs (`self.reference_inputs`)** — Only Example 69 uses them
13. **`self.datums` field for datum lookup** — Not covered
14. **`self.redeemers` field** — Mentioned in Example 2 but never demonstrated
15. **Plutus data encoding/decoding** — Not covered
16. **CIP-68 reference NFT patterns** — Not covered

### 2.3 Missing Error Correction Scenarios

Current corrections (198 examples) cover:
- Wrong interval argument order
- Wrong import paths (dot vs slash)
- Wrong asset API
- `dict.to_list` → `dict.to_pairs`
- `rational.divide` → `rational.new`
- Conway handler signature errors
- `ctx.transaction.*` → `self.*`

**Missing correction scenarios:**
1. **`fn` prefix in handler** — The most common error in the dataset itself, ironically
2. **`ScriptContext` usage** — Only partially covered
3. **Wrong `spend` signature** (e.g., datum not wrapped in `Option`)
4. **`value.lovelace` direct access** — Example 90 covers this once, needs more
5. **Mixing up `self.mint` (Value) with minting actions** 
6. **Using `list.find` when `list.find_map` is more appropriate** (and vice versa)
7. **`assets.from_list` vs `assets.from_asset` confusion**
8. **Confusing `assets.tokens` return type with list operations**
9. **Using `==` on `Value` types instead of proper comparison functions**
10. **Missing `else(_)` handler causing unexpected behavior**
11. **Wrong `Transaction` field names** (e.g., `self.fee` doesn't exist the way people expect)

### 2.4 Missing Real-World Contract Patterns

1. **DEX/AMM validators** — Constant product, order book
2. **Stablecoin/CDP contracts** — Collateralization checks
3. **Governance proposal validators** — Actual `propose` handler usage
4. **DRep delegation validators** — Conway-era governance
5. **Stake pool operator validators** — Using `publish` for pool registration/retirement
6. **Multi-asset swaps** — Beyond simple NFT swaps
7. **Merkle tree verification** — Common in bridge contracts
8. **State machine patterns** — Thread token + datum progression
9. **Batching/folding patterns** — Process multiple UTxOs efficiently
10. **Oracle integration patterns** — Beyond the single Example 69
11. **Flash loan prevention patterns**
12. **Parameterized minting with CIP-68 metadata**

---

## 3. Balance Issues

### 3.1 Overrepresented Topics (Overfitting Risk)

| Topic | Count | Risk |
|---|---|---|
| Multisig/threshold signing | ~15+ examples | High — model will default to multisig patterns for any ambiguous request |
| Simple signer check (`list.has(self.extra_signatories, ...)`) | ~30+ examples | Very High — this pattern appears in nearly every validator, risking template memorization |
| Time-locked/deadline patterns | ~12+ examples | Moderate — good coverage but repetitive |
| One-shot NFT minting | ~5 examples (very similar) | Moderate — Examples 23, 31, 32 are near-duplicates |
| `aiken/eutxo_crash_course` (93 examples) | Very High — conceptual knowledge that may crowd out practical patterns |
| `aiken/cardano.governance.protocol_parameters` (67 examples) | High — very niche topic with disproportionate representation |
| Hydra protocol (60 examples) | Moderate — useful but none contain Aiken code |

### 3.2 Underrepresented Critical Topics

| Topic | Estimated Count | Impact |
|---|---|---|
| `withdraw` validators | ~50-70 | High — common in DeFi |
| `publish` validators | ~30-40 | High — needed for Conway era |
| `vote` validators | ~20-30 | High — needed for Conway era |
| `propose` handlers | ~5-10 | Critical — nearly absent |
| Multi-handler validators (spend + mint in one) | ~30-50 | High — very common in production |
| Reference input patterns | ~10-20 | High — fundamental to modern Cardano |
| CIP-68 patterns | 0 | Critical — widely used standard |
| State machine / thread token | ~5-10 | High — fundamental pattern |
| `else(_)` fallback handler education | ~10-15 | Moderate |

### 3.3 Language Distribution

The dataset has substantial Spanish

---
_Generated by `scripts/audit_dataset_quality.py`_