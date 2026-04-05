use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

const label_222: ByteArray = #"000de140"
const label_100: ByteArray = #"000643b0"
const min_suffix_len: Int = 8

fn has_label(name: ByteArray, label: ByteArray) -> Bool {
  bytearray.length(name) >= 4 && bytearray.take(name, 4) == label
}

fn strip_label(name: ByteArray) -> ByteArray {
  bytearray.drop(name, 4)
}

/// CIP-68 token names must have a suffix of at least min_suffix_len bytes
fn suffix_long_enough(name: ByteArray) -> Bool {
  bytearray.length(strip_label(name)) >= min_suffix_len
}

fn credential_pairs_valid(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  dict.to_pairs(tokens)
    |> list.all(
        fn(p) {
          let Pair(name, qty) = p
          if has_label(name, label_222) {
            qty == 1 && suffix_long_enough(name) && {
              let ref = bytearray.concat(label_100, strip_label(name))
              dict.get(tokens, ref) == Some(1)
            }
          } else {
            True
          }
        },
      )
}

validator cip68_min_suffix {
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

test prop_min_suffix_long_ok(suffix via fuzz.bytearray_between(8, 28)) {
  let name = bytearray.concat(label_222, suffix)
  suffix_long_enough(name)
}

test prop_min_suffix_short_fails(suffix via fuzz.bytearray_between(1, 7)) {
  let name = bytearray.concat(label_222, suffix)
  !suffix_long_enough(name)
}

test prop_strip_label_length(suffix via fuzz.bytearray_between(1, 28)) {
  let full = bytearray.concat(label_222, suffix)
  bytearray.length(strip_label(full)) == bytearray.length(suffix)
}

test prop_pairs_valid_long_suffix() {
  let suffix = #"deadbeefcafebabe"
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
      |> dict.insert(bytearray.concat(label_100, suffix), 1)
  credential_pairs_valid(tokens)
}
