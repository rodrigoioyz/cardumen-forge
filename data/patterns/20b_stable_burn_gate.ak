use aiken/fuzz

/// Burning stablecoin is only valid when collateral is being proportionally returned
/// collateral_returned >= burn_amount * stability_fee / 100
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
