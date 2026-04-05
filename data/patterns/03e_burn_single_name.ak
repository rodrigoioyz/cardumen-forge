
/// Exactly one token name present and its quantity is negative
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}
fn single_name_burned(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  dict.size(tokens) == 1 && {
    let vals = dict.values(tokens)
    list.all(vals, fn(qty) { qty < 0 })
  }
}

validator burn_single_name {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    // Must burn exactly one token name with a negative quantity
    let valid_burn = single_name_burned(tokens)
    // Ensure there is at least one token name present (not empty)
    let has_tokens = dict.size(tokens) > 0
    // The mint field for this policy must not contain any positive quantities
    let no_minting =
      list.all(dict.values(tokens), fn(qty) { qty < 0 })
    // All three conditions must hold for a valid single-name burn
    valid_burn && has_tokens && no_minting
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_single_name_burned_empty_false() {
  !single_name_burned(dict.empty)
}

test prop_single_name_burned_correct(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_at_least(1)),
) {
  let (name, amt) = vals
  let d = dict.empty |> dict.insert(name, -amt)
  single_name_burned(d)
}

test prop_single_name_burned_positive_fails(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 1)
  !single_name_burned(d)
}

test prop_single_name_burned_zero_fails(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 0)
  !single_name_burned(d)
}

// ── Negative / fail tests ───────────────────────────────────────────────────

/// Empty dict always returns False — expect turns that into a runtime failure
test prop_fail_empty_dict_rejected() fail {
  expect single_name_burned(dict.empty)
}

/// A positive quantity is never a valid burn — single_name_burned returns False
test prop_fail_positive_qty_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_at_least(1)),
) fail {
  let (name, pos_qty) = vals
  let d = dict.empty |> dict.insert(name, pos_qty)
  expect single_name_burned(d)
}

/// A zero quantity is not a valid burn (qty < 0 is False for 0)
test prop_fail_zero_qty_rejected(name via fuzz.bytearray_between(1, 32)) fail {
  let d = dict.empty |> dict.insert(name, 0)
  expect single_name_burned(d)
}

/// Two entries in the dict violates the size == 1 requirement
test prop_fail_two_names_rejected(
  vals via fuzz.both(
    fuzz.both(fuzz.bytearray_between(1, 16), fuzz.bytearray_between(17, 32)),
    fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
  ),
) fail {
  let ((name1, name2), (qty1, qty2)) = vals
  let d =
    dict.empty
      |> dict.insert(name1, -qty1)
      |> dict.insert(name2, -qty2)
  expect single_name_burned(d)
}