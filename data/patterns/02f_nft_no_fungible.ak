use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}

/// No single token name may have quantity > 1 (prevents fungible issuance)
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
    no_fungible(tokens)
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
