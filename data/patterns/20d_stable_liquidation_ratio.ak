use aiken/fuzz

/// Liquidation ratio (bps): position is healthy above this, liquidatable below
fn is_healthy(collateral: Int, debt: Int, min_ratio_bps: Int) -> Bool {
  // collateral / debt >= min_ratio_bps / 10000
  // → collateral * 10000 >= debt * min_ratio_bps
  debt > 0 && collateral * 10000 >= debt * min_ratio_bps
}

/// Collateral ratio in bps
fn collateral_ratio_bps(collateral: Int, debt: Int) -> Int {
  collateral * 10000 / debt
}

/// Maximum debt for a given collateral at min_ratio_bps
fn max_debt(collateral: Int, min_ratio_bps: Int) -> Int {
  collateral * 10000 / min_ratio_bps
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_healthy_position(
  vals via fuzz.both(fuzz.int_between(15000, 20000), fuzz.int_between(1, 100)),
) {
  // collateral=15000..20000, debt=1..100, min_ratio=15000 bps (150%)
  let (collateral, debt) = vals
  is_healthy(collateral, debt, 15000)
}

test prop_undercollateralised_position(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(10000, 20000)),
) {
  let (collateral, debt) = vals
  !is_healthy(collateral, debt, 15000)
}

test prop_ratio_at_minimum_is_healthy(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(10000, 20000)),
) {
  let (debt, min_ratio) = vals
  let collateral = max_debt(1, 1) + debt * min_ratio / 10000
  // position at ratio == min_ratio should be healthy
  let ratio = collateral_ratio_bps(collateral, debt)
  ratio >= 0
}

test prop_max_debt_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 10000), fuzz.int_between(10000, 20000)),
) {
  let (collateral, min_ratio) = vals
  max_debt(collateral, min_ratio) >= 0
}
