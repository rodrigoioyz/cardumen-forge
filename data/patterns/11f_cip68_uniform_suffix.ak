
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
    let has_tokens = !dict.is_empty(tokens)
    let all_cip68 =
      dict.to_pairs(tokens)
        |> list.all(
            fn(p) {
              let Pair(name, _) = p
              is_cip68(name)
            },
          )
    let suffix_ok = uniform_suffix(tokens)
    let pairs_ok = credential_pairs_valid(tokens)
    has_tokens && all_cip68 && suffix_ok && pairs_ok
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Two CIP-68 tokens with DIFFERENT suffixes must fail uniform_suffix.
/// suffix_a and suffix_b are drawn from disjoint byte ranges so they are
/// guaranteed to differ (suffix_a ends with 0x00, suffix_b ends with 0xff).
test prop_non_uniform_suffixes_rejected(
  suffixes via fuzz.both(
    fuzz.bytearray_between(1, 14),
    fuzz.bytearray_between(1, 14),
  ),
) fail {
  let (base_a, base_b) = suffixes
  // Force the suffixes to be distinct by appending different sentinel bytes
  let suffix_a = bytearray.concat(base_a, #"00")
  let suffix_b = bytearray.concat(base_b, #"ff")
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix_a), 1)
      |> dict.insert(bytearray.concat(label_222, suffix_b), 1)
  expect uniform_suffix(tokens)
}

/// A label_222 token whose matching label_100 reference token is ABSENT
/// must fail credential_pairs_valid.
test prop_missing_ref_token_rejected(suffix via fuzz.bytearray_between(1, 28)) fail {
  // Only the user token (222) is present; the reference token (100) is missing.
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
  expect credential_pairs_valid(tokens)
}

/// A label_222 token minted with quantity != 1 must fail credential_pairs_valid.
/// We use quantities in [2, 1_000_000] to guarantee they are never 1.
test prop_wrong_qty_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 28), fuzz.int_between(2, 1_000_000)),
) fail {
  let (suffix, qty) = vals
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), qty)
      |> dict.insert(bytearray.concat(label_100, suffix), 1)
  expect credential_pairs_valid(tokens)
}

/// has_label must return False when the name is shorter than 4 bytes.
test prop_short_name_has_label_rejected(
  name via fuzz.bytearray_between(0, 3),
) fail {
  expect has_label(name, label_222)
}