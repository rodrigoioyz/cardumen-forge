
/// Burning stablecoin is only valid when collateral is being proportionally returned
/// collateral_returned >= burn_amount * stability_fee / 100
use aiken/fuzz
use cardano/assets
use cardano/transaction.{Transaction}
fn burn_returns_collateral(
  burn_amount:         Int,
  collateral_returned: Int,
  stability_fee:       Int,
) -> Bool {
  burn_amount > 0
    && collateral_returned >= burn_amount * stability_fee / 100
}

/// Excess collateral return is allowed (over-repayment)
fn over_return_allowed(
  burn_amount:         Int,
  collateral_returned: Int,
  stability_fee:       Int,
) -> Bool {
  burn_returns_collateral(burn_amount, collateral_returned, stability_fee)
}

// ── Validator ────────────────────────────────────────────────────────────────

pub type BurnRedeemer {
  collateral_returned: Int,
  stability_fee: Int,
}

validator stable_burn_gate(stablecoin_policy: ByteArray) {
  mint(redeemer: BurnRedeemer, policy_id: ByteArray, self: Transaction) {
    let burn_amount =
      assets.reduce(
        self.mint,
        0,
        fn(pid, _name, qty, acc) {
          if pid == policy_id {
            acc + qty
          } else {
            acc
          }
        },
      )
    let actual_burn = -burn_amount
    expect stablecoin_policy == policy_id
    over_return_allowed(
      actual_burn,
      redeemer.collateral_returned,
      redeemer.stability_fee,
    )
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_exact_return_valid(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(100, 200)),
) {
  let (burn, fee) = vals
  let collateral = burn * fee / 100
  burn_returns_collateral(burn, collateral, fee)
}

test prop_over_return_valid(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(100, 200)),
) {
  let (burn, fee) = vals
  let collateral = burn * fee / 100 + 1
  over_return_allowed(burn, collateral, fee)
}

test prop_zero_burn_rejected(
  fee via fuzz.int_between(100, 200),
) {
  !burn_returns_collateral(0, 0, fee)
}

test prop_under_return_rejected(
  vals via fuzz.both(fuzz.int_between(2, 1000), fuzz.int_between(101, 200)),
) {
  let (burn, fee) = vals
  let required = burn * fee / 100
  !burn_returns_collateral(burn, required - 1, fee)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// burn_amount = 0 always makes burn_returns_collateral return False
test prop_fail_zero_burn(
  vals via fuzz.both(fuzz.int_between(0, 10000), fuzz.int_between(100, 200)),
) fail {
  let (collateral, fee) = vals
  expect burn_returns_collateral(0, collateral, fee)
}

/// Negative burn_amount also always returns False
test prop_fail_negative_burn(
  vals via fuzz.both(fuzz.int_between(-10000, -1), fuzz.int_between(100, 200)),
) fail {
  let (burn, fee) = vals
  expect burn_returns_collateral(burn, 0, fee)
}

/// Collateral strictly below required: burn * fee / 100 - 1
/// Use burn >= 2 and fee >= 101 so required >= 2 and (required - 1) >= 1
test prop_fail_undercollateralized_burn(
  vals via fuzz.both(fuzz.int_between(2, 500), fuzz.int_between(101, 200)),
) fail {
  let (burn, fee) = vals
  let required = burn * fee / 100
  expect burn_returns_collateral(burn, required - 1, fee)
}

/// over_return_allowed inherits the same zero-burn rejection
test prop_fail_over_return_zero_burn(
  vals via fuzz.both(fuzz.int_between(0, 10000), fuzz.int_between(100, 200)),
) fail {
  let (collateral, fee) = vals
  expect over_return_allowed(0, collateral, fee)
}