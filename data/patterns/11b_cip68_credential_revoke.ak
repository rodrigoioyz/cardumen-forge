use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

const label_222: ByteArray = #"000de140"
const label_100: ByteArray = #"000643b0"

fn has_label(name: ByteArray, label: ByteArray) -> Bool {
  bytearray.length(name) >= 4 && bytearray.take(name, 4) == label
}

fn strip_label(name: ByteArray) -> ByteArray {
  bytearray.drop(name, 4)
}

/// Revocation: every (222)X burned must have matching (100)X also burned, both qty=-1
fn revocation_pairs_valid(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  dict.to_pairs(tokens)
    |> list.all(
        fn(p) {
          let Pair(name, qty) = p
          if has_label(name, label_222) {
            qty == -1 && {
              let ref = bytearray.concat(label_100, strip_label(name))
              dict.get(tokens, ref) == Some(-1)
            }
          } else {
            True
          }
        },
      )
}

validator cip68_credential_revoke {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    !dict.is_empty(tokens) && revocation_pairs_valid(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_revoke_has_label_222() {
  has_label(#"000de140ff", label_222)
}

test prop_revoke_strip_roundtrip(suffix via fuzz.bytearray_between(1, 28)) {
  let full = bytearray.concat(label_222, suffix)
  strip_label(full) == suffix
}

test prop_revoke_pairs_valid_balanced() {
  let suffix = #"deadbeef"
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), -1)
      |> dict.insert(bytearray.concat(label_100, suffix), -1)
  revocation_pairs_valid(tokens)
}

test prop_revoke_missing_ref_fails() {
  let suffix = #"deadbeef"
  let tokens = dict.empty |> dict.insert(bytearray.concat(label_222, suffix), -1)
  !revocation_pairs_valid(tokens)
}
