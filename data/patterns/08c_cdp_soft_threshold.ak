
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}
pub type CdpDatum {
  owner:        ByteArray,
  collateral:   Int,
  debt:         Int,
  warn_ratio:   Int,
  liq_ratio:    Int,
}

pub type CdpRedeemer {
  Repay
  Liquidate
}

fn is_undercollateralized(collateral: Int, debt: Int, ratio: Int) -> Bool {
  debt > 0 && collateral * 100 < debt * ratio
}

/// Position is in warning zone: below warn_ratio but above liq_ratio
fn in_warning_zone(
  collateral: Int,
  debt:       Int,
  warn_ratio: Int,
  liq_ratio:  Int,
) -> Bool {
  is_undercollateralized(collateral, debt, warn_ratio) && !is_undercollateralized(
    collateral,
    debt,
    liq_ratio,
  )
}

fn liquidator_pays_debt(
  outputs:       List<Output>,
  owner_addr:    Output,
  debt_lovelace: Int,
) -> Bool {
  let paid =
    list.foldl(
      outputs,
      0,
      fn(o, acc) {
        if o.address == owner_addr.address {
          acc + lovelace_of(o.value)
        } else {
          acc
        }
      },
    )
  paid >= debt_lovelace
}

validator cdp_soft_threshold {
  spend(
    datum: Option<CdpDatum>,
    redeemer: CdpRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Repay -> list.has(self.extra_signatories, d.owner)
      Liquidate ->
        is_undercollateralized(d.collateral, d.debt, d.liq_ratio)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_warning_zone_between_ratios(debt via fuzz.int_at_least(1)) {
  // collateral at 115% — below warn(120) but above liq(110)
  in_warning_zone(debt * 115, debt * 100, 120, 110)
}

test prop_below_liq_ratio_not_warning(debt via fuzz.int_at_least(1)) {
  // collateral at 105% — below both ratios, so not in warning zone
  !in_warning_zone(debt * 105, debt * 100, 120, 110)
}

test prop_above_warn_ratio_not_warning(debt via fuzz.int_at_least(1)) {
  // collateral at 130% — above warn ratio, not in warning zone
  !in_warning_zone(debt * 130, debt * 100, 120, 110)
}

test prop_undercollateralized_no_debt(
  vals via fuzz.both(fuzz.int_at_least(0), fuzz.int_at_least(1)),
) {
  let (collateral, ratio) = vals
  !is_undercollateralized(collateral, 0, ratio)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// is_undercollateralized must return False when debt is 0 (regardless of collateral/ratio)
test prop_not_undercollateralized_zero_debt(
  vals via fuzz.both(fuzz.int_at_least(0), fuzz.int_at_least(1)),
) fail {
  let (collateral, ratio) = vals
  expect is_undercollateralized(collateral, 0, ratio)
}

/// is_undercollateralized must return False when collateral * 100 >= debt * ratio
/// Here collateral = debt * ratio (so collateral*100 >= debt*ratio for ratio>=1, debt>=1)
test prop_not_undercollateralized_well_collateralized(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(1, 100)),
) fail {
  let (debt, ratio) = vals
  // collateral*100 = debt*ratio*100 >= debt*ratio → not undercollateralized
  expect is_undercollateralized(debt * ratio, debt, ratio)
}

/// in_warning_zone must return False when position is below liq_ratio
/// (below both ratios means is_undercollateralized holds for liq_ratio too)
test prop_not_in_warning_zone_below_liq(
  debt via fuzz.int_between(1, 1000),
) fail {
  // collateral at 105% — below liq_ratio(110) AND warn_ratio(120)
  // so !is_undercollateralized(coll,debt,liq_ratio) is False → in_warning_zone is False
  expect in_warning_zone(debt * 105, debt * 100, 120, 110)
}

/// in_warning_zone must return False when well above warn_ratio
test prop_not_in_warning_zone_above_warn(
  debt via fuzz.int_between(1, 1000),
) fail {
  // collateral at 200% — above warn_ratio(120)
  // is_undercollateralized(coll,debt,warn_ratio) is False → in_warning_zone is False
  expect in_warning_zone(debt * 200, debt * 100, 120, 110)
}