
use aiken/fuzz
use cardano/transaction.{OutputReference, Transaction}
pub type CdpDatum {
  owner:               ByteArray,
  collateral_lovelace: Int,
  debt_lovelace:       Int,
  interest_bps:        Int,
  debt_ceiling:        Int,
}

fn is_overcollateralized(collateral: Int, debt: Int, ratio: Int) -> Bool {
  collateral * 100 >= debt * ratio
}

/// Debt after interest accrual: principal + principal * bps / 10000
fn with_interest(debt: Int, interest_bps: Int) -> Int {
  debt + debt * interest_bps / 10000
}

/// Total debt with interest must not exceed the ceiling
fn within_ceiling(debt: Int, interest_bps: Int, ceiling: Int) -> Bool {
  with_interest(debt, interest_bps) <= ceiling
}

validator cdp_interest_accrual {
  spend(
    datum: Option<CdpDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let total_debt = with_interest(d.debt_lovelace, d.interest_bps)
    total_debt > 0 && within_ceiling(
      d.debt_lovelace,
      d.interest_bps,
      d.debt_ceiling,
    ) && is_overcollateralized(d.collateral_lovelace, total_debt, 150)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_interest_zero_bps(debt via fuzz.int_at_least(1)) {
  with_interest(debt, 0) == debt
}

test prop_interest_grows_debt(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (debt, bps) = vals
  with_interest(debt, bps) >= debt
}

test prop_within_ceiling_exact(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 1000)),
) {
  let (debt, bps) = vals
  let total = with_interest(debt, bps)
  within_ceiling(debt, bps, total)
}

test prop_above_ceiling_fails(
  vals via fuzz.both(fuzz.int_at_least(100), fuzz.int_between(100, 500)),
) {
  let (debt, bps) = vals
  let total = with_interest(debt, bps)
  !within_ceiling(debt, bps, total - 1)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// collateral=0 is never overcollateralized against any positive debt
test prop_zero_collateral_undercollateralized(
  debt via fuzz.int_at_least(1),
) fail {
  expect is_overcollateralized(0, debt, 150)
}

/// collateral * 100 < debt * ratio when collateral is tiny and debt is large
/// collateral=1, ratio=150 → need debt*150 <= 100, impossible for debt >= 1
test prop_insufficient_collateral_rejected(
  debt via fuzz.int_at_least(1),
) fail {
  expect is_overcollateralized(1, debt, 150)
}

/// ceiling of 0 means no positive-interest debt can ever be within ceiling
/// with_interest(debt, bps) >= debt >= 1 > 0 for debt >= 1, bps >= 0
test prop_zero_ceiling_always_exceeded(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 10000)),
) fail {
  let (debt, bps) = vals
  expect within_ceiling(debt, bps, 0)
}

/// Ceiling set to one less than the bare principal always fails when bps > 0
/// with_interest(debt, bps) > debt for bps >= 10000/debt (guaranteed here by large bps)
test prop_ceiling_below_accrued_debt_rejected(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(10000, 50000)),
) fail {
  let (debt, bps) = vals
  // with_interest adds at least debt*1 (bps=10000 → +100%), so total >= 2*debt
  // ceiling = debt means total > ceiling
  expect within_ceiling(debt, bps, debt)
}