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
