use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{OutputReference, Transaction}

/// Sum all quantities minted under a policy (positive only)
fn total_minted(tokens: dict.Dict<ByteArray, Int>) -> Int {
  list.foldl(
    dict.to_pairs(tokens),
    0,
    fn(p, acc) {
      let Pair(_, qty) = p
      if qty > 0 {
        acc + qty
      } else {
        acc
      }
    },
  )
}

/// At most `max_supply` tokens may be minted in a single transaction
validator nft_max_supply {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let max_supply = 100
    let tokens     = assets.tokens(self.mint, policy_id)
    total_minted(tokens) <= max_supply
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_total_minted_empty() {
  total_minted(dict.empty) == 0
}

test prop_total_minted_ignores_negatives(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, -5)
  total_minted(d) == 0
}

test prop_total_minted_sums_positives(
  vals via fuzz.both(fuzz.bytearray_between(1, 8), fuzz.int_between(1, 50)),
) {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  total_minted(d) == qty
}

test prop_total_minted_non_negative(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, 0)
  total_minted(d) >= 0
}
