
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}
  use cardano/assets
  use cardano/address.{from_verification_key}
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A well-collateralized position (collateral*100 >= debt*ratio) must NOT
/// be flagged as undercollateralized.
test prop_overcollateralized_not_undercollateralized(
  debt via fuzz.int_between(1, 1000),
) fail {
  // collateral = debt * 200, ratio = 150  →  debt*200*100 >= debt*150  always
  expect is_undercollateralized(debt * 200, debt, 150)
}

/// Zero debt can never make a position undercollateralized, regardless of
/// collateral and ratio.
test prop_zero_debt_never_undercollateralized(
  vals via fuzz.both(fuzz.int_at_least(0), fuzz.int_at_least(1)),
) fail {
  let (collateral, ratio) = vals
  expect is_undercollateralized(collateral, 0, ratio)
}

/// Negative debt (erroneous datum) must also be rejected by the guard.
test prop_negative_debt_not_undercollateralized(
  debt via fuzz.int_between(-1000, -1),
) fail {
  // debt <= 0 so the `debt > 0` guard is False
  expect is_undercollateralized(0, debt, 120)
}

/// When no outputs are provided the liquidator has paid nothing, so
/// liquidator_pays_debt must return False for any positive debt requirement.
test prop_no_outputs_liquidator_pays_nothing(
  debt via fuzz.int_at_least(1),
) fail {
  let dummy_addr = from_verification_key(#"00")
  let dummy_output =
    Output {
      address: dummy_addr,
      value: assets.zero,
      datum: transaction.NoDatum,
      reference_script: None,
    }
  expect liquidator_pays_debt([], dummy_output, debt)
}