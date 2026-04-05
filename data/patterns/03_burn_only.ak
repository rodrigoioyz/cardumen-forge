use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

/// All token quantities under this policy must be negative (burn only)
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
    let tokens = assets.tokens(self.mint, policy_id)
    all_negative(tokens)
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
