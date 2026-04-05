
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
    // Must mint at least one token
    let non_empty = !dict.is_empty(tokens)
    // Every 222-labelled user token must have a matching 100-labelled reference token
    let pairs_ok = credential_pairs_valid(tokens)
    // Every token name must carry either the user label or the reference label
    let all_labelled =
      dict.to_pairs(tokens)
        |> list.all(
            fn(p) {
              let Pair(name, _) = p
              has_label(name, label_222) || has_label(name, label_100)
            },
          )
    // Every reference token name must be non-empty after stripping the label
    let suffixes_nonempty =
      dict.to_pairs(tokens)
        |> list.all(
            fn(p) {
              let Pair(name, _) = p
              bytearray.length(strip_label(name)) > 0
            },
          )
    non_empty && pairs_ok && all_labelled && suffixes_nonempty
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// has_label must return False for any name shorter than 4 bytes,
/// regardless of what label we compare against.
test prop_has_label_rejects_short_name(
  name via fuzz.bytearray_between(0, 3),
) fail {
  expect has_label(name, label_222)
}

/// has_label must return False when the first 4 bytes do NOT match label_222.
/// We use label_100 as the name prefix, which is guaranteed ≠ label_222.
test prop_has_label_rejects_wrong_label(
  suffix via fuzz.bytearray_between(0, 28),
) fail {
  let name = bytearray.concat(label_100, suffix)
  expect has_label(name, label_222)
}

/// credential_pairs_valid must return False when a 222-token exists
/// but its paired 100-token is absent from the dict.
test prop_pairs_invalid_user_token_without_ref(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 1)
  expect credential_pairs_valid(tokens)
}

/// credential_pairs_valid must return False when the 222-token has qty ≠ 1,
/// even if the matching 100-token is present with qty = 1.
test prop_pairs_invalid_bad_qty() fail {
  let suffix = #"cafebabe"
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 2)
      |> dict.insert(bytearray.concat(label_100, suffix), 1)
  expect credential_pairs_valid(tokens)
}