
/// No single token name may have quantity > 1 (prevents fungible issuance)
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}
fn no_fungible(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  !dict.is_empty(tokens) && list.all(
    dict.to_pairs(tokens),
    fn(p) {
      let Pair(_, qty) = p
      qty == 1 || qty == -1
    },
  )
}

validator nft_no_fungible {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let all_nft = no_fungible(tokens)
    let token_count = dict.size(tokens)
    let has_at_least_one = token_count >= 1
    let pairs = dict.to_pairs(tokens)
    let no_zero_qty =
      list.all(
        pairs,
        fn(p) {
          let Pair(_, qty) = p
          qty != 0
        },
      )
    all_nft && has_at_least_one && no_zero_qty
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_no_fungible_empty_false() {
  !no_fungible(dict.empty)
}

test prop_no_fungible_qty_one(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 1)
  no_fungible(d)
}

test prop_no_fungible_qty_minus_one(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, -1)
  no_fungible(d)
}

test prop_no_fungible_qty_two_fails(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(2, 50)),
) {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  !no_fungible(d)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// Empty dict must always be rejected by no_fungible
test prop_no_fungible_rejects_empty_dict() fail {
  expect no_fungible(dict.empty)
}

/// Any quantity >= 2 is fungible and must be rejected
test prop_no_fungible_rejects_fungible_qty(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_between(2, 1000)),
) fail {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  expect no_fungible(d)
}

/// Any quantity <= -2 is an over-burn and must be rejected
test prop_no_fungible_rejects_negative_fungible_qty(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_between(-1000, -2)),
) fail {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  expect no_fungible(d)
}

/// Zero quantity must always be rejected
test prop_no_fungible_rejects_zero_qty(
  name via fuzz.bytearray_between(1, 32),
) fail {
  let d = dict.empty |> dict.insert(name, 0)
  expect no_fungible(d)
}