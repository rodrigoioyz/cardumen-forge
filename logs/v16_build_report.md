# Dataset v16 Build Report

**Input:** `data/processed/dataset_v15_train_split.jsonl` (3,363 examples)
**Output:** `data/processed/dataset_v16_train_split.jsonl` (3,357 examples)

## Fixes Applied

| Fix | Result |
|-----|--------|
| `fn else(` → `else(` | 22 occurrences fixed |
| Broken examples removed | 6 examples dropped |
| Truncated outputs detected | 62 flagged (not modified) |

## Removed Examples

- **assets.flatten(assets.from_asset_list([]))**
  - source: `aiken_docs`  topic: `aiken/getting_started`
  - instruction: Write a simple Aiken v3 mint validator that checks at least one token is minted under the script's own policy ID.

- **value.to_dict(**
  - source: `aiken_stdlib`  topic: `aiken/cardano.assets`
  - instruction: How do I check if a value is Ada using the ada_policy_id constant in Aiken?

- **value.to_dict(**
  - source: `aiken_stdlib`  topic: `aiken/cardano.assets`
  - instruction: ¿Cómo verifico si un valor contiene solamente Ada y no otros tokens en un validador Aiken?

- **value.to_dict(**
  - source: `aiken_stdlib`  topic: `aiken/cardano.assets`
  - instruction: Show me how to use to_dict() to iterate over all assets in a Value and check their quantities.

- **assets.flatten(assets.from_asset_list([]))**
  - source: `aiken_stdlib`  topic: `aiken/aiken.primitive.bytearray.to_hex`
  - instruction: Write an Aiken validator that checks whether the hex-encoded asset name of a minted token matches an expected hex string

- **assets.flatten(assets.from_asset_list([]))**
  - source: `cips`  topic: `cardano/cip/cip-0026`
  - instruction: Write an Aiken v3 minting policy that acts as an on-chain anchor for CIP-0026 metadata: it mints exactly one NFT (quanti

## Truncated Outputs (top 30)

These examples were kept but flagged for future regeneration.

| Source | Topic | Reason | Tail |
|--------|-------|--------|------|
| `aiken_design_pattern` | `aiken/patterns/lib/aiken-desig` | ends_abruptly: ...'_utxo)` and returns i | `own UTxO)↵5. Calls `validation_logic(in_` |
| `aiken_docs` | `aiken/getting_started` | ends_abruptly: ...'r Aiken validator scr | `your project↵- `validators/` – directory` |
| `aiken_docs` | `aiken/getting_started` | ends_abruptly: ...'than hand-editing thi | `ares stdlib; use `aiken packages` comman` |
| `aiken_docs` | `aiken/eutxo_crash_course` | ends_abruptly: ...'erification algorithm | `datum↵- signature → redeemer↵- digital-s` |
| `cips` | `cardano/cip/cip-0058` | ends_abruptly: ...'ic primitive implemen | ` representation and manipulation**↵- **C` |
| `aiken_stdlib` | `aiken/aiken.crypto.int224` | ends_abruptly: ...'in the valid range fo | `ntegers↵- Make sure your ByteArray value` |
| `aiken_stdlib` | `aiken/aiken.crypto.int224` | ends_abruptly: ...'uilding complex on-ch | `t of Aiken's low-level cryptographic too` |
| `aiken_stdlib` | `aiken/aiken.crypto.int224` | ends_abruptly: ...'do dentro del rango d | `úrate de que el ByteArray representa un ` |
| `aiken_stdlib` | `aiken/aiken.crypto.int256` | ends_abruptly: ...'ed to chain multiple  | `onverting bytes to integers separately w` |
| `aiken_stdlib` | `aiken/aiken.crypto.int256.test` | ends_abruptly: ...'emes or threshold cry | `monetary values↵- Working with multi-sig` |
| `aiken_stdlib` | `aiken/aiken.interval` | ends_abruptly: ...'o representado por tu | `alo durante pruebas↵- Entender rápidamen` |
| `aiken_stdlib` | `aiken/aiken.math.rational` | ends_abruptly: ...'floating-point roundi | `ns across contract executions↵- You want` |
| `aiken_stdlib` | `aiken/aiken.math.rational` | ends_abruptly: ...'al or mathematical co | `culations↵- Validate fractional amounts ` |
| `aiken_stdlib` | `aiken/aiken.math.rational` | ends_abruptly: ...'cálculos precisos de  | ` ideal para contratos financieros donde ` |
| `aiken_stdlib` | `aiken/aiken.math.rational` | ends_abruptly: ...'de la imparcialidad e | `lmente importante en distribuciones de a` |
| `aiken_stdlib` | `aiken/aiken.option` | ends_abruptly: ...'eries where each step | `s admin → get permissions)↵- Dependent d` |
| `aiken_stdlib` | `aiken/aiken.option` | ends_abruptly: ...'oice([]) == None` — e | `one, None]) == None` — no match found↵- ` |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | ends_abruptly: ...'e byte específico y p | `ran big-endian↵- Serializar valores con ` |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | ends_abruptly: ...'s and on-chain data s | `an needed↵- Useful for fixed-width binar` |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | ends_abruptly: ...'perados codificados c | ` que los datos de entrada coincidan con ` |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | ends_abruptly: ...'anges may cause runti | `start and end indexes are within bounds;` |
| `aiken_stdlib` | `aiken/aiken.primitive.string` | ends_abruptly: ...'r datos para consumo  | `rror que incluyan múltiples direcciones↵` |
| `aiken_stdlib` | `aiken/cardano.assets` | ends_abruptly: ...'tokens de políticas c | `sencial para seguridad: asegúrate de ace` |
| `aiken_stdlib` | `aiken/cardano.assets` | ends_abruptly: ..."'s a valid on-chain a | `s↵- Validate the length is ≤ 32 bytes to` |
| `aiken_stdlib` | `aiken/cardano.assets` | ends_abruptly: ...'lo trabaje con activo | `a prevenir errores y garantizar que el c` |
| `aiken_stdlib` | `aiken/cardano.assets` | ends_abruptly: ...'th only Ada + one spe | `rt contract logic that requires a "clean` |
| `aiken_stdlib` | `aiken/cardano.assets` | ends_abruptly: ...'equires specific NFT  | ` match exactly↵- Useful for validator lo` |
| `aiken_stdlib` | `aiken/cardano.assets` | ends_abruptly: ...'n propiedad específic | `exactamente↵- Muy útil en validadores qu` |
| `aiken_stdlib` | `aiken/cardano.assets` | ends_abruptly: ...' to validate token co | `y used in minting policies and spending ` |
| `aiken_stdlib` | `aiken/cardano.assets` | ends_abruptly: ...'report of valuable as | `ring out dust or zero amounts↵- Building` |

_...and 32 more. Full list in memory._

## Pending (not done in this build)

- [ ] Fix `import` → `use` (needs manual review)
- [ ] Fix `ScriptCredential` → `Script` (needs correction-example check)
- [ ] Fix `cardano/value` → `cardano/assets` (needs context check)
- [ ] Fix `PolicyId` wrong imports (~50-100 examples)
- [ ] Reduce 800+ duplicate signature-check examples
- [ ] Regenerate ~300-400 truncated outputs
- [ ] Verify 1,500 PLAUSIBLE_NEEDS_CHECK examples
- [ ] Generate new: propose(15), vote(20), publish(20), state machine(20), CIP-68(15)

_Generated by `scripts/build_v16.py`_