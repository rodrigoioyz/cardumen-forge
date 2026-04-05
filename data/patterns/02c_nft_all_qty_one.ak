use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}

/// Every token under this policy must have quantity exactly 1 (true NFTs)
fn all_qty_one(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  !dict.is_empty(tokens) && list.all(
    dict.to_pairs(tokens),
    fn(p) {
      let Pair(_, qty) = p
      qty == 1
    },
  )
}

validator nft_all_qty_one {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    all_qty_one(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_all_qty_one_empty_false() {
  !all_qty_one(dict.empty)
}

test prop_all_qty_one_single_true(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 1)
  all_qty_one(d)
}

test prop_all_qty_one_wrong_qty_false(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(2, 100)),
) {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  !all_qty_one(d)
}

test prop_all_qty_one_negative_false(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, -1)
  !all_qty_one(d)
}
