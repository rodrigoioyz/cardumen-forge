
/// Exactly one token burned: single entry with qty == -1
use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}
fn exactly_one_burned(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  dict.size(tokens) == 1 && {
    let pairs = dict.to_pairs(tokens)
    when pairs is {
      [Pair(_, qty)] -> qty == -1
      _ -> False
    }
  }
}

validator nft_burn_exactly_one {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let mint_size = dict.size(tokens)
    let is_burn = exactly_one_burned(tokens)
    let no_extra_minting = mint_size <= 1
    is_burn && no_extra_minting
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_exactly_one_burned_empty_false() {
  !exactly_one_burned(dict.empty)
}

test prop_exactly_one_burned_correct(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, -1)
  exactly_one_burned(d)
}

test prop_exactly_one_burned_wrong_qty(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 1)
  !exactly_one_burned(d)
}

test prop_exactly_one_burned_two_tokens(
  vals via fuzz.both(fuzz.bytearray_between(1, 8), fuzz.bytearray_between(9, 16)),
) {
  let (n1, n2) = vals
  let d =
    dict.empty
      |> dict.insert(n1, -1)
      |> dict.insert(n2, -1)
  !exactly_one_burned(d)
}

// ── Negative (fail) property tests ──────────────────────────────────────────

/// Empty dict always yields False — expect must fail
test prop_fail_empty_dict_rejected() fail {
  expect exactly_one_burned(dict.empty)
}

/// A positive quantity (minting, not burning) must always be rejected
test prop_fail_positive_qty_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_at_least(1)),
) fail {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  expect exactly_one_burned(d)
}

/// qty == 0 is neither a burn nor a mint — must always be rejected
test prop_fail_zero_qty_rejected(name via fuzz.bytearray_between(1, 32)) fail {
  let d = dict.empty |> dict.insert(name, 0)
  expect exactly_one_burned(d)
}

/// Two tokens, even both at -1, must always be rejected (size != 1)
test prop_fail_two_tokens_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 8), fuzz.bytearray_between(9, 16)),
) fail {
  let (n1, n2) = vals
  let d =
    dict.empty
      |> dict.insert(n1, -1)
      |> dict.insert(n2, -1)
  expect exactly_one_burned(d)
}