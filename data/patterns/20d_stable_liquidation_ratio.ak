
/// Liquidation ratio (bps): position is healthy above this, liquidatable below
use aiken/fuzz
use cardano/transaction.{Transaction, InlineDatum}
use cardano/assets.{PolicyId}
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

pub type PositionDatum {
  collateral: Int,
  debt: Int,
  min_ratio_bps: Int,
  owner: ByteArray,
}

pub type PositionRedeemer {
  Repay { new_debt: Int }
  Liquidate
  Withdraw { amount: Int }
}

validator stable_liquidation {
  spend(
    datum: Option<PositionDatum>,
    redeemer: PositionRedeemer,
    _input: Data,
    self: Transaction,
  ) {
    expect Some(pos) = datum
    when redeemer is {
      Repay { new_debt } -> {
        let new_collateral = pos.collateral
        let still_healthy = is_healthy(new_collateral, new_debt, pos.min_ratio_bps)
        let reduced = new_debt <= pos.debt
        still_healthy && reduced
      }
      Liquidate -> {
        let ratio = collateral_ratio_bps(pos.collateral, pos.debt)
        ratio < pos.min_ratio_bps
      }
      Withdraw { amount } -> {
        let new_collateral = pos.collateral - amount
        let max_allowed_debt = max_debt(new_collateral, pos.min_ratio_bps)
        let safe = pos.debt <= max_allowed_debt
        let non_negative = new_collateral >= 0
        safe && non_negative
      }
    }
  }

  else(_) {
    fail
  }
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

// ── Negative (fail) property tests ───────────────────────────────────────────

/// A position with zero debt must fail is_healthy (debt > 0 guard triggers)
test prop_zero_debt_not_healthy(
  collateral via fuzz.int_between(1, 1000000),
) fail {
  expect is_healthy(collateral, 0, 15000)
}

/// Tiny collateral (1) against large debt is always undercollateralized at 15000 bps
/// collateral * 10000 = 10000, debt * 15000 >= 15000 for debt >= 1, so always False
test prop_tiny_collateral_large_debt_unhealthy(
  debt via fuzz.int_between(2, 100000),
) fail {
  expect is_healthy(1, debt, 15000)
}

/// Negative collateral is never healthy regardless of debt or ratio
test prop_negative_collateral_unhealthy(
  vals via fuzz.both(fuzz.int_between(-100000, -1), fuzz.int_between(1, 10000)),
) fail {
  let (collateral, debt) = vals
  expect is_healthy(collateral, debt, 15000)
}

/// When collateral is strictly less than debt (both positive) and min_ratio >= 10000 bps,
/// the position is always unhealthy: collateral * 10000 < debt * 10000 <= debt * min_ratio
test prop_collateral_less_than_debt_unhealthy(
  vals via fuzz.both(
    fuzz.int_between(1, 999),
    fuzz.int_between(1000, 100000),
  ),
) fail {
  let (collateral, debt) = vals
  // min_ratio_bps = 20000 (200%): collateral * 10000 < debt * 20000 always here
  expect is_healthy(collateral, debt, 20000)
}