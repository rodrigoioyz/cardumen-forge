use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

/// Sum of absolute values of all negative quantities
fn total_burned(tokens: dict.Dict<ByteArray, Int>) -> Int {
  list.foldl(
    dict.values(tokens),
    0,
    fn(qty, acc) {
      if qty < 0 {
        acc + -qty
      } else {
        acc
      }
    },
  )
}

/// At least `min_burn` tokens must be burned in this transaction
validator burn_at_least {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let min_burn = 1
    let tokens   = assets.tokens(self.mint, policy_id)
    total_burned(tokens) >= min_burn
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_total_burned_empty_zero() {
  total_burned(dict.empty) == 0
}

test prop_total_burned_positive_ignored(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, 5)
  total_burned(d) == 0
}

test prop_total_burned_counts_negative(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_at_least(1)),
) {
  let (name, amt) = vals
  let d = dict.empty |> dict.insert(name, -amt)
  total_burned(d) == amt
}

test prop_total_burned_non_negative(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, -3)
  total_burned(d) >= 0
}
