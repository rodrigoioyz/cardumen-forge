use aiken/fuzz

/// Liquidation penalty: liquidator pays debt and receives collateral + bonus
fn liquidation_bonus(collateral: Int, bonus_bps: Int) -> Int {
  collateral * bonus_bps / 10000
}

/// Liquidator receives: collateral + bonus
fn liquidator_receives(collateral: Int, bonus_bps: Int) -> Int {
  collateral + liquidation_bonus(collateral, bonus_bps)
}

/// Bonus is non-negative and bounded
fn bonus_in_range(collateral: Int, bonus_bps: Int) -> Bool {
  bonus_bps >= 0 && bonus_bps < 10000
    && liquidation_bonus(collateral, bonus_bps) >= 0
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_zero_bonus_receives_exact_collateral(
  collateral via fuzz.int_between(1, 100000),
) {
  liquidator_receives(collateral, 0) == collateral
}

test prop_bonus_increases_proceeds(
  vals via fuzz.both(fuzz.int_between(10000, 100000), fuzz.int_between(1, 500)),
) {
  let (collateral, bonus_bps) = vals
  liquidator_receives(collateral, bonus_bps) > collateral
}

test prop_bonus_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 100000), fuzz.int_between(0, 500)),
) {
  let (collateral, bonus_bps) = vals
  liquidation_bonus(collateral, bonus_bps) >= 0
}

test prop_bonus_in_range_valid(
  collateral via fuzz.int_between(1, 100000),
) {
  bonus_in_range(collateral, 500)
}
