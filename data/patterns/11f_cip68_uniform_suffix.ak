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

fn is_cip68(name: ByteArray) -> Bool {
  has_label(name, label_222) || has_label(name, label_100)
}

/// All CIP-68 tokens must share the same suffix
fn uniform_suffix(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  let suffixes =
    dict.to_pairs(tokens)
      |> list.filter_map(
          fn(p) {
            let Pair(name, _) = p
            if is_cip68(name) {
              Some(strip_label(name))
            } else {
              None
            }
          },
        )
  when suffixes is {
    [] -> True
    [first, ..rest] -> list.all(rest, fn(s) { s == first })
  }
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

validator cip68_uniform_suffix {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    !dict.is_empty(tokens) && uniform_suffix(tokens) && credential_pairs_valid(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_uniform_suffix_empty() {
  uniform_suffix(dict.empty)
}

test prop_uniform_suffix_single(suffix via fuzz.bytearray_between(1, 28)) {
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
      |> dict.insert(bytearray.concat(label_100, suffix), 1)
  uniform_suffix(tokens)
}

test prop_strip_label_consistent(suffix via fuzz.bytearray_between(1, 28)) {
  let n222 = bytearray.concat(label_222, suffix)
  let n100 = bytearray.concat(label_100, suffix)
  strip_label(n222) == strip_label(n100)
}

test prop_has_label_both(suffix via fuzz.bytearray_between(1, 28)) {
  let n222 = bytearray.concat(label_222, suffix)
  let n100 = bytearray.concat(label_100, suffix)
  has_label(n222, label_222) && has_label(n100, label_100)
}
