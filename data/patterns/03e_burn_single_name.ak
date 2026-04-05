use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

/// Exactly one token name present and its quantity is negative
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
    single_name_burned(tokens)
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
