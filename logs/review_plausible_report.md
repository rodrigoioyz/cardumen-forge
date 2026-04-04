# Review PLAUSIBLE_NEEDS_CHECK Report

**Input:** `data/processed/dataset_v19_dedup.jsonl` (3,406 examples)
**Mode:** WRITE

## Summary

| Decision | Count | % |
|----------|-------|---|
| VERIFIED_V3_ALIGNED | 351 | 23.6% |
| FLAGGED_REMOVE | 87 | 5.8% |
| stays PLAUSIBLE | 1,052 | 70.6% |

## Flagged for removal

| Source | Topic | Bad patterns | Instruction |
|--------|-------|-------------|-------------|
| `aiken_stdlib` | `aiken/aiken.interval` | tx.validity_range | ¿Cómo puedo usar la función `to_string` del módulo `aiken.interval` pa |
| `aiken_stdlib` | `aiken/aiken.option` | policyd_wrong_module | What does aiken.option.choice() do and when would you use it in practi |
| `aiken_stdlib` | `aiken/cardano.assets` | policyd_wrong_module | ¿Cómo puedo extraer y validar el PolicyId de un token en un contrato A |
| `aiken_stdlib` | `aiken/cardano.assets` | policyd_wrong_module | How do I create and use an AssetName in Aiken to identify a custom tok |
| `aiken_stdlib` | `aiken/cardano.assets` | policyd_wrong_module | ¿Cómo validar que un AssetName es válido y que no es Ada en un contrat |
| `aiken_stdlib` | `aiken/cardano.assets` | assets.from_asset_list | How do I construct a Value from a list of assets using from_asset_list |
| `aiken_stdlib` | `aiken/cardano.assets` | policyd_wrong_module | How do I verify that a transaction output contains exactly one NFT fro |
| `aiken_stdlib` | `aiken/cardano.assets` | policyd_wrong_module | ¿Cómo puedo verificar si una salida de transacción contiene un NFT esp |
| `aiken_stdlib` | `aiken/cardano.assets` | policyd_wrong_module | What does the tokens() function do and when should I use it in my vali |
| `aiken_docs` | `aiken/language` | policyd_wrong_module | How would you implement a receipt minting validator in Aiken that crea |
| `aiken_docs` | `aiken/language` | policyd_wrong_module | ¿Cómo implementarías un validador de recibos en Aiken que cree un nomb |
| `aiken_docs` | `aiken/language` | policyd_wrong_module | Escribe un fragmento de código Aiken que muestre shadowing de variable |
| `aiken_docs` | `aiken/language` | policyd_wrong_module | ¿Cómo se define un validador con un handler mint que valida la acuñaci |
| `cips` | `cardano/cip/cip-0153` | policyd_wrong_module | Explain the current limitations of how Plutus Core handles multi-asset |
| `aiken_design_pattern` | `aiken/patterns` | policyd_wrong_module | How do I use `validate_mint` inside a spending validator to delegate l |
| `aiken_design_pattern` | `aiken/patterns` | tx.validity_range | How do I use `normalize_time_range` inside an Aiken validator to check |
| `aiken_design_pattern` | `aiken/patterns` | tx.validity_range | ¿Cómo aplico el patrón de normalización de rangos de tiempo en un vali |
| `aiken_stdlib` | `aiken/aiken.collection.list.an` | policyd_wrong_module | Write an Aiken v3 withdrawal validator that ensures at least one input |
| `aiken_stdlib` | `aiken/aiken.collection.list.co` | policyd_wrong_module | Escribe un validador `mint` en Aiken v3 que sólo permita acuñar si la  |
| `aiken_stdlib` | `aiken/aiken.collection.list.fi` | policyd_wrong_module | Escribe un validador `mint` en Aiken que solo permita la acuñación si  |
| `aiken_stdlib` | `aiken/aiken.collection.list.fi` | policyd_wrong_module | Write a validator that collects all lovelace amounts from transaction  |
| `aiken_stdlib` | `aiken/aiken.collection.list.sl` | policyd_wrong_module | Escribe un validador de tipo `mint` en Aiken que valide que solo se ac |
| `aiken_stdlib` | `aiken/aiken.collection.list.un` | policyd_wrong_module | ¿Cómo puedo usar `list.unique` para deduplicar una lista de `PolicyId` |
| `aiken_stdlib` | `aiken/aiken.collection.list.un` | assets.from_asset_list, policyd_wrong_module | Escribe un validador mint en Aiken que garantice que los nombres de ac |
| `aiken_stdlib` | `aiken/aiken.collection.list.fl` | policyd_wrong_module | How do I use `list.flat_map` to expand each transaction input into a l |
| `aiken_stdlib` | `aiken/aiken.collection.list.fl` | assets.from_asset_list, policyd_wrong_module | Escribe un validador en Aiken que use `list.flat_map` para recopilar t |
| `aiken_stdlib` | `aiken/aiken.collection.list.in` | policyd_wrong_module | Write a mint validator that only allows minting if the list of minted  |
| `aiken_stdlib` | `aiken/aiken.collection.list.di` | policyd_wrong_module | Escribe un validador en Aiken que permita quemar tokens solo si los as |
| `aiken_stdlib` | `aiken/aiken.collection.list.re` | policyd_wrong_module | ¿Cómo puedo usar `list.reduce` para contar cuántos tokens de una polít |
| `aiken_stdlib` | `aiken/aiken.option.map` | policyd_wrong_module | Escribe un validador de minteo en Aiken que use `option.map` para calc |
| `aiken_stdlib` | `aiken/aiken.option.or_else` | policyd_wrong_module | Escribe un validador `mint` en Aiken que lea una cantidad mínima opcio |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | policyd_wrong_module | ¿Cómo puedo usar `bytearray.from_string` para construir un `AssetName` |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | policyd_wrong_module | ¿Cómo puedo usar `bytearray.at` para leer un byte de una política de a |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | policyd_wrong_module | Write a mint validator in Aiken that validates an asset name by ensuri |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | policyd_wrong_module | Escribe un validador de minting en Aiken v3 que exija que el `AssetNam |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | policyd_wrong_module | Escribe un validador mint en Aiken que use `bytearray.foldr` para aseg |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | policyd_wrong_module | Escribe un validador de minteo en Aiken que decodifique la cantidad a  |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | policyd_wrong_module | ¿Cómo puedo verificar en un validador de Aiken que el nombre de un act |
| `aiken_stdlib` | `aiken/aiken.primitive.bytearra` | policyd_wrong_module | Write a mint validator in Aiken v3 that only allows minting tokens who |
| `aiken_stdlib` | `aiken/cardano.address.Address` | policyd_wrong_module | Escribe un validador Aiken v3 de tipo `mint` que solo permita acuñar t |
| `aiken_stdlib` | `aiken/cardano.address.from_ver` | policyd_wrong_module | Escribe un validador mint en Aiken que sólo permita acuñar tokens si a |
| `aiken_stdlib` | `aiken/cardano.address.with_del` | policyd_wrong_module | Escribe un validador de tipo `mint` que solo permita acuñar tokens cua |
| `aiken_stdlib` | `aiken/cardano.address.PaymentC` | policyd_wrong_module | Escribe un validador mint en Aiken v3 que solo permita acuñar si al me |
| `aiken_stdlib` | `aiken/cardano.assets.PolicyId ` | policyd_wrong_module | Escribe un validador de gasto en Aiken que verifique que la salida dev |
| `aiken_stdlib` | `aiken/cardano.assets.from_asse` | assets.from_asset_list | Escribe un validador de gasto en Aiken v3 que use `assets.from_asset_l |
| `aiken_stdlib` | `aiken/cardano.assets.has_any_n` | policyd_wrong_module | Write a `spend` validator that ensures the UTxO being spent holds exac |
| `aiken_stdlib` | `aiken/cardano.assets.has_any_n` | policyd_wrong_module | Escribe un validador `spend` que garantice que, al gastar un UTxO, tod |
| `aiken_stdlib` | `aiken/cardano.assets.has_nft` | policyd_wrong_module | Escribe un validador de minteo en Aiken v3 que permita acuñar exactame |
| `aiken_stdlib` | `aiken/cardano.assets.quantity_` | policyd_wrong_module | Write a complete Aiken v3 spend validator that ensures a specific NFT  |
| `aiken_stdlib` | `aiken/cardano.assets.quantity_` | policyd_wrong_module | Tengo un validador de gasto que necesita verificar que el output que s |
| `aiken_stdlib` | `aiken/cardano.assets.restricte` | policyd_wrong_module | Write a complete Aiken v3 spend validator that checks every transactio |
| `aiken_stdlib` | `aiken/cardano.assets.flatten` | policyd_wrong_module | Escribe un validador `spend` en Aiken que verifique que ningún output  |
| `aiken_stdlib` | `aiken/cardano.assets.to_dict` | policyd_wrong_module | Muéstrame cómo usar `assets.to_dict` dentro de un validador de minteo  |
| `aiken_design_pattern` | `aiken/patterns/lib/aiken-desig` | policyd_wrong_module | Escribe un validador Aiken v3 que use `one_to_one_no_redeemer` para va |
| `aiken_design_pattern` | `aiken/patterns/lib/aiken-desig` | policyd_wrong_module | Write a mint validator in Aiken v3 that uses the parameter-validation  |
| `aiken_design_pattern` | `aiken/patterns/lib/aiken-desig` | policyd_wrong_module | Implementa un validador completo en Aiken v3 que use `validate_mint_mi |
| `aiken_design_pattern` | `aiken/patterns/lib/tests/linke` | policyd_wrong_module | Write a helper function that, given a `PolicyId` and an `AssetName`, c |
| `aiken_design_pattern` | `aiken/patterns/lib/tests/tx-le` | policyd_wrong_module | How do I write a fuzz test in Aiken that picks a random policy from a  |
| `aiken_design_pattern` | `aiken/patterns/lib/tests/tx-le` | policyd_wrong_module | Write a failing fuzz test that confirms `validate_mint` rejects a hash |
| `aiken_design_pattern` | `aiken/patterns/lib/tests/tx-le` | policyd_wrong_module | ¿Cómo puedo construir una lista de redeemers para `validate_mint` en A |
| `aiken_design_pattern` | `aiken/patterns/validators/exam` | policyd_wrong_module | Write the `withdraw` handler of the multi-utxo-indexer example validat |
| `aiken_design_pattern` | `aiken/patterns/validators/exam` | policyd_wrong_module | Escribe el validador completo `example` del patrón multi-utxo-indexer  |
| `aiken_design_pattern` | `aiken/patterns/validators/exam` | policyd_wrong_module | How do I write a `one_to_one` spend validator using the singular UTxO  |
| `aiken_design_pattern` | `aiken/patterns/validators/exam` | policyd_wrong_module | Write a `one_to_many` spend validator using the singular UTxO indexer  |
| `aiken_design_pattern` | `aiken/patterns/validators/exam` | policyd_wrong_module | Refactor the `one_to_many` validator to add a real `input_output_valid |
| `aiken_docs` | `aiken/getting_started` | policyd_wrong_module | How do I count the number of inputs in a transaction that carry a spec |
| `aiken_docs` | `aiken/eutxo_crash_course` | policyd_wrong_module | Escribe un validador en Aiken que compruebe que la transacción tiene a |
| `aiken_docs` | `aiken/eutxo_crash_course` | policyd_wrong_module | Write an Aiken mint validator that enforces a maximum total supply by  |
| `aiken_docs` | `aiken/common_design_patterns` | policyd_wrong_module | Escribe un validador Aiken v3 de tipo `mint` que garantice que no se a |
| `aiken_docs` | `aiken/common_design_patterns` | policyd_wrong_module | ¿Cómo puedo refactorizar un validador de retiro en Aiken v3 para que v |
| `aiken_docs` | `aiken/common_design_patterns` | policyd_wrong_module | How do I refactor an Aiken v3 spend validator to use `list.any` instea |
| `aiken_docs` | `aiken/what_i_wish_i_knew_when_` | policyd_wrong_module | Write an Aiken v3 minting validator that checks a specific policy_id i |
| `cips` | `cardano/cip/cip-0027` | policyd_wrong_module | Write an Aiken v3 minting policy that enforces the CIP-0027 royalty to |
| `cips` | `cardano/cip/cip-0031` | policyd_wrong_module | Escribe un validador Aiken v3 de tipo `mint` que solo permita acuñar t |
| `cips` | `cardano/cip/cip-0040` | policyd_wrong_module | Escribe un validador Aiken v3 de tipo `mint` que verifique que la tran |
| `cips` | `cardano/cip/cip-0042` | policyd_wrong_module | Escribe un validador mint en Aiken v3 que use `builtin.serialise_data` |
| `cips` | `cardano/cip/cip-0049` | policyd_wrong_module | Escribe un validador mint en Aiken v3 que sólo permita acuñar tokens s |
| `cips` | `cardano/cip/cip-0069` | policyd_wrong_module | Escribe un validador Aiken v3 multi-propósito inspirado en el caso de  |
| `cips` | `cardano/cip/cip-0071` | policyd_wrong_module | Write an Aiken v3 minting policy validator for CIP-0071 NFT proxy voti |
| `cips` | `cardano/cip/cip-0071` | policyd_wrong_module | Escribe un validador Aiken v3 que implemente una "super-voto" según CI |
| `cips` | `cardano/cip/cip-0071` | policyd_wrong_module | Refactor this CIP-0071 ballot minting policy to add a validity range c |
| `cips` | `cardano/cip/cip-0091` | assets.from_asset_list, policyd_wrong_module | Explain the performance optimization strategy mentioned in CIP-0091 fo |
| `cips` | `cardano/cip/cip-0101` | policyd_wrong_module | Escribe un validador mint en Aiken v3 que sólo permita acuñar tokens s |
| `cips` | `cardano/cip/cip-0102` | policyd_wrong_module | Escribe un validador Aiken v3 de tipo `spend` que proteja la UTxO del  |
| `cips` | `cardano/cip/cip-0116` | assets.from_asset_list, policyd_wrong_module | Refactor this Aiken v3 mint validator to properly use the canonical `P |
| `cips` | `cardano/cip/cip-0118` | policyd_wrong_module | Write an Aiken v3 validator that implements a simple swap offer script |
| `cips` | `cardano/cip/cip-0121` | policyd_wrong_module | Escribe un validador Aiken v3 tipo `mint` que, antes de acuñar un toke |

## Most common unverified API calls

| Call | Count |
|------|-------|
| `scalar.inv` | 2 |
| `option.unwrap` | 2 |
| `list.each` | 2 |
| `scalar.pow` | 1 |
| `int256.multiply` | 1 |
| `int256.subtract` | 1 |
| `dict.from_list` | 1 |
| `crypto.hash_blake2b_224` | 1 |
| `pairs.to_list` | 1 |
| `assets.to_list` | 1 |
| `dict.empty` | 1 |

_Generated by `scripts/review_plausible.py`_