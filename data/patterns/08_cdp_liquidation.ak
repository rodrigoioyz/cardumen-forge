use aiken/collection/list
use aiken/fuzz
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}

pub type CdpDatum {
  owner:               ByteArray,
  collateral_lovelace: Int,
  debt_lovelace:       Int,
  liquidation_ratio:   Int,
}

pub type CdpRedeemer {
  Repay
  Liquidate
}

/// True when the position is undercollateralized (eligible for liquidation)
fn is_undercollateralized(
  collateral: Int,
  debt:       Int,
  ratio:      Int,
) -> Bool {
  debt > 0 && collateral * 100 < debt * ratio
}

/// Liquidator must send at least debt_lovelace to the owner
fn liquidator_pays_debt(
  outputs:        List<Output>,
  owner_addr:     Output,
  debt_lovelace:  Int,
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

validator cdp_liquidation {
  spend(
    datum: Option<CdpDatum>,
    redeemer: CdpRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Repay ->
        // Owner repays: they must sign
        list.has(self.extra_signatories, d.owner)
      Liquidate ->
        // Anyone can liquidate when undercollateralized
        is_undercollateralized(
          d.collateral_lovelace,
          d.debt_lovelace,
          d.liquidation_ratio,
        )
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_undercollateralized_below_ratio(debt via fuzz.int_at_least(1)) {
  // collateral = debt * 119/100 < debt * 120/100 → undercollateralized at ratio 120
  is_undercollateralized(debt * 119, debt * 100, 120)
}

test prop_not_undercollateralized_above_ratio(debt via fuzz.int_at_least(1)) {
  !is_undercollateralized(debt * 150, debt * 100, 120)
}

test prop_undercollateralized_always_requires_debt(
  vals via fuzz.both(fuzz.int_at_least(0), fuzz.int_at_least(1)),
) {
  let (collateral, ratio) = vals
  !is_undercollateralized(collateral, 0, ratio)
}

test prop_undercollateralized_inverse_of_overcollateralized(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (collateral, debt) = vals
  let ratio = 150
  let under = is_undercollateralized(collateral, debt, ratio)
  let over  = collateral * 100 >= debt * ratio
  // They cannot both be true simultaneously
  !(under && over)
}
