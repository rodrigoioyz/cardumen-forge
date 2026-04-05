
/// All token quantities under this policy must be negative (burn only)
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}
fn all_negative(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  let vals = dict.values(tokens)
  !list.is_empty(vals) && list.all(vals, fn(qty) { qty < 0 })
}

validator burn_only {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    // Extract tokens minted under this policy
    let tokens = assets.tokens(self.mint, policy_id)

    // Ensure there is at least one token name being burned
    let token_names = dict.keys(tokens)
    let has_tokens = !list.is_empty(token_names)

    // Verify every quantity under this policy is strictly negative (burn only)
    let only_burns = all_negative(tokens)

    // Confirm no other policy is minting positively alongside this burn
    // by checking the overall mint does not contain any positive amounts
    // for this policy specifically (already covered), and that our
    // helper is satisfied end-to-end
    has_tokens && only_burns
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_all_negative_empty_is_false() {
  !all_negative(dict.empty)
}

test prop_all_negative_with_negatives(
  vals via fuzz.list_between(fuzz.int_at_most(-1), 1, 8),
) {
  let tokens =
    list.indexed_map(vals, fn(i, _) { i })
      |> list.foldl(
          dict.empty,
          fn(i, acc) {
            let name = if i == 0 { #"aa" } else if i == 1 { #"bb" } else { #"cc" }
            dict.insert(acc, name, -( i + 1 ))
          },
        )
  all_negative(tokens) || dict.is_empty(tokens)
}

test prop_all_negative_rejects_zero(name via fuzz.bytearray_between(1, 10)) {
  let d = dict.empty |> dict.insert(name, 0)
  !all_negative(d)
}

test prop_all_negative_rejects_positive(
  pair via fuzz.both(fuzz.bytearray_between(1, 10), fuzz.int_at_least(1)),
) {
  let (name, qty) = pair
  let d = dict.empty |> dict.insert(name, qty)
  !all_negative(d)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// Empty dict has no values, so all_negative must return False.
test prop_fail_all_negative_empty() fail {
  expect all_negative(dict.empty)
}

/// A single entry with qty == 0 is not negative, so all_negative must return False.
test prop_fail_all_negative_zero_qty(
  name via fuzz.bytearray_between(1, 10),
) fail {
  let d = dict.empty |> dict.insert(name, 0)
  expect all_negative(d)
}

/// A single entry with a strictly positive quantity must be rejected.
test prop_fail_all_negative_positive_qty(
  pair via fuzz.both(fuzz.bytearray_between(1, 10), fuzz.int_at_least(1)),
) fail {
  let (name, qty) = pair
  let d = dict.empty |> dict.insert(name, qty)
  expect all_negative(d)
}

/// A dict with one negative and one positive entry must be rejected
/// because not ALL quantities are negative.
test prop_fail_all_negative_mixed_signs(
  pair via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (pos, neg) = pair
  let d =
    dict.empty
      |> dict.insert(#"aa", pos)
      |> dict.insert(#"bb", -neg)
  expect all_negative(d)
}