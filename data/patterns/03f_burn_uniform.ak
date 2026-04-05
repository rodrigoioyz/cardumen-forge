
/// All burned tokens must have the same quantity (uniform burn)
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}
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
    // Extract all tokens under this policy from the mint field
    let tokens = assets.tokens(self.mint, policy_id)

    // Must be burning at least one token name
    let token_count = dict.size(tokens)
    let has_tokens = token_count > 0

    // All burned tokens must share the same (negative) quantity
    let uniform_burn = all_same_negative_qty(tokens)

    // No outputs may contain tokens under this policy (strict burn)
    let no_outputs_hold_policy =
      list.all(
        self.outputs,
        fn(output) {
          let out_tokens = assets.tokens(output.value, policy_id)
          dict.size(out_tokens) == 0
        },
      )

    has_tokens && uniform_burn && no_outputs_hold_policy
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Empty dict always returns False — expect must fail
test prop_fail_empty_dict() fail {
  expect all_same_negative_qty(dict.empty)
}

/// A single positive quantity is never a valid burn — expect must fail
test prop_fail_single_positive_qty(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_at_least(1)),
) fail {
  let (name, pos_amt) = vals
  let d = dict.empty |> dict.insert(name, pos_amt)
  expect all_same_negative_qty(d)
}

/// A single zero quantity is never a valid burn — expect must fail
test prop_fail_single_zero_qty(name via fuzz.bytearray_between(1, 16)) fail {
  let d = dict.empty |> dict.insert(name, 0)
  expect all_same_negative_qty(d)
}

/// Two tokens with different negative quantities violate uniformity — expect must fail
test prop_fail_nonuniform_negative_qtys(
  vals via fuzz.both(
    fuzz.both(fuzz.bytearray_between(1, 8), fuzz.bytearray_between(9, 16)),
    fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 500)),
  ),
) fail {
  let ((name1, name2), (amt1, amt2)) = vals
  let d =
    dict.empty
      |> dict.insert(name1, -amt1)
      |> dict.insert(name2, -amt2)
  expect all_same_negative_qty(d)
}