use aiken/fuzz
use cardano/transaction.{OutputReference, Transaction}

pub type CdpDatum {
  owner:               ByteArray,
  collateral_lovelace: Int,
  debt_lovelace:       Int,
  max_debt:            Int,
}

fn is_overcollateralized(collateral: Int, debt: Int, ratio: Int) -> Bool {
  collateral * 100 >= debt * ratio
}

/// Debt must be positive and not exceed the cap
fn within_debt_cap(debt: Int, max_debt: Int) -> Bool {
  debt > 0 && debt <= max_debt
}

validator cdp_max_debt {
  spend(
    datum: Option<CdpDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    within_debt_cap(d.debt_lovelace, d.max_debt) && is_overcollateralized(
      d.collateral_lovelace,
      d.debt_lovelace,
      150,
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_within_cap_exact(cap via fuzz.int_at_least(1)) {
  within_debt_cap(cap, cap)
}

test prop_within_cap_below(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 1000)),
) {
  let (debt, slack) = vals
  within_debt_cap(debt, debt + slack)
}

test prop_above_cap_fails(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (cap, over) = vals
  !within_debt_cap(cap + over, cap)
}

test prop_zero_debt_fails(cap via fuzz.int_at_least(1)) {
  !within_debt_cap(0, cap)
}
