
use aiken/fuzz
use cardano/transaction.{OutputReference, Transaction}
pub type RepayDatum {
  owner:               ByteArray,
  collateral_lovelace: Int,
  debt_lovelace:       Int,
  min_ratio:           Int,
}

fn is_overcollateralized(collateral: Int, debt: Int, ratio: Int) -> Bool {
  collateral * 100 >= debt * ratio
}

/// After repaying repay_amt, remaining debt must still be valid and healthy
fn after_repay_healthy(
  collateral: Int,
  debt:       Int,
  repay_amt:  Int,
  ratio:      Int,
) -> Bool {
  let new_debt = debt - repay_amt
  new_debt > 0 && is_overcollateralized(collateral, new_debt, ratio)
}

/// Redeemer is the repayment amount
validator cdp_partial_repay {
  spend(
    datum: Option<RepayDatum>,
    redeemer: Int,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    redeemer > 0 && redeemer < d.debt_lovelace && after_repay_healthy(
      d.collateral_lovelace,
      d.debt_lovelace,
      redeemer,
      d.min_ratio,
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_repay_small_stays_healthy(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(1, 50)),
) {
  let (debt, repay) = vals
  let collateral = debt * 200
  after_repay_healthy(collateral, debt * 100, repay, 150)
}

test prop_repay_full_fails(debt via fuzz.int_at_least(1)) {
  !after_repay_healthy(debt * 200, debt, debt, 150)
}

test prop_repay_overcollateralized_threshold(debt via fuzz.int_at_least(1)) {
  is_overcollateralized(debt * 150, debt * 100, 150)
}

test prop_repay_zero_debt_unhealthy(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (collateral, ratio) = vals
  !after_repay_healthy(collateral, 5, 5, ratio)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// Collateral is 0, so collateral*100 = 0 < debt*ratio for any positive debt & ratio.
test prop_zero_collateral_never_overcollateralized(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (debt, ratio) = vals
  expect is_overcollateralized(0, debt, ratio)
}

// Repaying the full debt leaves new_debt = 0, which fails new_debt > 0.
test prop_full_repay_always_unhealthy(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (debt, collateral) = vals
  // repay_amt == debt  =>  new_debt = 0  =>  after_repay_healthy returns False
  expect after_repay_healthy(collateral, debt, debt, 150)
}

// Collateral is far too low: collateral=1, debt>=2, ratio>=200
// collateral*100 = 100  <  debt*ratio >= 2*200 = 400
test prop_undercollateralized_after_repay(
  vals via fuzz.both(fuzz.int_between(2, 1000), fuzz.int_between(200, 500)),
) fail {
  let (debt, ratio) = vals
  // repay 1 so new_debt = debt-1 >= 1; collateral=1 is far too small
  expect after_repay_healthy(1, debt, 1, ratio)
}

// Repaying more than the debt makes new_debt negative (<= 0), always unhealthy.
test prop_overrepay_always_unhealthy(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) fail {
  let (debt, extra) = vals
  // repay_amt = debt + extra  =>  new_debt = -extra <= 0
  expect after_repay_healthy(debt * 200, debt, debt + extra, 150)
}