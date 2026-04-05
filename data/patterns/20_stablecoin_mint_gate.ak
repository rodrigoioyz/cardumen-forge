use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId, lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}
pub type StableDatum {
  collateral_lovelace: Int,
  stability_fee:       Int,
}

/// Maximum stablecoins mintable given collateral and stability_fee (as %)
/// e.g. stability_fee = 150 → max = collateral * 100 / 150
fn max_mintable(collateral: Int, stability_fee: Int) -> Int {
  collateral * 100 / stability_fee
}

/// Total minted quantity for a policy (sum of positive values only)
fn total_minted(tokens: dict.Dict<ByteArray, Int>) -> Int {
  list.foldl(
    dict.values(tokens),
    0,
    fn(qty, acc) {
      if qty > 0 {
        acc + qty
      } else {
        acc
      }
    },
  )
}

/// Mint is valid when: amount > 0 and amount ≤ max_mintable(collateral, fee)
fn mint_within_collateral(
  mint_amount: Int,
  collateral:  Int,
  stability_fee: Int,
) -> Bool {
  mint_amount > 0 && mint_amount <= max_mintable(collateral, stability_fee)
}

/// Collateral output to the script must carry enough lovelace
fn collateral_sufficient(
  outputs:   List<Output>,
  own_addr:  Output,
  required:  Int,
) -> Bool {
  let deposited =
    list.foldl(
      outputs,
      0,
      fn(o, acc) {
        if o.address == own_addr.address {
          acc + lovelace_of(o.value)
        } else {
          acc
        }
      },
    )
  deposited >= required
}

validator stablecoin_mint_gate {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let minted = total_minted(tokens)
    minted > 0
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_max_mintable_at_100_pct(collateral via fuzz.int_at_least(1)) {
  max_mintable(collateral, 100) == collateral
}

test prop_max_mintable_decreases_with_fee(
  vals via fuzz.both(fuzz.int_at_least(1000), fuzz.int_between(101, 200)),
) {
  let (collateral, fee) = vals
  max_mintable(collateral, fee) < max_mintable(collateral, 100)
}

test prop_mint_within_collateral_ok(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(100, 200)),
) {
  let (collateral, fee) = vals
  let max = max_mintable(collateral, fee)
  if max > 0 {
    mint_within_collateral(max, collateral, fee)
  } else {
    True
  }
}

test prop_mint_above_collateral_fails(
  vals via fuzz.both(fuzz.int_at_least(100), fuzz.int_between(100, 200)),
) {
  let (collateral, fee) = vals
  let max = max_mintable(collateral, fee)
  !mint_within_collateral(max + 1, collateral, fee)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// Minting zero is never valid regardless of collateral or fee
test prop_zero_mint_rejected(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(100, 300)),
) fail {
  let (collateral, fee) = vals
  expect mint_within_collateral(0, collateral, fee)
}

// Minting a negative amount must always be rejected
test prop_negative_mint_rejected(
  vals via fuzz.both(fuzz.int_between(-10000, -1), fuzz.int_between(100, 300)),
) fail {
  let (mint_amount, fee) = vals
  expect mint_within_collateral(mint_amount, 1000, fee)
}

// When collateral is 0, max_mintable is 0, so any positive mint is rejected
test prop_zero_collateral_mint_rejected(
  vals via fuzz.both(fuzz.int_between(1, 10000), fuzz.int_between(100, 300)),
) fail {
  let (mint_amount, fee) = vals
  expect mint_within_collateral(mint_amount, 0, fee)
}

// With a very high stability fee, even large collateral yields max_mintable=0,
// so any positive mint must be rejected.
// collateral=1, fee=10000 → max = 1*100/10000 = 0 (integer division)
test prop_high_fee_blocks_mint(
  mint_amount via fuzz.int_between(1, 5000),
) fail {
  expect mint_within_collateral(mint_amount, 1, 10000)
}

// Minting more than collateral allows when fee is exactly 200 (50% LTV):
// max_mintable(collateral, 200) = collateral/2, so minting collateral is always too much
// for any collateral >= 2 (since collateral > collateral/2 when collateral >= 2)
test prop_over_ltv_mint_rejected(
  collateral via fuzz.int_between(2, 100000),
) fail {
  // fee=200 → max = collateral*100/200 = collateral/2
  // minting collateral itself always exceeds collateral/2 for collateral >= 2
  expect mint_within_collateral(collateral, collateral, 200)
}

// Minting one unit more than max_mintable is always rejected for any valid collateral/fee
test prop_one_over_max_rejected(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(101, 500)),
) fail {
  let (collateral, fee) = vals
  let over = max_mintable(collateral, fee) + 1
  expect mint_within_collateral(over, collateral, fee)
}