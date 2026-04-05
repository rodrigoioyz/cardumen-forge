
/// Every token under this policy must have quantity exactly 1 (true NFTs)
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}
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
    let minted_names = dict.keys(tokens)
    let names_non_empty = !list.is_empty(minted_names)
    let all_unique_names =
      list.length(minted_names) == list.length(list.unique(minted_names))
    let all_exactly_one = all_qty_one(tokens)
    names_non_empty && all_unique_names && all_exactly_one
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

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// Empty dict always causes all_qty_one to return False
test prop_fail_empty_dict_rejected() fail {
  expect all_qty_one(dict.empty)
}

/// A token with quantity > 1 is never a valid NFT
test prop_fail_qty_greater_than_one(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(2, 1000)),
) fail {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  expect all_qty_one(d)
}

/// A token with negative quantity is never a valid NFT
test prop_fail_negative_qty(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(-1000, -1)),
) fail {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  expect all_qty_one(d)
}

/// A token with quantity zero is never a valid NFT
test prop_fail_zero_qty(name via fuzz.bytearray_between(1, 16)) fail {
  let d = dict.empty |> dict.insert(name, 0)
  expect all_qty_one(d)
}