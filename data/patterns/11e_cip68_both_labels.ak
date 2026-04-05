
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
    let any_222 = has_any_222(tokens)
    let any_100 = has_any_100(tokens)
    let pairs_valid = credential_pairs_valid(tokens)
    let non_empty = dict.size(tokens) > 0
    non_empty && any_222 && any_100 && pairs_valid
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// has_any_222 must reject a dict that only has a (100) token — no (222) present
test prop_no_222_in_100_only_dict(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let tokens =
    dict.empty |> dict.insert(bytearray.concat(label_100, suffix), 1)
  expect has_any_222(tokens)
}

/// has_any_100 must reject a dict that only has a (222) token — no (100) present
test prop_no_100_in_222_only_dict(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let tokens =
    dict.empty |> dict.insert(bytearray.concat(label_222, suffix), 1)
  expect has_any_100(tokens)
}

/// credential_pairs_valid must reject a (222) token whose matching (100) is absent
test prop_unbalanced_pair_invalid(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  // Only the (222) token is inserted; no corresponding (100) counterpart exists
  let tokens =
    dict.empty |> dict.insert(bytearray.concat(label_222, suffix), 1)
  expect credential_pairs_valid(tokens)
}

/// credential_pairs_valid must reject a (222) token with quantity != 1
test prop_wrong_qty_pair_invalid() fail {
  let suffix = #"cafebabe"
  // qty=2 for the (222) token and a matching (100) token with qty=1;
  // the qty==1 check on the (222) side must fail
  let tokens =
    dict.empty
      |> dict.insert(bytearray.concat(label_222, suffix), 2)
      |> dict.insert(bytearray.concat(label_100, suffix), 1)
  expect credential_pairs_valid(tokens)
}