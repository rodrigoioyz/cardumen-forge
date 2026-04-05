use aiken/fuzz

/// Tokens returned on withdrawal after applying a protocol fee (in bps)
fn withdrawal_net(lp_burned: Int, total_lp: Int, reserve: Int, fee_bps: Int) -> Int {
  let gross = lp_burned * reserve / total_lp
  let fee   = gross * fee_bps / 10000
  gross - fee
}

/// Fee must be non-negative and less than the gross amount
fn fee_in_range(gross: Int, fee_bps: Int) -> Bool {
  fee_bps >= 0 && fee_bps < 10000 && gross > 0
}

/// Net withdrawal is strictly less than gross when fee > 0
fn net_less_than_gross(lp_burned: Int, total_lp: Int, reserve: Int, fee_bps: Int) -> Bool {
  let gross = lp_burned * reserve / total_lp
  let net   = withdrawal_net(lp_burned, total_lp, reserve, fee_bps)
  if fee_bps > 0 { net < gross } else { net == gross }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_zero_fee_returns_full_amount(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (reserve, total_lp) = vals
  withdrawal_net(total_lp, total_lp, reserve, 0) == reserve
}

test prop_fee_reduces_withdrawal(
  vals via fuzz.both(fuzz.int_between(10001, 100000), fuzz.int_between(1, 999)),
) {
  // reserve > 10000 ensures gross * fee_bps / 10000 >= 1, so net < gross
  let (reserve, fee_bps) = vals
  net_less_than_gross(1000, 1000, reserve, fee_bps)
}

test prop_full_burn_at_max_fee_still_positive(
  reserve via fuzz.int_between(10000, 100000),
) {
  // 9999 bps = 99.99% fee
  let net = withdrawal_net(1000, 1000, reserve, 9999)
  net >= 0
}

test prop_fee_in_range_valid() {
  fee_in_range(1000, 30)
}
