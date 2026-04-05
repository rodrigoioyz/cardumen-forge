use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}

/// Exactly one token burned: single entry with qty == -1
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
    exactly_one_burned(tokens)
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
