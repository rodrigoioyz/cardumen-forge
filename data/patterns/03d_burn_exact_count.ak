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
    count_burned_names(tokens) == 1
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
