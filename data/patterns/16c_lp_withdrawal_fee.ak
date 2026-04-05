
/// Tokens returned on withdrawal after applying a protocol fee (in bps)
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction, InlineDatum, Input}
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

pub type LpDatum {
  total_lp: Int,
  reserve: Int,
  fee_bps: Int,
}

pub type LpRedeemer {
  lp_burned: Int,
  min_net: Int,
}

validator lp_withdrawal_fee(policy_id: PolicyId) {
  spend(datum: Option<LpDatum>, redeemer: LpRedeemer, _input: Input, self: Transaction) {
    expect Some(LpDatum { total_lp, reserve, fee_bps }) = datum
    let LpRedeemer { lp_burned, min_net } = redeemer
    let gross = lp_burned * reserve / total_lp
    expect fee_in_range(gross, fee_bps)
    let net = withdrawal_net(lp_burned, total_lp, reserve, fee_bps)
    expect net_less_than_gross(lp_burned, total_lp, reserve, fee_bps) || fee_bps == 0
    expect lp_burned > 0
    expect lp_burned <= total_lp
    net >= min_net
  }

  else(_) {
    fail
  }
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

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// fee_in_range must reject fee_bps >= 10000 (e.g. 100% or more)
test prop_fee_bps_at_or_above_max_rejected(
  fee_bps via fuzz.int_between(10000, 50000),
) fail {
  expect fee_in_range(1000, fee_bps)
}

/// fee_in_range must reject negative fee_bps
test prop_negative_fee_bps_rejected(
  fee_bps via fuzz.int_between(-10000, -1),
) fail {
  expect fee_in_range(1000, fee_bps)
}

/// fee_in_range must reject gross <= 0 (zero gross means nothing to withdraw)
test prop_zero_gross_rejected(
  fee_bps via fuzz.int_between(0, 9999),
) fail {
  expect fee_in_range(0, fee_bps)
}

/// net_less_than_gross must return False when fee_bps == 0 but net != gross
/// Force this by making gross truncate to 0 via integer division:
/// lp_burned=1, total_lp=10000, reserve=1 => gross=0, net=0
/// With fee_bps == 0 the branch checks net == gross (0 == 0) — that's True.
/// Instead use fee_bps > 0 with a (lp_burned, total_lp, reserve) combo where
/// gross rounds to 0, so net == gross (both 0), making net < gross False.
test prop_zero_gross_net_not_less_than_gross_rejected(
  fee_bps via fuzz.int_between(1, 9999),
) fail {
  // lp_burned=1, total_lp=100000, reserve=1 => gross = 1*1/100000 = 0
  // net = 0 - 0 = 0; fee_bps > 0 branch: net < gross => 0 < 0 => False
  expect net_less_than_gross(1, 100000, 1, fee_bps)
}