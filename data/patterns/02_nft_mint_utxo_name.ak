
/// Exactly one token minted under the policy
use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}
fn exactly_one_token(
  tokens: dict.Dict<ByteArray, Int>,
) -> Bool {
  dict.size(tokens) == 1 && {
    let pairs = dict.to_pairs(tokens)
    when pairs is {
      [Pair(_, qty)] -> qty == 1
      _ -> False
    }
  }
}

validator nft_mint {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let one_token = exactly_one_token(tokens)
    let pairs = dict.to_pairs(tokens)
    let valid_name =
      when pairs is {
        [Pair(name, _)] -> dict.size(dict.empty |> dict.insert(name, 1)) == 1
        _ -> False
      }
    one_token && valid_name
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_exactly_one_token_empty_is_false() {
  !exactly_one_token(dict.empty)
}

test prop_exactly_one_token_two_is_false(
  vals via fuzz.both(fuzz.bytearray_between(1, 10), fuzz.bytearray_between(1, 10)),
) {
  let (n1, n2) = vals
  if n1 == n2 {
    True
  } else {
    let d =
      dict.empty
        |> dict.insert(n1, 1)
        |> dict.insert(n2, 1)
    !exactly_one_token(d)
  }
}

test prop_exactly_one_token_single_correct(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 1)
  exactly_one_token(d)
}

test prop_exactly_one_token_single_wrong_qty(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 2)
  !exactly_one_token(d)
}

// ── Fail tests ───────────────────────────────────────────────────────────────

/// Empty dict always returns False — expect must fail
test prop_fail_empty_dict_rejected() fail {
  expect exactly_one_token(dict.empty)
}

/// A single token with quantity 0 is always rejected
test prop_fail_zero_qty_rejected(name via fuzz.bytearray_between(1, 32)) fail {
  let d = dict.empty |> dict.insert(name, 0)
  expect exactly_one_token(d)
}

/// A single token with quantity >= 2 is always rejected
test prop_fail_qty_above_one_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_between(2, 1000)),
) fail {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  expect exactly_one_token(d)
}

/// A single token with negative quantity is always rejected
test prop_fail_negative_qty_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_between(-1000, -1)),
) fail {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  expect exactly_one_token(d)
}