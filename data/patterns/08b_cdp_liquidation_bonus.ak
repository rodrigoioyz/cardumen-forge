use aiken/collection/list
use aiken/fuzz
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}

pub type CdpDatum {
  owner:             ByteArray,
  collateral:        Int,
  debt:              Int,
  liquidation_ratio: Int,
  bonus_percent:     Int,
}

pub type CdpRedeemer {
  Repay
  Liquidate
}

fn is_undercollateralized(collateral: Int, debt: Int, ratio: Int) -> Bool {
  debt > 0 && collateral * 100 < debt * ratio
}

/// Liquidator pays discounted debt: debt * (100 - bonus_percent) / 100
fn discounted_debt(debt: Int, bonus_percent: Int) -> Int {
  debt * (100 - bonus_percent) / 100
}

fn liquidator_pays_discounted(
  outputs:       List<Output>,
  owner_addr:    Output,
  debt:          Int,
  bonus_percent: Int,
) -> Bool {
  let required = discounted_debt(debt, bonus_percent)
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
  paid >= required
}

validator cdp_liquidation_bonus {
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
        is_undercollateralized(d.collateral, d.debt, d.liquidation_ratio)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_discounted_debt_zero_bonus(debt via fuzz.int_at_least(1)) {
  discounted_debt(debt, 0) == debt
}

test prop_discounted_debt_less_than_full(
  vals via fuzz.both(fuzz.int_at_least(100), fuzz.int_between(1, 50)),
) {
  let (debt, bonus) = vals
  discounted_debt(debt, bonus) < debt
}

test prop_discounted_debt_non_negative(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 99)),
) {
  let (debt, bonus) = vals
  discounted_debt(debt, bonus) >= 0
}

test prop_undercollateralized_below_ratio(debt via fuzz.int_at_least(1)) {
  is_undercollateralized(debt * 119, debt * 100, 120)
}
