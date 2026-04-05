
use aiken/fuzz
use cardano/transaction.{OutputReference, Transaction}
pub type CdpDatum {
  owner:               ByteArray,
  collateral_lovelace: Int,
  debt_lovelace:       Int,
  min_collateral:      Int,
}

/// Collateral must meet both the ratio and an absolute minimum floor
fn is_overcollateralized(collateral: Int, debt: Int, ratio: Int) -> Bool {
  collateral * 100 >= debt * ratio
}

fn meets_min_collateral(collateral: Int, min_abs: Int) -> Bool {
  collateral >= min_abs
}

validator cdp_min_collateral {
  spend(
    datum: Option<CdpDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    d.debt_lovelace > 0 && meets_min_collateral(
      d.collateral_lovelace,
      d.min_collateral,
    ) && is_overcollateralized(d.collateral_lovelace, d.debt_lovelace, 150)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_min_collateral_exact(min via fuzz.int_at_least(0)) {
  meets_min_collateral(min, min)
}

test prop_min_collateral_above(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 1000)),
) {
  let (min, extra) = vals
  meets_min_collateral(min + extra, min)
}

test prop_min_collateral_below_fails(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (min, gap) = vals
  !meets_min_collateral(min - 1, min + gap - 1)
}

test prop_overcollateralized_at_ratio(debt via fuzz.int_at_least(1)) {
  is_overcollateralized(debt * 150, debt * 100, 150)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

// collateral is strictly below the minimum floor — meets_min_collateral must return False
test prop_below_min_collateral_rejected(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (min, gap) = vals
  // collateral = min - gap, which is always strictly less than min
  expect meets_min_collateral(min - gap, min)
}

// collateral * 100 < debt * 150 — undercollateralized, must return False
// collateral = debt - 1, so (debt-1)*100 = debt*100 - 100 < debt*150 for debt >= 1
test prop_undercollateralized_rejected(
  debt via fuzz.int_at_least(1),
) fail {
  expect is_overcollateralized(debt - 1, debt, 150)
}

// zero collateral against any positive debt at ratio 150 must always be rejected
test prop_zero_collateral_rejected(
  debt via fuzz.int_at_least(1),
) fail {
  expect is_overcollateralized(0, debt, 150)
}

// collateral exactly at ratio 149 (one below the required 150) must be rejected
// collateral = debt * 149, debt >= 1 → collateral*100 = debt*14900 < debt*150*100
test prop_one_below_ratio_rejected(
  debt via fuzz.int_at_least(1),
) fail {
  expect is_overcollateralized(debt * 149, debt * 100, 150)
}