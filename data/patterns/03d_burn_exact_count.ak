use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

/// Count distinct token names with negative quantity
fn count_burned_names(tokens: dict.Dict<ByteArray, Int>) -> Int {
  list.foldl(
    dict.values(tokens),
    0,
    fn(qty, acc) {
      if qty < 0 { acc + 1 } else { acc }
    },
  )
}

/// Exactly 1 distinct token name must be burned
validator burn_exact_count {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let burned_count = count_burned_names(tokens)
    // Must burn exactly 1 distinct token name
    let exactly_one_burned = burned_count == 1
    // The token dict must not be empty (something must be happening)
    let tokens_present = dict.size(tokens) > 0
    // Ensure no token is being minted (all quantities must be negative or zero)
    let no_minting =
      list.all(dict.values(tokens), fn(qty) { qty <= 0 })
    // Exactly one burned name, tokens are present, and nothing is being minted
    exactly_one_burned && tokens_present && no_minting
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_count_burned_empty_zero() {
  count_burned_names(dict.empty) == 0
}

test prop_count_burned_one(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, -2)
  count_burned_names(d) == 1
}

test prop_count_burned_positive_ignored(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 5)
  count_burned_names(d) == 0
}

test prop_count_burned_non_negative(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, -1)
  count_burned_names(d) >= 0
}