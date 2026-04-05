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

/// Count how many (222) tokens are in the dict
fn count_222(tokens: dict.Dict<ByteArray, Int>) -> Int {
  dict.to_pairs(tokens)
    |> list.foldl(
        0,
        fn(p, acc) {
          let Pair(name, _) = p
          if has_label(name, label_222) {
            acc + 1
          } else {
            acc
          }
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

/// Exactly one (222)/(100) pair may be minted per transaction
validator cip68_single_pair {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    count_222(tokens) == 1 && credential_pairs_valid(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_count_222_empty() {
  count_222(dict.empty) == 0
}

test prop_count_222_one(suffix via fuzz.bytearray_between(1, 28)) {
  let tokens = dict.empty |> dict.insert(bytearray.concat(label_222, suffix), 1)
  count_222(tokens) == 1
}

test prop_count_222_only_100_zero(suffix via fuzz.bytearray_between(1, 28)) {
  let tokens = dict.empty |> dict.insert(bytearray.concat(label_100, suffix), 1)
  count_222(tokens) == 0
}

test prop_pairs_valid_single() {
  let suffix = #"deadbeef"
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
      |> dict.insert(bytearray.concat(label_100, suffix), 1)
  count_222(tokens) == 1 && credential_pairs_valid(tokens)
}
