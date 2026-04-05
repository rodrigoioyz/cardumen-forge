use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

/// All burned tokens must have the same quantity (uniform burn)
fn all_same_negative_qty(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  let vals = dict.values(tokens)
  when vals is {
    [] -> False
    [first, ..rest] ->
      first < 0 && list.all(rest, fn(qty) { qty == first })
  }
}

validator burn_uniform {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    all_same_negative_qty(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_all_same_empty_false() {
  !all_same_negative_qty(dict.empty)
}

test prop_all_same_single_negative(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_at_least(1)),
) {
  let (name, amt) = vals
  let d = dict.empty |> dict.insert(name, -amt)
  all_same_negative_qty(d)
}

test prop_all_same_positive_fails(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, 3)
  !all_same_negative_qty(d)
}

test prop_all_same_zero_fails(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, 0)
  !all_same_negative_qty(d)
}
