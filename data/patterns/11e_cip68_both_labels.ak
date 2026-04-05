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

/// At least one (222) token is present
fn has_any_222(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  dict.to_pairs(tokens)
    |> list.any(
        fn(p) {
          let Pair(name, _) = p
          has_label(name, label_222)
        },
      )
}

/// At least one (100) token is present
fn has_any_100(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  dict.to_pairs(tokens)
    |> list.any(
        fn(p) {
          let Pair(name, _) = p
          has_label(name, label_100)
        },
      )
}

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

/// Both labels must be present and all pairs must be balanced
validator cip68_both_labels {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    has_any_222(tokens) && has_any_100(tokens) && credential_pairs_valid(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_has_222_detected(suffix via fuzz.bytearray_between(1, 28)) {
  let tokens = dict.empty |> dict.insert(bytearray.concat(label_222, suffix), 1)
  has_any_222(tokens)
}

test prop_has_100_detected(suffix via fuzz.bytearray_between(1, 28)) {
  let tokens = dict.empty |> dict.insert(bytearray.concat(label_100, suffix), 1)
  has_any_100(tokens)
}

test prop_has_222_empty_false() {
  !has_any_222(dict.empty)
}

test prop_both_labels_balanced() {
  let suffix = #"deadbeef"
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
      |> dict.insert(bytearray.concat(label_100, suffix), 1)
  has_any_222(tokens) && has_any_100(tokens) && credential_pairs_valid(tokens)
}
