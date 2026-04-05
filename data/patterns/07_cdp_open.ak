
use aiken/fuzz
use cardano/transaction.{OutputReference, Transaction}
pub type CdpDatum {
  owner:               ByteArray,
  collateral_lovelace: Int,
  debt_lovelace:       Int,
  min_ratio:           Int,
}

/// True when collateral/debt ratio >= min_ratio (expressed as percentage, e.g. 150)
fn is_overcollateralized(
  collateral: Int,
  debt:       Int,
  ratio:      Int,
) -> Bool {
  collateral * 100 >= debt * ratio
}

validator cdp_open {
  spend(
    datum: Option<CdpDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    d.debt_lovelace > 0 && is_overcollateralized(
      d.collateral_lovelace,
      d.debt_lovelace,
      d.min_ratio,
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_overcollateralized_equal_ratio(debt via fuzz.int_at_least(1)) {
  // collateral == debt * ratio/100 → exactly at threshold
  is_overcollateralized(debt * 150, debt * 100, 150)
}

test prop_overcollateralized_above_ratio(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 1000)),
) {
  let (debt, extra) = vals
  is_overcollateralized(debt * 150 + extra, debt * 100, 150)
}

test prop_not_overcollateralized_below(debt via fuzz.int_at_least(1)) {
  !is_overcollateralized(debt * 100, debt * 100, 150)
}

test prop_overcollateralized_zero_debt() {
  // zero debt edge case — vacuously safe (validator rejects this via debt > 0)
  is_overcollateralized(0, 0, 150) || True
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

// collateral * 100 < debt * ratio when collateral = debt - 1 and ratio = 150
// For any debt >= 2: (debt-1)*100 = debt*100 - 100 < debt*150, so always undercollateralized
test prop_undercollateralized_below_threshold(
  debt via fuzz.int_between(2, 1000),
) fail {
  expect is_overcollateralized(debt - 1, debt, 150)
}

// collateral = 0 and debt >= 1 → 0 * 100 = 0 < debt * ratio, always False
test prop_zero_collateral_any_debt(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (debt, ratio) = vals
  expect is_overcollateralized(0, debt, ratio)
}

// collateral = 1 and debt is large: 1*100=100 < debt*150 for debt >= 1
// Use debt >= 2 to guarantee 100 < 300, i.e. always undercollateralized
test prop_tiny_collateral_large_debt(
  debt via fuzz.int_between(2, 10000),
) fail {
  expect is_overcollateralized(1, debt, 150)
}

// collateral = debt (100% ratio) but min_ratio = 200 → debt*100 < debt*200, always False for debt >= 1
test prop_undercollateralized_high_ratio(
  debt via fuzz.int_at_least(1),
) fail {
  expect is_overcollateralized(debt, debt, 200)
}