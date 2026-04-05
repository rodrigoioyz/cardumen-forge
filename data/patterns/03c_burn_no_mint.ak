
/// No positive quantities (no minting) and at least one token present
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}
fn no_mint_only_burn(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  let vals = dict.values(tokens)
  !list.is_empty(vals) && list.all(vals, fn(qty) { qty <= 0 })
}

validator burn_no_mint {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let all_burn = no_mint_only_burn(tokens)
    let token_names = dict.keys(tokens)
    let has_tokens = !list.is_empty(token_names)
    let all_negative =
      list.all(dict.values(tokens), fn(qty) { qty < 0 })
    let no_zero_burn =
      !list.any(dict.values(tokens), fn(qty) { qty == 0 })
    all_burn && has_tokens && all_negative && no_zero_burn
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_no_mint_empty_false() {
  !no_mint_only_burn(dict.empty)
}

test prop_no_mint_negative_ok(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, -1)
  no_mint_only_burn(d)
}

test prop_no_mint_zero_ok(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, 0)
  no_mint_only_burn(d)
}

test prop_no_mint_positive_fails(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_at_least(1)),
) {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  !no_mint_only_burn(d)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// Empty dict always returns False — no tokens present
test prop_fail_empty_dict_rejects() fail {
  expect no_mint_only_burn(dict.empty)
}

/// A positive quantity (minting) must always be rejected
test prop_fail_positive_qty_rejects(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_at_least(1)),
) fail {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  expect no_mint_only_burn(d)
}

/// A mix of negative and positive quantities must be rejected
test prop_fail_mixed_qty_rejects(
  names via fuzz.both(
    fuzz.bytearray_between(1, 8),
    fuzz.bytearray_between(9, 16),
  ),
) fail {
  let (name1, name2) = names
  // name1 gets a burn (negative), name2 gets a mint (positive)
  // if name1 == name2 the dict collapses to one entry with qty=1, still positive → False
  let d =
    dict.empty
      |> dict.insert(name1, -1)
      |> dict.insert(name2, 1)
  expect no_mint_only_burn(d)
}

/// Large positive quantities are also rejected
test prop_fail_large_positive_rejects(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1000, 1000000)),
) fail {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  expect no_mint_only_burn(d)
}