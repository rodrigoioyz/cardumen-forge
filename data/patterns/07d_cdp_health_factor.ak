
use aiken/fuzz
use cardano/transaction.{OutputReference, Transaction}
pub type CdpDatum {
  owner:               ByteArray,
  collateral_lovelace: Int,
  debt_lovelace:       Int,
  ratio:               Int,
}

/// Health factor = (collateral * 100) / (debt * ratio); healthy when >= 100
/// Equivalent check without division: collateral * 100 >= debt * ratio * 100 / 100
/// Simplified: collateral >= debt * ratio / 100
fn health_factor_ok(collateral: Int, debt: Int, ratio: Int) -> Bool {
  collateral * 100 >= debt * ratio
}

/// Margin above minimum: how much extra collateral beyond the threshold
fn collateral_surplus(collateral: Int, debt: Int, ratio: Int) -> Int {
  collateral * 100 - debt * ratio
}

validator cdp_health_factor {
  spend(
    datum: Option<CdpDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    d.debt_lovelace > 0 && health_factor_ok(
      d.collateral_lovelace,
      d.debt_lovelace,
      d.ratio,
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_health_factor_at_threshold(debt via fuzz.int_at_least(1)) {
  health_factor_ok(debt * 150, debt * 100, 150)
}

test prop_health_factor_surplus_nonneg(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 500)),
) {
  let (debt, extra) = vals
  collateral_surplus(debt * 150 + extra, debt * 100, 150) >= 0
}

test prop_health_factor_below_fails(debt via fuzz.int_at_least(1)) {
  !health_factor_ok(debt * 100, debt * 100, 150)
}

test prop_surplus_grows_with_collateral(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (debt, extra) = vals
  let base = collateral_surplus(debt * 150, debt * 100, 150)
  let higher = collateral_surplus(debt * 150 + extra, debt * 100, 150)
  higher >= base
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

// collateral * 100 < debt * ratio when collateral = debt * ratio / 100 - 1
// For ratio=150, debt>=1: collateral = debt - 1 (when debt=1, collateral=0)
// debt*150 > (debt-1)*100 always for debt>=1, so health_factor_ok is always False
test prop_undercollateralized_rejected(
  debt via fuzz.int_at_least(1),
) fail {
  // collateral * 100 = (debt - 1) * 100, but required = debt * 150
  // (debt-1)*100 < debt*150 for all debt >= 1
  expect health_factor_ok(debt - 1, debt, 150)
}

// Zero collateral is always unhealthy for any positive debt and ratio
test prop_zero_collateral_rejected(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (debt, ratio) = vals
  // 0 * 100 = 0 < debt * ratio for debt >= 1, ratio >= 1
  expect health_factor_ok(0, debt, ratio)
}

// Extremely high ratio makes healthy collateral unhealthy:
// collateral = debt (1:1), ratio = 200 => collateral*100 = debt*100 < debt*200
test prop_high_ratio_rejected(
  debt via fuzz.int_at_least(1),
) fail {
  // debt * 100 < debt * 200 always for debt >= 1
  expect health_factor_ok(debt, debt, 200)
}

// Collateral is exactly one lovelace below the threshold:
// threshold = debt * ratio; need collateral * 100 >= debt * ratio
// If collateral * 100 = debt * ratio - 1, it fails.
// Use collateral = (debt * 150 - 1) / 100 rounded down, which is debt - 1 for small debt.
// Simpler: fix ratio=100, collateral = debt - 1 => (debt-1)*100 < debt*100 always for debt>=1
test prop_just_below_threshold_rejected(
  debt via fuzz.int_at_least(1),
) fail {
  // ratio=100: need collateral*100 >= debt*100, i.e. collateral >= debt
  // collateral = debt - 1 is strictly below for all debt >= 1
  expect health_factor_ok(debt - 1, debt, 100)
}