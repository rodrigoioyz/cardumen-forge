# Fix Types Report (Fix #2 + Fix #3)

**Input:** `data/processed/dataset_v16_train_split.jsonl`
**Mode:** WRITE

## Ground Truth (from data/raw/aiken_stdlib.json)

| Type | Module | Note |
|------|--------|------|
| `PolicyId` | `cardano/assets` | NOT in cardano/transaction |
| `Credential` | `cardano/address` | Constructors: `Script`, `VerificationKey` |
| `ScriptCredential` | — | Does NOT exist in Aiken v3 |
| `PubKeyCredential` | — | Does NOT exist in Aiken v3 |

## Fix #2 — Constructor Names

Examples touched: **2**  |  Total replacements: **2**

- `aiken_design_patterns` / `aiken/patterns/aiken_design_patterns_-_overview`
  - Write a minimal Aiken v3 spend validator that implements the 'withdraw zero trick': it should only c
  - `ScriptCredential → Script (2x): Plutus v2 name → Aiken v3 constructor`

- `aiken_docs` / `aiken/common_design_patterns`
  - Refactoriza un validador de gasto en Aiken v3 que actualmente verifica la firma del propietario en c
  - `ScriptCredential → Script (2x): Plutus v2 name → Aiken v3 constructor`

## Fix #3 — PolicyId Import

Examples touched: **17**

- `aiken_docs.json + aiken_stdlib.json` / `mint validator with admin signature and capped supply`
  - Write an Aiken v3 mint validator that requires an admin signature and caps the minted quantity of a 
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `time-bounded ICO mint validator with admin authorization`
  - Write an Aiken v3 mint validator for a time-bounded ICO: minting is only allowed within a specific t
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `burn-only mint validator with admin authorization`
  - Write an Aiken v3 burn-only policy validator: only negative quantities (burns) are accepted and must
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `validador de minteo con multifirma 2-de-2 y cantidad exacta`
  - Escribe un validador de minteo en Aiken v3 que requiera la firma de dos administradores (N-of-M 2-de
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `one-time NFT mint validator with deadline`
  - Write an Aiken v3 mint validator for a one-time NFT: exactly 1 token must be minted, and minting mus
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `validador de minteo con ventana de tiempo y tope de cantidad`
  - Escribe un validador de minteo en Aiken v3 que solo permita mintear dentro de un rango de tiempo esp
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `mint/burn split policy validator`
  - Write an Aiken v3 mint validator that allows either minting (positive qty, admin required) or burnin
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `validador de minteo post-lanzamiento con firma de admin`
  - Escribe un validador de minteo en Aiken v3 donde se requiere la firma del administrador y que el min
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `2-of-3 multisig mint validator with bounded quantity`
  - Write an Aiken v3 mint validator implementing a 2-of-3 multisig policy where minting requires at lea
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `validador de quema con límite de tiempo`
  - Escribe un validador de minteo en Aiken v3 para una política de quema total: solo se permiten cantid
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `validador de minteo de NFT único con admin y ventana de tiempo`
  - Escribe un validador de minteo en Aiken v3 que permita mintear un NFT único (cantidad exactamente 1)
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `sunset mint/burn policy validator`
  - Write an Aiken v3 mint validator where minting is forbidden (only burning allowed) after a sunset da
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `batch mint validator with minimum quantity and launch date`
  - Write an Aiken v3 mint validator that enforces a minimum batch size (at least 100 tokens) and requir
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `emergency burn + admin-gated mint validator`
  - Write an Aiken v3 mint validator for an emergency burn: any holder of the emergency key can burn tok
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `validador de ICO en dos fases con admin y límites por fase`
  - Escribe un validador de minteo en Aiken v3 que implemente una ICO en dos fases: en la primera fase (
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `validador con minteo en ventana y quema libre con admin`
  - Escribe un validador de minteo en Aiken v3 que combine control de tiempo y quema: permite quemar (ca
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

- `aiken_docs.json + aiken_stdlib.json` / `validador de minteo de colección NFT con cantidad 1 por activo`
  - Escribe un validador de minteo en Aiken v3 con control de suministro: se pueden mintear múltiples no
  - `Removed PolicyId from cardano/transaction import`
  - `Inserted new use cardano/assets.{PolicyId} line`

## Pending

- [ ] Fix `import` → `use` (needs manual review)
- [ ] Regenerate ~62 truncated outputs
- [ ] Generate new examples: propose(0→15), vote(20→40), publish(16→36)
- [ ] Reduce 800+ duplicate signature-check examples
- [ ] Verify 1,500 PLAUSIBLE_NEEDS_CHECK examples

_Generated by `scripts/fix_types.py`_