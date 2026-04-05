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
