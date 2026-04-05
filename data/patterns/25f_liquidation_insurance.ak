use aiken/fuzz

/// Insurance fund covers bad debt when collateral is insufficient
fn bad_debt(collateral: Int, debt: Int) -> Int {
  if debt > collateral { debt - collateral } else { 0 }
}

/// Insurance fund must cover bad debt
fn insurance_covers(
  collateral:    Int,
  debt:          Int,
  insurance_fund: Int,
) -> Bool {
  insurance_fund >= bad_debt(collateral, debt)
}

/// After insurance payout, remaining fund
fn remaining_fund(
  collateral:    Int,
  debt:          Int,
  insurance_fund: Int,
) -> Int {
  insurance_fund - bad_debt(collateral, debt)
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
