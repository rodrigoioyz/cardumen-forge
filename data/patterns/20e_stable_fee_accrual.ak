use aiken/fuzz

/// Stability fee accrues on outstanding debt (annual rate in bps, per-block approximation)
fn accrued_fee(debt: Int, rate_bps: Int, blocks: Int) -> Int {
  debt * rate_bps * blocks / 10000
}

/// Total obligation after fee accrual
fn total_owed(debt: Int, rate_bps: Int, blocks: Int) -> Int {
  debt + accrued_fee(debt, rate_bps, blocks)
}

/// Fee never exceeds the principal for reasonable rates and block counts
fn fee_bounded(debt: Int, rate_bps: Int, blocks: Int, max_multiplier: Int) -> Bool {
  total_owed(debt, rate_bps, blocks) <= debt * max_multiplier
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_zero_rate_no_fee(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(1, 1000)),
) {
  let (debt, blocks) = vals
  accrued_fee(debt, 0, blocks) == 0
}

test prop_fee_increases_with_blocks(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 100)),
) {
  let (debt, rate) = vals
  accrued_fee(debt, rate, 100) >= accrued_fee(debt, rate, 50)
}

test prop_total_owed_exceeds_principal(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 100)),
) {
  let (debt, rate) = vals
  total_owed(debt, rate, 100) >= debt
}

test prop_fee_bounded_by_multiplier(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 50)),
) {
  let (debt, rate_bps) = vals
  // Over 10 blocks at rate <= 50 bps, max fee = debt*50*10/10000 = 0.5%*debt << 2*debt
  fee_bounded(debt, rate_bps, 10, 2)
}
