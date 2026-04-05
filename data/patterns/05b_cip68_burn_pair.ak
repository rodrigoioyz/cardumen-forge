
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}
const label_222: ByteArray = #"000de140"
const label_100: ByteArray = #"000643b0"

fn has_cip68_label(name: ByteArray, label: ByteArray) -> Bool {
  bytearray.length(name) >= 4 && bytearray.take(name, 4) == label
}

fn base_name(name: ByteArray) -> ByteArray {
  bytearray.drop(name, 4)
}

/// For every (222) token burned, the matching (100) reference must also be burned
fn burn_pairs_balanced(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  list.all(
    dict.to_pairs(tokens),
    fn(p) {
      let Pair(name, qty) = p
      if has_cip68_label(name, label_222) {
        qty < 0 && {
          let ref_name = bytearray.concat(label_100, base_name(name))
          dict.get(tokens, ref_name) == Some(qty)
        }
      } else {
        True
      }
    },
  )
}

validator cip68_burn_pair {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    // Must have at least one token being minted/burned
    let token_pairs = dict.to_pairs(tokens)
    let has_tokens = !list.is_empty(token_pairs)
    // All burned tokens must be negative quantities
    let all_burned =
      list.all(
        token_pairs,
        fn(p) {
          let Pair(_, qty) = p
          qty < 0
        },
      )
    // Every (222) user token burn must be paired with a (100) reference burn
    let pairs_balanced = burn_pairs_balanced(tokens)
    // At least one (222) token must be present among the burned tokens
    let has_user_token =
      list.any(
        token_pairs,
        fn(p) {
          let Pair(name, _) = p
          has_cip68_label(name, label_222)
        },
      )
    has_tokens && all_burned && pairs_balanced && has_user_token
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_burn_pair_empty() {
  burn_pairs_balanced(dict.empty)
}

test prop_base_name_roundtrip(suffix via fuzz.bytearray_between(1, 28)) {
  let full = bytearray.concat(label_222, suffix)
  base_name(full) == suffix
}

test prop_has_label_222(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_222, suffix)
  has_cip68_label(name, label_222)
}

test prop_has_label_too_short(name via fuzz.bytearray_between(0, 3)) {
  !has_cip68_label(name, label_222)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A (222) token with a positive quantity (not a burn) must be rejected
test prop_user_token_positive_qty_rejected(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let name = bytearray.concat(label_222, suffix)
  // qty = +1 (positive), so qty < 0 is False → burn_pairs_balanced returns False
  let tokens = dict.insert(dict.empty, name, 1)
  expect burn_pairs_balanced(tokens)
}

/// A (222) token burned without its matching (100) reference must be rejected
test prop_unmatched_user_token_rejected(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let name = bytearray.concat(label_222, suffix)
  // Only the (222) token is present — no (100) counterpart → False
  let tokens = dict.insert(dict.empty, name, -1)
  expect burn_pairs_balanced(tokens)
}

/// A (222) token with a mismatched (100) quantity must be rejected
test prop_mismatched_ref_qty_rejected(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let user_name = bytearray.concat(label_222, suffix)
  let ref_name = bytearray.concat(label_100, suffix)
  // (222) qty = -1, (100) qty = -2 → Some(-2) != Some(-1) → False
  let tokens =
    dict.insert(dict.insert(dict.empty, user_name, -1), ref_name, -2)
  expect burn_pairs_balanced(tokens)
}

/// has_cip68_label must reject a name whose first 4 bytes are the wrong label
test prop_wrong_label_rejected(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  // label_100 is not label_222, so has_cip68_label with label_222 must be False
  let name = bytearray.concat(label_100, suffix)
  expect has_cip68_label(name, label_222)
}