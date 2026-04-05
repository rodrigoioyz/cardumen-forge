use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

const label_222: ByteArray = #"000de140"
const label_100: ByteArray = #"000643b0"

pub type CredentialMetadata {
  holder:  ByteArray,
  issuer:  ByteArray,
  expiry:  Int,
  role:    ByteArray,
}

fn has_label(name: ByteArray, label: ByteArray) -> Bool {
  bytearray.length(name) >= 4 && bytearray.take(name, 4) == label
}

fn strip_label(name: ByteArray) -> ByteArray {
  bytearray.drop(name, 4)
}

/// Every (222)X user token must have a paired (100)X reference token, both qty=1
fn credential_pairs_valid(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  dict.to_pairs(tokens)
    |> list.all(
        fn(p) {
          let Pair(name, qty) = p
          if has_label(name, label_222) {
            qty == 1 && {
              let ref = bytearray.concat(label_100, strip_label(name))
              dict.get(tokens, ref) == Some(1)
            }
          } else {
            True
          }
        },
      )
}

validator cip68_credential_mint {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    !dict.is_empty(tokens) && credential_pairs_valid(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_has_label_222_correct() {
  has_label(#"000de140ff", label_222)
}

test prop_has_label_100_correct() {
  has_label(#"000643b0ff", label_100)
}

test prop_has_label_short(name via fuzz.bytearray_between(0, 3)) {
  !has_label(name, label_222)
}

test prop_strip_label_roundtrip(suffix via fuzz.bytearray_between(1, 28)) {
  let full = bytearray.concat(label_222, suffix)
  strip_label(full) == suffix
}

test prop_pairs_valid_empty() {
  // empty tokens → valid (vacuously) but validator rejects via !is_empty check
  credential_pairs_valid(dict.empty)
}

test prop_pairs_valid_balanced() {
  let suffix = #"deadbeef"
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
      |> dict.insert(bytearray.concat(label_100, suffix), 1)
  credential_pairs_valid(tokens)
}

test prop_pairs_invalid_missing_ref() {
  let suffix = #"deadbeef"
  let tokens = dict.empty |> dict.insert(bytearray.concat(label_222, suffix), 1)
  !credential_pairs_valid(tokens)
}
