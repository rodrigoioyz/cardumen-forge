use aiken/collection/list
use aiken/fuzz
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}

pub type CdpDatum {
  owner:             ByteArray,
  collateral:        Int,
  debt:              Int,
  liquidation_ratio: Int,
  min_collateral:    Int,
}

pub type CdpRedeemer {
  Repay
  Liquidate
}

fn is_undercollateralized(collateral: Int, debt: Int, ratio: Int) -> Bool {
  debt > 0 && collateral * 100 < debt * ratio
}

/// Position must have at least min_collateral to be liquidatable (dust guard)
fn is_liquidatable(
  collateral:     Int,
  debt:           Int,
  ratio:          Int,
  min_collateral: Int,
) -> Bool {
  collateral >= min_collateral && is_undercollateralized(collateral, debt, ratio)
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

validator cdp_dust_guard {
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
        is_liquidatable(
          d.collateral,
          d.debt,
          d.liquidation_ratio,
          d.min_collateral,
        )
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_dust_guard_undercollateralized_above_min(debt via fuzz.int_at_least(1)) {
  let collateral = debt * 119
  is_liquidatable(collateral, debt * 100, 120, 1)
}

test prop_dust_guard_below_min_not_liquidatable(debt via fuzz.int_at_least(1)) {
  let collateral = debt * 119
  !is_liquidatable(collateral, debt * 100, 120, collateral + 1)
}

test prop_dust_guard_overcollateralized_not_liquidatable(debt via fuzz.int_at_least(1)) {
  !is_liquidatable(debt * 150, debt * 100, 120, 1)
}

test prop_undercollateralized_inverse(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (collateral, debt) = vals
  let ratio = 150
  !(is_undercollateralized(collateral, debt, ratio) && collateral * 100 >= debt * ratio)
}
