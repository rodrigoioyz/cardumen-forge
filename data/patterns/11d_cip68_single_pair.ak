
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
    let num_222 = count_222(tokens)
    let total_tokens = dict.size(tokens)
    // Must mint exactly one (222) user token
    let exactly_one_user = num_222 == 1
    // Must have a matching (100) reference token, so exactly 2 tokens total
    let exactly_two_total = total_tokens == 2
    // All (222) tokens must have a corresponding (100) token with qty 1
    let pairs_are_valid = credential_pairs_valid(tokens)
    // All conditions must hold
    exactly_one_user && exactly_two_total && pairs_are_valid
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

// ── Negative / fail tests ────────────────────────────────────────────────────

// A (222) token with no matching (100) reference token must be rejected.
test prop_pairs_invalid_missing_ref(suffix via fuzz.bytearray_between(1, 28)) fail {
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
  expect credential_pairs_valid(tokens)
}

// A (222) token with qty != 1 must be rejected (qty 0 used here).
test prop_pairs_invalid_zero_qty(suffix via fuzz.bytearray_between(1, 28)) fail {
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 0)
      |> dict.insert(bytearray.concat(label_100, suffix), 1)
  expect credential_pairs_valid(tokens)
}

// A (222) token paired with a (100) whose qty is not 1 must be rejected.
test prop_pairs_invalid_ref_qty_not_one(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 28),
    fuzz.int_between(2, 100),
  ),
) fail {
  let (suffix, bad_qty) = vals
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
      |> dict.insert(bytearray.concat(label_100, suffix), bad_qty)
  expect credential_pairs_valid(tokens)
}

// An empty dict has no (222) tokens, so count_222 == 0 != 1.
// Wrapping the equality check forces a fail when the dict is empty.
test prop_count_222_empty_is_not_one() fail {
  expect count_222(dict.empty) == 1
}