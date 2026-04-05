
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
    // Must burn at least one token
    let tokens_non_empty = !dict.is_empty(tokens)
    // Every (222) token burned must have a matching (100) reference token burned
    let pairs_valid = revocation_pairs_valid(tokens)
    // Every token in this policy must carry a known CIP-68 label (222 or 100)
    let all_labeled =
      dict.to_pairs(tokens)
        |> list.all(
            fn(p) {
              let Pair(name, _) = p
              has_label(name, label_222) || has_label(name, label_100)
            },
          )
    // There must be at least one (222) user token being burned
    let has_user_token =
      dict.to_pairs(tokens)
        |> list.any(fn(p) { has_label(p.1st, label_222) })
    tokens_non_empty && pairs_valid && all_labeled && has_user_token
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A (222) token with qty != -1 (e.g. +1 mint instead of burn) must be rejected
/// even when the matching (100) reference token is present with qty=-1.
test prop_222_wrong_qty_rejected(
  qty via fuzz.int_between(0, 100),
) fail {
  let suffix = #"cafebabe"
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), qty)
      |> dict.insert(bytearray.concat(label_100, suffix), -1)
  expect revocation_pairs_valid(tokens)
}

/// A (222) token whose matching (100) reference has a wrong qty (not -1) must fail.
test prop_100_wrong_qty_rejected(
  ref_qty via fuzz.int_between(0, 100),
) fail {
  let suffix = #"0badcafe"
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), -1)
      |> dict.insert(bytearray.concat(label_100, suffix), ref_qty)
  expect revocation_pairs_valid(tokens)
}

/// has_label must reject any bytearray shorter than 4 bytes.
test prop_has_label_too_short_rejected(
  name via fuzz.bytearray_between(0, 3),
) fail {
  expect has_label(name, label_222)
}

/// A (222) token with no (100) counterpart at all must be rejected,
/// regardless of the suffix used.
test prop_222_no_ref_token_rejected(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), -1)
  expect revocation_pairs_valid(tokens)
}