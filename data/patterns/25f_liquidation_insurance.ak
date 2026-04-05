
/// Insurance fund covers bad debt when collateral is insufficient
use aiken/fuzz
use cardano/transaction.{Transaction}
fn bad_debt(collateral: Int, debt: Int) -> Int {
  if debt > collateral { debt - collateral } else { 0 }
}

/// Insurance fund must cover bad debt
fn insurance_covers(
  collateral: Int,
  debt: Int,
  insurance_fund: Int,
) -> Bool {
  insurance_fund >= bad_debt(collateral, debt)
}

/// After insurance payout, remaining fund
fn remaining_fund(
  collateral: Int,
  debt: Int,
  insurance_fund: Int,
) -> Int {
  insurance_fund - bad_debt(collateral, debt)
}

pub type LiquidationDatum {
  collateral: Int,
  debt: Int,
  insurance_fund: Int,
}

pub type LiquidationRedeemer {
  Liquidate
  Replenish { amount: Int }
}

validator liquidation_insurance {
  spend(
    datum: Option<LiquidationDatum>,
    redeemer: LiquidationRedeemer,
    _output_ref: Data,
    _self: Transaction,
  ) {
    expect Some(d) = datum
    when redeemer is {
      Liquidate -> {
        let covered = insurance_covers(d.collateral, d.debt, d.insurance_fund)
        let remaining = remaining_fund(d.collateral, d.debt, d.insurance_fund)
        covered && remaining >= 0
      }
      Replenish { amount } -> {
        let new_fund = d.insurance_fund + amount
        insurance_covers(d.collateral, d.debt, new_fund)
      }
    }
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_no_bad_debt_when_overcollateralised(
  vals via fuzz.both(fuzz.int_between(101, 1000), fuzz.int_between(1, 100)),
) {
  let (collateral, debt) = vals
  bad_debt(collateral, debt) == 0
}

test prop_bad_debt_equals_shortfall(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 200)),
) {
  let (collateral, debt) = vals
  bad_debt(collateral, debt) == debt - collateral
}

test prop_sufficient_insurance_covers(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 200)),
) {
  let (collateral, debt) = vals
  let bd = bad_debt(collateral, debt)
  insurance_covers(collateral, debt, bd)
}

test prop_remaining_fund_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 200)),
) {
  let (collateral, debt) = vals
  let bd = bad_debt(collateral, debt)
  remaining_fund(collateral, debt, bd) >= 0
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// insurance_covers returns False when fund is strictly less than bad debt.
/// Here collateral=1, debt in [10,200], so bad_debt = debt-1 >= 9.
/// We pass insurance_fund = bad_debt - 1, which is always one short.
test prop_insufficient_insurance_rejected(
  debt via fuzz.int_between(10, 200),
) fail {
  let collateral = 1
  let bd = bad_debt(collateral, debt)
  // fund is one less than required — insurance_covers must return False
  expect insurance_covers(collateral, debt, bd - 1)
}

/// insurance_covers returns False when fund is zero but bad debt is positive.
/// collateral < debt guaranteed by ranges, so bad_debt > 0, fund=0 < bad_debt.
test prop_zero_fund_cannot_cover_bad_debt(
  vals via fuzz.both(fuzz.int_between(1, 50), fuzz.int_between(51, 200)),
) fail {
  let (collateral, debt) = vals
  // zero insurance fund cannot cover a positive bad debt
  expect insurance_covers(collateral, debt, 0)
}

/// insurance_covers returns False when the fund is negative.
/// collateral=0, debt in [1,100], bad_debt = debt >= 1; fund = -1 < bad_debt.
test prop_negative_fund_rejected(
  debt via fuzz.int_between(1, 100),
) fail {
  expect insurance_covers(0, debt, -1)
}

/// insurance_covers returns False when fund covers only half the bad debt.
/// collateral=0, debt in [2,100], bad_debt = debt; fund = debt/2 < debt for debt>=2.
test prop_partial_fund_rejected(
  debt via fuzz.int_between(2, 100),
) fail {
  let collateral = 0
  let bd = bad_debt(collateral, debt)
  // fund is exactly half (rounded down) — always strictly less than bd for debt>=2
  expect insurance_covers(collateral, debt, bd / 2)
}