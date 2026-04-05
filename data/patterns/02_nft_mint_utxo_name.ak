use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}

/// Exactly one token minted under the policy
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
    exactly_one_token(tokens)
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
