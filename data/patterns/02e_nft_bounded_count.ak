use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}

/// Count tokens minted (qty > 0) in this policy
fn count_minted(tokens: dict.Dict<ByteArray, Int>) -> Int {
  list.foldl(
    dict.to_pairs(tokens),
    0,
    fn(p, acc) {
      let Pair(_, qty) = p
      if qty > 0 { acc + 1 } else { acc }
    },
  )
}

/// Between 1 and 10 distinct NFTs may be minted per transaction
validator nft_bounded_count {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let n      = count_minted(tokens)
    n >= 1 && n <= 10
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_count_minted_empty_zero() {
  count_minted(dict.empty) == 0
}

test prop_count_minted_one(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 1)
  count_minted(d) == 1
}

test prop_count_minted_ignores_burns(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, -3)
  count_minted(d) == 0
}

test prop_count_minted_non_negative(name via fuzz.bytearray_between(1, 32)) {
  let d = dict.empty |> dict.insert(name, 5)
  count_minted(d) >= 1
}
