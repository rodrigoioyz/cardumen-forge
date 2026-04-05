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
