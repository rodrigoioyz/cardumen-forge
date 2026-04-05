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
