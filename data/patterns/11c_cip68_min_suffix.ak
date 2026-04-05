
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
    // Must mint at least one token
    let non_empty = !dict.is_empty(tokens)
    // Every 222-labelled token must have a suffix of at least min_suffix_len bytes
    // and a matching 100-labelled reference token also minted in this tx
    let pairs_ok = credential_pairs_valid(tokens)
    // Every token name in this policy must carry either label_222 or label_100
    let all_labelled =
      dict.to_pairs(tokens)
        |> list.all(
            fn(p) {
              let Pair(name, _qty) = p
              has_label(name, label_222) || has_label(name, label_100)
            },
          )
    // All 100-labelled (reference) tokens must themselves have a long-enough suffix
    let ref_suffixes_ok =
      dict.to_pairs(tokens)
        |> list.all(
            fn(p) {
              let Pair(name, _qty) = p
              if has_label(name, label_100) {
                suffix_long_enough(name)
              } else {
                True
              }
            },
          )
    non_empty && pairs_ok && all_labelled && ref_suffixes_ok
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

// ── Negative / fail tests ────────────────────────────────────────────────────

// A 222-labelled name with a suffix shorter than min_suffix_len (0–7 bytes)
// must always be rejected by suffix_long_enough.
test prop_short_suffix_rejected(
  suffix via fuzz.bytearray_between(0, 7),
) fail {
  let name = bytearray.concat(label_222, suffix)
  expect suffix_long_enough(name)
}

// A 222-labelled token with a short suffix must cause credential_pairs_valid
// to return False, because suffix_long_enough fails for that token.
test prop_pairs_invalid_short_suffix(
  suffix via fuzz.bytearray_between(0, 7),
) fail {
  let name_222 = bytearray.concat(label_222, suffix)
  let name_100 = bytearray.concat(label_100, suffix)
  let tokens =
    dict.empty
      |> dict.insert(name_222, 1)
      |> dict.insert(name_100, 1)
  expect credential_pairs_valid(tokens)
}

// A 222-labelled token whose matching 100-labelled reference token is absent
// must cause credential_pairs_valid to return False regardless of suffix length.
test prop_pairs_invalid_missing_ref() fail {
  let suffix = #"deadbeefcafebabe"
  // Only the 222 token is present; the required 100 reference is missing.
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
  expect credential_pairs_valid(tokens)
}

// A name whose total length is less than 4 bytes cannot carry any valid label,
// so has_label must always return False.
test prop_has_label_too_short(
  name via fuzz.bytearray_between(0, 3),
) fail {
  expect has_label(name, label_222)
}