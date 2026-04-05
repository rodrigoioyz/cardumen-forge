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
